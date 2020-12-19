import asyncio
import binascii
import enum
import logging
import time
from typing import Dict, Optional, Union

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
    """The status of a Device"""

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
        self._init_handle = None
        self.nwk = NWK(nwk)
        self.zdo = zdo.ZDO(self)
        self.endpoints: Dict[int, Union[zdo.ZDO, zigpy.endpoint.Endpoint]] = {
            0: self.zdo
        }
        self.lqi = None
        self.rssi = None
        self.last_seen = None
        self.status = Status.NEW
        self._group_scan_handle: Optional[asyncio.Task] = None
        self._listeners = {}
        self._manufacturer = None
        self._model = None
        self.node_desc = zdo.types.NodeDescriptor()
        self.neighbors = zigpy.neighbor.Neighbors(self)
        self._node_handle = None
        self._pending = zigpy.util.Requests()
        self._relays = None
        self._skip_configuration = False

    @property
    def initializing(self) -> bool:
        """Return True if device is being initialized."""
        return bool(self._init_handle and not self._init_handle.done())

    def schedule_initialize(self):
        self.cancel_initialization()
        self._init_handle = asyncio.create_task(self._initialize())

    def cancel_initialization(self) -> None:
        """Cancel initialization call."""
        if self.initializing:
            LOGGER.debug("Canceling old initialize call")
            self._init_handle.cancel()

    def schedule_group_membership_scan(self) -> None:
        """Rescan device group's membership."""
        if self._group_scan_handle and not self._group_scan_handle.done():
            self.debug("Cancelling old group rescan")
            self._group_scan_handle.cancel()
        self._group_scan_handle = asyncio.ensure_future(self.group_membership_scan())

    async def group_membership_scan(self) -> None:
        """Sync up group membership."""
        for ep_id, ep in self.endpoints.items():
            if ep_id:
                await ep.group_membership_scan()

    async def get_node_descriptor(self):
        self.info("Requesting 'Node Descriptor'")
        try:
            status, _, node_desc = await self.zdo.Node_Desc_req(
                self.nwk, tries=2, delay=0.1
            )
            if status == zdo.types.Status.SUCCESS:
                self.node_desc = node_desc
                self.info("Node Descriptor: %s", node_desc)
                return node_desc
            else:
                self.warning("Requesting Node Descriptor failed: %s", status)
        except (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException):
            self.warning("Requesting Node Descriptor failed", exc_info=True)

    async def _initialize(self):
        if self.status == Status.NEW:
            await self.get_node_descriptor()
            self.info("Discovering endpoints")
            try:
                status, _, endpoints = await self.zdo.Active_EP_req(
                    self.nwk, tries=3, delay=0.5
                )
                if status != zdo.types.Status.SUCCESS:
                    raise zigpy.exceptions.ControllerException(
                        "Endpoint request failed: %s", status
                    )
            except (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException):
                self.warning("Failed to discover active endpoints", exc_info=True)
                return

            self.info("Discovered endpoints: %s", endpoints)

            for endpoint_id in endpoints:
                self.add_endpoint(endpoint_id)

            self.status = Status.ZDO_INIT

        for endpoint_id, ep in self.endpoints.items():
            if endpoint_id == 0:  # ZDO
                continue
            try:
                await ep.initialize()
            except Exception as exc:
                self.warning("Endpoint %s initialization failure: %s", endpoint_id, exc)
                break
            if self.manufacturer is None or self.model is None:
                self.model, self.manufacturer = await ep.get_model_info()

        ep_failed_init = [
            ep.status == zigpy.endpoint.Status.NEW
            for epid, ep in self.endpoints.items()
            if epid
        ]
        if any(ep_failed_init):
            self.application.listener_event("device_init_failure", self)
            await self.application.remove(self.ieee)
            return

        self.status = Status.ENDPOINTS_INIT
        self._application.device_initialized(self)

    def add_endpoint(self, endpoint_id):
        ep = zigpy.endpoint.Endpoint(self, endpoint_id)
        self.endpoints[endpoint_id] = ep
        return ep

    async def add_to_group(self, grp_id: int, name: str = None):
        for ep_id, ep in self.endpoints.items():
            if ep_id:
                await ep.add_to_group(grp_id, name)

    async def remove_from_group(self, grp_id: int):
        for ep_id, ep in self.endpoints.items():
            if ep_id:
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
            Union[Addressing.Group, Addressing.IEEE, Addressing.NWK]
        ] = None,
    ):
        self.last_seen = time.time()
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
