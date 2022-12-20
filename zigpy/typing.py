"""Typing helpers for Zigpy."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Union

ConfigType = Dict[str, Any]

# pylint: disable=invalid-name
ClusterType = "Cluster"
ControllerApplicationType = "ControllerApplication"
CustomClusterType = "CustomCluster"
CustomDeviceType = "CustomDevice"
CustomEndpointType = "CustomEndpoint"
DeviceType = "Device"
EndpointType = "Endpoint"
ZDOType = "ZDO"
AddressingMode = "AddressingMode"

if TYPE_CHECKING:
    import zigpy.application
    import zigpy.device
    import zigpy.endpoint
    import zigpy.quirks
    import zigpy.types
    import zigpy.zcl
    import zigpy.zdo

    ClusterType = zigpy.zcl.Cluster
    ControllerApplicationType = zigpy.application.ControllerApplication
    CustomClusterType = zigpy.quirks.CustomCluster
    CustomDeviceType = zigpy.quirks.CustomDevice
    CustomEndpointType = zigpy.quirks.CustomEndpoint
    DeviceType = zigpy.device.Device
    EndpointType = zigpy.endpoint.Endpoint
    ZDOType = zigpy.zdo.ZDO

    AddressingMode = Union[
        zigpy.types.Addressing.Group,
        zigpy.types.Addressing.IEEE,
        zigpy.types.Addressing.NWK,
    ]
