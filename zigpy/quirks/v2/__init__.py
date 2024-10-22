"""Quirks v2 module."""

from __future__ import annotations

import collections
from copy import deepcopy
from enum import Enum
import inspect
import logging
import pathlib
import typing
from typing import TYPE_CHECKING, Any

import attrs
from frozendict import deepfreeze, frozendict

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_NODE_DESC,
    SIG_SKIP_CONFIG,
)
from zigpy.quirks import _DEVICE_REGISTRY, BaseCustomDevice, CustomCluster, FilterType
from zigpy.quirks.registry import DeviceRegistry
from zigpy.quirks.v2.homeassistant import EntityPlatform, EntityType
from zigpy.quirks.v2.homeassistant.binary_sensor import BinarySensorDeviceClass
from zigpy.quirks.v2.homeassistant.number import NumberDeviceClass
from zigpy.quirks.v2.homeassistant.sensor import SensorDeviceClass, SensorStateClass
import zigpy.types as t
from zigpy.zcl import ClusterType
from zigpy.zdo import ZDO
from zigpy.zdo.types import NodeDescriptor

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.device import Device
    from zigpy.endpoint import Endpoint
    from zigpy.zcl import Cluster
    from zigpy.zcl.foundation import ZCLAttributeDef

_LOGGER = logging.getLogger(__name__)

UNBUILT_QUIRK_BUILDERS: list[QuirkBuilder] = []


# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-few-public-methods


class CustomDeviceV2(BaseCustomDevice):
    """Implementation of a quirks v2 custom device."""

    _copy_cluster_attr_cache = True

    def __init__(
        self,
        application: ControllerApplication,
        ieee: t.EUI64,
        nwk: t.NWK,
        replaces: Device,
        quirk_metadata: QuirksV2RegistryEntry,
    ) -> None:
        self.quirk_metadata: QuirksV2RegistryEntry = quirk_metadata
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

        for add_meta in quirk_metadata.adds_metadata:
            add_meta(self)

        for remove_meta in quirk_metadata.removes_metadata:
            remove_meta(self)

        for replace_meta in quirk_metadata.replaces_metadata:
            replace_meta(self)

        for (
            replace_occurrences_meta
        ) in quirk_metadata.replaces_cluster_occurrences_metadata:
            replace_occurrences_meta(self)

        for entity_meta in quirk_metadata.entity_metadata:
            entity_meta(self)

        if quirk_metadata.device_automation_triggers_metadata:
            self.device_automation_triggers = (
                quirk_metadata.device_automation_triggers_metadata
            )

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
                for key, endpoint in replaces.endpoints.items()
                if not isinstance(endpoint, ZDO)
            }
        }
        self.replacement[SIG_SKIP_CONFIG] = (
            self.quirk_metadata.skip_device_configuration
        )
        if self.quirk_metadata.device_node_descriptor:
            self.replacement[SIG_NODE_DESC] = self.quirk_metadata.device_node_descriptor

    @property
    def exposes_metadata(
        self,
    ) -> dict[
        tuple[int, int, ClusterType],
        list[EntityMetadata],
    ]:
        """Return EntityMetadata for exposed entities.

        The key is a tuple of (endpoint_id, cluster_id, cluster_type).
        The value is a list of EntityMetadata instances.
        """
        return self._exposes_metadata


@attrs.define(frozen=True, kw_only=True, repr=True)
class AddsMetadata:
    """Adds metadata for adding a cluster to a device."""

    cluster: int | type[Cluster | CustomCluster] = attrs.field()
    endpoint_id: int = attrs.field(default=1)
    cluster_type: ClusterType = attrs.field(default=ClusterType.Server)
    constant_attributes: frozendict[ZCLAttributeDef, typing.Any] = attrs.field(
        factory=frozendict, converter=deepfreeze
    )

    def __call__(self, device: CustomDeviceV2) -> None:
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


@attrs.define(frozen=True, kw_only=True, repr=True)
class RemovesMetadata:
    """Removes metadata for removing a cluster from a device."""

    cluster_id: int = attrs.field()
    endpoint_id: int = attrs.field(default=1)
    cluster_type: ClusterType = attrs.field(default=ClusterType.Server)

    def __call__(self, device: CustomDeviceV2) -> None:
        """Process the remove."""
        endpoint = device.endpoints[self.endpoint_id]
        if self.cluster_type == ClusterType.Server:
            endpoint.in_clusters.pop(self.cluster_id, None)
        else:
            endpoint.out_clusters.pop(self.cluster_id, None)


