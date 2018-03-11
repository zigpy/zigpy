import asyncio
import logging

import zigpy.types as t
import zigpy.util

from . import types


LOGGER = logging.getLogger(__name__)


def deserialize(cluster_id, data):
    tsn, data = data[0], data[1:]

    is_reply = bool(cluster_id & 0x8000)
    try:
        cluster_details = types.CLUSTERS[cluster_id]
    except KeyError:
        LOGGER.warning("Unknown ZDO cluster 0x%02x", cluster_id)
        return tsn, cluster_id, is_reply, data

    args, data = t.deserialize(data, cluster_details[2])
    if data != b'':
        # TODO: Seems sane to check, but what should we do?
        LOGGER.warning("Data remains after deserializing ZDO frame")

    return tsn, cluster_id, is_reply, args


class ZDO(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """The ZDO endpoint of a device"""
    def __init__(self, device):
        self._device = device
        self._listeners = {}

    def _serialize(self, command, *args):
        sequence = self._device.application.get_sequence()
        data = sequence.to_bytes(1, 'little')
        schema = types.CLUSTERS[command][2]
        data += t.serialize(args, schema)
        return sequence, data

    @zigpy.util.retryable_request
    def request(self, command, *args):
        sequence, data = self._serialize(command, *args)
        return self._device.request(0, command, 0, 0, sequence, data)

    def reply(self, command, *args):
        sequence, data = self._serialize(command, *args)
        loop = asyncio.get_event_loop()
        loop.create_task(self._device.reply(0, command, 0, 0, sequence, data))

    def handle_message(self, is_reply, profile, cluster, tsn, command_id, args):
        if is_reply:
            self.debug("Unexpected ZDO reply 0x%04x: %s", command_id, args)
            return

        self.debug("ZDO request 0x%04x: %s", command_id, args)
        app = self._device.application
        if command_id == 0x0000:  # NWK_addr_req
            if app.ieee == args[0]:
                self.reply(0x8000, 0, app.ieee, app.nwk, 0, 0, [])
        elif command_id == 0x0001:  # IEEE_addr_req
            broadcast = (0xffff, 0xfffd, 0xfffc)
            if args[0] in broadcast or app.nwk == args[0]:
                self.reply(0x8001, 0, app.ieee, app.nwk, 0, 0, [])
        elif command_id == 0x0006:  # Match_Desc_req
            self.handle_match_desc(*args)
        elif command_id == 0x0013:  # Device_annce
            self.listener_event('device_announce', self._device)
        elif command_id == 0x0036:  # Mgmt_Permit_Joining_req
            self.listener_event('permit_duration', args[0])
        else:
            self.warn("Unsupported ZDO request 0x%04x", command_id)

    def handle_match_desc(self, addr, profile, in_clusters, out_clusters):
        local_addr = self._device.application.nwk
        if profile == 260:
            response = (0x8006, 0, local_addr, [t.uint8_t(1)])
        else:
            response = (0x8006, 0, local_addr, [])

        self.reply(*response)

    def bind(self, endpoint, cluster):
        dstaddr = types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self._device.application.ieee
        dstaddr.endpoint = endpoint
        return self.request(0x0021, self._device.ieee, endpoint, cluster, dstaddr)

    def unbind(self, endpoint, cluster):
        dstaddr = types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self._device.application.ieee
        dstaddr.endpoint = endpoint
        return self.request(0x0022, self._device.ieee, endpoint, cluster, dstaddr)

    def leave(self):
        dstaddr = types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self._device.application.ieee
        dstaddr.endpoint = 1
        return self.request(0x0034, self._device.ieee, 0x02, dstaddr)

    def log(self, lvl, msg, *args):
        msg = '[0x%04x:zdo] ' + msg
        args = (
            self._device.nwk,
        ) + args
        return LOGGER.log(lvl, msg, *args)

    @property
    def device(self):
        return self._device
