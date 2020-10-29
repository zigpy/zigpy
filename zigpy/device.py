import asyncio
import binascii
import enum
import logging
import time
from typing import Dict, Optional, Union

import zigpy.endpoint
import zigpy.exceptions
import zigpy.neighbor
from zigpy.types import NWK, BroadcastAddress, Relays
import zigpy.util
import zigpy.zcl.clusters as clusters
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
        self.initializing = False
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
        self._direct_initialization = False

    def schedule_initialize(self):
        if self.initializing:
            LOGGER.debug("Canceling old initialize call")
            self._init_handle.cancel()
        else:
            self.initializing = True
        self._init_handle = asyncio.ensure_future(self._initialize())

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
                self.nwk, tries=2, delay=1
            )
            if status == zdo.types.Status.SUCCESS:
                self.node_desc = node_desc
                self.info("Node Descriptor: %s", node_desc)
                return node_desc
            else:
                self.warning("Requesting Node Descriptor failed: %s", status)
        except Exception:
            self.warning("Requesting Node Descriptor failed", exc_info=True)

    async def refresh_node_descriptor(self):
        if await self.get_node_descriptor():
            self._application.listener_event("node_descriptor_updated", self)

    async def _initialize(self):
        if self.status == Status.NEW:
            if self._node_handle is None or self._node_handle.done():
                self._node_handle = asyncio.ensure_future(self.get_node_descriptor())
            await self._node_handle

        if self.status != Status.ENDPOINTS_INIT:
            await self._initialize_from_interview()

    async def _initialize_from_interview(self):
        LOGGER.info("Init with full interview")
        if self.status == Status.NEW:
            await asyncio.ensure_future(self.get_node_descriptor())
            self.info("Discovering endpoints")
            try:
                epr = await self.zdo.Active_EP_req(self.nwk, tries=3, delay=2)
                if epr[0] != 0:
                    raise Exception("Endpoint request failed: %s", epr)
            except Exception:
                self.initializing = False
                self.warning("Failed to discover active endpoints", exc_info=True)
                return

            self.info("Discovered endpoints: %s", epr[2])

            for endpoint_id in epr[2]:
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
            self.initializing = False
            self.application.listener_event("device_init_failure", self)
            await self.application.remove(self.ieee)
            return

        self._finish_init()

    async def _initialize_from_quirk(self, quirk):
        signature = quirk.signature
        LOGGER.info("Init from quirk. Signature: %s", signature)

        if "node_desc" in quirk.signature:
            self.node_desc = quirk.signature["node_desc"]
        elif "node_desc" in quirk.replacement:
            self.node_desc = quirk.replacement["node_desc"]

        if not self.node_desc.is_valid:
            await asyncio.ensure_future(self.get_node_descriptor())

        model_info = signature["models_info"][0]
        self.manufacturer = model_info[0]
        self.model = model_info[1]
        for endpoint_id, endpoint in signature["endpoints"].items():
            ep = self.add_endpoint(endpoint_id)
            ep.model = self.model
            ep.manufacturer = self.manufacturer
            ep.initialize_from_quirk(endpoint)
        self.status = Status.ZDO_INIT
        self._finish_init()

    def _finish_init(self):
        self.status = Status.ENDPOINTS_INIT
        self.initializing = False
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

    def handle_message(self, profile, cluster, src_ep, dst_ep, message):
        self.last_seen = time.time()

        if (
            self.status == Status.NEW
            and src_ep == 1
            and cluster == 0
            and src_ep not in self.endpoints
        ):
            LOGGER.debug("Handling special identification message")
            ep = self.add_endpoint(1)
            ep.profile_id = 260  # is this neded?
            ep.status = Status.ZDO_INIT  # needed?
            cl = ep.add_input_cluster(0)
            cl.add_listener(InitBasicClusterListener(self))

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
        return endpoint.handle_message(profile, cluster, hdr, args)

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

    @property
    def direct_initialization(self):
        return self._direct_initialization

    @direct_initialization.setter
    def direct_initialization(self, should_do_direct_initialization):
        if isinstance(should_do_direct_initialization, bool):
            self._direct_initialization = should_do_direct_initialization
        else:
            self._direct_initialization = False

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
        #    - Model Identifier ( Attribut 0x0005 of Basic Cluster 0x0000 )
        #    - Manufacturer Name ( Attribut 0x0004 of Basic Cluster 0x0000 )
        #    - Endpoint list
        #        - Profile Id, Device Id, Cluster Out, Cluster In
        signature = {}
        if self._manufacturer is not None:
            signature["manufacturer_name"] = self.manufacturer
        if self._model is not None:
            signature["model"] = self._model
        if self.node_desc.is_valid:
            signature["node_descriptor"] = self.node_desc.as_dict()

        for endpoint_id, endpoint in self.endpoints.items():
            if endpoint_id == 0:  # ZDO
                continue
            in_clusters = [c for c in endpoint.in_clusters]
            out_clusters = [c for c in endpoint.out_clusters]
            signature[endpoint_id] = {
                "profileid": endpoint.profile_id,
                "deviceid": endpoint.device_type,
                "in_clusters": in_clusters,
                "out_clusters": out_clusters,
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


class InitBasicClusterListener:
    def __init__(self, device: Device):
        self._device = device
        self._model = None
        self._init_started = False

    def attribute_updated(self, attrid, value):
        if self._init_started:
            return

        if attrid != clusters.general.Basic.attridx["model"]:
            return
        self._model = value

        if not self._model:
            return

        LOGGER.debug(
            "We have a model: %s",
            self._model,
        )

        self._init_started = True
        quirk = self._get_quirk()

        if (
            quirk
            and "direct_initialization" in quirk.signature
            and quirk.signature["direct_initialization"]
        ):
            asyncio.ensure_future(self._device._initialize_from_quirk(quirk))

    def cluster_command(self, *args, **kwargs):
        pass

    def general_command(self, *args, **kwargs):
        pass

    def _get_quirk(self):
        candidates = self._device.application.quirks.get_device_metadata(self._model)
        if not candidates:
            return None
        if not candidates[0]:
            return None

        device_metadata = candidates[0]
        LOGGER.debug("Found signature for init: %s", device_metadata.signature)
        return device_metadata
