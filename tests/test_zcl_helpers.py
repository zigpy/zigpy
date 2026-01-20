"""Tests for ZCL helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from zigpy import zcl
import zigpy.endpoint
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.helpers import UnsupportedAttribute


class HelperCluster(zcl.Cluster):
    cluster_id = 0xABCD
    ep_attribute = "helper_cluster"

    class AttributeDefs(zcl.BaseAttributeDefs):
        attr1 = foundation.ZCLAttributeDef(id=0x0001, type=t.uint8_t)
        attr2 = foundation.ZCLAttributeDef(id=0x0002, type=t.uint8_t)
        attr3 = foundation.ZCLAttributeDef(id=0x0003, type=t.uint8_t)
        attr4 = foundation.ZCLAttributeDef(id=0x0004, type=t.uint8_t)
        attr4_manuf = foundation.ZCLAttributeDef(
            id=0x0004, type=t.uint8_t, manufacturer_code=0x1234
        )
        attr4_manuf_other = foundation.ZCLAttributeDef(
            id=0x0004, type=t.uint8_t, manufacturer_code=0x5678
        )


def test_cache_value_operations() -> None:
    """Test setting, getting, and removing cached values."""
    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = HelperCluster(endpoint)
    cache = cluster._attr_cache

    # Initially empty
    with pytest.raises(KeyError):
        cache.get_value(HelperCluster.AttributeDefs.attr1)

    # Set and get value with explicit timestamp
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    cache.set_value(HelperCluster.AttributeDefs.attr1, 42, last_updated=timestamp)
    assert cache.get_value(HelperCluster.AttributeDefs.attr1) == 42
    assert cache.get_last_updated(HelperCluster.AttributeDefs.attr1) == timestamp

    # Set without explicit timestamp
    cache.set_value(HelperCluster.AttributeDefs.attr2, "test")
    assert cache.get_value(HelperCluster.AttributeDefs.attr2) == "test"
    assert cache.get_last_updated(HelperCluster.AttributeDefs.attr2) is not None

    # Remove clears value
    cache.remove(HelperCluster.AttributeDefs.attr1)
    with pytest.raises(KeyError):
        cache.get_value(HelperCluster.AttributeDefs.attr1)


def test_cache_unsupported_attributes() -> None:
    """Test marking, checking, and clearing unsupported attributes."""
    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = HelperCluster(endpoint)
    cache = cluster._attr_cache

    assert not cache.is_unsupported(HelperCluster.AttributeDefs.attr1)

    # Mark unsupported
    cache.mark_unsupported(HelperCluster.AttributeDefs.attr1)
    assert cache.is_unsupported(HelperCluster.AttributeDefs.attr1)
    assert not cache.is_unsupported(HelperCluster.AttributeDefs.attr2)

    with pytest.raises(UnsupportedAttribute):
        cache.get_value(HelperCluster.AttributeDefs.attr1)

    with pytest.raises(UnsupportedAttribute):
        cache.get_last_updated(HelperCluster.AttributeDefs.attr1)

    # Setting value clears unsupported status
    cache.set_value(HelperCluster.AttributeDefs.attr1, 99)
    assert not cache.is_unsupported(HelperCluster.AttributeDefs.attr1)
    assert cache.get_value(HelperCluster.AttributeDefs.attr1) == 99

    # remove() also clears unsupported
    cache.mark_unsupported(HelperCluster.AttributeDefs.attr2)
    cache.remove(HelperCluster.AttributeDefs.attr2)
    assert not cache.is_unsupported(HelperCluster.AttributeDefs.attr2)


def test_cache_dict_interface() -> None:
    """Test dict-like interface."""
    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = HelperCluster(endpoint)
    cache = cluster._attr_cache

    assert 0x0001 not in cache

    cache[0x0001] = 100
    assert cache[0x0001] == 100
    assert 0x0001 in cache

    assert cache.get(0x0001) == 100
    assert cache.get(0x0099, "default") == "default"

    cache.mark_unsupported(HelperCluster.AttributeDefs.attr2)
    assert cache.get(0x0002, "unsupported") == "unsupported"
    assert 0x0002 not in cache

    cache.remove_unsupported(HelperCluster.AttributeDefs.attr2)
    cache.update({0x0001: 200, 0x0002: 300})
    assert cache[0x0001] == 200
    assert cache[0x0002] == 300


def test_cache_manufacturer_specific() -> None:
    """Test that manufacturer-specific attributes use separate cache keys."""
    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = HelperCluster(endpoint)
    cache = cluster._attr_cache

    # Same attribute ID but different manufacturer codes are separate
    cache.set_value(HelperCluster.AttributeDefs.attr4, "standard")
    cache.set_value(HelperCluster.AttributeDefs.attr4_manuf, "manuf_1234")
    cache.set_value(HelperCluster.AttributeDefs.attr4_manuf_other, "manuf_5678")
    assert cache.get_value(HelperCluster.AttributeDefs.attr4) == "standard"
    assert cache.get_value(HelperCluster.AttributeDefs.attr4_manuf) == "manuf_1234"
    assert (
        cache.get_value(HelperCluster.AttributeDefs.attr4_manuf_other) == "manuf_5678"
    )

    # Unsupported status is also separate
    cache.mark_unsupported(HelperCluster.AttributeDefs.attr4_manuf)
    assert cache.is_unsupported(HelperCluster.AttributeDefs.attr4_manuf)
    assert not cache.is_unsupported(HelperCluster.AttributeDefs.attr4)
    assert not cache.is_unsupported(HelperCluster.AttributeDefs.attr4_manuf_other)


def test_cache_legacy_fallback() -> None:
    """Test legacy cache for unknown attributes."""
    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = HelperCluster(endpoint)
    cache = cluster._attr_cache

    # Unknown attribute raises KeyError
    with pytest.raises(KeyError):
        cache[0x9999]

    # Legacy cache provides fallback
    cache.set_legacy_value(0x9999, "legacy_value")
    assert cache[0x9999] == "legacy_value"
    assert 0x9999 in cache


def test_cache_clone() -> None:
    """Test cloning a cache for a new cluster."""
    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster1 = HelperCluster(endpoint)
    cache1 = cluster1._attr_cache

    attr1 = HelperCluster.AttributeDefs.attr1
    attr2 = HelperCluster.AttributeDefs.attr2

    cache1.set_value(attr1, "value1")
    cache1.mark_unsupported(attr2)
    cache1.set_legacy_value(0x9999, "legacy")

    cluster2 = HelperCluster(endpoint)
    cache2 = cache1.clone(cluster2)

    # Clone has same data
    assert cache2.get_value(attr1) == "value1"
    assert cache2.is_unsupported(attr2)
    assert cache2._legacy_cache[0x9999].value == "legacy"

    # Modifications are independent
    cache2.set_value(attr1, "modified")
    assert cache1.get_value(attr1) == "value1"
    assert cache2.get_value(attr1) == "modified"
