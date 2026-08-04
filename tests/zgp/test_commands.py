"""Tests for Green Power command payload parsing."""

from __future__ import annotations

import struct

import pytest

import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zgp.commands import (
    GPD_COMMAND_SCHEMAS,
    GPAttributeReportingPayload,
    GPChannelConfigurationPayload,
    GPChannelRequestPayload,
    GPClusterRecordRequest,
    GPCommissioningAppInfo,
    GPCommissioningExtendedOptions,
    GPCommissioningOptions,
    GPCommissioningPayload,
    GPCommissioningReplyOptions,
    GPCommissioningReplyPayload,
    GPContactStatusPayload,
    GPManufacturerDefinedPayload,
    GPManufacturerSpecificAttributeReportingPayload,
    GPManufacturerSpecificMultiClusterReportingPayload,
    GPMoveColorPayload,
    GPMovePayload,
    GPMultiClusterReportingPayload,
    GPNoPayload,
    GPRequestAttributesPayload,
    GPStepColorPayload,
    GPStepPayload,
    GPSwitchInformation,
    GPZCLTunnelingPayload,
)
from zigpy.zgp.types import GPDCommandID, SecurityKeyType, SecurityLevel, SwitchType


def test_all_bits_clear():
    opts = GPCommissioningOptions(0x00)
    assert not opts.mac_seq_num_capability
    assert not opts.rx_on_capability
    assert not opts.app_info_present
    assert not opts.pan_id_request
    assert not opts.security_key_request
    assert not opts.fixed_location


def test_mac_seq_num_capability():
    opts = GPCommissioningOptions(0x01)
    assert opts.mac_seq_num_capability


def test_rx_on_capability():
    opts = GPCommissioningOptions(0x02)  # bit 1
    assert opts.rx_on_capability


def test_app_info_present():
    opts = GPCommissioningOptions(0x04)  # bit 2
    assert opts.app_info_present


def test_pan_id_request():
    opts = GPCommissioningOptions(0x10)  # bit 4
    assert opts.pan_id_request


def test_security_key_request():
    opts = GPCommissioningOptions(0x20)  # bit 5
    assert opts.security_key_request


def test_fixed_location():
    opts = GPCommissioningOptions(0x40)  # bit 6
    assert opts.fixed_location


def test_extended_options_present():
    opts = GPCommissioningOptions(0x80)  # bit 7
    assert opts.extended_options_present


def test_multiple_flags():
    # MAC seq (bit 0) + RX on (bit 1) + App info (bit 2)
    opts = GPCommissioningOptions(0x01 | 0x02 | 0x04)
    assert opts.mac_seq_num_capability
    assert opts.rx_on_capability
    assert opts.app_info_present
    assert not opts.pan_id_request


def test_options_serialize():
    assert GPCommissioningOptions(0x84).serialize() == b"\x84"


def test_security_level():
    # SecurityLevel.Encrypted = 0b11
    ext = GPCommissioningExtendedOptions(0x03)
    assert ext.security_level == SecurityLevel.Encrypted


def test_key_type():
    # IndividualKey = 0b100, shifted left 2 = 0x10
    ext = GPCommissioningExtendedOptions(0x10)
    assert ext.key_type == SecurityKeyType.IndividualKey


def test_key_present():
    ext = GPCommissioningExtendedOptions(0x20)
    assert ext.key_present
    assert not ext.key_encrypted


def test_key_encrypted():
    ext = GPCommissioningExtendedOptions(0x60)  # key_present + key_encrypted
    assert ext.key_present
    assert ext.key_encrypted


def test_outgoing_counter_present():
    ext = GPCommissioningExtendedOptions(0x80)
    assert ext.outgoing_counter_present


def test_all_clear():
    ext = GPCommissioningExtendedOptions(0x00)
    assert ext.security_level == SecurityLevel.NoSecurity
    assert ext.key_type == SecurityKeyType.NoKey
    assert not ext.key_present
    assert not ext.key_encrypted
    assert not ext.outgoing_counter_present


def test_manufacturer_id_present():
    info = GPCommissioningAppInfo(0x01)
    assert info.manufacturer_id_present


def test_model_id_present():
    info = GPCommissioningAppInfo(0x02)
    assert info.model_id_present


def test_gpd_commands_present():
    info = GPCommissioningAppInfo(0x04)
    assert info.gpd_commands_present


def test_cluster_list_present():
    info = GPCommissioningAppInfo(0x08)
    assert info.cluster_list_present


