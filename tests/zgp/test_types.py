"""Tests for Green Power type definitions."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

import zigpy.types as t
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
