"""Tests for Green Power Device model."""

from __future__ import annotations

import pytest

import zigpy.types as t

from zigpy.zgp.device import (
    GP_IEEE_SUFFIX,
    GPDevice,
    ieee_to_source_id,
    source_id_to_ieee,
)
from zigpy.zgp.types import SecurityKeyType, SecurityLevel


class TestSourceIdToIeee:
    """Tests for sourceID to IEEE conversion."""

    def test_basic_conversion(self) -> None:
        """SourceID should be stored in lower 4 bytes (LE)."""
        ieee = source_id_to_ieee(0x12345678)
        ieee_bytes = bytes(ieee)
        assert ieee_bytes[:4] == b"\x78\x56\x34\x12"
        assert ieee_bytes[4:] == GP_IEEE_SUFFIX

    def test_zero_source_id(self) -> None:
        ieee = source_id_to_ieee(0)
        ieee_bytes = bytes(ieee)
        assert ieee_bytes == b"\x00" * 8

    def test_max_source_id(self) -> None:
        ieee = source_id_to_ieee(0xFFFFFFFF)
        ieee_bytes = bytes(ieee)
        assert ieee_bytes[:4] == b"\xFF\xFF\xFF\xFF"
        assert ieee_bytes[4:] == GP_IEEE_SUFFIX

    def test_returns_eui64(self) -> None:
        ieee = source_id_to_ieee(0x12345678)
        assert isinstance(ieee, t.EUI64)
        assert len(ieee) == 8

    def test_deterministic(self) -> None:
        """Same sourceID should always produce same IEEE."""
        assert source_id_to_ieee(0xAABBCCDD) == source_id_to_ieee(0xAABBCCDD)

    def test_different_source_ids_different_ieee(self) -> None:
        assert source_id_to_ieee(0x11111111) != source_id_to_ieee(0x22222222)


class TestIeeeToSourceId:
    """Tests for IEEE to sourceID reverse conversion."""

    def test_roundtrip(self) -> None:
        """Converting sourceID → IEEE → sourceID should be identity."""
        original = 0x12345678
        ieee = source_id_to_ieee(original)
        result = ieee_to_source_id(ieee)
        assert result == original

    def test_non_gp_ieee_returns_none(self) -> None:
        """Real IEEE addresses should return None."""
        real_ieee = t.EUI64.convert("00:11:22:33:44:55:66:77")
        assert ieee_to_source_id(real_ieee) is None

    def test_zero_roundtrip(self) -> None:
        ieee = source_id_to_ieee(0)
        assert ieee_to_source_id(ieee) == 0

    def test_max_roundtrip(self) -> None:
        ieee = source_id_to_ieee(0xFFFFFFFF)
        assert ieee_to_source_id(ieee) == 0xFFFFFFFF


class TestGPDevice:
    """Tests for GPDevice model."""

    def test_creation(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        assert dev.source_id == 0x12345678
        assert dev.device_id == 0x02
        assert dev.security_level == SecurityLevel.NoSecurity
        assert dev.security_key is None
        assert dev.frame_counter == 0

    def test_ieee_property(self) -> None:
        dev = GPDevice(source_id=0xAABBCCDD, device_id=0x02)
        expected = source_id_to_ieee(0xAABBCCDD)
        assert dev.ieee == expected

    def test_model_identifier(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        assert dev.model_identifier == "GreenPower_2"

        dev2 = GPDevice(source_id=0x12345678, device_id=0x07)
        assert dev2.model_identifier == "GreenPower_7"

        dev3 = GPDevice(source_id=0x12345678, device_id=254)
        assert dev3.model_identifier == "GreenPower_254"

    def test_update_frame_counter_accepts_higher(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
        assert dev.update_frame_counter(11) is True
        assert dev.frame_counter == 11
        assert dev.last_seen is not None

    def test_update_frame_counter_rejects_same(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
        assert dev.update_frame_counter(10) is False
        assert dev.frame_counter == 10

    def test_update_frame_counter_rejects_lower(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
        assert dev.update_frame_counter(5) is False
        assert dev.frame_counter == 10

    def test_update_frame_counter_rejects_zero(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=1)
        assert dev.update_frame_counter(0) is False

    def test_update_frame_counter_sequential(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=0)
        assert dev.update_frame_counter(1) is True
        assert dev.update_frame_counter(2) is True
        assert dev.update_frame_counter(100) is True
        assert dev.update_frame_counter(100) is False
        assert dev.update_frame_counter(99) is False
        assert dev.update_frame_counter(101) is True
        assert dev.frame_counter == 101


class TestGPDeviceSerialization:
    """Tests for GPDevice serialization/deserialization."""

    def test_minimal_roundtrip(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        data = dev.as_dict()
        restored = GPDevice.from_dict(data)

        assert restored.source_id == dev.source_id
        assert restored.device_id == dev.device_id
        assert restored.security_level == SecurityLevel.NoSecurity
        assert restored.security_key is None
        assert restored.frame_counter == 0

    def test_full_roundtrip(self) -> None:
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
        assert restored.security_key == bytes(range(16))
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

    def test_serialization_format(self) -> None:
        dev = GPDevice(
            source_id=0x12345678,
            device_id=0x02,
            security_key=b"\xAA" * 16,
            frame_counter=100,
        )
        data = dev.as_dict()

        assert data["source_id"] == 0x12345678
        assert data["device_id"] == 0x02
        assert data["security_key"] == "aa" * 16
        assert data["frame_counter"] == 100

    def test_none_security_key_serialization(self) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        data = dev.as_dict()
        assert data["security_key"] is None

        restored = GPDevice.from_dict(data)
        assert restored.security_key is None

    def test_missing_optional_fields(self) -> None:
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

    def test_last_seen_roundtrip(self) -> None:
        """last_seen should survive serialization/deserialization."""
        from datetime import UTC, datetime

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

    def test_last_seen_none_roundtrip(self) -> None:
        """None last_seen should survive serialization."""
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        assert dev.last_seen is None

        data = dev.as_dict()
        assert data["last_seen"] is None

        restored = GPDevice.from_dict(data)
        assert restored.last_seen is None


class TestGPDeviceRepr:
    """Tests for GPDevice string representation."""

    def test_repr(self) -> None:
        dev = GPDevice(
            source_id=0x12345678,
            device_id=0x02,
            security_level=SecurityLevel.Encrypted,
        )
        r = repr(dev)
        assert "0x12345678" in r.upper() or "12345678" in r.upper()
        assert "GreenPower_2" in r
        assert "Encrypted" in r
