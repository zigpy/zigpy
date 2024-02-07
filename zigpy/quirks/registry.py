from __future__ import annotations

import collections
import dataclasses
import enum
import itertools
import logging
import types
import typing

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_MODELS_INFO,
)
from zigpy.endpoint import Endpoint
from zigpy.exceptions import MultipleQuirksMatchException
import zigpy.quirks
from zigpy.typing import CustomDeviceType, DeviceType
from zigpy.zcl.foundation import ZCLAttributeDef

_LOGGER = logging.getLogger(__name__)

TYPE_MANUF_QUIRKS_DICT = typing.Dict[
    typing.Optional[str],
    typing.Dict[typing.Optional[str], typing.List["zigpy.quirks.CustomDevice"]],
]


class DeviceRegistry:
    def __init__(self, *args, **kwargs) -> None:
        self._registry: TYPE_MANUF_QUIRKS_DICT = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        self._registry_v2: dict[tuple[str, str], list[QuirksV2RegistryEntry]] = {}

    def add_to_registry_v2(self, manufacturer, model):
        """Add an entry to the registry."""
        key = (manufacturer, model)
        entry = QuirksV2RegistryEntry()
        entry.registry = self._registry_v2
        if key not in self._registry_v2:
            self._registry_v2[key] = []
        self._registry_v2[key].append(entry)
        return entry

    def add_to_registry(self, custom_device: CustomDeviceType) -> None:
        """Add a device to the registry"""
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                if custom_device not in self.registry[manuf][model]:
                    self.registry[manuf][model].insert(0, custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            if custom_device not in self.registry[manufacturer][model]:
                self.registry[manufacturer][model].insert(0, custom_device)

    def remove(self, custom_device: CustomDeviceType) -> None:
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                self.registry[manuf][model].remove(custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            self.registry[manufacturer][model].remove(custom_device)

    def get_device(self, device: DeviceType) -> CustomDeviceType | DeviceType:
        """Get a CustomDevice object, if one is available"""
        if isinstance(device, zigpy.quirks.CustomDevice) or isinstance(
            device, zigpy.quirks.CustomDeviceV2
        ):
            return device

        key = (device.manufacturer, device.model)
        if key in self._registry_v2:
            matches: list[QuirksV2RegistryEntry] = []
            entries = self._registry_v2[key]
            if len(entries) == 1:
                if entries[0].matches_device(device):
                    matches.append(entries[0])
            else:
                for entry in entries:
                    if entry.matches_device(device):
                        matches.append(entry)
            if len(matches) > 1:
                raise MultipleQuirksMatchException(
                    f"Multiple matches found for device {device}: {matches}"
                )
            if len(matches) == 1:
                quirk_entry: QuirksV2RegistryEntry = matches[0]
                if quirk_entry.custom_device_class:
                    return quirk_entry.custom_device_class(
                        device.application, device.ieee, device.nwk, device, quirk_entry
                    )
                return zigpy.quirks.CustomDeviceV2(
                    device.application, device.ieee, device.nwk, device, quirk_entry
                )

        _LOGGER.debug(
            "Checking quirks for %s %s (%s)",
            device.manufacturer,
            device.model,
            device.ieee,
        )
        for candidate in itertools.chain(
            self.registry[device.manufacturer][device.model],
            self.registry[device.manufacturer][None],
            self.registry[None][device.model],
            self.registry[None][None],
        ):
            matcher = signature_matches(candidate.signature)
            _LOGGER.debug("Considering %s", candidate)

            if not matcher(device):
                continue

            _LOGGER.debug(
                "Found custom device replacement for %s: %s", device.ieee, candidate
            )
            device = candidate(device._application, device.ieee, device.nwk, device)
            break

        return device

    @property
    def registry(self) -> TYPE_MANUF_QUIRKS_DICT:
        return self._registry

    def __contains__(self, device: CustomDeviceType) -> bool:
        manufacturer, model = device.signature.get(
            SIG_MODELS_INFO,
            [(device.signature.get(SIG_MANUFACTURER), device.signature.get(SIG_MODEL))],
        )[0]

        return device in itertools.chain(
            self.registry[manufacturer][model],
            self.registry[manufacturer][None],
            self.registry[None][None],
        )


MatcherType = typing.Callable[
    [zigpy.device.Device],
    bool,
]


def signature_matches(
    signature: dict[str, typing.Any],
) -> MatcherType:
    """Return True if device matches signature."""

    def _match(a: dict | typing.Iterable, b: dict | typing.Iterable) -> bool:
        return set(a) == set(b)

    def _filter(device: zigpy.device.Device) -> bool:
        """Return True if device matches signature."""
        if device.model != signature.get(SIG_MODEL, device.model):
            _LOGGER.debug("Fail, because device model mismatch: '%s'", device.model)
            return False

        if device.manufacturer != signature.get(SIG_MANUFACTURER, device.manufacturer):
            _LOGGER.debug(
                "Fail, because device manufacturer mismatch: '%s'",
                device.manufacturer,
            )
            return False

        dev_ep = set(device.endpoints) - {0}

        sig = signature.get(SIG_ENDPOINTS)
        if sig is None:
            return False

        if not _match(sig, dev_ep):
            _LOGGER.debug(
                "Fail because endpoint list mismatch: %s %s",
                set(sig.keys()),
                dev_ep,
            )
            return False

        if not all(
            device[eid].profile_id
            == sig[eid].get(SIG_EP_PROFILE, device[eid].profile_id)
            for eid in sig
        ):
            _LOGGER.debug("Fail because profile_id mismatch on at least one endpoint")
            return False

        if not all(
            device[eid].device_type
            == sig[eid].get(SIG_EP_TYPE, device[eid].device_type)
            for eid in sig
        ):
            _LOGGER.debug("Fail because device_type mismatch on at least one endpoint")
            return False

        if not all(
            _match(device[eid].in_clusters, ep.get(SIG_EP_INPUT, []))
            for eid, ep in sig.items()
        ):
            _LOGGER.debug(
                "Fail because input cluster mismatch on at least one endpoint"
            )
            return False

        if not all(
            _match(device[eid].out_clusters, ep.get(SIG_EP_OUTPUT, []))
            for eid, ep in sig.items()
        ):
            _LOGGER.debug(
                "Fail because output cluster mismatch on at least one endpoint"
            )
            return False

        _LOGGER.debug(
            "Device matches filter signature - device ieee[%s]: filter signature[%s]",
            device.ieee,
            signature,
        )
        return True

    return _filter


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

    cluster: int | type[zigpy.zcl.Cluster | zigpy.quirks.CustomCluster]
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: zigpy.zcl.ClusterType = dataclasses.field(
        default=zigpy.zcl.ClusterType.Server
    )
    zcl_init_attributes: set[ZCLAttributeDef] = dataclasses.field(default_factory=set)
    constant_attributes: dict[ZCLAttributeDef, typing.Any] = dataclasses.field(
        default_factory=dict
    )
    zcl_report_config: dict[ZCLAttributeDef, tuple[int, int, int]] = dataclasses.field(
        default_factory=dict
    )

    def __call__(self, device: zigpy.quirks.CustomDeviceV2):
        """Process the add."""
        endpoint: Endpoint = device.endpoints[self.endpoint_id]
        if self.cluster_type == zigpy.zcl.ClusterType.Server:
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
    cluster_type: zigpy.zcl.ClusterType = dataclasses.field(
        default=zigpy.zcl.ClusterType.Server
    )

    def __call__(self, device: zigpy.quirks.CustomDeviceV2):
        """Process the remove."""
        endpoint = device.endpoints[self.endpoint_id]
        if self.cluster_type == zigpy.zcl.ClusterType.Server:
            endpoint.in_clusters.pop(self.cluster_id, None)
        else:
            endpoint.out_clusters.pop(self.cluster_id, None)


@dataclasses.dataclass(frozen=True)
class ReplacesMetadata:
    """Replaces metadata for replacing a cluster on a device."""

    remove: RemovesMetadata
    add: AddsMetadata

    def __call__(self, device: zigpy.quirks.CustomDeviceV2):
        """Process the replace."""
        self.remove(device)
        self.add(device)


@dataclasses.dataclass(frozen=True)
class PatchesMetadata:
    """Patches metadata for replacing a method on a cluster on a device."""

    replacement_method: typing.Callable
    cluster_id: int
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: zigpy.zcl.ClusterType = dataclasses.field(
        default=zigpy.zcl.ClusterType.Server
    )

    def __call__(self, device: zigpy.quirks.CustomDeviceV2):
        """Apply the patch."""
        endpoint = device.endpoints[self.endpoint_id]
        cluster = (
            endpoint.in_clusters[self.cluster_id]
            if self.cluster_type == zigpy.zcl.ClusterType.Server
            else endpoint.out_clusters[self.cluster_id]
        )
        method_name = self.replacement_method.__name__
        cluster[method_name] = types.MethodType(self.replacement_method, cluster)


class EntityType(enum.Enum):
    """Entity type."""

    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
    STANDARD = "standard"


class EnumEntityPlatform(enum.Enum):
    """Enum entity platform."""

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
    """Metadata for exposed button entit that writes an attribute when pressed."""

    attribute_name: str
    attribute_value: int


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
    )
    entity_platform: EnumEntityPlatform
    entity_type: EntityType
    cluster_id: int
    endpoint_id: int = dataclasses.field(default=1)
    cluster_type: zigpy.zcl.ClusterType = dataclasses.field(
        default=zigpy.zcl.ClusterType.Server
    )

    def __call__(self, device: zigpy.quirks.CustomDeviceV2):
        """Add the entity metadata to the quirks v2 device."""
        device.exposes_metadata[
            (self.endpoint_id, self.cluster_id, self.cluster_type)
        ].append(self)


@dataclasses.dataclass
class QuirksV2RegistryEntry:
    """Quirks V2 registry entry."""

    registry: dict[tuple[str, str], list[QuirksV2RegistryEntry]] = None
    filters: list[MatcherType] = dataclasses.field(default_factory=list)
    custom_device_class: type[zigpy.quirks.CustomDeviceV2] | None = dataclasses.field(
        default=None
    )
    adds_metadata: list[AddsMetadata] = dataclasses.field(default_factory=list)
    removes_metadata: list[RemovesMetadata] = dataclasses.field(default_factory=list)
    replaces_metadata: list[ReplacesMetadata] = dataclasses.field(default_factory=list)
    patches_metadata: list[PatchesMetadata] = dataclasses.field(default_factory=list)
    entity_metadata: list[EntityMetadata] = dataclasses.field(default_factory=list)
    device_automation_triggers_metadata: dict[
        tuple[str, str], dict[str, str]
    ] = dataclasses.field(default_factory=dict)

    def with_device_class(self, custom_device_class: type[zigpy.quirks.CustomDeviceV2]):
        """Set the custom device class and returns self."""
        assert issubclass(
            custom_device_class, zigpy.quirks.CustomDeviceV2
        ), f"{custom_device_class} is not a subclass of zigpy.quirks.CustomDeviceV2"
        self.custom_device_class = custom_device_class
        return self

    def adds(
        self,
        cluster: int | type[zigpy.zcl.Cluster | zigpy.quirks.CustomCluster],
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
        endpoint_id: int = 1,
        zcl_init_attributes: set[ZCLAttributeDef] | None = None,
        constant_attributes: dict[ZCLAttributeDef, typing.Any] | None = None,
        zcl_report_config: dict[ZCLAttributeDef, tuple[int, int, int]] | None = None,
    ):
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
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
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
        replacement_cluster_class: type[zigpy.zcl.Cluster | zigpy.quirks.CustomCluster],
        cluster_id: int | None = None,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
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
        replacement_method: typing.Callable,
        cluster_id: int,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
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

    def exposes_enum_entity(
        self,
        attribute_name: str,
        enum_class: type[enum.Enum],
        cluster_id: int,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.CONFIG,
        entity_platform: EnumEntityPlatform = EnumEntityPlatform.SELECT,
    ):
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

    def exposes_switch(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
        endpoint_id: int = 1,
        force_inverted: bool = False,
        invert_attribute_name: str | None = None,
        entity_platform=EnumEntityPlatform.SWITCH,
    ):
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

    def exposes_number(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
        endpoint_id: int = 1,
        min_value: float | None = None,
        max_value: float | None = None,
        step: float | None = None,
        unit: str | None = None,
        mode: str | None = None,
        multiplier: float | None = None,
    ):
        """Add a number and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EnumEntityPlatform.NUMBER,
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

    def exposes_binary_sensor(
        self,
        attribute_name: str,
        cluster_id: int,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
        endpoint_id: int = 1,
    ):
        """Add a binary sensor and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EnumEntityPlatform.BINARY_SENSOR,
                entity_type=EntityType.DIAGNOSTIC,
                entity_metadata=BinarySensorMetadata(
                    attribute_name=attribute_name,
                ),
            )
        )
        return self

    def exposes_write_attribute_button(
        self,
        attribute_name: str,
        attribute_value: int,
        cluster_id: int,
        cluster_type: zigpy.zcl.ClusterType = zigpy.zcl.ClusterType.Server,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.CONFIG,
    ):
        """Add a write attribute button and return self."""
        self.entity_metadata.append(
            EntityMetadata(
                endpoint_id=endpoint_id,
                cluster_id=cluster_id,
                cluster_type=cluster_type,
                entity_platform=EnumEntityPlatform.BUTTON,
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

    def matches(self, filter_function: MatcherType):
        """Add a filter and returns self."""
        self.filters.append(filter_function)
        return self

    def matches_device(self, device: zigpy.device.Device) -> bool:
        """Process all filters and return True if all pass."""
        return all(_filter(device) for _filter in self.filters)
