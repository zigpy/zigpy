"""Green Power Device model.

A commissioned GPD uses a 32-bit sourceID, has no real network address, and
communicates through GP Proxy devices rather than standard zigpy Device objects.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import logging
import struct

import zigpy.types as t
from zigpy.zgp.types import SecurityKeyType, SecurityLevel

LOGGER = logging.getLogger(__name__)

# Prefix for synthetic IEEE addresses generated from GP sourceIDs.
# This uses a distinctive pattern to avoid collision with real IEEE addresses.
# Format: sourceID (4 bytes LE) + GP_IEEE_SUFFIX (4 bytes)
GP_IEEE_SUFFIX: bytes = b"\x00\x00\x00\x00"


def source_id_to_ieee(source_id: int) -> t.EUI64:
    """Convert a GP sourceID to a synthetic IEEE address (sourceID LE + zero padding)."""
    ieee_bytes = struct.pack("<I", source_id) + GP_IEEE_SUFFIX
    return t.EUI64([t.uint8_t(b) for b in ieee_bytes])


def ieee_to_source_id(ieee: t.EUI64) -> int | None:
    """Extract a GP sourceID from a synthetic IEEE address, or None if not one.

    The "unspecified" sourceID 0x00000000 is not rejected; callers validate it.
    """
    ieee_bytes = bytes(ieee)
    if ieee_bytes[4:] != GP_IEEE_SUFFIX:
        return None
    return struct.unpack("<I", ieee_bytes[:4])[0]


@dataclasses.dataclass
class GPDevice:
    """A commissioned Green Power Device, keyed by 32-bit sourceID.

    Uses a synthetic IEEE, has no real NWK address or standard ZCL endpoints,
    and keeps its own frame counter and security key for replay protection.
    """

    source_id: int
    device_id: int

    # Security configuration
    security_key: t.KeyData | None = None
    security_level: SecurityLevel = SecurityLevel.NoSecurity
    security_key_type: SecurityKeyType = SecurityKeyType.NoKey
    frame_counter: int = 0

    # Device information (from commissioning)
    manufacturer_id: int | None = None
    model_id: int | None = None
    gpd_commands: list[int] = dataclasses.field(default_factory=list)
    server_clusters: list[int] = dataclasses.field(default_factory=list)
    client_clusters: list[int] = dataclasses.field(default_factory=list)

    # Capabilities from commissioning
    mac_seq_num_capability: bool = False
    rx_on_capability: bool = False
    fixed_location: bool = False

    # Timestamps
    last_seen: datetime | None = None

    def __post_init__(self) -> None:
        """Normalize the security key to :class:`zigpy.types.KeyData`."""
        if self.security_key is not None and not isinstance(
            self.security_key, t.KeyData
        ):
            self.security_key = t.KeyData(self.security_key)

    @property
    def ieee(self) -> t.EUI64:
        """Synthetic IEEE address derived from sourceID."""
        return source_id_to_ieee(self.source_id)

    def update_frame_counter(self, counter: int) -> bool:
        """Update the frame counter, accepting only strictly greater values.

        Returns False (rejecting a replay) when counter <= the stored value.
        """
        if counter <= self.frame_counter:
            LOGGER.debug(
                "GP device 0x%08X: dropping frame counter %d <= stored %d",
                self.source_id,
                counter,
                self.frame_counter,
            )
            return False

        self.frame_counter = counter
        self.last_seen = datetime.now(UTC)
        return True

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__}"
            f" source_id=0x{self.source_id:08X}"
            f" device_id=0x{self.device_id:02X}"
            f" security={self.security_level.name}"
            f">"
        )
