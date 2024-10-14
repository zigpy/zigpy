"""Typing helpers for Zigpy."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any, Union

ConfigType = dict[str, Any]

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


class UndefinedType(enum.Enum):
    """Singleton type for use with not set sentinel values."""

    _singleton = 0


UNDEFINED = UndefinedType._singleton  # noqa: SLF001


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
    CustomDeviceType = zigpy.quirks.BaseCustomDevice
    CustomEndpointType = zigpy.quirks.CustomEndpoint
    DeviceType = zigpy.device.Device
    EndpointType = zigpy.endpoint.Endpoint
    ZDOType = zigpy.zdo.ZDO

    AddressingMode = Union[
        zigpy.types.Addressing.Group,
        zigpy.types.Addressing.IEEE,
        zigpy.types.Addressing.NWK,
    ]
