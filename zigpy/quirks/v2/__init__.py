"""Compatibility shims for the quirks v2 API, which moved into zha-device-handlers.

The quirks v2 authoring API lives in the `zhaquirks` package: the builder is
`zhaquirks.builder.QuirkBuilder` and the metadata model is `zhaquirks.builder.metadata`
(entity/device-class enums remain ZHA constructs in `zha.application`).
Importing these names from `zigpy.quirks.v2` is deprecated and requires
`zhaquirks` to be installed; the shims below lazily resolve the old names to
their new homes.
"""

from __future__ import annotations

import importlib
import typing
import warnings

_MOVED_NAMES: dict[str, tuple[str, str]] = {
    "CustomDeviceV2": ("zhaquirks.device", "CustomZigpyDevice"),
    "QuirkBuilder": ("zhaquirks.builder", "QuirkBuilder"),
    "UNBUILT_QUIRK_BUILDERS": ("zhaquirks.builder", "UNBUILT_QUIRK_BUILDERS"),
    "ReportingConfig": ("zhaquirks.builder.metadata", "ReportingConfig"),
    "EntityMetadata": ("zhaquirks.builder.metadata", "EntityMetadata"),
    "ZCLEnumMetadata": ("zhaquirks.builder.metadata", "ZCLEnumMetadata"),
    "ZCLSensorMetadata": ("zhaquirks.builder.metadata", "ZCLSensorMetadata"),
    "SwitchMetadata": ("zhaquirks.builder.metadata", "SwitchMetadata"),
    "NumberMetadata": ("zhaquirks.builder.metadata", "NumberMetadata"),
    "BinarySensorMetadata": ("zhaquirks.builder.metadata", "BinarySensorMetadata"),
    "WriteAttributeButtonMetadata": (
        "zhaquirks.builder.metadata",
        "WriteAttributeButtonMetadata",
    ),
    "ZCLCommandButtonMetadata": (
        "zhaquirks.builder.metadata",
        "ZCLCommandButtonMetadata",
    ),
    "FriendlyNameMetadata": ("zhaquirks.builder.metadata", "FriendlyNameMetadata"),
    "ExposesFeatureMetadata": ("zhaquirks.builder.metadata", "ExposesFeatureMetadata"),
    "DeviceAlertLevel": ("zhaquirks.builder.metadata", "DeviceAlertLevel"),
    "DeviceAlertMetadata": ("zhaquirks.builder.metadata", "DeviceAlertMetadata"),
    "PreventDefaultEntityCreationMetadata": (
        "zhaquirks.builder.metadata",
        "PreventDefaultEntityCreationMetadata",
    ),
    "ChangedEntityMetadata": ("zhaquirks.builder.metadata", "ChangedEntityMetadata"),
    "QuirksV2RegistryEntry": ("zhaquirks.builder.metadata", "QuirkDefinition"),
    "recursive_freeze": ("zhaquirks.builder.metadata", "recursive_freeze"),
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
    "CustomCluster": ("zhaquirks.clusters", "CustomCluster"),
    "FilterType": ("zhaquirks.legacy", "FilterType"),
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