@attrs.define(frozen=True, kw_only=True, repr=True)
class ReplacesMetadata:
    """Replaces metadata for replacing a cluster on a device."""

    remove: RemovesMetadata = attrs.field()
    add: AddsMetadata = attrs.field()

    def __call__(self, device: CustomDeviceV2) -> None:
        """Process the replace."""
        self.remove(device)
        self.add(device)


@attrs.define(frozen=True, kw_only=True, repr=True)
class ReplaceClusterOccurrencesMetadata:
    """Replaces metadata for replacing all occurrences of a cluster on a device."""

    cluster_types: tuple[ClusterType] = attrs.field()
    cluster: type[Cluster | CustomCluster] = attrs.field()

    def __call__(self, device: CustomDeviceV2) -> None:
        """Process the replace."""
        for endpoint in device.endpoints.values():
            if isinstance(endpoint, ZDO):
                continue
            if (
                ClusterType.Server in self.cluster_types
                and self.cluster.cluster_id in endpoint.in_clusters
            ):
                endpoint.in_clusters.pop(self.cluster.cluster_id)
                endpoint.add_input_cluster(
                    self.cluster.cluster_id, self.cluster(endpoint)
                )
            if (
                ClusterType.Client in self.cluster_types
                and self.cluster.cluster_id in endpoint.out_clusters
            ):
                endpoint.out_clusters.pop(self.cluster.cluster_id)
                endpoint.add_output_cluster(
                    self.cluster.cluster_id, self.cluster(endpoint, is_server=False)
                )


@attrs.define(frozen=True, kw_only=True, repr=True)
class EntityMetadata:
    """Metadata for an exposed entity."""

    entity_platform: EntityPlatform = attrs.field()
    entity_type: EntityType = attrs.field()
    cluster_id: int = attrs.field()
    endpoint_id: int = attrs.field(default=1)
    cluster_type: ClusterType = attrs.field(default=ClusterType.Server)
    initially_disabled: bool = attrs.field(default=False)
    attribute_initialized_from_cache: bool = attrs.field(default=True)
    translation_key: str | None = attrs.field(default=None)
    fallback_name: str = attrs.field(validator=attrs.validators.instance_of(str))

    def __attrs_post_init__(self) -> None:
        """Validate the entity metadata."""
        self._validate()

    def __call__(self, device: CustomDeviceV2) -> None:
        """Add the entity metadata to the quirks v2 device."""
        self._validate()
        device.exposes_metadata[
            (self.endpoint_id, self.cluster_id, self.cluster_type)
        ].append(self)

    def _validate(self) -> None:
        """Validate the entity metadata."""
        has_device_class: bool = getattr(self, "device_class", None) is not None
        if self.translation_key is None and not has_device_class:
            raise ValueError(
                f"EntityMetadata must have a translation_key or device_class: {self}"
            )


@attrs.define(frozen=True, kw_only=True, repr=True)
class ZCLEnumMetadata(EntityMetadata):
    """Metadata for exposed ZCL enum based entity."""

    enum: type[Enum] = attrs.field()
    attribute_name: str = attrs.field()


@attrs.define(frozen=True, kw_only=True, repr=True)
class ZCLSensorMetadata(EntityMetadata):
    """Metadata for exposed ZCL attribute based sensor entity."""

    attribute_name: str | None = attrs.field(default=None)
    divisor: int | None = attrs.field(default=None)
    multiplier: int | None = attrs.field(default=None)
    unit: str | None = attrs.field(default=None)
    device_class: SensorDeviceClass | None = attrs.field(default=None)
    state_class: SensorStateClass | None = attrs.field(default=None)


@attrs.define(frozen=True, kw_only=True, repr=True)
class SwitchMetadata(EntityMetadata):
    """Metadata for exposed switch entity."""

    attribute_name: str = attrs.field()
    force_inverted: bool = attrs.field(default=False)
    invert_attribute_name: str | None = attrs.field(default=None)
    off_value: int = attrs.field(default=0)
    on_value: int = attrs.field(default=1)


