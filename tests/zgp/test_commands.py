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


@pytest.mark.parametrize(
    "data",
    [
        # Extended Options announced by the Options field but absent
        b"\x02\x80",
        # GPDkey announced but short
        b"\x02\x80\x23" + b"\xaa" * 15,
        # GPDkeyMIC announced by GPDkeyEncryption but absent
        b"\x02\x80\x63" + b"\xaa" * 16,
        # GPDoutgoingCounter announced but absent
        b"\x02\x80\x80",
        # Application information announced by the Options field but absent
        b"\x02\x04",
        # ManufacturerID announced but absent
        b"\x02\x04\x01",
        # ModelID announced but absent
        b"\x02\x04\x02",
        # GPD CommandID list announced but absent
        b"\x02\x04\x04",
        # Cluster List announced but absent
        b"\x02\x04\x08",
        # Switch information announced but truncated mid-field
        b"\x02\x04\x10\x02\x22",
    ],
)
def test_commissioning_announced_field_missing(data: bytes) -> None:
    """A field announced by a control sub-field is mandatory (Figures 107 and 108)."""
    with pytest.raises(ValueError, match="too short"):
        GPCommissioningPayload.deserialize(data)


def test_commissioning_cluster_count_exceeds_data() -> None:
    """The cluster lists must hold exactly what the length nibbles announce (Fig. 113)."""
    # app_info=0x08: cluster list present, announcing one server cluster that is absent
    with pytest.raises(ValueError, match="Expected 1 items, got 0"):
        GPCommissioningPayload.deserialize(b"\x02\x04\x08\x01")


@pytest.mark.parametrize(
    ("schema", "data"),
    [
        # PANId announced by the Options field but absent (Figure 117)
        (GPCommissioningReplyPayload, b"\x01"),
        # GPDsecurityKey announced but absent
        (GPCommissioningReplyPayload, b"\x02"),
        # GPDkeyMIC announced by GPDkeyEncryption but absent
        (GPCommissioningReplyPayload, b"\x06" + b"\xaa" * 16),
        # Frame Counter announced by SecurityLevel 0b11 + key + encryption but absent
        (GPCommissioningReplyPayload, b"\x1e" + b"\xaa" * 16 + b"\x01\x02\x03\x04"),
        # ManufacturerID announced by the Options field but absent (Figure 144)
        (GPRequestAttributesPayload, b"\x02"),
        # ManufacturerID announced by the Options field but absent (Figure 137)
        (GPZCLTunnelingPayload, b"\x04"),
    ],
)
def test_announced_field_missing(schema: type[t.Struct], data: bytes) -> None:
    """A field announced by a control sub-field cannot be truncated away."""
    with pytest.raises(ValueError, match="too short"):
        schema.deserialize(data)


@pytest.mark.parametrize(
    ("payload", "missing"),
    [
        (
            GPCommissioningPayload(
                device_id=0x02, options=GPCommissioningOptions(0x80)
            ),
            "extended_options",
        ),
        (
            GPCommissioningPayload(
                device_id=0x02,
                options=GPCommissioningOptions(0x80),
                extended_options=GPCommissioningExtendedOptions(0x23),
            ),
            "security_key",
        ),
        (
            GPCommissioningPayload(
                device_id=0x02, options=GPCommissioningOptions(0x04)
            ),
            "app_info",
        ),
        (
            GPCommissioningPayload(
                device_id=0x02,
                options=GPCommissioningOptions(0x04),
                app_info=GPCommissioningAppInfo(0x01),
            ),
            "manufacturer_id",
        ),
        (
            GPCommissioningReplyPayload(options=GPCommissioningReplyOptions(0x01)),
            "pan_id",
        ),
        (
            GPRequestAttributesPayload(
                options=0x02,
                cluster_records=[
                    GPClusterRecordRequest(cluster_id=0x0402, attribute_ids=[0x0000])
                ],
            ),
            "manufacturer_id",
        ),
    ],
)
def test_serialize_announced_field_missing(payload: t.Struct, missing: str) -> None:
    """Announcing a field and leaving it unset must not silently omit it."""
    with pytest.raises(ValueError, match=f"Value for field {missing!r} is required"):
        payload.serialize()


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


