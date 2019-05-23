import asyncio
import enum
import logging
import time

import zigpy.endpoint
import zigpy.util
import zigpy.zdo as zdo
from zigpy.types import BroadcastAddress


LOGGER = logging.getLogger(__name__)


class Status(enum.IntEnum):
    """The status of a Device"""
    # No initialization done
    NEW = 0
    # ZDO endpoint discovery done
    ZDO_INIT = 1
    # Endpoints initialized
    ENDPOINTS_INIT = 2


class Device(zigpy.util.LocalLogMixin):
    """A device on the network"""

    def __init__(self, application, ieee, nwk):
        self._application = application
        self._ieee = ieee
        self._init_handle = None
        self.nwk = nwk
        self.zdo = zdo.ZDO(self)
        self.endpoints = {0: self.zdo}
        self.lqi = None
        self.rssi = None
        self.last_seen = None
        self.status = Status.NEW
        self.initializing = False
        self.node_desc = zdo.types.NodeDescriptor()
        self._node_handle = None

    def schedule_initialize(self):
        if self.initializing:
            LOGGER.debug("Canceling old initialize call")
            self._init_handle.cancel()
        else:
            self.initializing = True
        self._init_handle = asyncio.ensure_future(self._initialize())

    async def get_node_descriptor(self):
        self.info("Requesting 'Node Descriptor'")
        try:
            status, _, node_desc = await self.zdo.Node_Desc_req(self.nwk,
                                                                tries=2,
                                                                delay=1)
            if status == zdo.types.Status.SUCCESS:
                self.node_desc = node_desc
                self.info("Node Descriptor: %s", node_desc)
                return node_desc
            else:
                self.warn("Requesting Node Descriptor failed: %s", status)
        except Exception as exc:
            self.warn("Requesting Node Descriptor failed: %s", exc)

    async def refresh_node_descriptor(self):
        if await self.get_node_descriptor():
            self._application.listener_event('node_descriptor_updated', self)

    async def _initialize(self):
        if self.status == Status.NEW:
            self._node_handle = asyncio.ensure_future(
                self.get_node_descriptor())
            await self._node_handle
            self.info("Discovering endpoints")
            try:
                epr = await self.zdo.Active_EP_req(self.nwk, tries=3, delay=2)
                if epr[0] != 0:
                    raise Exception("Endpoint request failed: %s", epr)
            except Exception as exc:
                self.initializing = False
                LOGGER.exception("Failed ZDO request during device initialization: %s", exc)
                return

            self.info("Discovered endpoints: %s", epr[2])

            for endpoint_id in epr[2]:
                self.add_endpoint(endpoint_id)

            self.status = Status.ZDO_INIT

        for endpoint_id in self.endpoints.keys():
            if endpoint_id == 0:  # ZDO
                continue
            try:
                await self.endpoints[endpoint_id].initialize()
            except Exception as exc:
                self.debug("Endpoint %s initialization failure: %s",
                           endpoint_id, exc)
                break

        ep_failed_init = [
            ep.status == zigpy.endpoint.Status.NEW
            for epid, ep in self.endpoints.items() if epid
        ]
        if any(ep_failed_init):
            self.initializing = False
            self.application.listener_event('device_init_failure', self)
            await self.application.remove(self.ieee)
            return

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

    async def request(self, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True):
        result = await self._application.request(
            self.nwk,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=expect_reply,
        )
        # If application.request raises an exception, we won't get here, so
        # won't update last_seen, as expected
        self.last_seen = time.time()
        return result

    def deserialize(self, endpoint_id, cluster_id, data):
        return self.endpoints[endpoint_id].deserialize(cluster_id, data)

    def handle_message(self, is_reply, profile, cluster, src_ep, dst_ep, tsn, command_id, args):
        self.last_seen = time.time()
        if not self.node_desc.is_valid and \
                (self._node_handle is None or self._node_handle.done()):
            self._node_handle = asyncio.ensure_future(
                self.refresh_node_descriptor())
        try:
            endpoint = self.endpoints[src_ep]
        except KeyError:
            self.warn(
                "Message on unknown endpoint %s",
                src_ep,
            )
            return

        return endpoint.handle_message(is_reply, profile, cluster, tsn, command_id, args)

    def reply(self, profile, cluster, src_ep, dst_ep, sequence, data):
        return self._application.request(self.nwk, profile, cluster, src_ep, dst_ep, sequence, data, False)

    def radio_details(self, lqi, rssi):
        self.lqi = lqi
        self.rssi = rssi

    def log(self, lvl, msg, *args):
        msg = '[0x%04x] ' + msg
        args = (self.nwk, ) + args
        return LOGGER.log(lvl, msg, *args)

    @property
    def application(self):
        return self._application

    @property
    def ieee(self):
        return self._ieee

    def __getitem__(self, key):
        return self.endpoints[key]

    def get_signature(self):
        signature = {}
        for endpoint_id, endpoint in self.endpoints.items():
            if endpoint_id == 0:  # ZDO
                continue
            in_clusters = [c for c in endpoint.in_clusters]
            out_clusters = [c for c in endpoint.out_clusters]
            signature[endpoint_id] = {
                'in_clusters': in_clusters,
                'out_clusters': out_clusters
            }
        return signature


async def broadcast(app, profile, cluster, src_ep, dst_ep, grpid, radius,
                    sequence, data,
                    broadcast_address=BroadcastAddress.RX_ON_WHEN_IDLE):
    result = await app.broadcast(
        profile, cluster, src_ep, dst_ep, grpid, radius, sequence, data,
        broadcast_address=broadcast_address
    )
    return result
