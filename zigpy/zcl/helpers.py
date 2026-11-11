"""ZCL helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple

import zigpy.types as t
from zigpy.typing import UNDEFINED, UndefinedType

from .foundation import DataTypeId, TypeValue, ZCLAttributeDef

if TYPE_CHECKING:
    from . import Cluster

CacheKey = tuple[int, int | None]  # attribute id, manufacturer code

# The old attribute cache was a simple `attrid: value` mapping. This works 99.9% of the
# time but unfortunately some devices reuse the same attribute ID on a standard cluster
# for two separate purposes, using a manufacturer code to distinguish them. We migrate
# attributes safely at runtime, once a device quirk has loaded and we can tell for sure
# if the device has "colliding" attributes.
UNMIGRATED_MANUFACTURER_CODE = -1


class AttributeCacheRow(NamedTuple):
    """A row from the attribute cache table. This format is internal and will change."""

    ieee: t.EUI64
    endpoint_id: int
    cluster_type: int
    cluster_id: int
    attr_id: int
    manufacturer_code: int | None
    status: int
    value: Any
    data_type: DataTypeId | None
    last_updated: float

    @property
    def key(self) -> tuple[t.EUI64, int, int, int, int, int | None]:
        return (
            self.ieee,
            self.endpoint_id,
            self.cluster_type,
            self.cluster_id,
            self.attr_id,
            self.manufacturer_code,
        )


class AttributeCacheRowChange(NamedTuple):
    """An attribute cache row to replace, or to delete if `new` is `None`."""

    old: AttributeCacheRow
    new: AttributeCacheRow | None


@dataclass(kw_only=True)
class AttributeCacheLoadResult:
    """Database changes found while loading the attribute cache."""

    changes: list[AttributeCacheRowChange] = field(default_factory=list)

    # Rows whose value does not fit their attribute's type
    untyped: list[tuple[AttributeCacheRow, ZCLAttributeDef]] = field(
        default_factory=list
    )


def _convert_attribute_value(attr_def: ZCLAttributeDef, type_value: TypeValue) -> Any:
    """Convert a received attribute value into the attribute's declared type."""

    # `dataN` values are untyped bytes, so they are re-read with the declared type
    if isinstance(
        type_value.value,
        (
            t.data8,
            t.data16,
            t.data24,
            t.data32,
            t.data40,
            t.data48,
            t.data56,
            t.data64,
        ),
    ):
        value, rest = attr_def.type.deserialize(type_value.value.serialize())
        assert not rest

        return value

    return attr_def.type(type_value.value)


def _encode_attribute_value(
    attr_def: ZCLAttributeDef, value: Any
) -> tuple[DataTypeId | None, Any]:
    """Serialize a value with its attribute's type, or keep it as-is if it does not fit."""
    try:
        typed_value = attr_def.type(value)
    except (TypeError, ValueError):
        return None, value

    if typed_value != value or not hasattr(typed_value, "serialize"):
        return None, value

    return attr_def.zcl_type, typed_value.serialize()


def _decode_attribute_value(
    attr_def: ZCLAttributeDef | None, data_type: DataTypeId, data: bytes
) -> Any | UndefinedType:
    """Deserialize a value stored by `_encode_attribute_value`."""
    if attr_def is not None and attr_def.zcl_type == data_type:
        value, rest = attr_def.type.deserialize(data)
    elif data_type == DataTypeId.unk:
        # Only the attribute definition knows how to read a value of an unknown type
        return UNDEFINED
    else:
        type_value, rest = TypeValue.deserialize(bytes([data_type]) + data)
        value = (
            type_value.value
            if attr_def is None
            else _convert_attribute_value(attr_def, type_value)
        )

    assert not rest
    return value


@dataclass(kw_only=True, frozen=True)
class CacheItem:
    value: Any
    last_updated: datetime


class UnsupportedAttribute(Exception):
    """Exception for unsupported attributes."""

    def __init__(self, attr_def: ZCLAttributeDef) -> None:
        super().__init__(f"Attribute {attr_def} is unsupported")


