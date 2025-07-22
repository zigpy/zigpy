from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import enum
import itertools
import logging
import sys
import time
import typing
import warnings

from zigpy.exceptions import DeliveryError
from zigpy.ota.manager import update_firmware
from zigpy.zcl.clusters.general import Ota, PollControl

if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout  # pragma: no cover
else:
    from asyncio import timeout as asyncio_timeout  # pragma: no cover

from zigpy import zdo
from zigpy.const import (
    APS_REPLY_TIMEOUT,
    APS_REPLY_TIMEOUT_EXTENDED,
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_NODE_DESC,
)
import zigpy.datastructures
import zigpy.endpoint
import zigpy.exceptions
import zigpy.listeners
import zigpy.types as t
from zigpy.typing import AddressingMode
import zigpy.util
from zigpy.zcl import Cluster, ClusterType, foundation
import zigpy.zdo.types as zdo_t

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.ota.providers import OtaImageWithMetadata


LOGGER = logging.getLogger(__name__)

PACKET_DEBOUNCE_WINDOW = 10
MAX_DEVICE_CONCURRENCY = 1
FAST_POLL_TIMEOUT = 30

AFTER_OTA_ATTR_READ_DELAY = 10
OTA_RETRY_DECORATOR = zigpy.util.retryable_request(
    tries=4, delay=AFTER_OTA_ATTR_READ_DELAY
)


class Status(enum.IntEnum):
    """The status of a Device. Maintained for backwards compatibility."""

    # No initialization done
    NEW = 0
    # ZDO endpoint discovery done
    ZDO_INIT = 1
    # Endpoints initialized
    ENDPOINTS_INIT = 2


