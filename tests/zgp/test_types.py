"""Tests for Green Power type definitions."""

from __future__ import annotations

from datetime import UTC, datetime

import zigpy.types as t
from zigpy.zgp.types import (
    DEFAULT_GP_LINK_KEY,
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GP_GROUP_ID,
    ApplicationID,
    DeviceID,
    GPDCommandID,
    GPDCommandPayload,
    ProxyCommissioningModeExitMode,
    SinkCommissioningExitMode,
    SrcID,
)


def test_gp_endpoint():
    assert GP_ENDPOINT == 242


def test_gp_cluster_id():
    assert GP_CLUSTER_ID == 0x0021


def test_gp_group_id():
    assert GP_GROUP_ID == 0x0B84


def test_default_link_key():
    assert bytes(DEFAULT_GP_LINK_KEY) == b"ZigBeeAlliance09"
    assert len(DEFAULT_GP_LINK_KEY) == 16


def test_src_id_is_uint32():
    s = SrcID(0x12345678)
    assert int(s) == 0x12345678


def test_src_id_hex_repr():
    s = SrcID(0x02)
    assert "0x" in repr(s).lower()


def test_device_id_enum():
    assert DeviceID(0x02) is DeviceID.OnOffSwitch
    assert DeviceID.Undefined == 0xFE


def test_combined_exit_modes():
    """Flags compose via bitwise OR since the type is a bitmap."""
    on_expire = SinkCommissioningExitMode.OnExpire
    on_first = SinkCommissioningExitMode.OnFirstPairing
    on_explicit = SinkCommissioningExitMode.OnExplicitExit

    assert (on_expire | on_first) == 0b011
    assert (on_expire | on_explicit) == 0b101


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


def test_command_payload():
    payload, rest = GPDCommandPayload.deserialize(b"\x02\xaa\xbbrest")

    assert payload == b"\xaa\xbb"
    assert rest == b"rest"
    assert payload.serialize() == b"\x02\xaa\xbb"


def test_command_payload_empty():
    payload, rest = GPDCommandPayload.deserialize(b"\x00rest")

    assert payload == b""
    assert rest == b"rest"
    assert not payload.unspecified
    assert payload.serialize() == b"\x00"


def test_command_payload_unspecified():
    """A length byte of 0xff means unspecified, which is not an empty payload."""
    payload, rest = GPDCommandPayload.deserialize(b"\xffrest")

    assert payload == b""
    assert rest == b"rest"
    assert payload.unspecified
    assert payload.serialize() == b"\xff"


def test_command_payload_unspecified_is_not_empty():
    unspecified, _ = GPDCommandPayload.deserialize(b"\xff")
    empty, _ = GPDCommandPayload.deserialize(b"\x00")

    assert unspecified == empty
    assert unspecified.serialize() != empty.serialize()


def test_command_payload_copy_keeps_unspecified():
    unspecified, _ = GPDCommandPayload.deserialize(b"\xff")
    empty, _ = GPDCommandPayload.deserialize(b"\x00")

    assert GPDCommandPayload(unspecified).unspecified
    assert GPDCommandPayload(unspecified).serialize() == b"\xff"
    assert not GPDCommandPayload(empty).unspecified
    assert GPDCommandPayload(empty).serialize() == b"\x00"
    assert not GPDCommandPayload(b"").unspecified


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
