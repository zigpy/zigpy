"""Tests for Green Power Device model."""

from __future__ import annotations


import zigpy.types as t

from zigpy.zgp.device import (
    GP_IEEE_SUFFIX,
    GPDevice,
    ieee_to_source_id,
    source_id_to_ieee,
)
from zigpy.zgp.types import SecurityKeyType, SecurityLevel


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


def test_minimal_roundtrip():
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    data = dev.as_dict()
    restored = GPDevice.from_dict(data)

    assert restored.source_id == dev.source_id
    assert restored.device_id == dev.device_id
    assert restored.security_level == SecurityLevel.NoSecurity
    assert restored.security_key is None
    assert restored.frame_counter == 0


def test_full_roundtrip():
    dev = GPDevice(
        source_id=0xAABBCCDD,
        device_id=0x07,
        security_key=bytes(range(16)),
        security_level=SecurityLevel.Encrypted,
        security_key_type=SecurityKeyType.IndividualKey,
        frame_counter=42,
        manufacturer_id=0x1021,
        model_id=0x0002,
        gpd_commands=[0x20, 0x21, 0x22],
        server_clusters=[0x0006, 0x0008],
        client_clusters=[0x0300],
        mac_seq_num_capability=True,
        rx_on_capability=True,
        fixed_location=False,
    )

    data = dev.as_dict()
    restored = GPDevice.from_dict(data)

    assert restored.source_id == 0xAABBCCDD
    assert restored.device_id == 0x07
    assert bytes(restored.security_key) == bytes(range(16))
    assert restored.security_level == SecurityLevel.Encrypted
    assert restored.security_key_type == SecurityKeyType.IndividualKey
    assert restored.frame_counter == 42
    assert restored.manufacturer_id == 0x1021
    assert restored.model_id == 0x0002
    assert restored.gpd_commands == [0x20, 0x21, 0x22]
    assert restored.server_clusters == [0x0006, 0x0008]
    assert restored.client_clusters == [0x0300]
    assert restored.mac_seq_num_capability is True
    assert restored.rx_on_capability is True
    assert restored.fixed_location is False


def test_serialization_format():
    dev = GPDevice(
        source_id=0x12345678,
        device_id=0x02,
        security_key=b"\xaa" * 16,
        frame_counter=100,
    )
    data = dev.as_dict()

    assert data["source_id"] == 0x12345678
    assert data["device_id"] == 0x02
    assert data["security_key"] == "aa" * 16
    assert data["frame_counter"] == 100


def test_none_security_key_serialization():
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    data = dev.as_dict()
    assert data["security_key"] is None

    restored = GPDevice.from_dict(data)
    assert restored.security_key is None


def test_missing_optional_fields():
    """from_dict should handle missing optional fields gracefully."""
    data = {
        "source_id": 0x12345678,
        "device_id": 0x02,
    }
    dev = GPDevice.from_dict(data)
    assert dev.source_id == 0x12345678
    assert dev.device_id == 0x02
    assert dev.security_key is None
    assert dev.frame_counter == 0
    assert dev.gpd_commands == []
    assert dev.server_clusters == []
    assert dev.client_clusters == []
    assert dev.last_seen is None


def test_last_seen_roundtrip():
    """last_seen should survive serialization/deserialization."""

    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    dev.update_frame_counter(1)  # sets last_seen
    assert dev.last_seen is not None

    data = dev.as_dict()
    assert data["last_seen"] is not None
    assert isinstance(data["last_seen"], str)

    restored = GPDevice.from_dict(data)
    assert restored.last_seen is not None
    # Compare with microsecond tolerance (ISO 8601 roundtrip)
    assert abs((restored.last_seen - dev.last_seen).total_seconds()) < 0.001


def test_last_seen_none_roundtrip():
    """None last_seen should survive serialization."""
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    assert dev.last_seen is None

    data = dev.as_dict()
    assert data["last_seen"] is None

    restored = GPDevice.from_dict(data)
    assert restored.last_seen is None


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
