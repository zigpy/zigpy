"""Tests for Green Power type definitions."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    NotificationResponseSchema,
    PairingSchema,
    PairingSearchSchema,
    ResponseSchema,
)
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    GPDCommandPayload,
    ProxyCommissioningModeExitMode,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SinkCommissioningExitMode,
    SrcID,
)


def test_proxy_exit_mode_is_shifted():
    """The command's sub-field drops "on expiration", shifting the other bits down."""
    assert (
        ProxyCommissioningModeExitMode.OnFirstPairing
        == SinkCommissioningExitMode.OnFirstPairing >> 1
    )
    assert (
        ProxyCommissioningModeExitMode.OnExplicitExit
        == SinkCommissioningExitMode.OnExplicitExit >> 1
    )


@pytest.mark.parametrize(
    ("data", "payload", "unspecified"),
    [
        (b"\x02\xaa\xbb", b"\xaa\xbb", False),
        (b"\x00", b"", False),
        # A length byte of 0xff means unspecified, which is not an empty payload
        (b"\xff", b"", True),
    ],
)
def test_command_payload(data: bytes, payload: bytes, unspecified: bool) -> None:
    parsed, rest = GPDCommandPayload.deserialize(data + b"rest")

    assert parsed == payload
    assert rest == b"rest"
    assert parsed.unspecified is unspecified
    assert parsed.serialize() == data

    # A copy keeps the marker
    assert GPDCommandPayload(parsed).unspecified is unspecified
    assert GPDCommandPayload(parsed).serialize() == data


GPD_IEEE = t.EUI64.convert("11:22:33:44:55:66:77:88")


@pytest.mark.parametrize(
    ("schema", "serialized", "gpd_id", "gpd_ieee", "gpd_endpoint"),
    [
        # GP 1.1.2 Figure 28: options, GPD ID, endpoint
        (PairingSearchSchema, "0800 78563412", 0x12345678, None, None),
        (PairingSearchSchema, "0a00 8877665544332211 01", None, GPD_IEEE, 0x01),
        # Figure 49: options, GPD ID, endpoint, frame counter
        (NotificationResponseSchema, "08 78563412 10000000", 0x12345678, None, None),
        (
            NotificationResponseSchema,
            "0a 8877665544332211 01 10000000",
            None,
            GPD_IEEE,
            0x01,
        ),
        # Figures 51 and 52: options (remove GPD), GPD ID, endpoint
        (PairingSchema, "100000 78563412", 0x12345678, None, None),
        (PairingSchema, "120000 8877665544332211 01", None, GPD_IEEE, 0x01),
        # Options (add unicast sink), GPD ID, endpoint, sink IEEE, NWK, device ID
        (
            PairingSchema,
            "0a0000 8877665544332211 01 0807060504030201 3412 02",
            None,
            GPD_IEEE,
            0x01,
        ),
        # Figure 58: options, temp master address and channel, GPD ID, endpoint,
        # command ID and payload
        (ResponseSchema, "00 3412 04 78563412 f0 01aa", 0x12345678, None, None),
        (
            ResponseSchema,
            "0a 3412 04 8877665544332211 01 f0 01aa",
            None,
            GPD_IEEE,
            0x01,
        ),
    ],
)
def test_gpd_id_addressing(
    schema: type[foundation.CommandSchema],
    serialized: str,
    gpd_id: int | None,
    gpd_ieee: t.EUI64 | None,
    gpd_endpoint: int | None,
) -> None:
    """The GPD ID is a SrcID or an IEEE address with an endpoint, per ApplicationID."""
    command, rest = schema.deserialize(bytes.fromhex(serialized))

    assert rest == b""
    assert command.gpd_id == gpd_id
    assert command.gpd_ieee == gpd_ieee
    assert command.gpd_endpoint == gpd_endpoint
    assert command.serialize() == bytes.fromhex(serialized)
    assert schema(**command.as_dict()).serialize() == bytes.fromhex(serialized)


GP_PACKET_VALUES = {
    "application_id": ApplicationID.IEEE,
    "src_id": SrcID(0x12345678),
    "ieee": t.EUI64.convert("11:22:33:44:55:66:77:88"),
    "endpoint": t.uint8_t(1),
    "command_id": GPDCommandID.Toggle,
    "payload": t.SerializableBytes(b"\x01"),
    "frame_counter": t.uint32_t(1),
    "security_level": SecurityLevel.Encrypted,
    "security_key_type": SecurityKeyType.IndividualKey,
    "security_status": SecurityStatus.SecuritySuccess,
    "mic": t.uint32_t(1),
    "auto_commissioning": True,
    "rx_after_tx": True,
    "individual_key": True,
    "lqi": t.uint8_t(1),
    "rssi": t.int8s(-1),
    "gpp_distance": t.uint8_t(1),
    "gpp_short_addr": t.NWK(0x1234),
}


@pytest.mark.parametrize(
    "field",
    [f.name for f in dataclasses.fields(t.ZigbeeGpPacket) if f.compare],
)
def test_gp_packet_hash(field: str) -> None:
    """Every compared field is hashed, `__hash__` lists them by hand."""
    packet = t.ZigbeeGpPacket()
    other = packet.replace(**{field: GP_PACKET_VALUES[field]})

    assert packet != other
    assert hash(packet) != hash(other)


def test_gp_packet_hash_timestamp() -> None:
    """The timestamp is excluded from the hash and from comparisons."""
    packet = t.ZigbeeGpPacket()
    later = packet.replace(timestamp=datetime(2030, 1, 1, tzinfo=UTC))

    assert packet == later
    assert hash(packet) == hash(later)
