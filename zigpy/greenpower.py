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
import zigpy.types as t
import zigpy.util
import zigpy.zcl

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

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

class GreenPowerController(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """Controller that tracks the current GPS state"""
    def __init__(self, application: ControllerApplication):
        self._application: ControllerApplication = application
        self._controllerState: ControllerState = ControllerState.Uninitialized
        self._commissioningMode: CommissioningMode = CommissioningMode.NotCommissioning
        self._proxyUnicastTarget: zigpy.device.Device = None

    @property
    def _app_device(self) -> zigpy.device.Device:
        return self._application._device

    @property 
    def _gp_endpoint(self) -> zigpy.endpoint.Endpoint:
        return self._app_device.endpoints[self._application.get_endpoint_id(zigpy.zcl.clusters.general.GreenPowerProxy.cluster_id)]

    @property 
    def _gp_in_cluster(self) -> zigpy.zcl.Cluster:
        return self._gp_endpoint.in_clusters[zigpy.zcl.clusters.general.GreenPowerProxy.cluster_id]
    
    @property
    def _gp_out_cluster(self) -> zigpy.zcl.Cluster:
        return self._gp_endpoint.out_clusters[zigpy.zcl.clusters.general.GreenPowerProxy.cluster_id]

    async def initialize(self):
        self._gp_in_cluster.add_context_listener("cluster_command", self)
        self._controllerState = ControllerState.Operational
    
    async def cluster_command(self, cluster: zigpy.zcl.Cluster, tsn: t.uint8_t, command_id: t.uint8_t, args: list):
        self.info("GreenPowerController cluster_command callback received!")
        
    async def permit(self, time_s: int = 60, device: zigpy.device.Device = None):
        assert self._controllerState != ControllerState.Uninitialized
        assert 0 <= time_s <= 254

        if time_s == 0:
            await self._stop_permit()
            return

        if self._controllerState == ControllerState.Operational:
            if device is not None:
                # No GP endpoint nothing doing sorry
                if not device.endpoints[zigpy.application.GREENPOWER_ENDPOINT_ID]:
                    return
                
                # Figure 42
                # 0: Active
                # 1: during commissioning window 
                # 3: or until told to stop
                await device.endpoints[zigpy.application.GREENPOWER_ENDPOINT_ID].green_power.proxy_commissioning_mode(
                    options = 0b00001011,
                    window = time_s,
                )
                self._controllerState = ControllerState.Commissioning
                self._commissioningMode = CommissioningMode.ProxyUnicast
                self._proxyUnicastTarget = device
            else:
                await self._send_commissioning_broadcast_command(time_s)
                self._controllerState = ControllerState.Commissioning
                self._commissioningMode = CommissioningMode.ProxyUnicast
        else:
            self.warn(
                "GreenPowerController not valid to start unicast commissioning, current state: %d",
                self._controllerState
            )

    async def _stop_permit(self):
        assert self._controllerState != ControllerState.Uninitialized
        if self._controllerState != ControllerState.Commissioning:
            self.warn(
                "GreenPowerController not valid to stop commissioning, current state: %d",
                self._controllerState
            )
            return
        
        if self._commissioningMode == CommissioningMode.ProxyBroadcast:
            await self._send_commissioning_broadcast_command(0)
        elif self._commissioningMode == CommissioningMode.ProxyUnicast:
            await self._proxyUnicastTarget.endpoints[zigpy.application.GREENPOWER_ENDPOINT_ID].green_power.proxy_commissioning_mode(
                options=0b00000000,
            )
        
        self._controllerState = ControllerState.Operational
        self._commissioningMode = CommissioningMode.NotCommissioning
        self._proxyUnicastTarget = None

    async def _send_commissioning_broadcast_command(self, time_s: int):
        assert self._controllerState != ControllerState.Uninitialized
        assert 0 <= time_s <= 254

        tsn = self._application.get_sequence()
        hdr = zigpy.zcl.foundation.ZCLHeader.cluster(tsn, 2)  # commissioning
        hdr.frame_control.disable_default_response = True
        data = None
        if time_s == 0:
            data = hdr.serialize() + t.serialize((0x00), (t.bitmap8))
        else:
            data = hdr.serialize() + t.serialize((0b00001011, time_s), (t.bitmap8, t.uint16_t))
        await self._application.broadcast(
            profile=zigpy.profiles.zgp.PROFILE_ID,
            cluster=zigpy.zcl.clusters.general.GreenPowerProxy.cluster_id,
            src_ep=zigpy.application.GREENPOWER_ENDPOINT_ID,
            dst_ep=zigpy.application.GREENPOWER_ENDPOINT_ID,
            grpid=None,
            radius=30,
            sequence=tsn,
            data=data,
        )



