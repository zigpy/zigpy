import logging

import zigpy.appdb
import zigpy.device
import zigpy.types as t
import zigpy.util
import zigpy.zcl
import zigpy.zdo
import asyncio

LOGGER = logging.getLogger(__name__)


class ControllerApplication(zigpy.util.ListenableMixin):
    def __init__(self, database_file=None):
        self._send_sequence = 0
        self.devices = {}
        self.nwk2devices = dict()
        self._listeners = {}
        self._ieee = None
        self._nwk = None

        if database_file is not None:
            self._dblistener = zigpy.appdb.PersistingListener(database_file, self)
            self.add_listener(self._dblistener)
            self._dblistener.load()

        asyncio.ensure_future(self.run_topology())

    async def startup(self, auto_form=False):
        """Perform a complete application startup."""
        raise NotImplementedError

    async def form_network(self, channel=15, pan_id=None, extended_pan_id=None):
        """Form a new network."""
        raise NotImplementedError

    def add_device(self, ieee, nwk):
        assert isinstance(ieee, t.EUI64)
        # TODO: Shut down existing device

        dev = zigpy.device.Device(self, ieee, nwk)
        self.devices[ieee] = dev
        self.nwk2devices[nwk] = dev
        return dev

    def device_initialized(self, device):
        """Used by a device to signal that it is initialized."""
        self.listener_event('device_initialized', device)

    async def remove(self, ieee):
        LOGGER.debug("length devices before removal: %s", len(self.devices))
        assert isinstance(ieee, t.EUI64)
        dev = self.devices.pop(ieee, None)
        if not dev:
            LOGGER.debug("Device not found for removal: %s", ieee)
            return
        LOGGER.info("Removing device 0x%04x (%s)", dev.nwk, ieee)
        self.nwk2devices.pop(dev.nwk, None)
        dev.cleanup()
        LOGGER.debug("length devices after removal: %s", len(self.devices))

        zdo_worked = False
        try:
            resp = await dev.zdo.leave()
            zdo_worked = resp[0] == 0
        except Exception as exc:
            pass

        if not zdo_worked:
            await self.force_remove(dev)

        self.listener_event('device_removed', dev)

    async def force_remove(self, dev):
        raise NotImplementedError

    def deserialize(self, sender, endpoint_id, cluster_id, data):
        return sender.deserialize(endpoint_id, cluster_id, data)

    def handle_message(self, sender, is_reply, profile, cluster, src_ep, dst_ep, tsn, command_id, args):
        return sender.handle_message(is_reply, profile, cluster, src_ep, dst_ep, tsn, command_id, args)

    def handle_RouteRecord(self, sender, record):
        record.insert(0, sender)
        sender = record[-1]
        path = record[0:-1]
        if path == []:
            path = "direct*"
        try:
            device = self.get_device(nwk=sender)
        except KeyError:
            LOGGER.debug("No such device %s", sender)
            return
        device.handle_RouteRecord(path)

    def handle_join(self, nwk, ieee, parent):
        LOGGER.info("Device 0x%04x (%s) joined the network via %s", nwk, ieee, parent)
        if ieee in self.devices:
            dev = self.get_device(ieee)
            if dev.nwk != nwk:
                LOGGER.debug("Device %s changed id (0x%04x => 0x%04x)", ieee, dev.nwk, nwk)
                self.nwk2devices.pop(dev.nwk, None)
                self.nwk2devices[nwk] = dev
                dev.nwk = nwk 
#            elif dev.initializing or dev.status == zigpy.device.Status.ENDPOINTS_INIT:
            elif dev.status == zigpy.device.Status.ENDPOINTS_INIT:
                LOGGER.debug("Skip initialization for existing device %s", ieee)
                return
        else:
            dev = self.add_device(ieee, nwk)
            dev.path = parent

        self.listener_event('device_joined', dev)
        dev.schedule_initialize()

    def handle_leave(self, nwk, ieee):
        LOGGER.info("Device 0x%04x (%s) left the network", nwk, ieee)
        dev = self.devices.get(ieee, None)
        if dev is not None:
            self.listener_event('device_left', dev)
            if dev.initializing:
                dev._init_handle.cancel()

    @zigpy.util.retryable_request
    async def request(self, nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True, timeout=10):
        raise NotImplementedError

    def permit(self, time_s=60):
        raise NotImplementedError

    def permit_with_key(self, node, code, time_s=60):
        raise NotImplementedError

    def get_sequence(self):
        while True:
            self._send_sequence = (self._send_sequence + 1) % 256
            if self._send_sequence not in self._pending:
                break
        return self._send_sequence

    def get_device(self, ieee=None, nwk=None):
        if ieee is not None:
            return self.devices[ieee]
        if nwk is not None:
            return self.nwk2devices[nwk]
        raise KeyError

    @property
    def ieee(self):
        return self._ieee

    @property
    def nwk(self):
        return self._nwk

    async def subscribe_group(self, group_id):
        raise NotImplementedError

    async def unsubscribe_group(self, group_id):
        raise NotImplementedError

    async def run_topology(self, wakemeup=300):
        while True:
            await asyncio.sleep(wakemeup)
            await self.update_topology()

    async def update_topology(self):
        """ gather information for topology and write it to zigbee.db."""
        result = await self.read_neighbor_table()
        LOGGER.debug("neighbors: %s", result)
        for index in self._neighbor_table["index"]:
            neighbor = self._neighbor_table[index]
            self._dblistener.write_topology(
                                     src=neighbor.shortId,
                                     dst=0,
                                     lqi=neighbor.averageLqi,
                                     cost=neighbor.inCost)
            self._dblistener.write_topology(src=0, dst=neighbor.shortId, cost=neighbor.outCost)

            device = self.get_device(nwk=index)
            try:
                result = await device.zdo.get_Mgmt_Lqi()
            except:
                continue
            for neighbor in result:
                if not neighbor.NeighborType[2] == 4:
                    self._dblistener.write_topology(src=neighbor.NWKAddr, dst=index, lqi=neighbor.LQI, depth=neighbor.Depth)
        LOGGER.debug("Topology updated")

#        await device.zdo.get_Mgmt_Rtg()
#        await asyncio.wait_for(self.read_child_table(),15)
#        await self.read_route_table()
 
