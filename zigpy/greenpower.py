from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import enum
import logging
import sys
import typing 
import warnings

if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout  # pragma: no cover
else:
    from asyncio import timeout as asyncio_timeout  # pragma: no cover

import zigpy.application
import zigpy.device
import zigpy.endpoint
import zigpy.listeners
import zigpy.profiles.zgp
from zigpy.profiles.zgp import (
    GPCommand,
    GREENPOWER_BROADCAST_GROUP,
    GREENPOWER_ENDPOINT_ID,
)
import zigpy.types as t
from zigpy.types import (
    GPFrameType,
    GPSecurityLevel
)
import zigpy.util
import zigpy.zcl

from zigpy.zcl import Cluster, foundation
from zigpy.types.named import BroadcastAddress
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
    GPCommissioningNotificationOptions
)

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)

# Table 27
class SinkTableEntry(t.Struct):
    options: t.bitmap16
    gpd_id: t.GreenPowerDeviceID
    device_id: t.uint8_t
    radius: t.uint8_t = 0xff 
    sec_options: t.bitmap8
    sec_frame_counter: t.uint32_t
    key: t.KeyData

class ControllerState(enum.Enum):
    Uninitialized = 0
    Initializing = 1
    Operational = 2
    Commissioning = 3
    Error = 255

class CommissioningMode(enum.Flag):
    NotCommissioning = 0
    Direct         = 0b001
    ProxyUnicast   = 0b010
    ProxyBroadcast = 0b100