@attrs.define(frozen=True, kw_only=True, repr=True)
class NumberMetadata(EntityMetadata):
    """Metadata for exposed number entity."""

    attribute_name: str = attrs.field()
    min: float | None = attrs.field(default=None)
    max: float | None = attrs.field(default=None)
    step: float | None = attrs.field(default=None)
    unit: str | None = attrs.field(default=None)
    mode: str | None = attrs.field(default=None)
    multiplier: float | None = attrs.field(default=None)
    device_class: NumberDeviceClass | None = attrs.field(default=None)


@attrs.define(frozen=True, kw_only=True, repr=True)
class BinarySensorMetadata(EntityMetadata):
    """Metadata for exposed binary sensor entity."""

    attribute_name: str = attrs.field()
    device_class: BinarySensorDeviceClass | None = attrs.field(default=None)


@attrs.define(frozen=True, kw_only=True, repr=True)
class WriteAttributeButtonMetadata(EntityMetadata):
    """Metadata for exposed button entity that writes an attribute when pressed."""

    attribute_name: str = attrs.field()
    attribute_value: int = attrs.field()


@attrs.define(frozen=True, kw_only=True, repr=True)
class ZCLCommandButtonMetadata(EntityMetadata):
    """Metadata for exposed button entity that executes a ZCL command when pressed."""

    command_name: str = attrs.field()
    args: tuple = attrs.field(default=tuple)
    kwargs: frozendict[str, Any] = attrs.field(default=frozendict, converter=frozendict)


@attrs.define(frozen=True, kw_only=True, repr=True)
class ManufacturerModelMetadata:
    """Metadata for manufacturers and models to apply this quirk to."""

    manufacturer: str = attrs.field(default=None)
    model: str = attrs.field(default=None)


@attrs.define(frozen=True, kw_only=True, repr=True)
class FriendlyNameMetadata:
    """Metadata to rename a device."""

    model: str = attrs.field()
    manufacturer: str = attrs.field()


@attrs.define(frozen=True, kw_only=True, repr=True)
class QuirksV2RegistryEntry:
    """Quirks V2 registry entry."""

    quirk_file: str = attrs.field(default=None, eq=False)
    quirk_file_line: int = attrs.field(default=None, eq=False)
    manufacturer_model_metadata: tuple[ManufacturerModelMetadata] = attrs.field(
        factory=tuple
    )
    friendly_name: FriendlyNameMetadata | None = attrs.field(default=None)
    filters: tuple[FilterType] = attrs.field(factory=tuple)
    custom_device_class: type[CustomDeviceV2] | None = attrs.field(default=None)
    device_node_descriptor: NodeDescriptor | None = attrs.field(default=None)
    skip_device_configuration: bool = attrs.field(default=False)
    adds_metadata: tuple[AddsMetadata] = attrs.field(factory=tuple)
    removes_metadata: tuple[RemovesMetadata] = attrs.field(factory=tuple)
    replaces_metadata: tuple[ReplacesMetadata] = attrs.field(factory=tuple)
    replaces_cluster_occurrences_metadata: tuple[ReplaceClusterOccurrencesMetadata] = (
        attrs.field(factory=tuple)
    )
    entity_metadata: tuple[
        ZCLEnumMetadata
        | SwitchMetadata
        | NumberMetadata
        | BinarySensorMetadata
        | WriteAttributeButtonMetadata
        | ZCLCommandButtonMetadata
    ] = attrs.field(factory=tuple)
    device_automation_triggers_metadata: frozendict[
        tuple[str, str], frozendict[str, str]
    ] = attrs.field(factory=frozendict, converter=deepfreeze)

    def matches_device(self, device: Device) -> bool:
        """Determine if this quirk should be applied to the passed in device."""
        return all(_filter(device) for _filter in self.filters)

    def create_device(self, device: Device) -> CustomDeviceV2:
        """Create the quirked device."""
        if self.custom_device_class:
            return self.custom_device_class(
                device.application, device.ieee, device.nwk, device, self
            )
        return CustomDeviceV2(device.application, device.ieee, device.nwk, device, self)


