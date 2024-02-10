"""Quirks v2 module."""
from __future__ import annotations

import collections
from collections.abc import Callable
import dataclasses
import enum
import logging
import types
import typing
from typing import TYPE_CHECKING

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
)
from zigpy.quirks import _DEVICE_REGISTRY, CustomCluster, CustomDevice, FilterType
from zigpy.quirks.registry import DeviceRegistry
import zigpy.types as t
from zigpy.zcl import ClusterType
from zigpy.zdo import ZDO

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.device import Device
    from zigpy.endpoint import Endpoint
    from zigpy.zcl import Cluster
    from zigpy.zcl.foundation import ZCLAttributeDef

_LOGGER = logging.getLogger(__name__)


class CustomDeviceV2(CustomDevice):
    """Implementation of a quirks v2 custom device."""

    _copy_attr_cache = True

    def __init__(
        self,
        application: ControllerApplication,
        ieee: t.EUI64,
        nwk: t.NWK,
        replaces: Device,
        quirk_metadata: QuirksV2RegistryEntry,
    ) -> None:
        # this is done to simplify extending from CustomDevice
        self._replacement_from_replaces(replaces)
        super().__init__(application, ieee, nwk, replaces)
        # we no longer need this after calling super().__init__
        self.replacement = {}
        self._exposes_metadata: dict[
            # (endpoint_id, cluster_id, cluster_type)
            tuple[int, int, ClusterType],
            list[EntityMetadata],
        ] = collections.defaultdict(list)
        self._quirk_metadata: QuirksV2RegistryEntry = quirk_metadata

        for add_meta in quirk_metadata.adds_metadata:
            add_meta(self)

        for remove_meta in quirk_metadata.removes_metadata:
            remove_meta(self)

        for replace_meta in quirk_metadata.replaces_metadata:
            replace_meta(self)

        for patch_meta in quirk_metadata.patches_metadata:
            patch_meta(self)

        for entity_meta in quirk_metadata.entity_metadata:
            entity_meta(self)

    def _replacement_from_replaces(self, replaces: Device) -> None:
        """Set replacement data from replaces device."""
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
            }
            for key, endpoint in replaces.endpoints.items()
            if not isinstance(endpoint, ZDO)
        }

    @property
    def exposes_metadata(
        self,
    ) -> dict[tuple[int, int, ClusterType], list[EntityMetadata],]:
        """Return the metadata for exposed entities."""
        return self._exposes_metadata

    async def apply_custom_configuration(self, *args, **kwargs):
        """Hook for applications to instruct instances to apply custom configuration."""
        for endpoint in self.endpoints.values():
            if isinstance(endpoint, ZDO):
                continue
            for cluster in endpoint.in_clusters.values():
                if (
                    isinstance(cluster, CustomCluster)
                    and cluster.apply_custom_configuration
                    != CustomCluster.apply_custom_configuration
                ):
                    await cluster.apply_custom_configuration(*args, **kwargs)
            for cluster in endpoint.out_clusters.values():
                if (
                    isinstance(cluster, CustomCluster)
                    and cluster.apply_custom_configuration
                    != CustomCluster.apply_custom_configuration
                ):
                    await cluster.apply_custom_configuration(*args, **kwargs)


@dataclasses.dataclass(frozen=True)
class ClusterApplicationMetadata:
    """Adds metadata for applications leveraging zigpy to interact with custom clusters."""

    zcl_init_attributes: set[str] = dataclasses.field(default_factory=set)
    zcl_report_config: dict[str, tuple[int, int, int]] = dataclasses.field(
        default_factory=dict
    )