def test_switch_info_present():
    info = GPCommissioningAppInfo(0x10)
    assert info.switch_info_present
    assert not info.app_description_follows


def test_app_description_follows():
    info = GPCommissioningAppInfo(0x20)
    assert info.app_description_follows
    assert not info.switch_info_present


def test_minimal_payload():
    """Minimal commissioning: device_id + options (no extended, no app info)."""
    data = bytes([0x02, 0x00])  # device_id=2, options=0
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.device_id == 0x02
    assert not payload.options.mac_seq_num_capability
    assert payload.extended_options is None
    assert payload.security_key is None
    assert payload.app_info is None


def test_with_extended_options_no_key():
    """Commissioning with extended options but no security key."""
    # options: bit 7 set (extended present) = 0x80
    # extended: security_level=0b11 (Encrypted), no key, no counter = 0x03
    data = bytes([0x02, 0x80, 0x03])
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.device_id == 0x02
    assert payload.extended_options is not None
    assert payload.extended_options.security_level == SecurityLevel.Encrypted
    assert not payload.extended_options.key_present
    assert payload.security_key is None


def test_with_unencrypted_key():
    """Commissioning with security key present but not encrypted."""
    # options: extended present = 0x80
    # extended: Encrypted + key_present = 0x03 | 0x20 = 0x23
    security_key = bytes(range(16))
    data = bytes([0x02, 0x80, 0x23]) + security_key
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.extended_options is not None
    assert payload.extended_options.key_present
    assert not payload.extended_options.key_encrypted
    assert bytes(payload.security_key) == security_key
    assert payload.key_mic is None


def test_with_encrypted_key_and_mic():
    """Commissioning with encrypted security key and MIC."""
    # extended: Encrypted + key_present + key_encrypted = 0x03 | 0x20 | 0x40 = 0x63
    security_key = bytes(range(16))
    key_mic = 0xDEADBEEF
    data = bytes([0x07, 0x80, 0x63]) + security_key + struct.pack("<I", key_mic)
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.device_id == 0x07
    assert payload.extended_options is not None
    assert payload.extended_options.key_encrypted
    assert bytes(payload.security_key) == security_key
    assert payload.key_mic == 0xDEADBEEF


def test_with_outgoing_counter():
    """Commissioning with outgoing frame counter."""
    # extended: outgoing_counter_present = 0x80
    counter = 0x00001234
    data = bytes([0x02, 0x80, 0x80]) + struct.pack("<I", counter)
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.extended_options is not None
    assert payload.extended_options.outgoing_counter_present
    assert payload.outgoing_counter == 0x00001234


def test_with_key_and_counter():
    """Commissioning with both key and outgoing counter."""
    # extended: key_present + outgoing_counter_present = 0x20 | 0x80 = 0xA0
    security_key = b"\xaa" * 16
    counter = 0x00000042
    data = bytes([0x02, 0x80, 0xA0]) + security_key + struct.pack("<I", counter)
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert bytes(payload.security_key) == security_key
    assert payload.outgoing_counter == 0x00000042


def test_with_app_info_manufacturer_and_model():
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
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.app_info is not None
    assert payload.manufacturer_id == 0x1234
    assert payload.model_id == 0x5678


def test_with_gpd_commands():
    """Commissioning with GPD command list."""
    # options: app_info_present = bit 2 = 0x04
    # app_info: gpd_commands_present = 0x04
    commands = [0x20, 0x21, 0x22]  # Off, On, Toggle
    data = bytes([0x02, 0x04, 0x04, len(commands)]) + bytes(commands)
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert list(payload.gpd_commands) == commands


def test_with_cluster_list():
    """Commissioning with server and client cluster lists."""
    # options: app_info_present = bit 2 = 0x04
    # app_info: cluster_list_present = 0x08
    server_clusters = [0x0006, 0x0008]  # On/Off, Level Control
    client_clusters = [0x0300]  # Color Control

    data = bytearray([0x02, 0x04, 0x08])
    # length byte: lower nibble = num_server, upper = num_client
    data.append((len(server_clusters) & 0x0F) | ((len(client_clusters) & 0x0F) << 4))
    for c in server_clusters:
        data.extend(struct.pack("<H", c))
    for c in client_clusters:
        data.extend(struct.pack("<H", c))

    payload, rest = GPCommissioningPayload.deserialize(bytes(data))

    assert rest == b""
    assert list(payload.server_clusters) == [0x0006, 0x0008]
    assert list(payload.client_clusters) == [0x0300]


