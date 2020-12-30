import functools
import logging
from typing import Coroutine, List, Optional, Union

import zigpy.types as t
import zigpy.util

from . import types

LOGGER = logging.getLogger(__name__)


class ZDO(zigpy.util.CatchingTaskMixin, zigpy.util.ListenableMixin):
    """The ZDO endpoint of a device"""

    def __init__(self, device):
        self._device = device
        self._listeners = {}

    def _serialize(self, command, *args):
        schema = types.CLUSTERS[command][1]
        data = t.serialize(args, schema)
        return data

    def deserialize(self, cluster_id, data):
        hdr, data = types.ZDOHeader.deserialize(cluster_id, data)
        try:
            cluster_details = types.CLUSTERS[cluster_id]
        except KeyError:
            self.warning("Unknown ZDO cluster 0x%04x", cluster_id)
            return hdr, data

        args, data = t.deserialize(data, cluster_details[1])
        if data != b"":
            # TODO: Seems sane to check, but what should we do?
            self.warning("Data remains after deserializing ZDO frame")

        return hdr, args

    @zigpy.util.retryable_request
    def request(self, command, *args, use_ieee=False):
        data = self._serialize(command, *args)
        tsn = self.device.application.get_sequence()
        data = t.uint8_t(tsn).serialize() + data
        return self._device.request(0, command, 0, 0, tsn, data, use_ieee=use_ieee)

    def reply(self, command, *args, tsn=None, use_ieee=False):
        data = self._serialize(command, *args)
        if tsn is None:
            tsn = self.device.application.get_sequence()
        data = t.uint8_t(tsn).serialize() + data
        return self._device.reply(0, command, 0, 0, tsn, data, use_ieee=use_ieee)

    def handle_message(
        self,
        profile: int,
        cluster: int,
        hdr: types.ZDOHeader,
        args: List,
        *,
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
    ) -> None:
        self.debug("ZDO request %s: %s", hdr.command_id, args)
        app = self._device.application
        if hdr.command_id == types.ZDOCmd.NWK_addr_req:
            if app.ieee == args[0]:
                self.create_catching_task(
                    self.NWK_addr_rsp(0, app.ieee, app.nwk, 0, 0, [], tsn=hdr.tsn)
                )
        elif hdr.command_id == types.ZDOCmd.IEEE_addr_req:
            broadcast = (0xFFFF, 0xFFFD, 0xFFFC)
            if args[0] in broadcast or app.nwk == args[0]:
                self.create_catching_task(
                    self.IEEE_addr_rsp(0, app.ieee, app.nwk, 0, 0, [], tsn=hdr.tsn)
                )
        elif hdr.command_id == types.ZDOCmd.Match_Desc_req:
            self.handle_match_desc(*args, tsn=hdr.tsn)
        elif hdr.command_id == types.ZDOCmd.Device_annce:
            self.listener_event("device_announce", self._device)
        elif hdr.command_id == types.ZDOCmd.Mgmt_Permit_Joining_req:
            self.listener_event("permit_duration", args[0])
        else:
            self.debug("Unsupported ZDO request:%s", hdr.command_id)

    def handle_match_desc(self, addr, profile, in_clusters, out_clusters, *, tsn=None):
        local_addr = self._device.application.nwk
        if profile != 260:
            self.create_catching_task(self.Match_Desc_rsp(0, local_addr, [], tsn=tsn))
            return

        self.create_catching_task(
            self.Match_Desc_rsp(0, local_addr, [t.uint8_t(1)], tsn=tsn)
        )

    def bind(self, cluster):
        return self.Bind_req(
            self._device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_id,
            self.device.application.get_dst_address(cluster),
        )

    def unbind(self, cluster):
        return self.Unbind_req(
            self._device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_id,
            self.device.application.get_dst_address(cluster),
        )

    def leave(self, remove_children: bool = True, rejoin: bool = False) -> Coroutine:
        flags = 0x00
        if remove_children:
            flags |= 0x02
        if rejoin:
            flags |= 0x01

        return self.Mgmt_Leave_req(self._device.ieee, flags)

    def permit(self, duration=60, tc_significance=0):
        return self.Mgmt_Permit_Joining_req(duration, tc_significance)

    def log(self, lvl, msg, *args, **kwargs):
        msg = "[0x%04x:zdo] " + msg
        args = (self._device.nwk,) + args
        return LOGGER.log(lvl, msg, *args, **kwargs)

    @property
    def device(self):
        return self._device

    def __getattr__(self, name):
        try:
            command = types.ZDOCmd[name]
        except KeyError:
            raise AttributeError("No such '%s' ZDO command" % (name,))

        if command & 0x8000:
            return functools.partial(self.reply, command)
        return functools.partial(self.request, command)


def broadcast(
    app,
    command,
    grpid,
    radius,
    *args,
    broadcast_address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
):
    sequence = app.get_sequence()
    data = sequence.to_bytes(1, "little")
    schema = types.CLUSTERS[command][1]
    data += t.serialize(args, schema)
    return zigpy.device.broadcast(
        app,
        0,
        command,
        0,
        0,
        grpid,
        radius,
        sequence,
        data,
        broadcast_address=broadcast_address,
    )
