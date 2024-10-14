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

from zigpy.ota.manager import find_ota_cluster, update_firmware
from zigpy.zcl.clusters.general import Ota

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
from zigpy.zcl import foundation
import zigpy.zdo.types as zdo_t

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.ota.providers import OtaImageWithMetadata


LOGGER = logging.getLogger(__name__)

PACKET_DEBOUNCE_WINDOW = 10
MAX_DEVICE_CONCURRENCY = 1

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

        self._packet_debouncer = zigpy.datastructures.Debouncer()
        self._concurrent_requests_semaphore = (
            zigpy.datastructures.PriorityDynamicBoundedSemaphore(MAX_DEVICE_CONCURRENCY)
        )

        # Retained for backwards compatibility, will be removed in a future release
        self.status = Status.NEW

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
            priority=t.PacketPriority.HIGH,
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
                self.nwk, priority=t.PacketPriority.HIGH
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

        # Initialize all of the discovered endpoints
        if self.all_endpoints_init:
            self.info(
                "All endpoints are already initialized: %s", self.non_zdo_endpoints
            )
        else:
            self.info("Initializing endpoints %s", self.non_zdo_endpoints)

            for ep in self.non_zdo_endpoints:
                await ep.initialize()

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
        priority: int = t.PacketPriority.NORMAL,
    ):
        extended_timeout = False

        if expect_reply and (self.node_desc is None or self.node_desc.is_end_device):
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

    def deserialize(self, endpoint_id, cluster_id, data):
        """Deprecated compatibility function."""
        warnings.warn(
            "`deserialize` is deprecated, avoid rewriting packet structures this way",
            DeprecationWarning,
        )
        return self.endpoints[endpoint_id].deserialize(cluster_id, data)

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

        # Filter out packets that refer to unknown endpoints or clusters
        if packet.src_ep not in self.endpoints:
            self.debug(
                "Ignoring message on unknown endpoint %s (expected one of %s)",
                packet.src_ep,
                self.endpoints,
            )
            return

        endpoint = self.endpoints[packet.src_ep]

        # Ignore packets that do not match the endpoint's clusters.
        # TODO: this isn't actually necessary, we can parse most packets by cluster ID.
        if (
            packet.dst_ep != zdo.ZDO_ENDPOINT
            and packet.cluster_id not in endpoint.in_clusters
            and packet.cluster_id not in endpoint.out_clusters
        ):
            self.debug(
                "Ignoring message on unknown cluster %s for endpoint %s",
                packet.cluster_id,
                endpoint,
            )
            return

        # Parse the ZCL/ZDO header first. This should never fail.
        data = packet.data.serialize()

        if packet.dst_ep == zdo.ZDO_ENDPOINT:
            hdr, _ = zdo_t.ZDOHeader.deserialize(packet.cluster_id, data)
        else:
            hdr, _ = foundation.ZCLHeader.deserialize(data)

        try:
            if (
                type(self).deserialize is not Device.deserialize
                or getattr(self.deserialize, "__func__", None) is not Device.deserialize
            ):
                # XXX: support for custom deserialization will be removed
                hdr, args = self.deserialize(packet.src_ep, packet.cluster_id, data)
            else:
                # Next, parse the ZCL/ZDO payload
                # FIXME: ZCL deserialization mutates the header!
                hdr, args = endpoint.deserialize(packet.cluster_id, data)
        except Exception as exc:  # noqa: BLE001
            error = zigpy.exceptions.ParsingError()
            error.__cause__ = exc

            self.debug("Failed to parse packet %r", packet, exc_info=error)
        else:
            error = None

        # Resolve the future if this is a response to a request
        if hdr.tsn in self._pending and (
            hdr.direction == foundation.Direction.Server_to_Client
            if isinstance(hdr, foundation.ZCLHeader)
            else hdr.is_reply
        ):
            future = self._pending[hdr.tsn]

            try:
                if error is not None:
                    future.result.set_exception(error)
                else:
                    future.result.set_result(args)
            except asyncio.InvalidStateError:
                self.debug(
                    (
                        "Invalid state on future for 0x%02x seq "
                        "-- probably duplicate response"
                    ),
                    hdr.tsn,
                )

            return

        if error is not None:
            return

        # Pass the request off to a listener, if one is registered
        for listener in itertools.chain(
            self._application._req_listeners[zigpy.listeners.ANY_DEVICE],
            self._application._req_listeners[self],
        ):
            # Resolve only until the first future listener
            if listener.resolve(hdr, args) and isinstance(
                listener, zigpy.listeners.FutureListener
            ):
                break

        # Finally, pass it off to the endpoint message handler. This will be removed.
        endpoint.handle_message(
            packet.profile_id,
            packet.cluster_id,
            hdr,
            args,
            dst_addressing=packet.dst.addr_mode if packet.dst is not None else None,
        )

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
        ota = find_ota_cluster(self)
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
