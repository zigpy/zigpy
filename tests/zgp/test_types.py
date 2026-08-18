"""Tests for Green Power type definitions."""

from __future__ import annotations

from zigpy.zgp.types import (
    DEFAULT_GP_LINK_KEY,
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GP_GROUP_ID,
    GPDCommandPayload,
    ProxyCommissioningModeExitMode,
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


def test_device_id_is_uint32():
    d = SrcID(0x12345678)
    assert int(d) == 0x12345678


def test_device_id_hex_repr():
    d = SrcID(0x02)
    assert "0x" in repr(d).lower()


def test_combined_exit_modes():
    """Flags compose via bitwise OR since the type is a bitmap."""
    on_expire = ProxyCommissioningModeExitMode.OnExpire
    on_first = ProxyCommissioningModeExitMode.OnFirstPairing
    on_explicit = ProxyCommissioningModeExitMode.OnExplicitExit

    assert (on_expire | on_first) == 0b011
    assert (on_expire | on_explicit) == 0b101


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
