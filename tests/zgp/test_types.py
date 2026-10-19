"""Tests for Green Power type definitions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import zigpy.types as t
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    GPDCommandPayload,
    ProxyCommissioningModeExitMode,
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


def test_gp_packet_hash():
    packet = t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(0x12345678),
        command_id=GPDCommandID.Toggle,
        frame_counter=t.uint32_t(1),
    )

    # The timestamp is excluded from the hash and from comparisons
    later = packet.replace(timestamp=datetime(2030, 1, 1, tzinfo=UTC))
    assert hash(packet) == hash(later)
    assert packet == later

    assert hash(packet) != hash(packet.replace(frame_counter=t.uint32_t(2)))
    assert hash(packet) != hash(packet.replace(gpp_distance=t.uint8_t(0x42)))
