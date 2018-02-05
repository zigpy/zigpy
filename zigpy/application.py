import asyncio
import logging

import zigpy.appdb
import zigpy.device
import zigpy.types as t
import zigpy.util
import zigpy.zcl
import zigpy.zdo

LOGGER = logging.getLogger(__name__)


class ControllerApplication(zigpy.util.ListenableMixin):
    def __init__(self, database_file=None):
        self._send_sequence = 0
        self.devices = {}
        self._listeners = {}
        self._ieee = None
        self._nwk = None

        if database_file is not None:
            self._dblistener = zigpy.appdb.PersistingListener(database_file, self)
            self.add_listener(self._dblistener)
            self._dblistener.load()

    @asyncio.coroutine
    def startup(self, auto_form=False):
        """Perform a complete application startup"""
        raise NotImplementedError

    @asyncio.coroutine
    def form_network(self, channel=15, pan_id=None, extended_pan_id=None):
        """Form a new network"""
        raise NotImplementedError

    def add_device(self, ieee, nwk):
        assert isinstance(ieee, t.EUI64)
        # TODO: Shut down existing device

        dev = zigpy.device.Device(self, ieee, nwk)
        self.devices[ieee] = dev
        return dev

    @asyncio.coroutine
    def remove(self, ieee):
        assert isinstance(ieee, t.EUI64)
        dev = self.devices.pop(ieee, None)
        if not dev:
            LOGGER.debug("Device not found for removal: %s", ieee)
            return
        LOGGER.info("Removing device 0x%04x (%s)", dev.nwk, ieee)
        zdo_worked = False
        try:
            resp = yield from dev.zdo.leave()
            zdo_worked = resp[0] == 0
        except Exception as exc:
            pass

        if not zdo_worked:
            yield from self.force_remove(dev)

        self.listener_event('device_removed', dev)

    @asyncio.coroutine
    def force_remove(self, dev):
        raise NotImplementedError

    def handle_message(self, is_reply, sender, profile, cluster, src_ep, dst_ep, tsn, command_id, args):
        try:
            device = self.get_device(nwk=sender)
        except KeyError:
            LOGGER.warning("Message on unknown device 0x%04x", sender)
            return

        return device.handle_message(is_reply, profile, cluster, src_ep, dst_ep, tsn, command_id, args)

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
    @asyncio.coroutine
    def request(self, nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True, timeout=10):
        raise NotImplementedError

    def permit(self, time_s=60):
        raise NotImplementedError

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
    def ieee(self):
        return self._ieee

    @property
    def nwk(self):
        return self._nwk
