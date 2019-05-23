import asyncio
import functools
import logging

import zigpy.types as t
import zigpy.util

from . import types


LOGGER = logging.getLogger(__name__)


class ZDO(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """The ZDO endpoint of a device"""
    def __init__(self, device):
        self._device = device
        self._listeners = {}

    def _serialize(self, command, *args):
        sequence = self._device.application.get_sequence()
        data = sequence.to_bytes(1, 'little')
        schema = types.CLUSTERS[command][1]
        data += t.serialize(args, schema)
        return sequence, data

    def deserialize(self, cluster_id, data):
        tsn, data = data[0], data[1:]

        is_reply = bool(cluster_id & 0x8000)
        try:
            cluster_id = types.ZDOCmd(cluster_id)
        except ValueError:
            self.warn("Unsupported ZDO cluster id 0x%04x", cluster_id)
        try:
            cluster_details = types.CLUSTERS[cluster_id]
        except KeyError:
            self.warn("Unknown ZDO cluster 0x%04x", cluster_id)
            return tsn, cluster_id, is_reply, data

        args, data = t.deserialize(data, cluster_details[1])
        if data != b'':
            # TODO: Seems sane to check, but what should we do?
            self.warn("Data remains after deserializing ZDO frame")

        return tsn, cluster_id, is_reply, args

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
            self.debug("Unexpected ZDO reply %s: %s", command_id, args)
            return

        self.debug("ZDO request %s: %s", command_id, args)
        app = self._device.application
        if command_id == types.ZDOCmd.NWK_addr_req:
            if app.ieee == args[0]:
                self.NWK_addr_rsp(0, app.ieee, app.nwk, 0, 0, [])
        elif command_id == types.ZDOCmd.IEEE_addr_req:
            broadcast = (0xffff, 0xfffd, 0xfffc)
            if args[0] in broadcast or app.nwk == args[0]:
                self.IEEE_addr_rsp(0, app.ieee, app.nwk, 0, 0, [])
        elif command_id == types.ZDOCmd.Match_Desc_req:
            self.handle_match_desc(*args)
        elif command_id == types.ZDOCmd.Device_annce:
            self.listener_event('device_announce', self._device)
        elif command_id == types.ZDOCmd.Mgmt_Permit_Joining_req:
            self.listener_event('permit_duration', args[0])
        else:
            self.warn("Unsupported ZDO request:%s", command_id)

    def handle_match_desc(self, addr, profile, in_clusters, out_clusters):
        local_addr = self._device.application.nwk
        if profile != 260:
            return self.Match_Desc_rsp(0, local_addr, [])

        return self.Match_Desc_rsp(0, local_addr, [t.uint8_t(1)])

    def bind(self, endpoint, cluster):
        dstaddr = types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self._device.application.ieee
        dstaddr.endpoint = endpoint
        return self.Bind_req(self._device.ieee, endpoint, cluster, dstaddr)

    def unbind(self, endpoint, cluster):
        dstaddr = types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self._device.application.ieee
        dstaddr.endpoint = endpoint
        return self.Unbind_req(self._device.ieee, endpoint, cluster, dstaddr)

    def leave(self):
        return self.Mgmt_Leave_req(self._device.ieee, 0x02)

    def permit(self, duration=60, tc_significance=0):
        return self.Mgmt_Permit_Joining_req(duration, tc_significance)

    def log(self, lvl, msg, *args):
        msg = '[0x%04x:zdo] ' + msg
        args = (
            self._device.nwk,
        ) + args
        return LOGGER.log(lvl, msg, *args)

    @property
    def device(self):
        return self._device

    def __getattr__(self, name):
        try:
            command = types.ZDOCmd[name]
        except KeyError:
            raise AttributeError("No such '%s' ZDO command" % (name, ))

        if command & 0x8000:
            return functools.partial(self.reply, command)
        return functools.partial(self.request, command)


def broadcast(app, command, grpid, radius, *args,
              broadcast_address=t.BroadcastAddress.RX_ON_WHEN_IDLE):
    sequence = app.get_sequence()
    data = sequence.to_bytes(1, 'little')
    schema = types.CLUSTERS[command][1]
    data += t.serialize(args, schema)
    return zigpy.device.broadcast(
        app, 0, command, 0, 0, grpid, radius, sequence, data,
        broadcast_address=broadcast_address
    )
