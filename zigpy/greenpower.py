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

import zigpy.device
import zigpy.endpoint
import zigpy.listeners
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

class GreenPowerController(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """Controller that tracks the current GPS state"""
    def __init__(self, application: ControllerApplication):
        self._application: ControllerApplication = application

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
        self._gp_in_cluster.add_listener("cluster_command", self)
        
    def cluster_command(self, hdr_tsn : t.uint8_t, command_id: t.uint8_t, args: list[typing.Any]):
        pass

    async def permit(self, time_s: int = 60):

        pass

