"""Compatibility shims for the quirks v2 API, which moved into ZHA.

The quirks v2 implementation lives in the `zha` package: the builder is
`zha.quirks.v2.QuirkBuilder` and the metadata model is `zha.quirks.metadata`.
Importing these names from `zigpy.quirks.v2` is deprecated and requires `zha`
to be installed; the shims below lazily resolve the old names to their new
homes.

Only `CustomDeviceV2` remains a real class here: it wraps the zigpy device
object so quirks can override low-level device behavior, which is inherently
zigpy-level functionality.
"""

from __future__ import annotations

import importlib
import typing
import warnings

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
)
from zigpy.quirks import BaseCustomDevice
from zigpy.zdo import ZDO

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.device import Device
    import zigpy.types as t


class CustomDeviceV2(BaseCustomDevice):
    """Base class for quirks that replace the zigpy device object.

    Wraps a freshly-constructed device 1:1 (same endpoints and clusters, with
    cached attribute values preserved) so that subclasses can override
    low-level device behavior such as `request`.
    """

    _copy_cluster_attr_cache = True

    def __init__(
        self,
        application: ControllerApplication,
        ieee: t.EUI64,
        nwk: t.NWK,
        replaces: Device,
    ) -> None:
        self.replacement = {
            SIG_ENDPOINTS: {
                key: {
                    SIG_EP_PROFILE: endpoint.profile_id,
                    SIG_EP_TYPE: endpoint.device_type,
                    SIG_EP_INPUT: [
                        cluster.cluster_id for cluster in endpoint.in_clusters.values()
                    ],
                    SIG_EP_OUTPUT: [
                        cluster.cluster_id for cluster in endpoint.out_clusters.values()
                    ],
                }
                for key, endpoint in replaces.endpoints.items()
                if not isinstance(endpoint, ZDO)
            }
        }
        super().__init__(application, ieee, nwk, replaces)


_MOVED_NAMES: dict[str, tuple[str, str]] = {
    "QuirkBuilder": ("zha.quirks.v2", "QuirkBuilder"),
    "UNBUILT_QUIRK_BUILDERS": ("zha.quirks.v2", "UNBUILT_QUIRK_BUILDERS"),
    "ReportingConfig": ("zha.quirks.metadata", "ReportingConfig"),
    "EntityMetadata": ("zha.quirks.metadata", "EntityMetadata"),
    "ZCLEnumMetadata": ("zha.quirks.metadata", "ZCLEnumMetadata"),
    "ZCLSensorMetadata": ("zha.quirks.metadata", "ZCLSensorMetadata"),
    "SwitchMetadata": ("zha.quirks.metadata", "SwitchMetadata"),
    "NumberMetadata": ("zha.quirks.metadata", "NumberMetadata"),
    "BinarySensorMetadata": ("zha.quirks.metadata", "BinarySensorMetadata"),
    "WriteAttributeButtonMetadata": (
        "zha.quirks.metadata",
        "WriteAttributeButtonMetadata",
    ),
    "ZCLCommandButtonMetadata": ("zha.quirks.metadata", "ZCLCommandButtonMetadata"),
    "FriendlyNameMetadata": ("zha.quirks.metadata", "FriendlyNameMetadata"),
    "ExposesFeatureMetadata": ("zha.quirks.metadata", "ExposesFeatureMetadata"),
    "DeviceAlertLevel": ("zha.quirks.metadata", "DeviceAlertLevel"),
    "DeviceAlertMetadata": ("zha.quirks.metadata", "DeviceAlertMetadata"),
    "PreventDefaultEntityCreationMetadata": (
        "zha.quirks.metadata",
        "PreventDefaultEntityCreationMetadata",
    ),
    "ChangedEntityMetadata": ("zha.quirks.metadata", "ChangedEntityMetadata"),
    "QuirksV2RegistryEntry": ("zha.quirks.metadata", "QuirkDefinition"),
    "recursive_freeze": ("zha.quirks.metadata", "recursive_freeze"),
    "ManufacturerModelMetadata": ("zha.quirks", "ModelInfo"),
    "EntityType": ("zha.application", "EntityType"),
    "EntityPlatform": ("zha.application", "EntityPlatform"),
    "BinarySensorDeviceClass": (
        "zha.application.platforms.binary_sensor.device_class",
        "BinarySensorDeviceClass",
    ),
    "NumberDeviceClass": (
        "zha.application.platforms.number.device_class",
        "NumberDeviceClass",
    ),
    "SensorDeviceClass": (
        "zha.application.platforms.sensor.device_class",
        "SensorDeviceClass",
    ),
    "SensorStateClass": (
        "zha.application.platforms.sensor.device_class",
        "SensorStateClass",
    ),
    "ClusterType": ("zigpy.zcl", "ClusterType"),
    "CustomCluster": ("zigpy.quirks", "CustomCluster"),
    "FilterType": ("zigpy.quirks", "FilterType"),
}


def __getattr__(name: str) -> typing.Any:
    if name not in _MOVED_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr = _MOVED_NAMES[name]
    warnings.warn(
        f"`{__name__}.{name}` is deprecated, import `{attr}` from"
        f" `{module_path}` instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return getattr(importlib.import_module(module_path), attr)