@dataclasses.dataclass(frozen=True)
class AddsMetadata:
    """Adds metadata for adding a cluster to a device."""

    cluster: int | type[Cluster | CustomCluster]
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: ClusterType = dataclasses.field(default=ClusterType.Server)
    zcl_init_attributes: set[ZCLAttributeDef] = dataclasses.field(default_factory=set)
    constant_attributes: dict[ZCLAttributeDef, typing.Any] = dataclasses.field(
        default_factory=dict
    )
    zcl_report_config: dict[ZCLAttributeDef, tuple[int, int, int]] = dataclasses.field(
        default_factory=dict
    )

    def __call__(self, device: CustomDeviceV2):
        """Process the add."""
        endpoint: Endpoint = device.endpoints[self.endpoint_id]
        if self.cluster_type == ClusterType.Server:
            add_cluster = endpoint.add_input_cluster
        else:
            add_cluster = endpoint.add_output_cluster

        if isinstance(self.cluster, int):
            cluster = None
            cluster_id = self.cluster
        else:
            cluster = self.cluster(endpoint, is_server=True)
            cluster_id = cluster.cluster_id

        cluster = add_cluster(cluster_id, cluster)

        if self.constant_attributes:
            cluster._CONSTANT_ATTRIBUTES = {
                attribute.name: value
                for attribute, value in self.constant_attributes.items()
            }

        if self.zcl_init_attributes or self.zcl_report_config:
            cluster.application_metadata = ClusterApplicationMetadata(
                zcl_init_attributes={
                    attribute.name for attribute in self.zcl_init_attributes
                },
                zcl_report_config={
                    attribute.name: report_config
                    for attribute, report_config in self.zcl_report_config.items()
                },
            )


@dataclasses.dataclass(frozen=True)
class RemovesMetadata:
    """Removes metadata for removing a cluster from a device."""

    cluster_id: int
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: ClusterType = dataclasses.field(default=ClusterType.Server)

    def __call__(self, device: CustomDeviceV2):
        """Process the remove."""
        endpoint = device.endpoints[self.endpoint_id]
        if self.cluster_type == ClusterType.Server:
            endpoint.in_clusters.pop(self.cluster_id, None)
        else:
            endpoint.out_clusters.pop(self.cluster_id, None)


@dataclasses.dataclass(frozen=True)
class ReplacesMetadata:
    """Replaces metadata for replacing a cluster on a device."""

    remove: RemovesMetadata
    add: AddsMetadata

    def __call__(self, device: CustomDeviceV2):
        """Process the replace."""
        self.remove(device)
        self.add(device)


@dataclasses.dataclass(frozen=True)
class PatchesMetadata:
    """Patches metadata for replacing a method on a cluster on a device."""

    replacement_method: Callable
    cluster_id: int
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: ClusterType = dataclasses.field(default=ClusterType.Server)

    def __call__(self, device: CustomDeviceV2):
        """Apply the patch."""
        endpoint = device.endpoints[self.endpoint_id]
        cluster = (
            endpoint.in_clusters[self.cluster_id]
            if self.cluster_type == ClusterType.Server
            else endpoint.out_clusters[self.cluster_id]
        )
        method_name = self.replacement_method.__name__
        cluster[method_name] = types.MethodType(self.replacement_method, cluster)


class EntityType(enum.Enum):
    """Entity type."""

    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
    STANDARD = "standard"


class EntityPlatform(enum.Enum):
    """Entity platform."""

    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    NUMBER = "number"
    SENSOR = "sensor"
    SELECT = "select"
    SWITCH = "switch"


@dataclasses.dataclass(frozen=True)
class EnumMetadata:
    """Metadata for exposed enum based entity."""

    enum: type[enum.Enum]


@dataclasses.dataclass(frozen=True)
class ZCLEnumMetadata(EnumMetadata):
    """Metadata for exposed ZCL enum based entity."""

    attribute_name: str | None = dataclasses.field(default=None)


@dataclasses.dataclass(frozen=True)
class ZCLSensorMetadata:
    """Metadata for exposed ZCL attribute based sensor entity."""

    attribute_name: str | None = dataclasses.field(default=None)
    decimals: int | None = dataclasses.field(default=None)
    divisor: int | None = dataclasses.field(default=None)
    multiplier: int | None = dataclasses.field(default=None)


@dataclasses.dataclass(frozen=True)
class SwitchMetadata:
    """Metadata for exposed switch entity."""

    attribute_name: str
    force_inverted: bool = dataclasses.field(default=False)
    invert_attribute_name: str | None = dataclasses.field(default=None)


@dataclasses.dataclass(frozen=True)
class NumberMetadata:
    """Metadata for exposed number entity."""

    attribute_name: str
    min: float | None = dataclasses.field(default=None)
    max: float | None = dataclasses.field(default=None)
    step: float | None = dataclasses.field(default=None)
    unit: str | None = dataclasses.field(default=None)
    mode: str | None = dataclasses.field(default=None)
    multiplier: float | None = dataclasses.field(default=None)


@dataclasses.dataclass(frozen=True)
class BinarySensorMetadata:
    """Metadata for exposed binary sensor entity."""

    attribute_name: str