def test_full_commissioning_payload():
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
    length_byte = (len(server_clusters) & 0x0F) | ((len(client_clusters) & 0x0F) << 4)
    data.append(length_byte)
    for c in server_clusters:
        data.extend(struct.pack("<H", c))

    payload, rest = GPCommissioningPayload.deserialize(bytes(data))

    assert rest == b""
    assert payload.device_id == 0x02
    assert payload.extended_options is not None
    assert payload.extended_options.security_level == SecurityLevel.Encrypted
    assert bytes(payload.security_key) == security_key
    assert payload.key_mic == key_mic
    assert payload.outgoing_counter == counter
    assert payload.manufacturer_id == manufacturer_id
    assert payload.model_id == model_id
    assert list(payload.gpd_commands) == commands
    assert list(payload.server_clusters) == [0x0006]
    assert list(payload.client_clusters) == []


def test_roundtrip_serialization():
    """Parsing and re-serializing should produce identical bytes."""
    security_key = b"\xcc" * 16
    data = bytes([0x02, 0x80, 0x23]) + security_key
    payload, _ = GPCommissioningPayload.deserialize(data)
    assert payload.serialize() == data


def test_roundtrip_full_payload():
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

    payload, _ = GPCommissioningPayload.deserialize(bytes(data))
    assert payload.serialize() == bytes(data)


def test_too_short_payload():
    """Payload without the mandatory options byte should raise ValueError."""
    with pytest.raises(ValueError, match="too short"):
        GPCommissioningPayload.deserialize(b"\x00")


def test_empty_payload():
    """Empty payload should raise ValueError."""
    with pytest.raises(ValueError, match="too short"):
        GPCommissioningPayload.deserialize(b"")


def test_serialize_with_encrypted_key_and_mic():
    """Serialization must include encrypted key + MIC per Figure 107.

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
    result = payload.serialize()

    # Must contain: device_id(1) + options(1) + extended(1) + key(16) + mic(4) = 23
    assert len(result) == 23
    assert result[3:19] == key  # key at offset 3
    assert struct.unpack_from("<I", result, 19)[0] == 0xCAFEBABE


def test_serialize_with_manufacturer_and_model():
    """Serialization must include manufacturer_id and model_id per Figure 108."""
    payload = GPCommissioningPayload(
        device_id=0x07,
        options=GPCommissioningOptions(0x04),  # app_info present (bit 2)
        app_info=GPCommissioningAppInfo(0x03),  # mfr + model
        manufacturer_id=0x1234,
        model_id=0x5678,
    )
    result = payload.serialize()

    # device_id(1) + options(1) + app_info(1) + mfr(2) + model(2) = 7
    assert len(result) == 7
    assert struct.unpack_from("<H", result, 3)[0] == 0x1234
    assert struct.unpack_from("<H", result, 5)[0] == 0x5678


def test_serialize_with_gpd_commands_and_clusters():
    """Serialization must include GPD commands list and cluster list.

    Per Figure 113, cluster list length byte uses low nibble for server
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
    result = payload.serialize()

    # Parse back to verify
    restored, _ = GPCommissioningPayload.deserialize(result)
    assert list(restored.gpd_commands) == [0x20, 0x21, 0x22]
    assert list(restored.server_clusters) == [0x0006]
    assert list(restored.client_clusters) == [0x0300]


def test_channel_11():
    """Channel 11 = nibble offset 0 (IEEE channel == nibble + 11)."""
    payload, rest = GPChannelRequestPayload.deserialize(b"\x00")
    assert rest == b""
    assert payload.next_channel == 0
    assert payload.second_next_channel == 0


def test_channel_26():
    """Channel 26 = nibble offset 15 (IEEE channel == nibble + 11)."""
    payload, rest = GPChannelRequestPayload.deserialize(b"\xff")
    assert rest == b""
    assert payload.next_channel == 15
    assert payload.second_next_channel == 15


def test_mixed_channels():
    """Different next and second-next channels."""
    # next=nibble 4 (channel 15), second_next=nibble 9 (channel 20)
    byte_val = 4 | (9 << 4)
    payload, rest = GPChannelRequestPayload.deserialize(bytes([byte_val]))
    assert rest == b""
    assert payload.next_channel == 4
    assert payload.second_next_channel == 9
    assert payload.serialize() == bytes([byte_val])


def test_empty_payload_raises():
    """Empty data should raise ValueError."""
    with pytest.raises(ValueError, match="too short"):
        GPChannelRequestPayload.deserialize(b"")


