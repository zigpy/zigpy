from __future__ import annotations

import asyncio
import binascii
import enum
import logging
import time
from typing import Optional

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_NODE_DESC,
)
import zigpy.endpoint
import zigpy.exceptions
import zigpy.neighbor
from zigpy.types import NWK, Addressing, BroadcastAddress, Relays
import zigpy.util
import zigpy.zcl.foundation as foundation
import zigpy.zdo as zdo

APS_REPLY_TIMEOUT = 5
APS_REPLY_TIMEOUT_EXTENDED = 28
LOGGER = logging.getLogger(__name__)


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

    def __init__(self, application, ieee, nwk):
        self._application = application
        self._ieee = ieee
        self._initialize_task = None
        self.nwk = NWK(nwk)
        self.zdo = zdo.ZDO(self)
        self.endpoints: dict[int, zdo.ZDO | zigpy.endpoint.Endpoint] = {0: self.zdo}
        self.lqi = None
        self.rssi = None
        self.last_seen = None
        self._initialize_task: Optional[asyncio.Task] = None
        self._group_scan_task: Optional[asyncio.Task] = None
        self._listeners = {}
        self._manufacturer = None
        self._model = None
        self.node_desc = zdo.types.NodeDescriptor()
        self.neighbors = zigpy.neighbor.Neighbors(self)
        self._pending = zigpy.util.Requests()
        self._relays = None
        self._skip_configuration = False

        # Retained for backwards compatibility, will be removed in a future release
        self.status = Status.NEW

    @property
    def non_zdo_endpoints(self):
        return [ep for epid, ep in self.endpoints.items() if epid != 0]

    @property
    def has_node_descriptor(self) -> bool:
        return self.node_desc is not None and self.node_desc.is_valid

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
        return self.has_node_descriptor and self.all_endpoints_init

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
            self._initialize_task.cancel()

    def schedule_initialize(self) -> Optional[asyncio.Task]:
        # Already-initialized devices don't need to be re-initialized
        if self.is_initialized:
            self.debug("Skipping initialization, device is fully initialized")
            self._application.device_initialized(self)
            return None

        self.debug("Scheduling initialization")

        self.cancel_initialization()
        self._initialize_task = asyncio.create_task(self.initialize())

        return self._initialize_task

    async def get_node_descriptor(self) -> zdo.types.NodeDescriptor:
        self.info("Requesting 'Node Descriptor'")

        status, _, node_desc = await self.zdo.Node_Desc_req(
            self.nwk, tries=2, delay=0.1
        )

        if status != zdo.types.Status.SUCCESS:
            raise zigpy.exceptions.InvalidResponse(
                f"Requesting Node Descriptor failed: {status}"
            )

        self.node_desc = node_desc
        self.info("Got Node Descriptor: %s", node_desc)

        return node_desc

    async def initialize(self):
        try:
            await self._initialize()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not isinstance(
                e, (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException)
            ):
                LOGGER.warning(
                    "Device failed to initialize due to unexpected error", exc_info=True
                )

            self.application.listener_event("device_init_failure", self)

    @zigpy.util.retryable(
        (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException), tries=3, delay=0.5
    )
    async def _initialize(self):
        """
        Attempts multiple times to discover all basic information about a device: namely
        its node descriptor, all endpoints and clusters, and the model and manufacturer
        attributes from any Basic cluster exposing those attributes.
        """

        # Some devices are improperly initialized and are missing a node descriptor
        if not self.has_node_descriptor:
            await self.get_node_descriptor()

        # Devices should have endpoints other than ZDO
        if self.has_non_zdo_endpoints:
            self.info("Already have endpoints: %s", self.endpoints)
        else:
            self.info("Discovering endpoints")

            status, _, endpoints = await self.zdo.Active_EP_req(
                self.nwk, tries=3, delay=0.5
            )

            if status != zdo.types.Status.SUCCESS:
                raise zigpy.exceptions.InvalidResponse(
                    f"Endpoint request failed: {status}"
                )

            self.info("Discovered endpoints: %s", endpoints)

            for endpoint_id in endpoints:
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

    def add_endpoint(self, endpoint_id):
        ep = zigpy.endpoint.Endpoint(self, endpoint_id)
        self.endpoints[endpoint_id] = ep
        return ep

    async def add_to_group(self, grp_id: int, name: str = None):
        for ep in self.non_zdo_endpoints:
            await ep.add_to_group(grp_id, name)

    async def remove_from_group(self, grp_id: int):
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
    ):
        if expect_reply and self.node_desc.is_end_device in (True, None):
            self.debug("Extending timeout for 0x%02x request", sequence)
            timeout = APS_REPLY_TIMEOUT_EXTENDED
        with self._pending.new(sequence) as req:
            result, msg = await self._application.request(
                self,
                profile,
                cluster,
                src_ep,
                dst_ep,
                sequence,
                data,
                expect_reply=expect_reply,
                use_ieee=use_ieee,
            )
            if result != foundation.Status.SUCCESS:
                self.debug(
                    (
                        "Delivery error for seq # 0x%02x, on endpoint id %s "
                        "cluster 0x%04x: %s"
                    ),
                    sequence,
                    dst_ep,
                    cluster,
                    msg,
                )
                raise zigpy.exceptions.DeliveryError(
                    "[0x{:04x}:{}:0x{:04x}]: Message send failure".format(
                        self.nwk, dst_ep, cluster
                    )
                )
            # If application.request raises an exception, we won't get here, so
            # won't update last_seen, as expected
            self.last_seen = time.time()
            if expect_reply:
                result = await asyncio.wait_for(req.result, timeout)

        return result

    def deserialize(self, endpoint_id, cluster_id, data):
        return self.endpoints[endpoint_id].deserialize(cluster_id, data)

    def handle_message(
        self,
        profile: int,
        cluster: int,
        src_ep: int,
        dst_ep: int,
        message: bytes,
        *,
        dst_addressing: Optional[
            Addressing.Group | Addressing.IEEE | Addressing.NWK
        ] = None,
    ):
        self.last_seen = time.time()

        if not self.is_initialized and not self.initializing:
            self.warning("Received a message from an uninitialized device")
            self.schedule_initialize()

        try:
            hdr, args = self.deserialize(src_ep, cluster, message)
        except ValueError as e:
            LOGGER.error(
                "Failed to parse message (%s) on cluster %d, because %s",
                binascii.hexlify(message),
                cluster,
                e,
            )
            return
        except KeyError as e:
            LOGGER.debug(
                (
                    "Ignoring message (%s) on cluster %d: "
                    "unknown endpoint or cluster id: %s"
                ),
                binascii.hexlify(message),
                cluster,
                e,
            )
            return

        if hdr.tsn in self._pending and hdr.is_reply:
            try:
                self._pending[hdr.tsn].result.set_result(args)
                return
            except asyncio.InvalidStateError:
                self.debug(
                    (
                        "Invalid state on future for 0x%02x seq "
                        "-- probably duplicate response"
                    ),
                    hdr.tsn,
                )
                return

        endpoint = self.endpoints[src_ep]
        return endpoint.handle_message(
            profile, cluster, hdr, args, dst_addressing=dst_addressing
        )

    def reply(self, profile, cluster, src_ep, dst_ep, sequence, data, use_ieee=False):
        return self.request(
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=False,
            use_ieee=use_ieee,
        )

    def radio_details(self, lqi, rssi):
        self.lqi = lqi
        self.rssi = rssi

    def log(self, lvl, msg, *args, **kwargs):
        msg = "[0x%04x] " + msg
        args = (self.nwk,) + args
        return LOGGER.log(lvl, msg, *args, **kwargs)

    @property
    def application(self):
        return self._application

    @property
    def ieee(self):
        return self._ieee

    @property
    def manufacturer(self):
        return self._manufacturer

    @manufacturer.setter
    def manufacturer(self, value):
        if isinstance(value, str):
            self._manufacturer = value

    @property
    def manufacturer_id(self) -> Optional[int]:
        """Return manufacturer id."""
        return self.manufacturer_id_override or self.node_desc.manufacturer_code

    @property
    def model(self):
        return self._model

    @property
    def skip_configuration(self):
        return self._skip_configuration

    @skip_configuration.setter
    def skip_configuration(self, should_skip_configuration):
        if isinstance(should_skip_configuration, bool):
            self._skip_configuration = should_skip_configuration
        else:
            self._skip_configuration = False

    @model.setter
    def model(self, value):
        if isinstance(value, str):
            self._model = value

    @property
    def relays(self) -> Optional[Relays]:
        """Relay list."""
        return self._relays

    @relays.setter
    def relays(self, relays: Optional[Relays]) -> None:
        self._relays = relays
        self.listener_event("device_relays_updated", relays)

    def __getitem__(self, key):
        return self.endpoints[key]

    def get_signature(self):
        # return the device signature by providing essential device information
        #    - Model Identifier ( Attribute 0x0005 of Basic Cluster 0x0000 )
        #    - Manufacturer Name ( Attribute 0x0004 of Basic Cluster 0x0000 )
        #    - Endpoint list
        #        - Profile Id, Device Id, Cluster Out, Cluster In
        signature = {}
        if self._manufacturer is not None:
            signature[SIG_MANUFACTURER] = self.manufacturer
        if self._model is not None:
            signature[SIG_MODEL] = self._model
        if self.node_desc.is_valid:
            signature[SIG_NODE_DESC] = self.node_desc.as_dict()

        for endpoint_id, endpoint in self.endpoints.items():
            if endpoint_id == 0:  # ZDO
                continue
            signature.setdefault(SIG_ENDPOINTS, {})
            in_clusters = [c for c in endpoint.in_clusters]
            out_clusters = [c for c in endpoint.out_clusters]
            signature[SIG_ENDPOINTS][endpoint_id] = {
                SIG_EP_PROFILE: endpoint.profile_id,
                SIG_EP_TYPE: endpoint.device_type,
                SIG_EP_INPUT: in_clusters,
                SIG_EP_OUTPUT: out_clusters,
            }
        return signature

    def __repr__(self):
        return (
            f"<"
            f"{type(self).__name__}"
            f" model={self.model!r}"
            f" manuf={self.manufacturer!r}"
            f" nwk={NWK(self.nwk)}"
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
    broadcast_address=BroadcastAddress.RX_ON_WHEN_IDLE,
):
    result = await app.broadcast(
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
    return result