@dataclasses.dataclass(frozen=True)
class WriteAttributeButtonMetadata:
    """Metadata for exposed button entity that writes an attribute when pressed."""

    attribute_name: str
    attribute_value: int


@dataclasses.dataclass(frozen=True)
class ZCLCommandButtonMetadata:
    """Metadata for exposed button entity that executes a ZCL command when pressed."""

    command_name: str
    arguments: tuple = dataclasses.field(default_factory=tuple)
    kwargs: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class EntityMetadata:
    """Metadata for exposed select entity."""

    entity_metadata: (
        EnumMetadata
        | ZCLEnumMetadata
        | SwitchMetadata
        | NumberMetadata
        | BinarySensorMetadata
        | WriteAttributeButtonMetadata
        | ZCLCommandButtonMetadata
    )
    entity_platform: EntityPlatform
    entity_type: EntityType
    cluster_id: int
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: ClusterType = dataclasses.field(default=ClusterType.Server)

    def __call__(self, device: CustomDeviceV2):
        """Add the entity metadata to the quirks v2 device."""
        device.exposes_metadata[
            (self.endpoint_id, self.cluster_id, self.cluster_type)
        ].append(self)


@dataclasses.dataclass
class QuirksV2RegistryEntry:  # pylint: disable=too-many-instance-attributes
    """Quirks V2 registry entry."""

    registry: DeviceRegistry = None
    filters: list[FilterType] = dataclasses.field(default_factory=list)
    custom_device_class: type[CustomDeviceV2] | None = dataclasses.field(default=None)
    adds_metadata: list[AddsMetadata] = dataclasses.field(default_factory=list)
    removes_metadata: list[RemovesMetadata] = dataclasses.field(default_factory=list)
    replaces_metadata: list[ReplacesMetadata] = dataclasses.field(default_factory=list)
    patches_metadata: list[PatchesMetadata] = dataclasses.field(default_factory=list)
    entity_metadata: list[EntityMetadata] = dataclasses.field(default_factory=list)
    device_automation_triggers_metadata: dict[
        tuple[str, str], dict[str, str]
    ] = dataclasses.field(default_factory=dict)

    def also_applies_to(self, manufacturer: str, model: str):
        """Register this quirks v2 entry for an additional manufacturer and model."""
        return self.registry.add_to_registry_v2(manufacturer, model, self)

    def device_class(self, custom_device_class: type[CustomDeviceV2]):
        """Set the custom device class and returns self."""
        assert issubclass(
            custom_device_class, CustomDeviceV2
        ), f"{custom_device_class} is not a subclass of CustomDeviceV2"
        self.custom_device_class = custom_device_class
        return self

    def filter(self, filter_function: FilterType):
        """Add a filter and returns self."""
        self.filters.append(filter_function)
        return self

    def matches_device(self, device: Device) -> bool:
        """Process all filters and return True if all pass."""
        return all(_filter(device) for _filter in self.filters)

    def adds(
        self,
        cluster: int | type[Cluster | CustomCluster],
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        zcl_init_attributes: set[ZCLAttributeDef] | None = None,
        constant_attributes: dict[ZCLAttributeDef, typing.Any] | None = None,
        zcl_report_config: dict[ZCLAttributeDef, tuple[int, int, int]] | None = None,
    ):  # pylint: disable=too-many-arguments
        """Add an AddsMetadata entry and returns self."""
        add = AddsMetadata(
            endpoint_id=endpoint_id,
            cluster=cluster,
            cluster_type=cluster_type,
            zcl_init_attributes=zcl_init_attributes or set(),
            constant_attributes=constant_attributes or {},
            zcl_report_config=zcl_report_config or {},
        )
        self.adds_metadata.append(add)
        return self

    def removes(
        self,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
    ):
        """Add a RemovesMetadata entry and returns self."""
        remove = RemovesMetadata(
            endpoint_id=endpoint_id,
            cluster_id=cluster_id,
            cluster_type=cluster_type,
        )
        self.removes_metadata.append(remove)
        return self

    def replaces(
        self,
        replacement_cluster_class: type[Cluster | CustomCluster],
        cluster_id: int | None = None,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
    ):
        """Add a ReplacesMetadata entry and returns self."""
        remove = RemovesMetadata(
            endpoint_id=endpoint_id,
            cluster_id=cluster_id
            if cluster_id is not None
            else replacement_cluster_class.cluster_id,
            cluster_type=cluster_type,
        )
        add = AddsMetadata(
            endpoint_id=endpoint_id,
            cluster=replacement_cluster_class,
            cluster_type=cluster_type,
        )
        replace = ReplacesMetadata(remove=remove, add=add)
        self.replaces_metadata.append(replace)
        return self

    def patches(
        self,
        replacement_method: Callable,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
    ):
        """Add a patch and returns self."""
        patch = PatchesMetadata(
            endpoint_id=endpoint_id,
            cluster_id=cluster_id,
            cluster_type=cluster_type,
            replacement_method=replacement_method,
        )
        self.patches_metadata.append(patch)
        return self

    def enum(
        self,
        attribute_name: str,
        enum_class: type[enum.Enum],
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.CONFIG,
        entity_platform: EntityPlatform = EntityPlatform.SELECT,
    ):  # pylint: disable=too-many-arguments
        """Add a enum and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_type=entity_type,
                entity_platform=entity_platform,
                entity_metadata=ZCLEnumMetadata(
                    attribute_name=attribute_name,
                    enum=enum_class,
                ),
            )
        )
        return self

    def sensor(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        decimals: int = 1,
        divisor: int = 1,
        multiplier: int = 1,
        entity_type: EntityType = EntityType.STANDARD,
    ):  # pylint: disable=too-many-arguments
        """Add a switch and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.SENSOR,
                entity_type=entity_type,
                entity_metadata=ZCLSensorMetadata(
                    attribute_name=attribute_name,
                    decimals=decimals,
                    divisor=divisor,
                    multiplier=multiplier,
                ),
            )
        )
        return self

    def switch(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        force_inverted: bool = False,
        invert_attribute_name: str | None = None,
        entity_platform=EntityPlatform.SWITCH,
    ):  # pylint: disable=too-many-arguments
        """Add a switch and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=entity_platform,
                entity_type=EntityType.CONFIG,
                entity_metadata=SwitchMetadata(
                    attribute_name=attribute_name,
                    force_inverted=force_inverted,
                    invert_attribute_name=invert_attribute_name,
                ),
            )
        )
        return self

    def number(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        min_value: float | None = None,
        max_value: float | None = None,
        step: float | None = None,
        unit: str | None = None,
        mode: str | None = None,
        multiplier: float | None = None,
    ):  # pylint: disable=too-many-arguments
        """Add a number and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.NUMBER,
                entity_type=EntityType.CONFIG,
                entity_metadata=NumberMetadata(
                    attribute_name=attribute_name,
                    min=min_value,
                    max=max_value,
                    step=step,
                    unit=unit,
                    mode=mode,
                    multiplier=multiplier,
                ),
            )
        )
        return self

    def binary_sensor(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
    ):
        """Add a binary sensor and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.BINARY_SENSOR,
                entity_type=EntityType.DIAGNOSTIC,
                entity_metadata=BinarySensorMetadata(
                    attribute_name=attribute_name,
                ),
            )
        )
        return self

    def write_attr_button(
        self,
        attribute_name: str,
        attribute_value: int,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.CONFIG,
    ):  # pylint: disable=too-many-arguments
        """Add a write attribute button and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.BUTTON,
                entity_type=entity_type,
                entity_metadata=WriteAttributeButtonMetadata(
                    attribute_name=attribute_name,
                    attribute_value=attribute_value,
                ),
            )
        )
        return self

    def device_automation_triggers(
        self, device_automation_triggers: dict[tuple[str, str], dict[str, str]]
    ):
        """Add a device automation trigger and returns self."""
        self.device_automation_triggers_metadata.update(device_automation_triggers)
        return self

    def create_device(self, device: Device) -> CustomDeviceV2:
        """Create a quirked device."""
        if self.custom_device_class:
            return self.custom_device_class(
                device.application, device.ieee, device.nwk, device, self
            )
        return CustomDeviceV2(device.application, device.ieee, device.nwk, device, self)


def add_to_registry_v2(
    manufacturer: str, model: str, registry: DeviceRegistry = _DEVICE_REGISTRY
) -> QuirksV2RegistryEntry:
    """Add an entry to the registry."""
    entry = QuirksV2RegistryEntry()
    return registry.add_to_registry_v2(manufacturer, model, entry)