def test_switch_information() -> None:
    """Switch information field, gated by app_info bit 4 (Figure 111, Figure 114)."""
    # app_info=0x10: switch information present only
    # config=0x22: 2 contacts, rocker switch; contact status: both contacts closed
    data = b"\x07\x04\x10" + b"\x02\x22\x03"
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert payload.switch_information.length == 2
    assert payload.switch_information.configuration.num_contacts == 2
    assert payload.switch_information.configuration.switch_type == SwitchType.Rocker
    assert payload.switch_information.contact_status == 0b11
    assert payload.serialize() == data


def test_switch_information_absent() -> None:
    """Without the switch information bit the field stays unparsed."""
    payload, rest = GPCommissioningPayload.deserialize(b"\x07\x04\x00")

    assert rest == b""
    assert payload.switch_information is None


def test_switch_information_follows_cluster_list() -> None:
    """Switch information is the last field of the payload (Figure 108)."""
    # app_info=0x18: cluster list + switch information
    data = b"\x07\x04\x18" + b"\x01\x06\x00" + b"\x02\x11\x01"
    payload, rest = GPCommissioningPayload.deserialize(data)

    assert rest == b""
    assert list(payload.server_clusters) == [0x0006]
    assert payload.switch_information.configuration.num_contacts == 1
    assert payload.switch_information.configuration.switch_type == SwitchType.Button
    assert payload.serialize() == data


def test_switch_information_length_derived() -> None:
    """The switch info length byte is derived from the fields it describes."""
    info = GPSwitchInformation(configuration=0x22, contact_status=0x03)

    assert info.length == 2
    assert info.serialize() == b"\x02\x22\x03"


@pytest.mark.parametrize(
    ("schema", "data"),
    [
        # Payloadless commands (Table 54)
        (GPNoPayload, b""),
        # Commissioning Reply, Figures 116 and 117
        (GPCommissioningReplyPayload, b"\x00"),
        (GPCommissioningReplyPayload, b"\x01\x34\x12"),
        (GPCommissioningReplyPayload, b"\x02" + b"\xaa" * 16),
        # PAN ID + key + encrypted key + Encrypted level + individual key: the MIC and
        # the frame counter are both present
        (
            GPCommissioningReplyPayload,
            b"\x9f\x34\x12" + b"\xaa" * 16 + b"\x01\x02\x03\x04\x05\x06\x07\x08",
        ),
        # Channel Configuration, Figures 120 and 121
        (GPChannelConfigurationPayload, b"\x14"),
        # 8-bit vector press/release, Figure 129
        (GPContactStatusPayload, b"\x05"),
        # Move commands, Figure 139: the rate is optional
        (GPMovePayload, b""),
        (GPMovePayload, b"\x32"),
        # Step commands, Figure 140: the transition time is optional
        (GPStepPayload, b"\x10"),
        (GPStepPayload, b"\x10\x05\x00"),
        # Move Color, Figure 141
        (GPMoveColorPayload, b"\xff\xff\x01\x00"),
        # Step Color, Figure 142: the transition time is optional
        (GPStepColorPayload, b"\x01\x00\x02\x00"),
        (GPStepColorPayload, b"\x01\x00\x02\x00\x0a\x00"),
        # Attribute Reporting, Figures 130 and 131
        (GPAttributeReportingPayload, b"\x02\x04" + b"\x00\x00\x29\xfc\x08"),
        (
            GPAttributeReportingPayload,
            b"\x02\x04" + b"\x00\x00\x29\xfc\x08" + b"\x03\x00\x29\x10\x27",
        ),
        # Manufacturer-Specific Attribute Reporting, Figure 132
        (
            GPManufacturerSpecificAttributeReportingPayload,
            b"\x21\x10\x02\xfc" + b"\x00\x50\x20\x07",
        ),
        # Multi-Cluster Reporting, Figures 133 and 134
        (
            GPMultiClusterReportingPayload,
            b"\x02\x04\x00\x00\x29\xfc\x08" + b"\x05\x04\x00\x00\x21\x10\x27",
        ),
        # Manufacturer-Specific Multi-Cluster Reporting, Figure 135
        (
            GPManufacturerSpecificMultiClusterReportingPayload,
            b"\x21\x10" + b"\x02\xfc\x00\x50\x20\x07",
        ),
        # Request Attributes, Figures 143 to 145
        (GPRequestAttributesPayload, b"\x00" + b"\x06\x00\x02\x00\x00"),
        (
            GPRequestAttributesPayload,
            b"\x03" + b"\x21\x10" + b"\x02\x04\x04\x00\x00\x01\x00",
        ),
        (
            GPRequestAttributesPayload,
            b"\x01" + b"\x06\x00\x02\x00\x00" + b"\x02\x04\x02\x00\x00",
        ),
        # ZCL Tunneling, Figures 136 and 137
        (GPZCLTunnelingPayload, b"\x00" + b"\x06\x00" + b"\x02" + b"\x00"),
        (
            GPZCLTunnelingPayload,
            b"\x0d" + b"\x21\x10" + b"\x00\xfc" + b"\x01" + b"\x02\xaa\xbb",
        ),
        # Manufacturer-defined commands, Figure 152
        (GPManufacturerDefinedPayload, b"\x21\x10"),
        (GPManufacturerDefinedPayload, b"\x21\x10" + b"\xde\xad\xbe\xef"),
    ],
)
def test_payload_roundtrip(schema: type[t.Struct], data: bytes) -> None:
    """Every payload must deserialize completely and re-serialize identically."""
    payload, rest = schema.deserialize(data)

    assert rest == b""
    assert payload.serialize() == data


