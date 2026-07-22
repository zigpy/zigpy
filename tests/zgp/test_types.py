"""Tests for Green Power type definitions."""

from __future__ import annotations

from zigpy.zgp.types import (
    DEFAULT_GP_LINK_KEY,
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GP_GROUP_ID,
    DeviceID,
    ProxyCommissioningModeExitMode,
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
    d = DeviceID(0x12345678)
    assert int(d) == 0x12345678


def test_device_id_hex_repr():
    d = DeviceID(0x02)
    assert "0x" in repr(d).lower()


def test_combined_exit_modes():
    """Flags compose via bitwise OR since the type is a bitmap."""
    on_expire = ProxyCommissioningModeExitMode.OnExpire
    on_first = ProxyCommissioningModeExitMode.OnFirstPairing
    on_explicit = ProxyCommissioningModeExitMode.OnExplicitExit

    assert (on_expire | on_first) == 0b011
    assert (on_expire | on_explicit) == 0b101
