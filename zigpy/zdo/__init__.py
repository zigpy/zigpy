from __future__ import annotations

import functools
import logging
from typing import Coroutine

import zigpy.profiles
import zigpy.types as t
import zigpy.util

from . import types

LOGGER = logging.getLogger(__name__)


class ZDO(zigpy.util.CatchingTaskMixin, zigpy.util.ListenableMixin):
    """The ZDO endpoint of a device"""

    class LeaveOptions(t.bitmap8):
        """ZDO Mgmt_Leave_req Options."""

        NONE = 0
        RemoveChildren = 1 << 6
        Rejoin = 1 << 7

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
        args: list,
        *,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ) -> None:
        self.debug("ZDO request %s: %s", hdr.command_id, args)

        handler = getattr(self, f"handle_{hdr.command_id.name.lower()}", None)
        if handler is not None:
            handler(hdr, *args, dst_addressing=dst_addressing)
        else:
            self.debug("No handler for ZDO request:%s(%s)", hdr.command_id, args)

        self.listener_event(
            f"zdo_{hdr.command_id.name.lower()}",
            self._device,
            dst_addressing,
            hdr,
            args,
        )

    def handle_nwk_addr_req(
        self,
        hdr: types.ZDOHeader,
        ieee: t.EUI64,
        request_type: int,
        start_index: int | None = None,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ):
        """Handle ZDO NWK Address request."""

        app = self._device.application
        if ieee == app.ieee:
            self.create_catching_task(
                self.NWK_addr_rsp(0, app.ieee, app.nwk, 0, 0, [], tsn=hdr.tsn)
            )

    def handle_ieee_addr_req(
        self,
        hdr: types.ZDOHeader,
        nwk: t.NWK,
        request_type: int,
        start_index: int | None = None,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ):
        """Handle ZDO IEEE Address request."""

        app = self._device.application
        if nwk in (0xFFFF, 0xFFFD, 0xFFFC, app.nwk):
            self.create_catching_task(
                self.IEEE_addr_rsp(0, app.ieee, app.nwk, 0, 0, [], tsn=hdr.tsn)
            )

    def handle_device_annce(
        self,
        hdr: types.ZDOHeader,
        nwk: t.NWK,
        ieee: t.EUI64,
        capability: int,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ):
        """Handle ZDO device announcement request."""
        self.listener_event("device_announce", self._device)

    def handle_mgmt_permit_joining_req(
        self,
        hdr: types.ZDOHeader,
        permit_duration: int,
        tc_significance: int,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ):
        """Handle ZDO permit joining request."""

        self.listener_event("permit_duration", permit_duration)

    def handle_match_desc_req(
        self,
        hdr: types.ZDOHeader,
        addr: t.NWK,
        profile: int,
        in_clusters: list,
        out_cluster: list,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ):
        """Handle ZDO Match_desc_req request."""

        local_addr = self._device.application.nwk
        if profile != zigpy.profiles.zha.PROFILE_ID:
            self.create_catching_task(
                self.Match_Desc_rsp(0, local_addr, [], tsn=hdr.tsn)
            )
            return

        self.create_catching_task(
            self.Match_Desc_rsp(0, local_addr, [t.uint8_t(1)], tsn=hdr.tsn)
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
        opts = self.LeaveOptions.NONE
        if remove_children:
            opts |= self.LeaveOptions.RemoveChildren
        if rejoin:
            opts |= self.LeaveOptions.Rejoin

        return self.Mgmt_Leave_req(self._device.ieee, opts)

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
            raise AttributeError(f"No such '{name}' ZDO command")

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