def test_commissioning_reply_options() -> None:
    """Options sub-fields of the Commissioning Reply command (Figure 117)."""
    options = GPCommissioningReplyOptions(0x9F)

    assert options.pan_id_present
    assert options.security_key_present
    assert options.key_encrypted
    assert options.security_level == SecurityLevel.Encrypted
    assert options.key_type == SecurityKeyType.IndividualKey


def test_commissioning_reply_unencrypted_key() -> None:
    """An unencrypted key has neither a MIC nor a frame counter (sec. A.4.2.1.2.1)."""
    # key present, not encrypted, Encrypted security level
    data = b"\x1a" + b"\xaa" * 16
    payload, rest = GPCommissioningReplyPayload.deserialize(data)

    assert rest == b""
    assert bytes(payload.security_key) == b"\xaa" * 16
    assert payload.key_mic is None
    assert payload.frame_counter is None
    assert payload.serialize() == data


def test_commissioning_reply_no_frame_counter_without_security() -> None:
    """The frame counter requires a frame-counter security level (sec. A.4.2.1.2.1)."""
    # key present + encrypted, but security level 0b00: MIC but no frame counter
    data = b"\x06" + b"\xaa" * 16 + b"\x01\x02\x03\x04"
    payload, rest = GPCommissioningReplyPayload.deserialize(data)

    assert rest == b""
    assert payload.key_mic == 0x04030201
    assert payload.frame_counter is None
    assert payload.serialize() == data


def test_channel_configuration() -> None:
    """Channel Configuration sub-fields (Figure 121)."""
    payload, rest = GPChannelConfigurationPayload.deserialize(b"\x14")

    assert rest == b""
    # nibble 4 == IEEE 802.15.4 channel 15
    assert payload.operational_channel == 4
    assert payload.basic == 1


def test_contact_status() -> None:
    """Contact status bits, a set bit being a closed contact (sec. A.4.2.2.1)."""
    payload, rest = GPContactStatusPayload.deserialize(b"\x0a")

    assert rest == b""
    assert payload.contact_status == 0b1010


def test_attribute_reporting_values() -> None:
    """Attribute reports are ZCL attribute records (Figure 131)."""
    # Temperature Measurement, MeasuredValue = 23.00 degrees as int16s
    payload, rest = GPAttributeReportingPayload.deserialize(
        b"\x02\x04" + b"\x00\x00\x29\xfc\x08"
    )

    assert rest == b""
    assert payload.cluster_id == 0x0402
    assert payload.attributes == [
        foundation.Attribute(
            attrid=0x0000,
            value=foundation.TypeValue(type=0x29, value=t.int16s(2300)),
        )
    ]


def test_multi_cluster_reporting_values() -> None:
    """Each cluster report carries its own cluster ID (Figure 134)."""
    payload, rest = GPMultiClusterReportingPayload.deserialize(
        b"\x02\x04\x00\x00\x29\xfc\x08" + b"\x05\x04\x00\x00\x21\x10\x27"
    )

    assert rest == b""
    assert [report.cluster_id for report in payload.reports] == [0x0402, 0x0405]
    assert [report.attribute.value.value for report in payload.reports] == [2300, 10000]


