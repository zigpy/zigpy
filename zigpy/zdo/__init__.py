from __future__ import annotations

import logging

import zigpy.profiles
import zigpy.types as t
import zigpy.util

from . import commands, types

LOGGER = logging.getLogger(__name__)

ZDO_ENDPOINT = 0


class ZDO(zigpy.util.CatchingTaskMixin, zigpy.util.ListenableMixin):
    """The ZDO endpoint of a device"""

    def __init__(self, device):
        self._device = device
        self._listeners = {}

    def handle_message(
        self,
        profile: int,
        cluster: int,
        hdr: types.ZDOHeader,
        command: commands.ZDOCommand,
    ) -> None:
        self.debug("ZDO request %s: %s", hdr.command_id, command)

        handler = getattr(self, f"handle_{hdr.command_id.name.lower()}", None)
        if handler is not None:
            handler(hdr, command)
        else:
            self.debug("No handler for ZDO request:%s(%s)", hdr.command_id, command)

        self.listener_event(
            f"zdo_{hdr.command_id.name.lower()}",
            self._device,
            None,  # was `dst_addressing` but this was never set
            hdr,
            command,
        )

    def handle_nwk_addr_req(
        self, hdr: types.ZDOHeader, command: commands.NwkAddrReq
    ) -> None:
        """Handle ZDO NWK Address request."""

        app = self._device.application
        if command.ieee_addr == app.state.node_info.ieee:
            self.create_catching_task(
                self._device.send_zdo_command(
                    commands.NwkAddrRsp(
                        status=types.Status.SUCCESS,
                        ieee_addr=app.state.node_info.ieee,
                        nwk_addr=app.state.node_info.nwk,
                        num_assoc_dev=(
                            0
                            if command.request_type == types.AddrRequestType.Extended
                            else None
                        ),
                    ),
                    tsn=hdr.tsn,
                    priority=t.PacketPriority.LOW,
                    retries=self._device.reply_retries,
                )
            )

    def handle_ieee_addr_req(
        self, hdr: types.ZDOHeader, command: commands.IeeeAddrReq
    ) -> None:
        """Handle ZDO IEEE Address request."""

        app = self._device.application
        if command.nwk_addr_of_interest in (
            t.BroadcastAddress.ALL_DEVICES,
            t.BroadcastAddress.RX_ON_WHEN_IDLE,
            t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
            app.state.node_info.nwk,
        ):
            self.create_catching_task(
                self._device.send_zdo_command(
                    commands.IeeeAddrRsp(
                        status=types.Status.SUCCESS,
                        ieee_addr=app.state.node_info.ieee,
                        nwk_addr=app.state.node_info.nwk,
                        num_assoc_dev=(
                            0
                            if command.request_type == types.AddrRequestType.Extended
                            else None
                        ),
                    ),
                    tsn=hdr.tsn,
                    priority=t.PacketPriority.LOW,
                    retries=self._device.reply_retries,
                )
            )

    def handle_device_annce(
        self, hdr: types.ZDOHeader, command: commands.DeviceAnnce
    ) -> None:
        """Handle ZDO device announcement request."""
        self.listener_event("device_announce", self._device)

    def handle_mgmt_permit_joining_req(
        self, hdr: types.ZDOHeader, command: commands.MgmtPermitJoiningReq
    ) -> None:
        """Handle ZDO permit joining request."""

        self.listener_event("permit_duration", command.permit_duration)

    def handle_match_desc_req(
        self, hdr: types.ZDOHeader, command: commands.MatchDescReq
    ) -> None:
        """Handle ZDO Match_desc_req request."""

        if command.profile_id == zigpy.profiles.zha.PROFILE_ID:
            match_list = [t.uint8_t(1)]
        else:
            match_list = []

        self.create_catching_task(
            self._device.send_zdo_command(
                commands.MatchDescRsp(
                    status=types.Status.SUCCESS,
                    nwk_addr_of_interest=self._device.application.state.node_info.nwk,
                    match_list=match_list,
                ),
                tsn=hdr.tsn,
                priority=t.PacketPriority.CRITICAL,
            )
        )

    async def bind(self, cluster, **kwargs) -> commands.BindRsp:
        return await self._device.send_zdo_command(
            commands.BindReq(
                src_address=self._device.ieee,
                src_endpoint=cluster.endpoint.endpoint_id,
                cluster_id=cluster.cluster_id,
                dst_address=self._device.application.get_dst_address(cluster),
            ),
            response_type=commands.BindRsp,
            **kwargs,
        )

    async def unbind(self, cluster) -> commands.UnbindRsp:
        return await self._device.send_zdo_command(
            commands.UnbindReq(
                src_address=self._device.ieee,
                src_endpoint=cluster.endpoint.endpoint_id,
                cluster_id=cluster.cluster_id,
                dst_address=self._device.application.get_dst_address(cluster),
            ),
            response_type=commands.UnbindRsp,
        )

    async def leave(
        self, remove_children: bool = True, rejoin: bool = False
    ) -> commands.MgmtLeaveRsp:
        opts = commands.LeaveOptions.NONE
        if remove_children:
            opts |= commands.LeaveOptions.RemoveChildren
        if rejoin:
            opts |= commands.LeaveOptions.Rejoin

        return await self._device.send_zdo_command(
            commands.MgmtLeaveReq(device_address=self._device.ieee, options=opts),
            response_type=commands.MgmtLeaveRsp,
        )

    async def permit(
        self, duration: int = 60, tc_significance: bool = False
    ) -> commands.MgmtPermitJoiningRsp:
        return await self._device.send_zdo_command(
            commands.MgmtPermitJoiningReq(
                permit_duration=duration, tc_significant=tc_significance
            ),
            response_type=commands.MgmtPermitJoiningRsp,
        )

    def log(self, lvl, msg, *args, **kwargs):
        msg = "[0x%04x:zdo] " + msg
        args = (self._device.nwk, *args)
        return LOGGER.log(lvl, msg, *args, **kwargs)

    @property
    def device(self):
        return self._device


def broadcast(
    app,
    command: commands.ZDOCommand,
    grpid,
    radius,
    *,
    broadcast_address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
):
    sequence = app.get_sequence()
    data = bytes([sequence]) + command.serialize()

    return zigpy.device.broadcast(
        app,
        0,
        command.command_id,
        0,
        0,
        grpid,
        radius,
        sequence,
        data,
        broadcast_address=broadcast_address,
    )
