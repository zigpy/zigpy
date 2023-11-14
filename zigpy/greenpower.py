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
from zigpy.profiles.zgp import GPCommand
import zigpy.types as t
import zigpy.util
import zigpy.zcl

from zigpy.zcl import Cluster, foundation
from zigpy.types.named import BroadcastAddress
from zigpy.zcl.clusters.general import GreenPowerProxy

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)

# Table 27
class SinkTableEntry(t.Struct):
    options: t.bitmap16
    gpd_id: t.uint32_t
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

class GPFrameType(enum.Enum):
    DataFrame = 0x00
    MaintenanceFrame = 0x01

class GPApplicationID(enum.Enum):
    GPZero = 0b000
    GPTwo  = 0b010
    LPED   = 0b001

# Table 13
class GPSecurityLevel(t.enum2):
    NoSecurity = 0b00
    ShortFrameCounterAndMIC = 0b01
    FullFrameCounterAndMIC = 0b10
    Encrypted = 0b11


# Table 14
class GPSecurityKeyType(t.enum3):
    NoKey = 0b000
    NWKKey = 0b001
    GPDGroupKey = 0b010
    NWKKeyDerivedGPD = 0b011
    IndividualKey = 0b100
    DerivedIndividual = 0b111

COMMAND_PAYLOADS = {
    
}


def deserialize_green_power_frame(data: bytes):
    # this comes almost entirely from 
    # https://github.com/dresden-elektronik/deconz-serial-protocol/issues/13#issuecomment-992586453
    # since they seem to know what's what
    options, data = t.bitmap8.deserialize(data)
    ext_options = 0
    auto_commissioning = options & 0b01000000
    has_frame_control_extension = options & 0b10000000
    frame_type = GPFrameType(options & 0x03)
    if frame_type not in (GPFrameType.DataFrame, GPFrameType.MaintenanceFrame):
        raise Exception("Bad GDPF type %d", frame_type)
    if has_frame_control_extension: # parse extended data frame
        ext_options, data = t.bitmap8.deserialize(data)
    application_id = GPApplicationID(ext_options & 0b0000011)
    if application_id not in (GPApplicationID.GPZero, GPApplicationID.GPTwo, GPApplicationID.LPED):
        raise Exception("Bad Application ID %d", application_id)

    src_id = 0
    if frame_type == GPFrameType.DataFrame and application_id == GPApplicationID.GPZero:
        src_id, data = t.uint32_t.deserialize(data)
    elif frame_type == GPFrameType.MaintenanceFrame and has_frame_control_extension and application_id == GPApplicationID.GPZero:
        src_id, data = t.uint32_t.deserialize(data)

    frame_counter = 0
    security_level = GPSecurityLevel.NoSecurity
    if has_frame_control_extension:
        security_level = GPSecurityLevel((ext_options >> 3) & 0x03)
        has_security_key = (ext_options >> 5) & 0x01
        rx_after_tx = (ext_options >> 6) & 0x01
        direction = (ext_options >> 7) & 0x01
        if security_level in (GPSecurityLevel.FullFrameCounterAndMIC, GPSecurityLevel.Encrypted):
            frame_counter, data = t.uint32_t.deserialize(data)
    
    command_id = 0
    mic = 0
    if application_id != GPApplicationID.LPED:
        command_id, data = t.uint8_t.deserialize(data)

        if security_level == GPSecurityLevel.ShortFrameCounterAndMIC:
            mic, _ = t.uint16_t.deserialize(data[-2:])
            data = data[:-2]
        elif security_level in (GPSecurityLevel.FullFrameCounterAndMIC, GPSecurityLevel.Encrypted):
            mic, _ = t.uint32_t.deserialize(data[-4:])
            data = data[:-4]
            
        command_payload = data
    
    return {
        options: options,
        ext_options: ext_options,
        frame_type: frame_type,
        auto_commissioning: auto_commissioning,
        src_id: src_id,
        frame_counter: frame_counter,
        command_id: command_id,
        command_payload: command_payload,
        mic: mic
    }

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
        self._controller_state = ControllerState.Operational
        LOGGER.info("Green Power Controller initialized!")


    async def permit(self, time_s: int = 60, device: zigpy.device.Device = None):
        assert 0 <= time_s <= 254

        if time_s == 0:
            await self._stop_permit()
            return

        assert self._controller_state != ControllerState.Uninitialized

        if self._controller_state == ControllerState.Operational:
            if device is not None:
                # No GP endpoint nothing doing sorry
                if not device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID]:
                    return
                
                # Figure 42
                # 0: Active
                # 1: during commissioning window 
                # 3: or until told to stop
                await device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID].green_power.proxy_commissioning_mode(
                    options = 0x0B,
                    window = 25
                )
                LOGGER.debug("Successfully sent commissioning mode request to %s", str(device.ieee))
                self._controller_state = ControllerState.Commissioning
                self._commissioning_mode = CommissioningMode.ProxyUnicast
                self._proxy_unicast_target = device
            else:
                await self._send_commissioning_broadcast_command(time_s)
                self._controller_state = ControllerState.Commissioning
                self._commissioning_mode = CommissioningMode.ProxyBroadcast
        else:
            LOGGER.debug(
                "GreenPowerController not valid to start commissioning, current state: %s",
                str(self._controller_state)
            )

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
        
        if self._commissioning_mode == CommissioningMode.ProxyBroadcast:
            await self._send_commissioning_broadcast_command(0)
        elif self._commissioning_mode == CommissioningMode.ProxyUnicast:
            await self._proxy_unicast_target.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID].green_power.proxy_commissioning_mode(
                options=0x00,
            )
        
        self._controller_state = ControllerState.Operational
        self._commissioning_mode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target = None

    async def _send_commissioning_broadcast_command(self, time_s: int):
        named_arguments = None
        if time_s > 0:
            named_arguments = {
                "options": 0x0B,
                "window": time_s
            }
        else:
            named_arguments = {"options": 0x00}

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
            disable_default_response=False,
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



