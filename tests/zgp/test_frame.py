"""Tests for Green Power frame parsing."""

from __future__ import annotations

import struct

import pytest

from zigpy.zgp.frame import (
    GPChannelRequestPayload,
    GPCommissioningAppInfo,
    GPCommissioningExtendedOptions,
    GPCommissioningOptions,
    GPCommissioningPayload,
)
from zigpy.zgp.types import SecurityKeyType, SecurityLevel


class TestGPCommissioningOptions:
    """Tests for commissioning options byte parsing."""

    def test_all_bits_clear(self) -> None:
        opts = GPCommissioningOptions(0x00)
        assert not opts.mac_seq_num_capability
        assert not opts.rx_on_capability
        assert not opts.app_info_present
        assert not opts.pan_id_request
        assert not opts.security_key_request
        assert not opts.fixed_location

    def test_mac_seq_num_capability(self) -> None:
        opts = GPCommissioningOptions(0x01)
        assert opts.mac_seq_num_capability

    def test_rx_on_capability(self) -> None:
        opts = GPCommissioningOptions(0x02)  # bit 1
        assert opts.rx_on_capability

    def test_app_info_present(self) -> None:
        opts = GPCommissioningOptions(0x04)  # bit 2
        assert opts.app_info_present

    def test_pan_id_request(self) -> None:
        opts = GPCommissioningOptions(0x10)  # bit 4
        assert opts.pan_id_request

    def test_security_key_request(self) -> None:
        opts = GPCommissioningOptions(0x20)  # bit 5
        assert opts.security_key_request

    def test_fixed_location(self) -> None:
        opts = GPCommissioningOptions(0x40)  # bit 6
        assert opts.fixed_location

    def test_extended_options_present(self) -> None:
        opts = GPCommissioningOptions(0x80)  # bit 7
        assert bool(opts.raw & (1 << 7))

    def test_multiple_flags(self) -> None:
        # MAC seq (bit 0) + RX on (bit 1) + App info (bit 2)
        opts = GPCommissioningOptions(0x01 | 0x02 | 0x04)
        assert opts.mac_seq_num_capability
        assert opts.rx_on_capability
        assert opts.app_info_present
        assert not opts.pan_id_request


class TestGPCommissioningExtendedOptions:
    """Tests for extended commissioning options byte."""

    def test_security_level(self) -> None:
        # SecurityLevel.Encrypted = 0b11
        ext = GPCommissioningExtendedOptions(0x03)
        assert ext.security_level == SecurityLevel.Encrypted

    def test_key_type(self) -> None:
        # IndividualKey = 0b100, shifted left 2 = 0x10
        ext = GPCommissioningExtendedOptions(0x10)
        assert ext.key_type == SecurityKeyType.IndividualKey

    def test_key_present(self) -> None:
        ext = GPCommissioningExtendedOptions(0x20)
        assert ext.key_present
        assert not ext.key_encrypted

    def test_key_encrypted(self) -> None:
        ext = GPCommissioningExtendedOptions(0x60)  # key_present + key_encrypted
        assert ext.key_present
        assert ext.key_encrypted

    def test_outgoing_counter_present(self) -> None:
        ext = GPCommissioningExtendedOptions(0x80)
        assert ext.outgoing_counter_present

    def test_all_clear(self) -> None:
        ext = GPCommissioningExtendedOptions(0x00)
        assert ext.security_level == SecurityLevel.NoSecurity
        assert ext.key_type == SecurityKeyType.NoKey
        assert not ext.key_present
        assert not ext.key_encrypted
        assert not ext.outgoing_counter_present


class TestGPCommissioningAppInfo:
    """Tests for application information byte."""

    def test_manufacturer_id_present(self) -> None:
        info = GPCommissioningAppInfo(0x01)
        assert info.manufacturer_id_present

    def test_model_id_present(self) -> None:
        info = GPCommissioningAppInfo(0x02)
        assert info.model_id_present

    def test_gpd_commands_present(self) -> None:
        info = GPCommissioningAppInfo(0x04)
        assert info.gpd_commands_present

    def test_cluster_list_present(self) -> None:
        info = GPCommissioningAppInfo(0x08)
        assert info.cluster_list_present


