from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
import enum
import itertools
import logging
import sys
import time
import typing
import warnings

from zigpy.backports.contextlib import nullcontext
from zigpy.exceptions import DeliveryError
from zigpy.ota.manager import update_firmware
from zigpy.profiles import zha, zll
from zigpy.zcl.clusters.general import Ota, PollControl

if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout  # pragma: no cover
else:
    from asyncio import timeout as asyncio_timeout  # pragma: no cover


from dataclasses import dataclass

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
DEFAULT_FAST_POLL_TIMEOUT = 30

AFTER_OTA_ATTR_READ_DELAY = 10
OTA_RETRY_DECORATOR = zigpy.util.retryable_request(
    tries=4, delay=AFTER_OTA_ATTR_READ_DELAY
)


# TODO: Only Python 3.10+ support `slots=True` for dataclasses
@dataclass(frozen=True, **({"slots": True} if sys.version_info[:2] >= (3, 10) else {}))
class ResponseKey:
    """Key for request/response matching."""

    endpoint_id: int
    cluster_id: int
    direction: foundation.Direction | None
    tsn: int


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
        self._requests: dict[ResponseKey, asyncio.Future] = {}
        self._relays: t.Relays | None = None
        self._skip_configuration: bool = False
        self._send_sequence: int = 0

        self._fast_polling_end_time = datetime.min.replace(tzinfo=timezone.utc)
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
    async def _limit_concurrency(self, *, priority: int | None = None):
        """Async context manager to limit device request concurrency."""
        # Defer to the current app-level priority if not specified
        if priority is None:
            priority = self._application._packet_priority_var.get()

        start_time = time.monotonic()
        manager: contextlib.AbstractAsyncContextManager

        if priority >= t.PacketPriority.CRITICAL:
            LOGGER.debug(
                "Critical priority request received (%s), skipping queue with %d requests",
                priority,
                self._concurrent_requests_semaphore.num_waiting,
            )
            manager = nullcontext()
            was_locked = False
        else:
            manager = self._concurrent_requests_semaphore(priority=priority)
            was_locked = self._concurrent_requests_semaphore.locked()

        if was_locked:
            LOGGER.debug(
                "Device concurrency (%s) reached, delaying device request (%s enqueued)",
                self._concurrent_requests_semaphore.max_value,
                self._concurrent_requests_semaphore.num_waiting,
            )

        async with manager:
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

        status, _, node_desc = await self.zdo.Node_Desc_req(self.nwk)

        if status != zdo_t.Status.SUCCESS:
            raise zigpy.exceptions.InvalidResponse(
                f"Requesting Node Descriptor failed: {status}"
            )

        self.node_desc = node_desc
        self.info("Got Node Descriptor: %s", node_desc)

        return node_desc

    async def initialize(self) -> None:
        try:
            # Perform initialization with critical priority
            async with self._application.request_priority(t.PacketPriority.CRITICAL):
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
        """Find the first cluster by its ID and type on any endpoint."""
        for ep in self.non_zdo_endpoints:
            if cluster_type == ClusterType.Server and cluster_id in ep.in_clusters:
                return ep.in_clusters[cluster_id]
            elif cluster_type == ClusterType.Client and cluster_id in ep.out_clusters:
                return ep.out_clusters[cluster_id]
        raise ValueError(
            f"Cluster {cluster_id:#06x} not found in any endpoint of device {self}"
        )

    async def poll_control_checkin_callback(
        self,
        zcl_hdr: foundation.ZCLHeader,
        command: foundation.CommandSchema,
    ) -> None:
        """Handle Poll Control check-in callback."""
        poll_control = self.find_cluster(cluster_id=PollControl.cluster_id)

        async with self._application.request_priority(t.PacketPriority.CRITICAL):
            if self.initializing or self._concurrent_requests_semaphore.locked():
                # Initiate fast polling mode if we are initializing or waiting for
                # requests to be sent
                await poll_control.checkin_response(
                    start_fast_polling=True,
                    fast_poll_timeout=int(DEFAULT_FAST_POLL_TIMEOUT * 4),
                    tsn=zcl_hdr.tsn,
                )
            else:
                await poll_control.checkin_response(
                    start_fast_polling=False,
                    fast_poll_timeout=0,
                    tsn=zcl_hdr.tsn,
                )

    async def begin_fast_polling(
        self, timeout: float = DEFAULT_FAST_POLL_TIMEOUT
    ) -> None:
        """Ask the device to enter fast polling mode."""
        try:
            poll_control = self.find_cluster(cluster_id=PollControl.cluster_id)
        except ValueError:
            # The device doesn't have the cluster, there's nothing more we can do
            return

        LOGGER.debug("Beginning fast polling for %0.2fs", timeout)

        # We must first bind to the cluster, otherwise the device will not send a check-
        # in command
        await poll_control.bind()
        await poll_control.write_attributes(
            # The units are quarter seconds
            {
                PollControl.AttributeDefs.fast_poll_timeout.id: int(timeout * 4),
            }
        )

        self._fast_polling_end_time = datetime.now(timezone.utc) + timedelta(
            seconds=timeout
        )

    def reset_timers(self) -> None:
        """Reset timers if we suspect a device has rebooted or reset."""
        self._fast_polling_end_time = datetime.min.replace(tzinfo=timezone.utc)

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

            status, _, endpoints = await self.zdo.Active_EP_req(self.nwk)

            if status != zdo_t.Status.SUCCESS:
                raise zigpy.exceptions.InvalidResponse(
                    f"Endpoint request failed: {status}"
                )

            self.info("Discovered endpoints: %s", endpoints)

            for endpoint_id in endpoints:
                if endpoint_id != 0:
                    self.add_endpoint(endpoint_id)

        self.status = Status.ZDO_INIT

        # Initialize all of the discovered endpoints
        initiated_fast_polling = self._fast_polling_end_time > datetime.now(
            timezone.utc
        )

        if self.all_endpoints_init:
            self.info(
                "All endpoints are already initialized: %s", self.non_zdo_endpoints
            )

            if not initiated_fast_polling:
                # Begin fast polling if we are re-initializing
                await self.begin_fast_polling()
        else:
            self.info("Initializing endpoints %s", self.non_zdo_endpoints)

            for ep in self.non_zdo_endpoints:
                await ep.initialize()

                if not initiated_fast_polling:
                    # Ask the device to enter fast polling mode as soon as we are
                    # aware of a PollControl cluster
                    try:
                        await self.begin_fast_polling()
                    except (asyncio.TimeoutError, DeliveryError):
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
        priority: int | None = None,
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

            if dst_ep == zdo.ZDO_ENDPOINT:
                rsp_key = ResponseKey(
                    endpoint_id=dst_ep,
                    # e.g. Node_Desc_req = 0x0002 corresponds to Node_Desc_rsp = 0x8002
                    cluster_id=cluster ^ 0x8000,
                    direction=None,
                    tsn=sequence,
                )
            else:
                zcl_hdr, _ = foundation.ZCLHeader.deserialize(data)
                rsp_key = ResponseKey(
                    endpoint_id=dst_ep,
                    cluster_id=cluster,
                    direction=zcl_hdr.frame_control.direction.flip(),
                    tsn=sequence,
                )

            if rsp_key in self._requests:
                self.debug(
                    "Duplicate request key %s, pending requests %s",
                    rsp_key,
                    self._requests,
                )
                raise zigpy.exceptions.ControllerException(
                    f"Duplicate request key: {rsp_key}"
                )

            future: asyncio.Future[list[typing.Any, ...] | foundation.CommandSchema] = (
                asyncio.Future()
            )
            self._requests[rsp_key] = future

            try:
                await send_request()
                async with asyncio_timeout(timeout):
                    return await future
            finally:
                if not future.done():
                    future.cancel()
                self._requests.pop(rsp_key, None)

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

    def _find_zcl_cluster(
        self, hdr: foundation.ZCLHeader, packet: t.ZigbeePacket
    ) -> Cluster:
        """Find the ZCL cluster for a given header and packet."""
        assert packet.src_ep is not None
        ep = self.endpoints[packet.src_ep]

        if hdr.frame_control.direction == foundation.Direction.Client_to_Server:
            return ep.out_clusters[packet.cluster_id]
        else:
            return ep.in_clusters[packet.cluster_id]

    def custom_profile_packet_received(self, packet: t.ZigbeePacket) -> None:
        """Handle packets with a custom profile ID."""
        self.debug(
            "Received packet with custom profile 0x%04x, ignoring",
            packet.profile_id,
        )

    def _should_filter_packet(self, packet: t.ZigbeePacket) -> bool:
        """Check if packet should be filtered as duplicate."""
        return self._packet_debouncer.filter(
            # Be conservative with deduplication
            obj=packet.replace(timestamp=None, tsn=None, lqi=None, rssi=None),
            expire_in=PACKET_DEBOUNCE_WINDOW,
        )

    def _parse_packet_header(
        self, packet: t.ZigbeePacket
    ) -> tuple[zdo_t.ZDOHeader | foundation.ZCLHeader, ResponseKey] | tuple[None, None]:
        """Parse packet header and create response key."""
        data = packet.data.serialize()

        if packet.src_ep == zdo.ZDO_ENDPOINT:
            hdr, _ = zdo_t.ZDOHeader.deserialize(packet.cluster_id, data)
            rsp_key = ResponseKey(
                endpoint_id=packet.src_ep,
                cluster_id=packet.cluster_id,
                direction=None,
                tsn=hdr.tsn,
            )
            return hdr, rsp_key
        elif packet.profile_id in (zha.PROFILE_ID, zll.PROFILE_ID):
            hdr, _ = foundation.ZCLHeader.deserialize(data)
            rsp_key = ResponseKey(
                endpoint_id=packet.src_ep,
                cluster_id=packet.cluster_id,
                direction=hdr.frame_control.direction,
                tsn=hdr.tsn,
            )
            return hdr, rsp_key
        else:
            return None, None

    def _match_packet_endpoint_cluster(
        self, packet: t.ZigbeePacket, hdr: zdo_t.ZDOHeader | foundation.ZCLHeader
    ) -> (
        tuple[zigpy.endpoint.Endpoint, Cluster]
        | tuple[zigpy.zdo.ZDO, None]
        | tuple[None, None]
    ):
        """Validate packet routing and find target endpoint and cluster."""
        if packet.src_ep not in self.endpoints:
            self.debug(
                "Ignoring message on unknown endpoint %s (expected one of %s)",
                packet.src_ep,
                self.endpoints,
            )
            return None, None

        endpoint = self.endpoints[packet.src_ep]

        if packet.src_ep == zdo.ZDO_ENDPOINT:
            return endpoint, None
        else:
            try:
                zcl_cluster = self._find_zcl_cluster(hdr, packet)
            except KeyError:
                self.debug(
                    "Ignoring message on unknown cluster: 0x%04x",
                    packet.cluster_id,
                )
                return None, None
            else:
                return endpoint, zcl_cluster

    def _parse_packet_command(
        self, packet: t.ZigbeePacket, endpoint: typing.Any, zcl_cluster: Cluster | None
    ) -> typing.Any:
        """Deserialize packet data."""
        data = packet.data.serialize()

        if packet.src_ep == zdo.ZDO_ENDPOINT:
            _, cmd = endpoint.deserialize(packet.cluster_id, data)
        else:
            assert zcl_cluster is not None
            _, cmd = zcl_cluster.deserialize(data)

        return cmd

    def _maybe_match_response(
        self, rsp_key: ResponseKey, cmd: typing.Any | None, error: Exception | None
    ) -> bool:
        """Handle response matching for pending requests, returns True if packet was matched."""
        future = self._requests.get(rsp_key)
        if future is None:
            return False

        try:
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(cmd)
        except asyncio.InvalidStateError:
            self.debug(
                "Invalid state on future for %s -- probably duplicate response",
                rsp_key,
            )

        return True

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        """Process received packet through the device's packet handling pipeline."""
        self.last_seen = packet.timestamp

        if packet.lqi is not None:
            self.lqi = packet.lqi

        if packet.rssi is not None:
            self.rssi = packet.rssi

        # Filter duplicate packets
        if self._should_filter_packet(packet):
            self.debug("Filtering duplicate packet")
            return

        # Parse packet header and create response key
        hdr, rsp_key = self._parse_packet_header(packet)
        if hdr is None:
            self.custom_profile_packet_received(packet)
            return

        # Validate packet routing and find target endpoint/cluster
        endpoint, zcl_cluster = self._match_packet_endpoint_cluster(packet, hdr)
        if endpoint is None:
            return

        # Deserialize packet data
        try:
            cmd = self._parse_packet_command(packet, endpoint, zcl_cluster)
        except Exception as exc:  # noqa: BLE001
            cmd = None
            error = zigpy.exceptions.ParsingError()
            error.__cause__ = exc
            self.debug("Failed to parse packet %r", packet, exc_info=error)
        else:
            error = None

        # Handle response matching for pending requests
        if self._maybe_match_response(rsp_key, cmd, error):
            return

        # Skip further processing if there was a parsing error
        if error is not None:
            return

        # Pass the request off to a listener, if one is registered
        for listener in itertools.chain(
            self._application._req_listeners[zigpy.listeners.ANY_DEVICE],
            self._application._req_listeners[self],
        ):
            # Resolve only until the first future listener
            if listener.resolve(hdr, cmd) and isinstance(
                listener, zigpy.listeners.FutureListener
            ):
                break

        # Finally, pass it off to the cluster message handler. This will be removed.
        if zcl_cluster is not None:
            zcl_cluster.handle_message(hdr, cmd)
        else:
            assert isinstance(endpoint, zdo.ZDO)
            endpoint.handle_message(packet.profile_id, packet.cluster_id, hdr, cmd)

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
        priority: int | None = None,
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
            if endpoint_id == zdo.ZDO_ENDPOINT:  # ZDO
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
