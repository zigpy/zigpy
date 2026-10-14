"""Tests for Green Power helper functions."""

from __future__ import annotations

import pytest

import zigpy.types as t
from zigpy.zgp.util import derive_alias, synthetic_ieee


@pytest.mark.parametrize(
    ("gpd_id", "alias"),
    [
        # The two LSBs are directly usable
        (0x12345678, 0x5678),
        # The two LSBs are the coordinator address and so is the XOR fallback
        (0x00000000, 0x0007),
        # The two LSBs are reserved but the XOR with the next two bytes is usable
        (0x1234FFF8, 0xEDCC),
        # Both the two LSBs and the XOR are reserved: subtract 0x0008
        (0xFFF8FFF8, 0xFFF0),
        (0x0000FFFF, 0xFFF7),
        # IEEE-addressed GPDs derive the alias from the EUI64
        (t.EUI64.convert("00:00:00:00:12:34:56:78"), 0x5678),
        (t.EUI64.convert("11:22:33:44:55:66:77:88"), 0x7788),
    ],
)
def test_derive_alias(gpd_id, alias):
    assert derive_alias(gpd_id) == t.NWK(alias)


def test_synthetic_ieee():
    ieee = synthetic_ieee(0x12345678)

    assert ieee == t.EUI64.convert("00:00:00:00:12:34:56:78")
    assert derive_alias(ieee) == derive_alias(0x12345678)