class QuirkBuilder:
    """Quirks V2 registry entry."""

    def __init__(
        self,
        manufacturer: str | None = None,
        model: str | None = None,
        registry: DeviceRegistry = _DEVICE_REGISTRY,
    ) -> None:
        """Initialize the quirk builder."""
        if manufacturer and not model or model and not manufacturer:
            raise ValueError(
                "manufacturer and model must be provided together or completely omitted."
            )

        self.registry: DeviceRegistry = registry
        self.manufacturer_model_metadata: list[ManufacturerModelMetadata] = []
        self.friendly_name_metadata: FriendlyNameMetadata | None = None
        self.filters: list[FilterType] = []
        self.custom_device_class: type[CustomDeviceV2] | None = None
        self.device_node_descriptor: NodeDescriptor | None = None
        self.skip_device_configuration: bool = False
        self.adds_metadata: list[AddsMetadata] = []
        self.removes_metadata: list[RemovesMetadata] = []
        self.replaces_metadata: list[ReplacesMetadata] = []
        self.replaces_cluster_occurrences_metadata: list[
            ReplaceClusterOccurrencesMetadata
        ] = []
        self.entity_metadata: list[
            ZCLEnumMetadata
            | SwitchMetadata
            | NumberMetadata
            | BinarySensorMetadata
            | WriteAttributeButtonMetadata
            | ZCLCommandButtonMetadata
        ] = []
        self.device_automation_triggers_metadata: dict[
            tuple[str, str], dict[str, str]
        ] = {}

        stack: list[inspect.FrameInfo] = inspect.stack()
        caller: inspect.FrameInfo = stack[1]
        self.quirk_file = pathlib.Path(caller.filename)
        self.quirk_file_line = caller.lineno

        if manufacturer and model:
            self.applies_to(manufacturer, model)

        UNBUILT_QUIRK_BUILDERS.append(self)

    def applies_to(self, manufacturer: str, model: str) -> QuirkBuilder:
        """Register this quirks v2 entry for the specified manufacturer and model."""
        self.manufacturer_model_metadata.append(
            ManufacturerModelMetadata(manufacturer=manufacturer, model=model)
        )
        return self

    # backward compatibility
    also_applies_to = applies_to

    def filter(self, filter_function: FilterType) -> QuirkBuilder:
        """Add a filter and returns self.

        The filter function should take a single argument, a zigpy.device.Device
        instance, and return a boolean if the condition the filter is testing
        passes.

        Ex: def some_filter(device: zigpy.device.Device) -> bool:
        """
        self.filters.append(filter_function)
        return self

    def device_class(self, custom_device_class: type[CustomDeviceV2]) -> QuirkBuilder:
        """Set the custom device class to be used in this quirk and returns self.

        The custom device class must be a subclass of CustomDeviceV2.
        """
        assert issubclass(
            custom_device_class, CustomDeviceV2
        ), f"{custom_device_class} is not a subclass of CustomDeviceV2"
        self.custom_device_class = custom_device_class
        return self

    def node_descriptor(self, node_descriptor: NodeDescriptor) -> QuirkBuilder:
        """Set the node descriptor and returns self.

        The node descriptor must be a NodeDescriptor instance and it will be used
        to replace the node descriptor of the device when the quirk is applied.
        """
        self.device_node_descriptor = node_descriptor.freeze()
        return self

    def skip_configuration(self, skip_configuration: bool = True) -> QuirkBuilder:
        """Set the skip_configuration and returns self.

        If skip_configuration is True, reporting configuration will not be
        applied to any cluster on this device.
        """
        self.skip_device_configuration = skip_configuration
        return self

    def adds(
        self,
        cluster: int | type[Cluster | CustomCluster],
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        constant_attributes: dict[ZCLAttributeDef, typing.Any] | None = None,
    ) -> QuirkBuilder:
        """Add an AddsMetadata entry and returns self.

        This method allows adding a cluster to a device when the quirk is applied.

        If cluster is an int, it will be used as the cluster_id. If cluster is a
        subclass of Cluster or CustomCluster, it will be used to create a new
        cluster instance.

        If constant_attributes is provided, it should be a dictionary of ZCLAttributeDef
        instances and their values. These attributes will be added to the cluster when
        the quirk is applied and the values will be constant.
        """
        add = AddsMetadata(
            endpoint_id=endpoint_id,
            cluster=cluster,
            cluster_type=cluster_type,
            constant_attributes=constant_attributes or {},
        )
        self.adds_metadata.append(add)
        return self

    def removes(
        self,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
    ) -> QuirkBuilder:
        """Add a RemovesMetadata entry and returns self.

        This method allows removing a cluster from a device when the quirk is applied.
        """
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
    ) -> QuirkBuilder:
        """Add a ReplacesMetadata entry and returns self.

        This method allows replacing a cluster on a device when the quirk is applied.

        replacement_cluster_class should be a subclass of Cluster or CustomCluster and
        will be used to create a new cluster instance to replace the existing cluster.

        If cluster_id is provided, it will be used as the cluster_id for the cluster to
        be removed. If cluster_id is not provided, the cluster_id of the replacement
        cluster will be used.
        """
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

    def replace_cluster_occurrences(
        self,
        replacement_cluster_class: type[Cluster | CustomCluster],
        replace_server_instances: bool = True,
        replace_client_instances: bool = True,
    ) -> QuirkBuilder:
        """Add a ReplaceClusterOccurrencesMetadata entry and returns self.

        This method allows replacing a cluster on a device across all endpoints
        for the specified cluster types when the quirk is applied.

        replacement_cluster_class should be a subclass of Cluster or CustomCluster and
        will be used to create a new cluster instance to replace the existing cluster.

        replace_server_instances and replace_client_instances control the cluster types
        that will be replaced. If replace_server_instances is True, all server instances
        of the cluster will be replaced. If replace_client_instances is True, all client
        instances of the cluster will be replaced.
        """
        types = []
        if replace_server_instances:
            types.append(ClusterType.Server)
        if replace_client_instances:
            types.append(ClusterType.Client)
        self.replaces_cluster_occurrences_metadata.append(
            ReplaceClusterOccurrencesMetadata(
                cluster_types=tuple(types),
                cluster=replacement_cluster_class,
            )
        )
        return self

    def enum(
        self,
        attribute_name: str,
        enum_class: type[Enum],
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        entity_platform: EntityPlatform = EntityPlatform.SELECT,
        entity_type: EntityType = EntityType.CONFIG,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing ZCLEnumMetadata and return self.

        This method allows exposing an enum based entity in Home Assistant.
        """
        self.entity_metadata.append(
            ZCLEnumMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=entity_platform,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                attribute_initialized_from_cache=attribute_initialized_from_cache,
                translation_key=translation_key,
                fallback_name=fallback_name,
                enum=enum_class,
                attribute_name=attribute_name,
            )
        )
        return self

    def sensor(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        divisor: int = 1,
        multiplier: int = 1,
        entity_type: EntityType = EntityType.STANDARD,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing ZCLSensorMetadata and return self.

        This method allows exposing a sensor entity in Home Assistant.
        """
        self.entity_metadata.append(
            ZCLSensorMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.SENSOR,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                attribute_initialized_from_cache=attribute_initialized_from_cache,
                translation_key=translation_key,
                fallback_name=fallback_name,
                attribute_name=attribute_name,
                divisor=divisor,
                multiplier=multiplier,
                unit=unit,
                device_class=device_class,
                state_class=state_class,
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
        off_value: int = 0,
        on_value: int = 1,
        entity_platform=EntityPlatform.SWITCH,
        entity_type: EntityType = EntityType.CONFIG,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing SwitchMetadata and return self.

        This method allows exposing a switch entity in Home Assistant.
        """
        self.entity_metadata.append(
            SwitchMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=entity_platform,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                attribute_initialized_from_cache=attribute_initialized_from_cache,
                translation_key=translation_key,
                fallback_name=fallback_name,
                attribute_name=attribute_name,
                force_inverted=force_inverted,
                invert_attribute_name=invert_attribute_name,
                off_value=off_value,
                on_value=on_value,
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
        entity_type: EntityType = EntityType.CONFIG,
        device_class: NumberDeviceClass | None = None,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing NumberMetadata and return self.

        This method allows exposing a number entity in Home Assistant.
        """
        self.entity_metadata.append(
            NumberMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.NUMBER,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                attribute_initialized_from_cache=attribute_initialized_from_cache,
                translation_key=translation_key,
                fallback_name=fallback_name,
                attribute_name=attribute_name,
                min=min_value,
                max=max_value,
                step=step,
                unit=unit,
                mode=mode,
                multiplier=multiplier,
                device_class=device_class,
            )
        )
        return self

    def binary_sensor(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.DIAGNOSTIC,
        device_class: BinarySensorDeviceClass | None = None,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing BinarySensorMetadata and return self.

        This method allows exposing a binary sensor entity in Home Assistant.
        """
        self.entity_metadata.append(
            BinarySensorMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.BINARY_SENSOR,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                attribute_initialized_from_cache=attribute_initialized_from_cache,
                translation_key=translation_key,
                fallback_name=fallback_name,
                attribute_name=attribute_name,
                device_class=device_class,
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
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing WriteAttributeButtonMetadata and return self.

        This method allows exposing a button entity in Home Assistant that writes
        a value to an attribute when pressed.
        """
        self.entity_metadata.append(
            WriteAttributeButtonMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.BUTTON,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                attribute_initialized_from_cache=attribute_initialized_from_cache,
                translation_key=translation_key,
                fallback_name=fallback_name,
                attribute_name=attribute_name,
                attribute_value=attribute_value,
            )
        )
        return self

    def command_button(
        self,
        command_name: str,
        cluster_id: int,
        command_args: tuple | None = None,
        command_kwargs: dict[str, Any] | None = None,
        cluster_type: ClusterType = ClusterType.Server,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.CONFIG,
        initially_disabled: bool = False,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing ZCLCommandButtonMetadata and return self.

        This method allows exposing a button entity in Home Assistant that executes
        a ZCL command when pressed.
        """
        self.entity_metadata.append(
            ZCLCommandButtonMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EntityPlatform.BUTTON,
                entity_type=entity_type,
                initially_disabled=initially_disabled,
                translation_key=translation_key,
                fallback_name=fallback_name,
                command_name=command_name,
                args=command_args if command_args is not None else (),
                kwargs=command_kwargs if command_kwargs is not None else frozendict(),
            )
        )
        return self

    def device_automation_triggers(
        self, device_automation_triggers: dict[tuple[str, str], dict[str, str]]
    ) -> QuirkBuilder:
        """Add device automation triggers and returns self."""
        self.device_automation_triggers_metadata.update(device_automation_triggers)
        return self

    def friendly_name(self, *, model: str, manufacturer: str) -> QuirkBuilder:
        """Renames the device."""
        self.friendly_name_metadata = FriendlyNameMetadata(
            model=model, manufacturer=manufacturer
        )
        return self

    def add_to_registry(self) -> QuirksV2RegistryEntry:
        """Build the quirks v2 registry entry."""
        if not self.manufacturer_model_metadata:
            raise ValueError(
                "At least one manufacturer and model must be specified for a v2 quirk."
            )
        quirk: QuirksV2RegistryEntry = QuirksV2RegistryEntry(
            manufacturer_model_metadata=tuple(self.manufacturer_model_metadata),
            friendly_name=self.friendly_name_metadata,
            quirk_file=self.quirk_file,
            quirk_file_line=self.quirk_file_line,
            filters=tuple(self.filters),
            custom_device_class=self.custom_device_class,
            device_node_descriptor=self.device_node_descriptor,
            skip_device_configuration=self.skip_device_configuration,
            adds_metadata=tuple(self.adds_metadata),
            removes_metadata=tuple(self.removes_metadata),
            replaces_metadata=tuple(self.replaces_metadata),
            replaces_cluster_occurrences_metadata=tuple(
                self.replaces_cluster_occurrences_metadata
            ),
            entity_metadata=tuple(self.entity_metadata),
            device_automation_triggers_metadata=self.device_automation_triggers_metadata,
        )
        for manufacturer_model in self.manufacturer_model_metadata:
            self.registry.add_to_registry_v2(
                manufacturer_model.manufacturer, manufacturer_model.model, quirk
            )

        if self in UNBUILT_QUIRK_BUILDERS:
            UNBUILT_QUIRK_BUILDERS.remove(self)

        return quirk

    def clone(self, omit_man_model_data=True) -> QuirkBuilder:
        """Clone this QuirkBuilder potentially omitting manufacturer and model data."""
        new_builder = deepcopy(self)
        new_builder.registry = self.registry
        if omit_man_model_data:
            new_builder.manufacturer_model_metadata = []
        return new_builder


def add_to_registry_v2(
    manufacturer: str, model: str, registry: DeviceRegistry = _DEVICE_REGISTRY
) -> QuirkBuilder:
    """Add an entry to the registry."""
    _LOGGER.error(
        "add_to_registry_v2 is deprecated and will be removed in a future release. "
        "Please QuirkBuilder() instead and ensure you call add_to_registry()."
    )
    return QuirkBuilder(manufacturer, model, registry=registry)