def test_cluster_counts_derived() -> None:
    """The cluster list count byte is derived from the lists (Figure 113)."""
    payload = GPCommissioningPayload(
        device_id=0x02,
        options=GPCommissioningOptions(0x04),
        app_info=GPCommissioningAppInfo(0x08),
        server_clusters=[0x0006, 0x0008],
        client_clusters=[0x0300],
    )

    assert payload.serialize() == b"\x02\x04\x08\x12\x06\x00\x08\x00\x00\x03"


@pytest.mark.parametrize(
    ("schema", "data"),
    [
        # Payloadless commands (Table 54)
        (GPNoPayload, b""),
        # Commissioning, Figures 107 to 115: DeviceID only
        (GPCommissioningPayload, b"\x02\x00"),
        # Extended options 0x03: Encrypted, no key, no outgoing counter
        (GPCommissioningPayload, b"\x02\x80\x03"),
        # Extended options 0xE3: Encrypted, key protected with a MIC, outgoing counter
        (
            GPCommissioningPayload,
            b"\x02\x80\xe3" + b"\xaa" * 16 + b"\xef\xbe\xad\xde" + b"\x34\x12\x00\x00",
        ),
        # Extended options 0xA0: key in the clear, outgoing counter. Application
        # information 0x04: GPD commands
        (
            GPCommissioningPayload,
            b"\x07\x84\xa0" + b"\xdd" * 16 + b"\x99\x00\x00\x00" + b"\x04\x02\x20\x21",
        ),
        # Application information 0x0B: manufacturer ID, model ID and cluster lists
        (
            GPCommissioningPayload,
            b"\x02\x04\x0b\x34\x12\x78\x56" + b"\x12\x06\x00\x08\x00\x00\x03",
        ),
        # Channel Request, Figure 119: next channel 15, second next channel 20
        (GPChannelRequestPayload, b"\x94"),
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
    assert list(payload.cluster_records[0].attribute_ids) == [0x0000, 0x0001]


def test_request_attributes_record_length_derived() -> None:
    """The octet length of the attribute list comes from the list itself."""
    record = GPClusterRecordRequest(cluster_id=0x0402, attribute_ids=[0x0000, 0x0001])

    assert record.serialize() == b"\x02\x04\x04\x00\x00\x01\x00"


@pytest.mark.parametrize(
    "data",
    [
        # A record list length that does not cover whole attribute IDs must not shift
        # the parse of everything after it: without the size prefix delimiting the
        # region, this used to yield a bogus second record and no trailing data
        b"\x00" + b"\x06\x00\x03\x00\x00" + b"\x00\x02\x00",
        b"\x00" + b"\x06\x00\x03\x00\x00\xff",
        # A length longer than the data available
        b"\x00" + b"\x06\x00\x08\x00\x00",
    ],
)
def test_request_attributes_misaligned_record_length(data: bytes) -> None:
    """A record list length inconsistent with its contents is rejected."""
    with pytest.raises(ValueError, match="too short"):
        GPRequestAttributesPayload.deserialize(data)


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
    "command_id", [GPDCommandID.AnySensorCommand, GPDCommandID.AnyCommand]
)
def test_translation_table_pseudo_ids_are_unmapped(command_id: GPDCommandID) -> None:
    """0xAF and 0xFF only ever appear in the Translation Table (sec. A.3.6.3.3)."""
    assert command_id not in GPD_COMMAND_SCHEMAS


@pytest.mark.parametrize("command_id", range(0xB0, 0xC0))
def test_manufacturer_defined_range_is_mapped(command_id: int) -> None:
    """The whole 0xB0 - 0xBF range is manufacturer-defined (Table 55)."""
    assert GPD_COMMAND_SCHEMAS[GPDCommandID(command_id)] is GPManufacturerDefinedPayload


def test_unknown_command_id_is_unmapped() -> None:
    """A reserved command ID has no entry at all."""
    assert GPDCommandID(0xC5) not in GPD_COMMAND_SCHEMAS
