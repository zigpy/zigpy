"""Green Power helper functions."""

from __future__ import annotations

import zigpy.types as t

# Marks a synthetic EUI64 built from a 32-bit GPD SrcID
GP_SYNTHETIC_IEEE_MARKER = b"\x00\x00\x00\x00"


def synthetic_ieee(src_id: int) -> t.EUI64:
    """Build the synthetic EUI64 under which a SrcID-addressed GPD is registered."""
    return t.EUI64(int(src_id).to_bytes(4, "little") + GP_SYNTHETIC_IEEE_MARKER)


def derive_alias(gpd_id: int | t.EUI64) -> t.NWK:
    """Derive the alias NWK source address from a GPD ID (spec A.3.6.3.3.1).

    The alias is the NWK short address that proxies use as the source address when
    sending frames on behalf of a GPD. The GPD ID is the SrcID for ApplicationID
    0b000 and the GPD IEEE address for 0b010; the GPD endpoint is never used.
    """
    if isinstance(gpd_id, t.EUI64):
        gpd_id = int.from_bytes(gpd_id.serialize(), "little")

    # Reserved addresses are 0x0000 (the coordinator) and >0xFFF7 (broadcasts)
    alias = gpd_id & 0xFFFF

    if 0x0000 < alias <= 0xFFF7:
        return t.NWK(alias)

    xored = alias ^ ((gpd_id >> 16) & 0xFFFF)

    if 0x0000 < xored <= 0xFFF7:
        return t.NWK(xored)

    if alias == 0x0000:
        return t.NWK(0x0007)

    return t.NWK(alias - 0x0008)
