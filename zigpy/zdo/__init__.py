from __future__ import annotations

from collections.abc import Coroutine
import functools
import logging

from zigpy.const import APS_REPLY_TIMEOUT
import zigpy.profiles
import zigpy.types as t
from zigpy.typing import AddressingMode
import zigpy.util

from . import types

LOGGER = logging.getLogger(__name__)

ZDO_ENDPOINT = 0


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

    def _serialize(self, command, *args, **kwargs):
        keys, schema = types.CLUSTERS[command]
        # TODO: expose this in a future PR
        assert not kwargs
        return t.serialize(args, schema)

    def deserialize(self, cluster_id, data):
        if cluster_id not in types.CLUSTERS:
            raise ValueError(f"Invalid ZDO cluster ID: 0x{cluster_id:04X}")

        _, param_types = types.CLUSTERS[cluster_id]
        hdr, data = types.ZDOHeader.deserialize(cluster_id, data)
        args, data = t.deserialize(data, param_types)

        if data:
            # TODO: Seems sane to check, but what should we do?
            self.warning("Data remains after deserializing ZDO frame: %r", data)

        return hdr, args

    async def request(
        self,
        command,
        *args,
        timeout=APS_REPLY_TIMEOUT,
        expect_reply: bool = True,
        use_ieee: bool = False,
        ask_for_ack: bool | None = None,
        priority: int = t.PacketPriority.NORMAL,
        **kwargs,
    ):
        data = self._serialize(command, *args, **kwargs)
        tsn = self.device.get_sequence()
        return await self._device.request(
            profile=0x0000,
            cluster=command,
            src_ep=ZDO_ENDPOINT,
            dst_ep=ZDO_ENDPOINT,
            sequence=tsn,
            data=t.uint8_t(tsn).serialize() + data,
            timeout=timeout,
            expect_reply=expect_reply,
            use_ieee=use_ieee,
            ask_for_ack=ask_for_ack,
            priority=priority,
        )

    async def reply(
        self,
        command,
        *args,
        tsn: int | t.uint8_t | None = None,
        timeout=APS_REPLY_TIMEOUT,
        expect_reply: bool = False,
        use_ieee: bool = False,
        ask_for_ack: bool | None = None,
        priority: int = t.PacketPriority.NORMAL,
        **kwargs,
    ):
        data = self._serialize(command, *args, **kwargs)
        if tsn is None:
            tsn = self.device.get_sequence()
        return await self._device.reply(
            profile=0x0000,
            cluster=command,
            src_ep=ZDO_ENDPOINT,
            dst_ep=ZDO_ENDPOINT,
            sequence=tsn,
            data=t.uint8_t(tsn).serialize() + data,
            timeout=timeout,
            expect_reply=expect_reply,
            use_ieee=use_ieee,
            ask_for_ack=ask_for_ack,
            priority=priority,
        )

    def handle_message(
        self,
        profile: int,
        cluster: int,
        hdr: types.ZDOHeader,
        args: list,
        *,
        dst_addressing: AddressingMode | None = None,
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
        dst_addressing: AddressingMode | None = None,
    ):
        """Handle ZDO NWK Address request."""

        app = self._device.application
        if ieee == app.state.node_info.ieee:
            self.create_catching_task(
                self.NWK_addr_rsp(
                    0,
                    app.state.node_info.ieee,
                    app.state.node_info.nwk,
                    0,
                    0,
                    [],
                    tsn=hdr.tsn,
                    priority=t.PacketPriority.LOW,
                )
            )

    def handle_ieee_addr_req(
        self,
        hdr: types.ZDOHeader,
        nwk: t.NWK,
        request_type: int,
        start_index: int | None = None,
        dst_addressing: AddressingMode | None = None,
    ):
        """Handle ZDO IEEE Address request."""

        app = self._device.application
        if nwk in (
            t.BroadcastAddress.ALL_DEVICES,
            t.BroadcastAddress.RX_ON_WHEN_IDLE,
            t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
            app.state.node_info.nwk,
        ):
            self.create_catching_task(
                self.IEEE_addr_rsp(
                    0,
                    app.state.node_info.ieee,
                    app.state.node_info.nwk,
                    0,
                    0,
                    [],
                    tsn=hdr.tsn,
                    priority=t.PacketPriority.LOW,
                )
            )

    def handle_device_annce(
        self,
        hdr: types.ZDOHeader,
        nwk: t.NWK,
        ieee: t.EUI64,
        capability: int,
        dst_addressing: AddressingMode | None = None,
    ):
        """Handle ZDO device announcement request."""
        self.listener_event("device_announce", self._device)

    def handle_mgmt_permit_joining_req(
        self,
        hdr: types.ZDOHeader,
        permit_duration: int,
        tc_significance: int,
        dst_addressing: AddressingMode | None = None,
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
        dst_addressing: AddressingMode | None = None,
    ):
        """Handle ZDO Match_desc_req request."""

        local_addr = self._device.application.state.node_info.nwk
        if profile != zigpy.profiles.zha.PROFILE_ID:
            self.create_catching_task(
                self.Match_Desc_rsp(
                    0,
                    local_addr,
                    [],
                    tsn=hdr.tsn,
                    priority=t.PacketPriority.HIGH,
                )
            )
            return

        self.create_catching_task(
            self.Match_Desc_rsp(
                0,
                local_addr,
                [t.uint8_t(1)],
                tsn=hdr.tsn,
                priority=t.PacketPriority.HIGH,
            )
        )

    async def bind(self, cluster):
        return await self.Bind_req(
            self._device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_id,
            self.device.application.get_dst_address(cluster),
        )

    async def unbind(self, cluster):
        return await self.Unbind_req(
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
        args = (self._device.nwk, *args)
        return LOGGER.log(lvl, msg, *args, **kwargs)

    @property
    def device(self):
        return self._device

    def __getattr__(self, name):
        try:
            command = types.ZDOCmd[name]
        except KeyError as exc:
            raise AttributeError(f"No such '{name}' ZDO command") from exc

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
    **kwargs,
):
    params, param_types = types.CLUSTERS[command]

    named_args = dict(zip(params, args))
    named_args.update(kwargs)
    assert set(named_args.keys()) & set(params)

    sequence = app.get_sequence()
    data = bytes([sequence]) + t.serialize(named_args.values(), param_types)

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
