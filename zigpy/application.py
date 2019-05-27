import asyncio
import logging

import zigpy.appdb
import zigpy.device
import zigpy.group
import zigpy.quirks
import zigpy.types as t
import zigpy.util
import zigpy.zcl
import zigpy.zdo

LOGGER = logging.getLogger(__name__)


class ControllerApplication(zigpy.util.ListenableMixin):
    def __init__(self, database_file=None):
        self._send_sequence = 0
        self.devices = {}
        self._groups = zigpy.group.Groups(self)
        self._listeners = {}
        self._ieee = None
        self._nwk = None

        if database_file is not None:
            self._dblistener = zigpy.appdb.PersistingListener(database_file, self)
            self.add_listener(self._dblistener)
            self.groups.add_listener(self._dblistener)
            self._dblistener.load()

    async def shutdown(self):
        """Perform a complete application shutdown."""
        pass

    async def startup(self, auto_form=False):
        """Perform a complete application startup"""
        raise NotImplementedError

    async def form_network(self, channel=15, pan_id=None, extended_pan_id=None):
        """Form a new network"""
        raise NotImplementedError

    def add_device(self, ieee, nwk):
        assert isinstance(ieee, t.EUI64)
        # TODO: Shut down existing device

        dev = zigpy.device.Device(self, ieee, nwk)
        self.devices[ieee] = dev
        return dev

    def device_initialized(self, device):
        """Used by a device to signal that it is initialized"""
        self.listener_event('raw_device_initialized', device)
        device = zigpy.quirks.get_device(device)
        self.devices[device.ieee] = device
        self.listener_event('device_initialized', device)

    async def remove(self, ieee):
        assert isinstance(ieee, t.EUI64)
        dev = self.devices.get(ieee)
        if not dev:
            LOGGER.debug("Device not found for removal: %s", ieee)
            return
        LOGGER.info("Removing device 0x%04x (%s)", dev.nwk, ieee)
        zdo_worked = False
        try:
            resp = await dev.zdo.leave()
            zdo_worked = resp[0] == 0
        except (zigpy.exceptions.DeliveryError, asyncio.TimeoutError) as ex:
            LOGGER.debug("Sending 'zdo_leave_req' failed: %s", ex)

        if not zdo_worked:
            await self.force_remove(dev)
        self.devices.pop(ieee, None)

        self.listener_event('device_removed', dev)

    async def force_remove(self, dev):
        raise NotImplementedError

    def deserialize(self, sender, endpoint_id, cluster_id, data):
        return sender.deserialize(endpoint_id, cluster_id, data)

    def handle_message(self, sender, is_reply, profile, cluster, src_ep, dst_ep, tsn, command_id, args):
        return sender.handle_message(is_reply, profile, cluster, src_ep, dst_ep, tsn, command_id, args)

    def handle_join(self, nwk, ieee, parent_nwk):
        LOGGER.info("Device 0x%04x (%s) joined the network", nwk, ieee)
        if ieee in self.devices:
            dev = self.get_device(ieee)
            if dev.nwk != nwk:
                LOGGER.debug("Device %s changed id (0x%04x => 0x%04x)", ieee, dev.nwk, nwk)
                dev.nwk = nwk
            elif dev.initializing or dev.status == zigpy.device.Status.ENDPOINTS_INIT:
                LOGGER.debug("Skip initialization for existing device %s", ieee)
                return
        else:
            dev = self.add_device(ieee, nwk)

        self.listener_event('device_joined', dev)
        dev.schedule_initialize()

    def handle_leave(self, nwk, ieee):
        LOGGER.info("Device 0x%04x (%s) left the network", nwk, ieee)
        dev = self.devices.get(ieee, None)
        if dev is not None:
            self.listener_event('device_left', dev)

    @zigpy.util.retryable_request
    async def request(self, nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True, timeout=10):
        raise NotImplementedError

    async def broadcast(self, profile, cluster, src_ep, dst_ep, grpid, radius,
                        sequence, data, broadcast_address):
        raise NotImplementedError

    async def permit_ncp(self, time_s=60):
        """Permit joining on NCP."""
        raise NotImplementedError

    async def permit(self, time_s=60, node=None):
        """Permit joining on a specific node or all router nodes."""
        assert 0 <= time_s <= 254
        if node is not None:
            if not isinstance(node, t.EUI64):
                node = t.EUI64([t.uint8_t(p) for p in node])
            if node != self._ieee:
                try:
                    dev = self.get_device(ieee=node)
                    r = await dev.zdo.permit(time_s)
                    LOGGER.debug("Sent 'mgmt_permit_joining_req' to %s: %s",
                                 node, r)
                except KeyError:
                    LOGGER.warning("Device '%s' not found", node)
                except zigpy.exceptions.DeliveryError as ex:
                    LOGGER.warning(
                        "Couldn't open '%s' for joining: %s", node, ex)
            else:
                await self.permit_ncp(time_s)
            return

        await zigpy.zdo.broadcast(
            self, 0x0036, 0x0000, 0x00, time_s, 0,
            broadcast_address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR
        )
        return await self.permit_ncp(time_s)

    def permit_with_key(self, node, code, time_s=60):
        raise NotImplementedError

    def get_sequence(self):
        self._send_sequence = (self._send_sequence + 1) % 256
        return self._send_sequence

    def get_device(self, ieee=None, nwk=None):
        if ieee is not None:
            return self.devices[ieee]

        for dev in self.devices.values():
            # TODO: Make this not terrible
            if dev.nwk == nwk:
                return dev

        raise KeyError

    @property
    def groups(self):
        return self._groups

    @property
    def ieee(self):
        return self._ieee

    @property
    def nwk(self):
        return self._nwk