class GreenPowerController(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """Controller that tracks the current GPS state"""
    def __init__(self, application: ControllerApplication):
        self._application: ControllerApplication = application
        self.__controller_state: ControllerState = ControllerState.Uninitialized
        self._commissioning_mode: CommissioningMode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target: zigpy.device.Device = None

    @property 
    def _controller_state(self):
        return self.__controller_state

    @_controller_state.setter
    def _controller_state(self, value):
        if self.__controller_state != value:
            LOGGER.debug(
                "Green power controller transition states '%s' to '%s'", 
                str(self.__controller_state), 
                str(value))
            self.__controller_state = value

    async def initialize(self):
        # register callbacks
        # self._application._callback_for_response()
        self._application._callback_for_response(zigpy.listeners.ANY_DEVICE, [
            GreenPowerProxy.ServerCommandDefs.notification.schema()
        ], self._on_zcl_notification)
        self._application._callback_for_response(zigpy.listeners.ANY_DEVICE, [
            GreenPowerProxy.ServerCommandDefs.commissioning_notification.schema()
        ], self._on_zcl_commissioning_notification)

        try:
            await self._application._device.endpoints[GREENPOWER_ENDPOINT_ID].add_to_group(GREENPOWER_BROADCAST_GROUP)
        except (IndexError, KeyError):
            LOGGER.warn("No GP endpoint to add to GP Group; GP broadcasts will not function")
        
        self._controller_state = ControllerState.Operational
        LOGGER.info("Green Power Controller initialized!")

    def _on_zcl_notification(self, hdr, command):
        LOGGER.info("Got green power ZCL notification")

    def _on_zcl_commissioning_notification(self, hdr, command):
        LOGGER.info("Got green power ZCL commissioning notification")

    def handle_unknown_tunneled_green_power_frame(self, packet: t.ZigbeePacket):
        # if we're not listening for commissioning packets, don't worry too much about it
        # we can't really scan for these things so don't worry about the ZDO followup either
        if self._controller_state != ControllerState.Commissioning:
            return

        hdr, rest = foundation.ZCLHeader.deserialize(packet.data.value)
        if hdr.command_id == GreenPowerProxy.ServerCommandDefs.commissioning_notification.id:
            # here we go
            notif, rest = GreenPowerProxy.ServerCommandDefs.commissioning_notification.schema.deserialize(rest)
            options: GPCommissioningNotificationOptions = notif.options
            if options.security_level == GPSecurityLevel.NoSecurity and notif.command_id == GPCommand.Commissioning:
                
                pass
            
            # if we have security level > 0, it's not a proper 0xE0 commissioning command; pass
            
       
    async def handle_received_green_power_frame(self, frame: t.GPDataFrame):
        """Build this out later to allow for direct interaction and commissioning"""
    
    async def permit(self, time_s: int = 60, device: zigpy.device.Device = None):
        assert 0 <= time_s <= 254

        if time_s == 0:
            await self._stop_permit()
            return

        assert self._controller_state != ControllerState.Uninitialized

        # this flow kinda stinks, but ZHA doesn't give us a message to
        # stop commissioning near as I can tell. it just waits for the
        # window to close
        if self._controller_state == ControllerState.Commissioning:
            await self._stop_permit()
            # really, really let it settle, as devices hate the close/open
            await asyncio.sleep(0.2)

        assert self._controller_state == ControllerState.Operational

        if device is not None:
            # We can direct commission without a lot of help
            if device == self._application._device:
                self._commissioning_mode = CommissioningMode.Direct
                return

            # No GP endpoint nothing doing sorry
            if not device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID]:
                return
            
            # Figure 42
            # 0: Active
            # 1: during commissioning window 
            # 3: or until told to stop
            await device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].proxy_commissioning_mode(
                options = GreenPowerProxy.GPProxyCommissioningModeOptions(
                    enter=1,
                    exit_mode=t.GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
                ),
                window = time_s
            )
            LOGGER.debug("Successfully sent commissioning mode request to %s", str(device.ieee))
            self._controller_state = ControllerState.Commissioning
            self._commissioning_mode = CommissioningMode.ProxyUnicast
            self._proxy_unicast_target = device
        else:
            await self._send_commissioning_broadcast_command(time_s)
            self._controller_state = ControllerState.Commissioning
            self._commissioning_mode = CommissioningMode.ProxyBroadcast


    async def _stop_permit(self):
        # this may happen if the application experiences an unexpected
        # shutdown before we're initialized, or during startup when the NCP
        # state is being ensured. more common paths are asserted, not tested.
        if self._controller_state == ControllerState.Uninitialized:
            LOGGER.debug("GreenPowerController ignoring stop permit request on uninitialized state")
            return
        
        if self._controller_state != ControllerState.Commissioning:
            LOGGER.debug(
                "GreenPowerController not valid to stop commissioning, current state: %s",
                str(self._controller_state)
            )
            return
        
        if CommissioningMode.ProxyBroadcast in self._commissioning_mode:
            await self._send_commissioning_broadcast_command(0)
        elif CommissioningMode.ProxyUnicast in self._commissioning_mode:
            await self._proxy_unicast_target.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].proxy_commissioning_mode(
                options=GreenPowerProxy.GPProxyCommissioningModeOptions(enter=0),
            )
        self._controller_state = ControllerState.Operational
        self._commissioning_mode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target = None
        # we need to give the network and devices time to settle
        # just in case we have to immediately request more commissioning
        await asyncio.sleep(0.2)

    async def _send_commissioning_broadcast_command(self, time_s: int):
        named_arguments = None
        if time_s > 0:
            named_arguments = {
                "options": GreenPowerProxy.GPProxyCommissioningModeOptions(
                    enter=1,
                    exit_mode=t.GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
                ),
                "window": time_s
            }
        else:
            named_arguments = {
                "options": GreenPowerProxy.GPProxyCommissioningModeOptions(enter=0)
            }

        await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode, named_arguments)

    async def _zcl_broadcast(
        self,
        command: zigpy.foundation.ZCLCommandDef,
        kwargs: dict = {},
        address: t.BroadcastAddress = BroadcastAddress.RX_ON_WHEN_IDLE,
        dst_ep: t.uint16_t = zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID,
        cluster_id: t.uint16_t = GreenPowerProxy.cluster_id,
        profile_id: t.uint16_t = zigpy.profiles.zgp.PROFILE_ID,
        radius=30,
    ):
        tsn = self._application.get_sequence()

        hdr, request = Cluster._create_request(
            self=None,
            general=False,
            command_id=command.id,
            schema=command.schema,
            tsn=tsn,
            disable_default_response=True,
            direction=command.direction,
            args=(),
            kwargs=kwargs,
        )

        # Broadcast
        await self._application.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK, address=self._application.state.node_info.nwk
                ),
                src_ep=zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID,
                dst=t.AddrModeAddress(addr_mode=t.AddrMode.Broadcast, address=address),
                dst_ep=dst_ep,
                tsn=tsn,
                profile_id=profile_id,
                cluster_id=cluster_id,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
                tx_options=t.TransmitOptions.NONE,
                radius=radius,
            )
        )