class TestGPCommissioningPayload:
    """Tests for full commissioning payload parsing."""

    def test_minimal_payload(self) -> None:
        """Minimal commissioning: device_id + options (no extended, no app info)."""
        data = bytes([0x02, 0x00])  # device_id=2, options=0
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.device_id == 0x02
        assert not payload.options.mac_seq_num_capability
        assert payload.extended_options is None
        assert payload.security_key is None
        assert payload.app_info is None

    def test_with_extended_options_no_key(self) -> None:
        """Commissioning with extended options but no security key."""
        # options: bit 7 set (extended present) = 0x80
        # extended: security_level=0b11 (Encrypted), no key, no counter = 0x03
        data = bytes([0x02, 0x80, 0x03])
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.device_id == 0x02
        assert payload.extended_options is not None
        assert payload.extended_options.security_level == SecurityLevel.Encrypted
        assert not payload.extended_options.key_present
        assert payload.security_key is None

    def test_with_unencrypted_key(self) -> None:
        """Commissioning with security key present but not encrypted."""
        # options: extended present = 0x80
        # extended: Encrypted + key_present = 0x03 | 0x20 = 0x23
        security_key = bytes(range(16))
        data = bytes([0x02, 0x80, 0x23]) + security_key
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.extended_options is not None
        assert payload.extended_options.key_present
        assert not payload.extended_options.key_encrypted
        assert payload.security_key == security_key
        assert payload.key_mic is None

    def test_with_encrypted_key_and_mic(self) -> None:
        """Commissioning with encrypted security key and MIC."""
        # extended: Encrypted + key_present + key_encrypted = 0x03 | 0x20 | 0x40 = 0x63
        security_key = bytes(range(16))
        key_mic = 0xDEADBEEF
        data = bytes([0x07, 0x80, 0x63]) + security_key + struct.pack("<I", key_mic)
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.device_id == 0x07
        assert payload.extended_options is not None
        assert payload.extended_options.key_encrypted
        assert payload.security_key == security_key
        assert payload.key_mic == 0xDEADBEEF

    def test_with_outgoing_counter(self) -> None:
        """Commissioning with outgoing frame counter."""
        # extended: outgoing_counter_present = 0x80
        counter = 0x00001234
        data = bytes([0x02, 0x80, 0x80]) + struct.pack("<I", counter)
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.extended_options is not None
        assert payload.extended_options.outgoing_counter_present
        assert payload.outgoing_counter == 0x00001234

    def test_with_key_and_counter(self) -> None:
        """Commissioning with both key and outgoing counter."""
        # extended: key_present + outgoing_counter_present = 0x20 | 0x80 = 0xA0
        security_key = b"\xaa" * 16
        counter = 0x00000042
        data = bytes([0x02, 0x80, 0xA0]) + security_key + struct.pack("<I", counter)
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.security_key == security_key
        assert payload.outgoing_counter == 0x00000042

    def test_with_app_info_manufacturer_and_model(self) -> None:
        """Commissioning with application info: manufacturer and model ID."""
        # options: app_info_present = bit 2 = 0x04
        # app_info: manufacturer_id + model_id = 0x01 | 0x02 = 0x03
        manufacturer_id = 0x1234
        model_id = 0x5678
        data = (
            bytes([0x02, 0x04, 0x03])
            + struct.pack("<H", manufacturer_id)
            + struct.pack("<H", model_id)
        )
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.app_info is not None
        assert payload.manufacturer_id == 0x1234
        assert payload.model_id == 0x5678

    def test_with_gpd_commands(self) -> None:
        """Commissioning with GPD command list."""
        # options: app_info_present = bit 2 = 0x04
        # app_info: gpd_commands_present = 0x04
        commands = [0x20, 0x21, 0x22]  # Off, On, Toggle
        data = bytes([0x02, 0x04, 0x04, len(commands)]) + bytes(commands)
        payload = GPCommissioningPayload.from_bytes(data)

        assert payload.gpd_commands == commands

    def test_with_cluster_list(self) -> None:
        """Commissioning with server and client cluster lists."""
        # options: app_info_present = bit 2 = 0x04
        # app_info: cluster_list_present = 0x08
        server_clusters = [0x0006, 0x0008]  # On/Off, Level Control
        client_clusters = [0x0300]  # Color Control

        data = bytearray([0x02, 0x04, 0x08])
        # length byte: lower nibble = num_server, upper = num_client
        data.append(
            (len(server_clusters) & 0x0F) | ((len(client_clusters) & 0x0F) << 4)
        )
        for c in server_clusters:
            data.extend(struct.pack("<H", c))
        for c in client_clusters:
            data.extend(struct.pack("<H", c))

        payload = GPCommissioningPayload.from_bytes(bytes(data))

        assert payload.server_clusters == [0x0006, 0x0008]
        assert payload.client_clusters == [0x0300]

    def test_full_commissioning_payload(self) -> None:
        """Full commissioning with all optional fields."""
        security_key = b"\xbb" * 16
        key_mic = 0xCAFEBABE
        counter = 0x00000100
        manufacturer_id = 0x1021
        model_id = 0x0002
        commands = [0x20, 0x21, 0x22]
        server_clusters = [0x0006]
        client_clusters: list[int] = []

        data = bytearray()
        # device_id=2
        data.append(0x02)
        # options: extended (bit 7) + app_info (bit 2) = 0x80 | 0x04 = 0x84
        data.append(0x84)
        # extended: Encrypted + key_present + key_encrypted + outgoing_counter
        # = 0x03 | 0x20 | 0x40 | 0x80 = 0xE3
        data.append(0xE3)
        data.extend(security_key)
        data.extend(struct.pack("<I", key_mic))
        data.extend(struct.pack("<I", counter))
        # app_info: all fields = 0x01 | 0x02 | 0x04 | 0x08 = 0x0F
        data.append(0x0F)
        data.extend(struct.pack("<H", manufacturer_id))
        data.extend(struct.pack("<H", model_id))
        data.append(len(commands))
        data.extend(commands)
        length_byte = (len(server_clusters) & 0x0F) | (
            (len(client_clusters) & 0x0F) << 4
        )
        data.append(length_byte)
        for c in server_clusters:
            data.extend(struct.pack("<H", c))

        payload = GPCommissioningPayload.from_bytes(bytes(data))

        assert payload.device_id == 0x02
        assert payload.extended_options is not None
        assert payload.extended_options.security_level == SecurityLevel.Encrypted
        assert payload.security_key == security_key
        assert payload.key_mic == key_mic
        assert payload.outgoing_counter == counter
        assert payload.manufacturer_id == manufacturer_id
        assert payload.model_id == model_id
        assert payload.gpd_commands == commands
        assert payload.server_clusters == [0x0006]
        assert payload.client_clusters == []

    def test_roundtrip_serialization(self) -> None:
        """Parsing and re-serializing should produce identical bytes."""
        security_key = b"\xcc" * 16
        data = bytes([0x02, 0x80, 0x23]) + security_key
        payload = GPCommissioningPayload.from_bytes(data)
        serialized = payload.to_bytes()
        assert serialized == data

    def test_roundtrip_full_payload(self) -> None:
        """Full payload round-trip."""
        commands = [0x20, 0x21]
        data = bytearray()
        data.append(0x07)  # device_id
        data.append(0x84)  # options: extended (bit 7) + app_info (bit 2)
        data.append(0xA0)  # extended: key_present + outgoing_counter
        data.extend(b"\xdd" * 16)  # security key
        data.extend(struct.pack("<I", 0x00000099))  # outgoing counter
        data.append(0x04)  # app_info: gpd_commands
        data.append(len(commands))
        data.extend(commands)

        payload = GPCommissioningPayload.from_bytes(bytes(data))
        serialized = payload.to_bytes()
        assert serialized == bytes(data)

    def test_too_short_payload(self) -> None:
        """Payload shorter than 2 bytes should raise ValueError."""
        with pytest.raises(ValueError, match="too short"):
            GPCommissioningPayload.from_bytes(b"\x00")

    def test_empty_payload(self) -> None:
        """Empty payload should raise ValueError."""
        with pytest.raises(ValueError, match="too short"):
            GPCommissioningPayload.from_bytes(b"")

    def test_to_bytes_with_encrypted_key_and_mic(self) -> None:
        """Serialization must include encrypted key + MIC per Table 54.

        Extended 0x63: Encrypted(0b11) + key_present(bit5) + key_encrypted(bit6).
        MIC follows key as uint32 LE.
        """
        key = b"\xaa" * 16
        payload = GPCommissioningPayload(
            device_id=0x02,
            options=GPCommissioningOptions(0x80),  # extended present
            extended_options=GPCommissioningExtendedOptions(0x63),
            security_key=key,
            key_mic=0xCAFEBABE,
        )
        result = payload.to_bytes()

        # Must contain: device_id(1) + options(1) + extended(1) + key(16) + mic(4) = 23
        assert len(result) == 23
        assert result[3:19] == key  # key at offset 3
        assert struct.unpack_from("<I", result, 19)[0] == 0xCAFEBABE

    def test_to_bytes_with_manufacturer_and_model(self) -> None:
        """Serialization must include manufacturer_id and model_id per Table 55."""
        payload = GPCommissioningPayload(
            device_id=0x07,
            options=GPCommissioningOptions(0x04),  # app_info present (bit 2)
            app_info=GPCommissioningAppInfo(0x03),  # mfr + model
            manufacturer_id=0x1234,
            model_id=0x5678,
        )
        result = payload.to_bytes()

        # device_id(1) + options(1) + app_info(1) + mfr(2) + model(2) = 7
        assert len(result) == 7
        assert struct.unpack_from("<H", result, 3)[0] == 0x1234
        assert struct.unpack_from("<H", result, 5)[0] == 0x5678

    def test_to_bytes_with_gpd_commands_and_clusters(self) -> None:
        """Serialization must include GPD commands list and cluster list.

        Per Table 55, cluster list length byte uses low nibble for server
        count and high nibble for client count.
        """
        payload = GPCommissioningPayload(
            device_id=0x02,
            options=GPCommissioningOptions(0x04),  # app_info present (bit 2)
            app_info=GPCommissioningAppInfo(0x0C),  # commands + clusters
            gpd_commands=[0x20, 0x21, 0x22],
            server_clusters=[0x0006],
            client_clusters=[0x0300],
        )
        result = payload.to_bytes()

        # Parse back to verify
        restored = GPCommissioningPayload.from_bytes(result)
        assert restored.gpd_commands == [0x20, 0x21, 0x22]
        assert restored.server_clusters == [0x0006]
        assert restored.client_clusters == [0x0300]


class TestGPChannelRequestPayload:
    """Tests for channel request payload parsing."""

    def test_channel_11(self) -> None:
        """Channel 11 = offset 0."""
        payload = GPChannelRequestPayload.from_bytes(b"\x00")
        assert payload.next_channel == 11
        assert payload.second_next_channel == 11

    def test_channel_26(self) -> None:
        """Channel 26 = offset 15."""
        payload = GPChannelRequestPayload.from_bytes(b"\xff")
        assert payload.next_channel == 26
        assert payload.second_next_channel == 26

    def test_mixed_channels(self) -> None:
        """Different next and second-next channels."""
        # next=15 (offset 4), second_next=20 (offset 9)
        byte_val = 4 | (9 << 4)
        payload = GPChannelRequestPayload.from_bytes(bytes([byte_val]))
        assert payload.next_channel == 15
        assert payload.second_next_channel == 20

    def test_empty_payload_raises(self) -> None:
        """Empty data should raise ValueError."""
        with pytest.raises(ValueError, match="at least 1 byte"):
            GPChannelRequestPayload.from_bytes(b"")