def test_request_attributes_records() -> None:
    """The record list length is in octets, not attributes (Figure 145)."""
    payload, rest = GPRequestAttributesPayload.deserialize(
        b"\x03" + b"\x21\x10" + b"\x02\x04\x04\x00\x00\x01\x00"
    )

    assert rest == b""
    assert payload.options.multi_record
    assert payload.manufacturer_id == 0x1021
    assert len(payload.cluster_records) == 1
    assert payload.cluster_records[0].cluster_id == 0x0402
    assert payload.cluster_records[0].record_list_length == 4
    assert list(payload.cluster_records[0].attribute_ids) == [0x0000, 0x0001]


def test_request_attributes_record_length_derived() -> None:
    """The octet length of the attribute list is derived from the list itself."""
    record = GPClusterRecordRequest(cluster_id=0x0402, attribute_ids=[0x0000, 0x0001])

    assert record.record_list_length == 4
    assert record.serialize() == b"\x02\x04\x04\x00\x00\x01\x00"


def test_request_attributes_no_manufacturer_id() -> None:
    """Without the manufacturer bit the ManufacturerID field is absent (Figure 144)."""
    payload, rest = GPRequestAttributesPayload.deserialize(
        b"\x00" + b"\x06\x00\x02\x00\x00"
    )

    assert rest == b""
    assert payload.manufacturer_id is None
    assert list(payload.cluster_records[0].attribute_ids) == [0x0000]


def test_zcl_tunneling() -> None:
    """ZCL Tunneling wraps a ZCL command with its own frame control (Figure 136)."""
    payload, rest = GPZCLTunnelingPayload.deserialize(
        b"\x0d" + b"\x21\x10" + b"\x00\xfc" + b"\x01" + b"\x02\xaa\xbb"
    )

    assert rest == b""
    assert payload.options.frame_type == foundation.FrameType.CLUSTER_COMMAND
    assert payload.options.direction == foundation.Direction.Server_to_Client
    assert payload.manufacturer_id == 0x1021
    assert payload.cluster_id == 0xFC00
    assert payload.command_id == 0x01
    assert payload.payload == b"\xaa\xbb"


def test_manufacturer_defined_payload() -> None:
    """Everything past the ManufacturerID is manufacturer-specific (Figure 152)."""
    payload, rest = GPManufacturerDefinedPayload.deserialize(
        b"\x21\x10" + b"\xde\xad\xbe\xef"
    )

    assert rest == b""
    assert payload.manufacturer_id == 0x1021
    assert payload.data == b"\xde\xad\xbe\xef"


@pytest.mark.parametrize(
    "command_id",
    [
        command_id
        for command_id in GPDCommandID
        if command_id not in (GPDCommandID.AnySensorCommand, GPDCommandID.AnyCommand)
    ],
)
def test_every_command_id_is_mapped(command_id: GPDCommandID) -> None:
    """Every command ID that can appear on the wire needs a mapping entry."""
    assert command_id in GPD_COMMAND_SCHEMAS


@pytest.mark.parametrize(
    "command_id", [GPDCommandID.AnySensorCommand, GPDCommandID.AnyCommand]
)
def test_translation_table_pseudo_ids_are_unmapped(command_id: GPDCommandID) -> None:
    """0xAF and 0xFF only ever appear in the Translation Table (sec. A.3.6.3.3)."""
    assert command_id not in GPD_COMMAND_SCHEMAS


@pytest.mark.parametrize("command_id", range(0xB0, 0xC0))
def test_manufacturer_defined_range_is_mapped(command_id: int) -> None:
    """The whole 0xB0 - 0xBF range is manufacturer-defined (Table 55)."""
    assert GPD_COMMAND_SCHEMAS[GPDCommandID(command_id)] is GPManufacturerDefinedPayload


@pytest.mark.parametrize(
    "command_id",
    [
        GPDCommandID.ReadAttributesResponse,
        GPDCommandID.CompactAttributeReporting,
        GPDCommandID.ApplicationDescription,
        GPDCommandID.WriteAttributes,
    ],
)
def test_unimplemented_payloads_are_explicitly_none(command_id: GPDCommandID) -> None:
    """Commands whose payload parser is still missing map to `None`, not absence."""
    assert GPD_COMMAND_SCHEMAS[command_id] is None


def test_unknown_command_id_is_unmapped() -> None:
    """A reserved command ID has no entry at all."""
    assert GPDCommandID(0xC5) not in GPD_COMMAND_SCHEMAS