class AttributeCache:
    def __init__(self, cluster) -> None:
        self._cluster = cluster

        self._cache: dict[CacheKey, CacheItem] = {}
        self._unsupported: set[CacheKey] = set()

        # FIXME: Legacy cache for unknown attributes from quirks that use the attribute
        # cache as generic data storage. Keyed by attr_id only.
        self._legacy_cache: dict[int, CacheItem] = {}

    def _cache_key(self, attr_def: ZCLAttributeDef) -> CacheKey:
        """Create a cache key using the effective manufacturer code."""
        return (
            attr_def.id,
            self._cluster._get_effective_manufacturer_code(attr_def),
        )

    def clear(self) -> None:
        self._cache.clear()
        self._unsupported.clear()
        self._legacy_cache.clear()

    def remove(self, attr_def: ZCLAttributeDef) -> None:
        key = self._cache_key(attr_def)
        self._cache.pop(key, None)
        self._unsupported.discard(key)

    def _raise_if_unsupported(self, attr_def: ZCLAttributeDef) -> None:
        if self._cache_key(attr_def) in self._unsupported:
            raise UnsupportedAttribute(attr_def)

    def remove_unsupported(self, attr_def: ZCLAttributeDef) -> None:
        self._unsupported.discard(self._cache_key(attr_def))

    def mark_unsupported(self, attr_def: ZCLAttributeDef) -> None:
        self._unsupported.add(self._cache_key(attr_def))

    def is_unsupported(self, attr_def: ZCLAttributeDef) -> bool:
        return self._cache_key(attr_def) in self._unsupported

    def get_value(self, attr_def: ZCLAttributeDef) -> Any:
        self._raise_if_unsupported(attr_def)
        return self._cache[self._cache_key(attr_def)].value

    def get_last_updated(self, attr_def: ZCLAttributeDef) -> datetime:
        self._raise_if_unsupported(attr_def)
        return self._cache[self._cache_key(attr_def)].last_updated

    def set_value(
        self,
        attr_def: ZCLAttributeDef,
        value: Any,
        *,
        last_updated: datetime | None = None,
    ) -> None:
        self.remove_unsupported(attr_def)
        self._cache[self._cache_key(attr_def)] = CacheItem(
            value=value,
            last_updated=datetime.now(UTC) if last_updated is None else last_updated,
        )

    def set_legacy_value(
        self, attr_id: int, value: Any, *, last_updated: datetime | None = None
    ) -> None:
        """Store a value in the legacy cache for unknown attributes."""
        self._legacy_cache[attr_id] = CacheItem(
            value=value,
            last_updated=datetime.now(UTC) if last_updated is None else last_updated,
        )

    def get(self, key: int, default: Any | None = None) -> Any:
        try:
            return self[key]
        except (KeyError, UnsupportedAttribute):
            return default

    def __getitem__(self, key: int) -> Any:
        try:
            return self.get_value(self._cluster.find_attribute(key))
        except KeyError:
            # Fall back to legacy cache for unknown attributes
            if key in self._legacy_cache:
                return self._legacy_cache[key].value
            raise

    def __setitem__(self, key: int, value: Any) -> None:
        attr_def = self._cluster.find_attribute(key)
        self.set_value(attr_def, value)

    def update(self, updates: dict[int, Any]) -> None:
        for attr_id, value in updates.items():
            self[attr_id] = value

    def __contains__(self, key: int) -> bool:
        try:
            self[key]
        except UnsupportedAttribute:
            return False
        except KeyError:
            return False
        else:
            return True

    def clone(self, cluster: Cluster) -> AttributeCache:
        """Create a copy of this cache for a new cluster."""
        new_cache = AttributeCache(cluster)
        new_cache._cache = self._cache.copy()
        new_cache._unsupported = self._unsupported.copy()
        new_cache._legacy_cache = self._legacy_cache.copy()
        return new_cache


@dataclass(frozen=True)
class ReportingConfig:
    """Reporting config for a ZCL attribute."""

    min_interval: int
    max_interval: int
    reportable_change: int
