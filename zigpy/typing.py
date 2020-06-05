"""Typing helpers for Zigpy."""

from typing import TYPE_CHECKING

# pylint: disable=invalid-name
ClusterType = "Cluster"
ControllerApplicationType = "ControllerApplication"
CustomClusterType = "CustomCluster"
CustomDeviceType = "CustomDevice"
CustomEndpointType = "CustomEndpoint"
DeviceType = "Device"
EndpointType = "Endpoint"
ZDOType = "ZDO"

if TYPE_CHECKING:
    import zigpy.application
    import zigpy.device
    import zigpy.endpoint
    import zigpy.quirks
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
