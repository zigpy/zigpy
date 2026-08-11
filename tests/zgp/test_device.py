"""Tests for Green Power Device model."""

from __future__ import annotations

import zigpy.types as t
from zigpy.zgp.device import (
    GP_IEEE_SUFFIX,
    GPDevice,
    ieee_to_source_id,
    source_id_to_ieee,
)
from zigpy.zgp.types import SecurityLevel


def test_basic_conversion():
    """SourceID should be stored in lower 4 bytes (LE)."""
    ieee = source_id_to_ieee(0x12345678)
    ieee_bytes = bytes(ieee)
    assert ieee_bytes[:4] == b"\x78\x56\x34\x12"
    assert ieee_bytes[4:] == GP_IEEE_SUFFIX


def test_zero_source_id():
    ieee = source_id_to_ieee(0)
    ieee_bytes = bytes(ieee)
    assert ieee_bytes == b"\x00" * 8


def test_max_source_id():
    ieee = source_id_to_ieee(0xFFFFFFFF)
    ieee_bytes = bytes(ieee)
    assert ieee_bytes[:4] == b"\xff\xff\xff\xff"
    assert ieee_bytes[4:] == GP_IEEE_SUFFIX


def test_returns_eui64():
    ieee = source_id_to_ieee(0x12345678)
    assert isinstance(ieee, t.EUI64)
    assert len(ieee) == 8


def test_deterministic():
    """Same sourceID should always produce same IEEE."""
    assert source_id_to_ieee(0xAABBCCDD) == source_id_to_ieee(0xAABBCCDD)


def test_different_source_ids_different_ieee():
    assert source_id_to_ieee(0x11111111) != source_id_to_ieee(0x22222222)


def test_roundtrip():
    """Converting sourceID → IEEE → sourceID should be identity."""
    original = 0x12345678
    ieee = source_id_to_ieee(original)
    result = ieee_to_source_id(ieee)
    assert result == original


def test_non_gp_ieee_returns_none():
    """Real IEEE addresses should return None."""
    real_ieee = t.EUI64.convert("00:11:22:33:44:55:66:77")
    assert ieee_to_source_id(real_ieee) is None


def test_zero_roundtrip():
    ieee = source_id_to_ieee(0)
    assert ieee_to_source_id(ieee) == 0


def test_max_roundtrip():
    ieee = source_id_to_ieee(0xFFFFFFFF)
    assert ieee_to_source_id(ieee) == 0xFFFFFFFF


def test_creation():
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    assert dev.source_id == 0x12345678
    assert dev.device_id == 0x02
    assert dev.security_level == SecurityLevel.NoSecurity
    assert dev.security_key is None
    assert dev.frame_counter == 0


def test_ieee_property():
    dev = GPDevice(source_id=0xAABBCCDD, device_id=0x02)
    expected = source_id_to_ieee(0xAABBCCDD)
    assert dev.ieee == expected


def test_update_frame_counter_accepts_higher():
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
    assert dev.update_frame_counter(11) is True
    assert dev.frame_counter == 11
    assert dev.last_seen is not None


def test_update_frame_counter_rejects_same():
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
    assert dev.update_frame_counter(10) is False
    assert dev.frame_counter == 10


def test_update_frame_counter_rejects_lower():
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
    assert dev.update_frame_counter(5) is False
    assert dev.frame_counter == 10


def test_update_frame_counter_rejects_zero():
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=1)
    assert dev.update_frame_counter(0) is False


def test_update_frame_counter_sequential():
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=0)
    assert dev.update_frame_counter(1) is True
    assert dev.update_frame_counter(2) is True
    assert dev.update_frame_counter(100) is True
    assert dev.update_frame_counter(100) is False
    assert dev.update_frame_counter(99) is False
    assert dev.update_frame_counter(101) is True
    assert dev.frame_counter == 101


def test_repr():
    dev = GPDevice(
        source_id=0x12345678,
        device_id=0x02,
        security_level=SecurityLevel.Encrypted,
    )
    r = repr(dev)
    assert r.startswith("<GPDevice")
    assert r.endswith(">")
    assert "12345678" in r.upper()
    assert "Encrypted" in r
