"""ZCL helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from zigpy.typing import UNDEFINED

from .foundation import ZCLAttributeDef

if TYPE_CHECKING:
    from . import Cluster

CacheKey = tuple[int, int | None]  # attribute id, manufacturer code


def _cache_key(attr_def: ZCLAttributeDef) -> CacheKey:
    """Create a cache key, resolving UNDEFINED to None."""
    manuf_code = attr_def.manufacturer_code
    if manuf_code is UNDEFINED:
        manuf_code = None
    return (attr_def.id, manuf_code)


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

    def remove(self, attr_def: ZCLAttributeDef) -> None:
        key = _cache_key(attr_def)
        self._cache.pop(key, None)
        self._unsupported.discard(key)

    def _raise_if_unsupported(self, attr_def: ZCLAttributeDef) -> None:
        if _cache_key(attr_def) in self._unsupported:
            raise UnsupportedAttribute(attr_def)

    def remove_unsupported(self, attr_def: ZCLAttributeDef) -> None:
        self._unsupported.discard(_cache_key(attr_def))

    def mark_unsupported(self, attr_def: ZCLAttributeDef) -> None:
        self._unsupported.add(_cache_key(attr_def))

    def is_unsupported(self, attr_def: ZCLAttributeDef) -> bool:
        return _cache_key(attr_def) in self._unsupported

    def get_value(self, attr_def: ZCLAttributeDef) -> Any:
        self._raise_if_unsupported(attr_def)
        return self._cache[_cache_key(attr_def)].value

    def get_last_updated(self, attr_def: ZCLAttributeDef) -> datetime:
        self._raise_if_unsupported(attr_def)
        return self._cache[_cache_key(attr_def)].last_updated

    def set_value(
        self,
        attr_def: ZCLAttributeDef,
        value: Any,
        *,
        last_updated: datetime | None = None,
    ) -> None:
        self.remove_unsupported(attr_def)
        self._cache[_cache_key(attr_def)] = CacheItem(
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