class Device(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """A device on the network"""

    manufacturer_id_override = None

    def __init__(self, application: ControllerApplication, ieee: t.EUI64, nwk: t.NWK):
        self._application: ControllerApplication = application
        self._ieee: t.EUI64 = ieee
        self.nwk: t.NWK = t.NWK(nwk)
        self.zdo: zdo.ZDO = zdo.ZDO(self)
        self.endpoints: dict[int, zdo.ZDO | zigpy.endpoint.Endpoint] = {0: self.zdo}
        self.lqi: int | None = None
        self.rssi: int | None = None
        self.ota_in_progress: bool = False
        self._last_seen: datetime | None = None
        self._initialize_task: asyncio.Task | None = None
        self._group_scan_task: asyncio.Task | None = None
        self._listeners = {}
        self._manufacturer: str | None = None
        self._model: str | None = None
        self.node_desc: zdo_t.NodeDescriptor | None = None
        self._pending: zigpy.util.Requests[t.uint8_t] = zigpy.util.Requests()
        self._relays: t.Relays | None = None
        self._skip_configuration: bool = False
        self._send_sequence: int = 0

        self._on_remove_callbacks: list[typing.Callable[[], None]] = []

        self._packet_debouncer = zigpy.datastructures.Debouncer()
        self._concurrent_requests_semaphore = (
            zigpy.datastructures.PriorityDynamicBoundedSemaphore(MAX_DEVICE_CONCURRENCY)
        )

        # Retained for backwards compatibility, will be removed in a future release
        self.status = Status.NEW

        self._on_remove_callbacks.append(
            self._application.register_callback_listener(
                src=self,
                filters=[PollControl.ClientCommandDefs.checkin.schema()],
                callback=self.poll_control_checkin_callback,
            )
        )

    def on_remove(self) -> None:
        """Call on remove callbacks."""
        for callback in self._on_remove_callbacks:
            callback()

        self._on_remove_callbacks.clear()

    @contextlib.asynccontextmanager
    async def _limit_concurrency(self, *, priority: int = 0):
        """Async context manager to limit device request concurrency."""

        start_time = time.monotonic()
        was_locked = self._concurrent_requests_semaphore.locked()

        if was_locked:
            LOGGER.debug(
                "Device concurrency (%s) reached, delaying device request (%s enqueued)",
                self._concurrent_requests_semaphore.max_value,
                self._concurrent_requests_semaphore.num_waiting,
            )

        async with self._concurrent_requests_semaphore(priority=priority):
            if was_locked:
                LOGGER.debug(
                    "Previously delayed device request is now running, delayed by %0.2fs",
                    time.monotonic() - start_time,
                )

            yield

    def get_sequence(self) -> t.uint8_t:
        self._send_sequence = (self._send_sequence + 1) % 256
        return self._send_sequence

    @property
    def name(self) -> str:
        return f"0x{self.nwk:04X}"

    def update_last_seen(self) -> None:
        """Update the `last_seen` attribute to the current time and emit an event."""

        warnings.warn(
            "Calling `update_last_seen` directly is deprecated", DeprecationWarning
        )

        self.last_seen = datetime.now(timezone.utc)

    @property
    def last_seen(self) -> float | None:
        return self._last_seen.timestamp() if self._last_seen is not None else None

    @last_seen.setter
    def last_seen(self, value: datetime | float):
        if isinstance(value, (int, float)):
            value = datetime.fromtimestamp(value, timezone.utc)

        self._last_seen = value
        self.listener_event("device_last_seen_updated", self._last_seen)

    @property
    def non_zdo_endpoints(self) -> list[zigpy.endpoint.Endpoint]:
        return [
            ep for epid, ep in self.endpoints.items() if not (isinstance(ep, zdo.ZDO))
        ]

    @property
    def has_non_zdo_endpoints(self) -> bool:
        return bool(self.non_zdo_endpoints)

    @property
    def all_endpoints_init(self) -> bool:
        return self.has_non_zdo_endpoints and all(
            ep.status != zigpy.endpoint.Status.NEW for ep in self.non_zdo_endpoints
        )

    @property
    def is_initialized(self) -> bool:
        return self.node_desc is not None and self.all_endpoints_init

    def schedule_group_membership_scan(self) -> asyncio.Task:
        """Rescan device group's membership."""
        if self._group_scan_task and not self._group_scan_task.done():
            self.debug("Cancelling old group rescan")
            self._group_scan_task.cancel()

        self._group_scan_task = asyncio.create_task(self.group_membership_scan())
        return self._group_scan_task

    async def group_membership_scan(self) -> None:
        """Sync up group membership."""
        for ep in self.non_zdo_endpoints:
            await ep.group_membership_scan()

    @property
    def initializing(self) -> bool:
        """Return True if device is being initialized."""
        return self._initialize_task is not None and not self._initialize_task.done()

    def cancel_initialization(self) -> None:
        """Cancel initialization call."""
        if self.initializing:
            self.debug("Canceling old initialize call")
            self._initialize_task.cancel()  # type:ignore[union-attr]

    def schedule_initialize(self) -> asyncio.Task | None:
        # Already-initialized devices don't need to be re-initialized
        if self.is_initialized:
            self.debug("Skipping initialization, device is fully initialized")
            self._application.device_initialized(self)
            return None

        self.debug("Scheduling initialization")

        self.cancel_initialization()
        self._initialize_task = asyncio.create_task(self.initialize())

        return self._initialize_task

    async def get_node_descriptor(self) -> zdo_t.NodeDescriptor:
        self.info("Requesting 'Node Descriptor'")

        status, _, node_desc = await self.zdo.Node_Desc_req(
            self.nwk,
            priority=t.PacketPriority.CRITICAL,
        )

        if status != zdo_t.Status.SUCCESS:
            raise zigpy.exceptions.InvalidResponse(
                f"Requesting Node Descriptor failed: {status}"
            )

        self.node_desc = node_desc
        self.info("Got Node Descriptor: %s", node_desc)

        return node_desc

    async def initialize(self) -> None:
        try:
            await self._initialize()
        except (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException):
            self.application.listener_event("device_init_failure", self)
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "Device %r failed to initialize due to unexpected error",
                self,
                exc_info=True,
            )

            self.application.listener_event("device_init_failure", self)

    def find_cluster(
        self, cluster_id: int, cluster_type: ClusterType = ClusterType.Server
    ) -> Cluster:
        """Find a cluster by its ID and type on any endpoint."""
        for ep in self.non_zdo_endpoints:
            if cluster_type == ClusterType.Server and cluster_id in ep.in_clusters:
                return ep.in_clusters[cluster_id]
            elif cluster_type == ClusterType.Client and cluster_id in ep.out_clusters:
                return ep.out_clusters[cluster_id]
        raise ValueError(
            f"Cluster {cluster_id:#04x} not found in any endpoint of device {self}"
        )

    async def poll_control_checkin_callback(
        self,
        zcl_hdr: foundation.ZCLHeader,
        command: foundation.CommandSchema,
    ) -> None:
        """Handle Poll Control check-in callback."""
        poll_control = self.find_cluster(cluster_id=PollControl.id)

        if self.initializing or self._concurrent_requests_semaphore.locked():
            # Initiate fast polling mode if we are initializing or waiting for requests
            # to be sent
            await poll_control.checkin_response(
                start_fast_polling=True,
                fast_poll_timeout=int(FAST_POLL_TIMEOUT * 4),
                tsn=zcl_hdr.tsn,
                priority=t.PacketPriority.CRITICAL,
            )
        else:
            await poll_control.checkin_response(
                start_fast_polling=False,
                fast_poll_timeout=0,
                tsn=zcl_hdr.tsn,
                priority=t.PacketPriority.CRITICAL,
            )

    async def begin_fast_polling(self, timeout: float) -> None:
        poll_control = self.find_cluster(cluster_id=PollControl.cluster_id)

        await poll_control.bind()
        await poll_control.write_attributes(
            # The units for the fast poll timeout are quarter seconds
            {PollControl.AttributeDefs.fast_poll_timeout.id: int(timeout * 4)},
            priority=t.PacketPriority.CRITICAL,
        )

    @zigpy.util.retryable_request(tries=5, delay=0.5)
    async def _initialize(self) -> None:
        """Attempts multiple times to discover all basic information about a device: namely
        its node descriptor, all endpoints and clusters, and the model and manufacturer
        attributes from any Basic cluster exposing those attributes.
        """

        # Some devices are improperly initialized and are missing a node descriptor
        if self.node_desc is None:
            await self.get_node_descriptor()

        # Devices should have endpoints other than ZDO
        if self.has_non_zdo_endpoints:
            self.info("Already have endpoints: %s", self.endpoints)
        else:
            self.info("Discovering endpoints")

            status, _, endpoints = await self.zdo.Active_EP_req(
                self.nwk, priority=t.PacketPriority.CRITICAL
            )

            if status != zdo_t.Status.SUCCESS:
                raise zigpy.exceptions.InvalidResponse(
                    f"Endpoint request failed: {status}"
                )

            self.info("Discovered endpoints: %s", endpoints)

            for endpoint_id in endpoints:
                if endpoint_id != 0:
                    self.add_endpoint(endpoint_id)

        self.status = Status.ZDO_INIT

        initiated_fast_polling = False

        # Initialize all of the discovered endpoints
        if self.all_endpoints_init:
            self.info(
                "All endpoints are already initialized: %s", self.non_zdo_endpoints
            )

            # Begin fast polling if we are re-initializing
            with contextlib.suppress(ValueError):
                await self.begin_fast_polling(FAST_POLL_TIMEOUT)
        else:
            self.info("Initializing endpoints %s", self.non_zdo_endpoints)

            initiated_fast_polling = False

            for ep in self.non_zdo_endpoints:
                await ep.initialize()

                if not initiated_fast_polling:
                    # Ask the device to enter fast polling mode mode as soon as we are
                    # aware of a PollControl cluster
                    try:
                        await self.begin_fast_polling(FAST_POLL_TIMEOUT)
                    except (ValueError, asyncio.TimeoutError, DeliveryError):
                        pass
                    else:
                        initiated_fast_polling = True

        # Query model info
        if self.model is not None and self.manufacturer is not None:
            self.info("Already have model and manufacturer info")
        else:
            for ep in self.non_zdo_endpoints:
                if self.model is None or self.manufacturer is None:
                    model, manufacturer = await ep.get_model_info()
                    self.info(
                        "Read model %r and manufacturer %r from %s",
                        model,
                        manufacturer,
                        ep,
                    )

                    if model is not None:
                        self.model = model

                    if manufacturer is not None:
                        self.manufacturer = manufacturer

        # Query current OTA info
        try:
            ota = self.find_cluster(
                cluster_id=Ota.cluster_id, cluster_type=ClusterType.Client
            )
        except ValueError:
            pass
        else:
            if ota.get(Ota.AttributeDefs.current_file_version.id) is None:
                self.info("Reading current OTA file version")
                await ota.read_attributes(
                    [Ota.AttributeDefs.current_file_version.name],
                )

        self.status = Status.ENDPOINTS_INIT

        self.info("Discovered basic device information for %s", self)

        # Signal to the application that the device is ready
        self._application.device_initialized(self)

    def add_endpoint(self, endpoint_id) -> zigpy.endpoint.Endpoint:
        ep = zigpy.endpoint.Endpoint(self, endpoint_id)
        self.endpoints[endpoint_id] = ep
        return ep

    async def add_to_group(self, grp_id: int, name: str | None = None) -> None:
        for ep in self.non_zdo_endpoints:
            await ep.add_to_group(grp_id, name)

    async def remove_from_group(self, grp_id: int) -> None:
        for ep in self.non_zdo_endpoints:
            await ep.remove_from_group(grp_id)

    async def request(
        self,
        profile,
        cluster,
        src_ep,
        dst_ep,
        sequence,
        data,
        expect_reply=True,
        timeout=APS_REPLY_TIMEOUT,
        use_ieee=False,
        ask_for_ack: bool | None = None,
        priority: int = t.PacketPriority.NORMAL,
    ):
        extended_timeout = False

        if self.node_desc is None or self.node_desc.is_end_device:
            self.debug("Extending timeout for 0x%02x request", sequence)
            timeout = APS_REPLY_TIMEOUT_EXTENDED
            extended_timeout = True

        # Use a lambda so we don't leave the coroutine unawaited in case of an exception
        send_request = lambda: self._application.request(  # noqa: E731
            device=self,
            profile=profile,
            cluster=cluster,
            src_ep=src_ep,
            dst_ep=dst_ep,
            sequence=sequence,
            data=data,
            expect_reply=expect_reply,
            use_ieee=use_ieee,
            extended_timeout=extended_timeout,
            ask_for_ack=ask_for_ack,
            priority=priority,
        )

        async with self._limit_concurrency(priority=priority):
            if not expect_reply:
                await send_request()
                return None

            # Only create a pending request if we are expecting a reply
            with self._pending.new(sequence) as req:
                await send_request()

                async with asyncio_timeout(timeout):
                    return await req.result

    def handle_message(
        self,
        profile: int,
        cluster: int,
        src_ep: int,
        dst_ep: int,
        message: bytes,
        *,
        dst_addressing: AddressingMode | None = None,
    ):
        """Deprecated compatibility function. Use `packet_received` instead."""

        warnings.warn(
            "`handle_message` is deprecated, use `packet_received`", DeprecationWarning
        )

        if dst_addressing is None:
            dst_addressing = t.AddrMode.NWK

        self.packet_received(
            t.ZigbeePacket(
                profile_id=profile,
                cluster_id=cluster,
                src_ep=src_ep,
                dst_ep=dst_ep,
                data=t.SerializableBytes(message),
                dst=t.AddrModeAddress(
                    addr_mode=dst_addressing,
                    address={
                        t.AddrMode.NWK: self.nwk,
                        t.AddrMode.IEEE: self.ieee,
                    }[dst_addressing],
                ),
            )
        )

    def _find_zcl_cluster_for_packet(
        self, zcl_hdr: foundation.ZCLHeader, packet: t.ZigbeePacket
    ) -> Cluster:
        """Find a cluster for the packet."""
        assert packet.src_ep is not None
        endpoint = self.endpoints[packet.src_ep]

        if zcl_hdr.direction == foundation.Direction.Client_to_Server:
            return endpoint.out_clusters[packet.cluster_id]
        else:
            return endpoint.in_clusters[packet.cluster_id]

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        # Set radio details that can be read from any type of packet
        self.last_seen = packet.timestamp

        if packet.lqi is not None:
            self.lqi = packet.lqi

        if packet.rssi is not None:
            self.rssi = packet.rssi

        if self._packet_debouncer.filter(
            # Be conservative with deduplication
            obj=packet.replace(timestamp=None, tsn=None, lqi=None, rssi=None),
            expire_in=PACKET_DEBOUNCE_WINDOW,
        ):
            self.debug("Filtering duplicate packet")
            return

        # Filter out packets that come from unregistered endpoints
        if packet.src_ep not in self.endpoints:
            self.debug(
                "Ignoring message on unknown endpoint %s (expected one of %s)",
                packet.src_ep,
                self.endpoints,
            )
            return

        if packet.dst_ep == zdo.ZDO_ENDPOINT:
            self.zdo_packet_received(packet)
        else:
            self.zcl_packet_received(packet)

    def _parse_zcl_command(
        self, zcl_cluster: Cluster, zcl_hdr: foundation.ZCLHeader, command_data: bytes
    ) -> tuple[typing.Any, bytes]:
        """Parse a ZCL command from the data."""
        if zcl_hdr.frame_control.frame_type == foundation.FrameType.GLOBAL_COMMAND:
            cmd, remaining = foundation.GENERAL_COMMANDS[
                zcl_hdr.command_id
            ].schema.deserialize(command_data)
        else:
            if zcl_hdr.direction == foundation.Direction.Server_to_Client:
                commands = zcl_cluster.client_commands
            else:
                commands = zcl_cluster.server_commands

            cmd, remaining = commands[zcl_hdr.command_id].deserialize(command_data)

        return cmd, remaining

    def zcl_packet_received(self, packet: t.ZigbeePacket) -> None:
        # ZCL packets need to be parsed a little to determine where they go
        data = packet.data.serialize()
        zcl_hdr, command_data = foundation.ZCLHeader.deserialize(data)

        try:
            zcl_cluster = self._find_zcl_cluster_for_packet(zcl_hdr, packet)
        except KeyError:
            self.debug("Ignoring message on an unexpected cluster", packet.cluster_id)
            return

        try:
            cmd, remaining = self._parse_zcl_command(zcl_cluster, zcl_hdr, command_data)
        except Exception as exc:  # noqa: BLE001
            error = zigpy.exceptions.ParsingError()
            error.__cause__ = exc

            self.debug("Failed to parse packet %r", packet, exc_info=error)
        else:
            error = None
            self.debug("Decoded ZCL frame: %s:%r", type(zcl_cluster).__name__, cmd)

            if remaining:
                self.debug(
                    "Data remains after deserializing ZCL command: %r", remaining
                )

        # Resolve the future if this is a response to a request
        # TODO: this needs to be further narrowed down by cluster ID and endpoint ID
        if zcl_hdr.tsn in self._pending:
            future = self._pending[zcl_hdr.tsn]

            if error is not None:
                future.result.set_exception(error)
            else:
                future.result.set_result(cmd)

            return

        if error is not None:
            return

        # Pass the request off to a listener, if one is registered
        for listener in itertools.chain(
            self._application._req_listeners[zigpy.listeners.ANY_DEVICE],
            self._application._req_listeners[self],
        ):
            # Resolve only until the first future listener
            if listener.resolve(zcl_hdr, cmd) and isinstance(
                listener, zigpy.listeners.FutureListener
            ):
                break

        # Finally, pass it off to a cluster to generate events
        if zcl_hdr.frame_control.frame_type == foundation.FrameType.GLOBAL_COMMAND:
            zcl_cluster.handle_cluster_general_request(zcl_hdr, cmd)
            zcl_cluster.listener_event("general_command", zcl_hdr, cmd)
        else:
            zcl_cluster.handle_cluster_request(zcl_hdr, cmd)
            zcl_cluster.listener_event(
                "cluster_command", zcl_hdr.tsn, zcl_hdr.command_id, cmd
            )

    def zdo_packet_received(self, packet: t.ZigbeePacket) -> None:
        assert packet.src_ep is not None
        zdo_endpoint = self.endpoints[packet.src_ep]
        data = packet.data.serialize()

        zdo_hdr, _ = zdo_t.ZDOHeader.deserialize(packet.cluster_id, data)

        # Next, try to parse the command
        try:
            _, cmd = zdo_endpoint.deserialize(packet.cluster_id, data)
        except Exception as exc:  # noqa: BLE001
            error = zigpy.exceptions.ParsingError()
            error.__cause__ = exc

            self.debug("Failed to parse packet %r", packet, exc_info=error)
        else:
            error = None

        # Resolve the future if this is a response to a request
        if zdo_hdr.tsn in self._pending and zdo_hdr.is_reply:
            future = self._pending[zdo_hdr.tsn]

            if error is not None:
                future.result.set_exception(error)
            else:
                future.result.set_result(cmd)

            return

        if error is not None:
            return

        # Pass the request off to a listener, if one is registered
        for listener in itertools.chain(
            self._application._req_listeners[zigpy.listeners.ANY_DEVICE],
            self._application._req_listeners[self],
        ):
            # Resolve only until the first future listener
            if listener.resolve(zdo_hdr, cmd) and isinstance(
                listener, zigpy.listeners.FutureListener
            ):
                break

    async def reply(
        self,
        profile,
        cluster,
        src_ep,
        dst_ep,
        sequence,
        data,
        timeout=APS_REPLY_TIMEOUT,
        expect_reply: bool = False,
        use_ieee: bool = False,
        ask_for_ack: bool | None = None,
        priority: int = t.PacketPriority.NORMAL,
    ):
        return await self.request(
            profile=profile,
            cluster=cluster,
            src_ep=src_ep,
            dst_ep=dst_ep,
            sequence=sequence,
            data=data,
            expect_reply=expect_reply,
            timeout=timeout,
            use_ieee=use_ieee,
            ask_for_ack=ask_for_ack,
            priority=priority,
        )

    async def update_firmware(
        self,
        image: OtaImageWithMetadata,
        progress_callback: callable | None = None,
        force: bool = False,
    ) -> foundation.Status:
        """Update device firmware."""
        if self.ota_in_progress:
            self.debug("OTA already in progress")
            return None

        self.ota_in_progress = True

        try:
            result = await update_firmware(
                device=self,
                image=image,
                progress_callback=progress_callback,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001
            self.debug("OTA failed!", exc_info=exc)
            raise
        finally:
            self.ota_in_progress = False

        if result != foundation.Status.SUCCESS:
            return result

        # Clear the current file version when the update succeeds
        ota = self.find_cluster(
            cluster_id=Ota.cluster_id, cluster_type=ClusterType.Client
        )
        ota.update_attribute(Ota.AttributeDefs.current_file_version.id, None)

        await asyncio.sleep(AFTER_OTA_ATTR_READ_DELAY)
        await OTA_RETRY_DECORATOR(ota.read_attributes)(
            [Ota.AttributeDefs.current_file_version.name]
        )

        return result

    def radio_details(self, lqi=None, rssi=None) -> None:
        if lqi is not None:
            self.lqi = lqi
        if rssi is not None:
            self.rssi = rssi

    def log(self, lvl, msg, *args, **kwargs) -> None:
        msg = "[0x%04x] " + msg
        args = (self.nwk, *args)
        LOGGER.log(lvl, msg, *args, **kwargs)

    @property
    def application(self) -> ControllerApplication:
        return self._application

    @property
    def ieee(self) -> t.EUI64:
        return self._ieee

    @property
    def manufacturer(self) -> str | None:
        return self._manufacturer

    @manufacturer.setter
    def manufacturer(self, value) -> None:
        if isinstance(value, str):
            self._manufacturer = value

    @property
    def manufacturer_id(self) -> int | None:
        """Return manufacturer id."""
        if self.manufacturer_id_override:
            return self.manufacturer_id_override
        elif self.node_desc is not None:
            return self.node_desc.manufacturer_code
        else:
            return None

    @property
    def model(self) -> str | None:
        return self._model

    @model.setter
    def model(self, value) -> None:
        if isinstance(value, str):
            self._model = value

    @property
    def skip_configuration(self) -> bool:
        return self._skip_configuration

    @skip_configuration.setter
    def skip_configuration(self, should_skip_configuration) -> None:
        if isinstance(should_skip_configuration, bool):
            self._skip_configuration = should_skip_configuration
        else:
            self._skip_configuration = False

    @property
    def relays(self) -> t.Relays | None:
        """Relay list."""
        return self._relays

    @relays.setter
    def relays(self, relays: t.Relays | None) -> None:
        if relays is None:
            pass
        elif not isinstance(relays, t.Relays):
            relays = t.Relays(relays)

        self._relays = relays
        self.listener_event("device_relays_updated", relays)

    def __getitem__(self, key):
        return self.endpoints[key]

    def get_signature(self) -> dict[str, typing.Any]:
        # return the device signature by providing essential device information
        #    - Model Identifier ( Attribute 0x0005 of Basic Cluster 0x0000 )
        #    - Manufacturer Name ( Attribute 0x0004 of Basic Cluster 0x0000 )
        #    - Endpoint list
        #        - Profile Id, Device Id, Cluster Out, Cluster In
        signature: dict[str, typing.Any] = {}
        if self._manufacturer is not None:
            signature[SIG_MANUFACTURER] = self.manufacturer
        if self._model is not None:
            signature[SIG_MODEL] = self._model
        if self.node_desc is not None:
            signature[SIG_NODE_DESC] = self.node_desc.as_dict()

        for endpoint_id, endpoint in self.endpoints.items():
            if endpoint_id == 0:  # ZDO
                continue
            signature.setdefault(SIG_ENDPOINTS, {})
            in_clusters = list(endpoint.in_clusters)
            out_clusters = list(endpoint.out_clusters)
            signature[SIG_ENDPOINTS][endpoint_id] = {
                SIG_EP_PROFILE: endpoint.profile_id,
                SIG_EP_TYPE: endpoint.device_type,
                SIG_EP_INPUT: in_clusters,
                SIG_EP_OUTPUT: out_clusters,
            }
        return signature

    def __repr__(self) -> str:
        return (
            f"<"
            f"{type(self).__name__}"
            f" model={self.model!r}"
            f" manuf={self.manufacturer!r}"
            f" nwk={t.NWK(self.nwk)}"
            f" ieee={self.ieee}"
            f" is_initialized={self.is_initialized}"
            f">"
        )


async def broadcast(
    app,
    profile,
    cluster,
    src_ep,
    dst_ep,
    grpid,
    radius,
    sequence,
    data,
    broadcast_address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
):
    return await app.broadcast(
        profile,
        cluster,
        src_ep,
        dst_ep,
        grpid,
        radius,
        sequence,
        data,
        broadcast_address=broadcast_address,
    )
