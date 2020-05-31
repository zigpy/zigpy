"""Typing helpers for Zigpy."""

from typing import TYPE_CHECKING

# pylint: disable=invalid-name
ClusterType = "Cluster"
ControllerApplicationType = "ControllerApplication"
DeviceType = "Device"
EndpointType = "Endpoint"
ZDOType = "ZDO"

if TYPE_CHECKING:
    import zigpy.application
    import zigpy.device
    import zigpy.endpoint
    import zigpy.zcl
    import zigpy.zdo

    ClusterType = zigpy.zcl.Cluster
    ControllerApplicationType = zigpy.application.ControllerApplication
    DeviceType = zigpy.device.Device
    EndpointType = zigpy.endpoint.Endpoint
    ZDOType = zigpy.zdo.ZDO
