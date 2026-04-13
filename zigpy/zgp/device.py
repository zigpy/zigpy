"""Green Power Device model.

Represents a commissioned Green Power Device (GPD) within zigpy's
device registry. Unlike standard zigpy Device objects, GPDevices
use 32-bit sourceIDs, have no real network address, and communicate
through GP Proxy devices.
"""

from __future__ import annotations

import dataclasses
import logging
import struct
from datetime import UTC, datetime

import zigpy.types as t

from zigpy.zgp.types import (
    DeviceID,
    SecurityKeyType,
    SecurityLevel,
)

LOGGER = logging.getLogger(__name__)

# Prefix for synthetic IEEE addresses generated from GP sourceIDs.
# This uses a distinctive pattern to avoid collision with real IEEE addresses.
# Format: sourceID (4 bytes LE) + GP_IEEE_SUFFIX (4 bytes)
GP_IEEE_SUFFIX: bytes = b"\x00\x00\x00\x00"


def source_id_to_ieee(source_id: int) -> t.EUI64:
    """Convert a GP sourceID to a synthetic IEEE address.

    The synthetic IEEE is constructed by placing the sourceID in the
    lower 4 bytes (little-endian) and padding the upper 4 bytes with zeros.
    This matches the convention used by zigbee-herdsman/zigbee2mqtt.

    Args:
        source_id: 32-bit GP device source identifier.

    Returns:
        Synthetic 8-byte EUI64 address.
    """
    ieee_bytes = struct.pack("<I", source_id) + GP_IEEE_SUFFIX
    return t.EUI64([t.uint8_t(b) for b in ieee_bytes])


def ieee_to_source_id(ieee: t.EUI64) -> int | None:
    """Extract a GP sourceID from a synthetic IEEE address.

    Returns None if the IEEE address doesn't look like a GP synthetic address
    (i.e., upper 4 bytes are not all zeros).

    Args:
        ieee: EUI64 address to check.

    Returns:
        32-bit sourceID if this is a GP synthetic address, None otherwise.
    """
    ieee_bytes = bytes(ieee)
    if ieee_bytes[4:] != GP_IEEE_SUFFIX:
        return None
    return struct.unpack("<I", ieee_bytes[:4])[0]


@dataclasses.dataclass
class GPDevice:
    """Represents a commissioned Green Power Device.

    Unlike standard zigpy Device objects, GPDevices:
    - Use sourceID (32-bit) as primary identifier
    - Have synthetic IEEE addresses (derived from sourceID)
    - Have no real NWK address
    - Do not have standard ZCL endpoints or clusters
    - Maintain their own frame counter for replay protection
    - Store their security key and security level
    - Are receive-only (commands flow GPD → coordinator, never reverse
      except during commissioning for RX-capable GPDs)
    """

    source_id: int
    device_id: int

    # Security configuration
    security_key: bytes | None = None
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

    @property
    def ieee(self) -> t.EUI64:
        """Synthetic IEEE address derived from sourceID."""
        return source_id_to_ieee(self.source_id)

    @property
    def model_identifier(self) -> str:
        """Return a model string for quirks matching.

        Pattern matches zigbee2mqtt convention: 'GreenPower_{device_id_value}'.
        """
        return f"GreenPower_{self.device_id}"

    def update_frame_counter(self, counter: int) -> bool:
        """Update frame counter with replay protection.

        The frame counter must be strictly greater than the stored value
        to prevent replay attacks. This is a core security mechanism
        for Green Power devices.

        Args:
            counter: New frame counter value from received frame.

        Returns:
            True if the counter was accepted and updated.
            False if the counter is not greater than the stored value
            (potential replay attack).
        """
        if counter <= self.frame_counter:
            LOGGER.warning(
                "GP device 0x%08X: frame counter %d <= stored %d, "
                "possible replay attack",
                self.source_id,
                counter,
                self.frame_counter,
            )
            return False

        self.frame_counter = counter
        self.last_seen = datetime.now(UTC)
        return True

    def as_dict(self) -> dict:
        """Serialize to a dictionary for database persistence."""
        return {
            "source_id": self.source_id,
            "device_id": self.device_id,
            "security_key": self.security_key.hex() if self.security_key else None,
            "security_level": int(self.security_level),
            "security_key_type": int(self.security_key_type),
            "frame_counter": self.frame_counter,
            "manufacturer_id": self.manufacturer_id,
            "model_id": self.model_id,
            "gpd_commands": self.gpd_commands,
            "server_clusters": self.server_clusters,
            "client_clusters": self.client_clusters,
            "mac_seq_num_capability": self.mac_seq_num_capability,
            "rx_on_capability": self.rx_on_capability,
            "fixed_location": self.fixed_location,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GPDevice:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary as produced by as_dict().

        Returns:
            GPDevice instance.
        """
        security_key_hex = data.get("security_key")
        return cls(
            source_id=data["source_id"],
            device_id=data["device_id"],
            security_key=(
                bytes.fromhex(security_key_hex) if security_key_hex else None
            ),
            security_level=SecurityLevel(data.get("security_level", 0)),
            security_key_type=SecurityKeyType(data.get("security_key_type", 0)),
            frame_counter=data.get("frame_counter", 0),
            manufacturer_id=data.get("manufacturer_id"),
            model_id=data.get("model_id"),
            gpd_commands=data.get("gpd_commands", []),
            server_clusters=data.get("server_clusters", []),
            client_clusters=data.get("client_clusters", []),
            mac_seq_num_capability=data.get("mac_seq_num_capability", False),
            rx_on_capability=data.get("rx_on_capability", False),
            fixed_location=data.get("fixed_location", False),
        )

    def __repr__(self) -> str:
        return (
            f"GPDevice(source_id=0x{self.source_id:08X}, "
            f"device_id=0x{self.device_id:02X}, "
            f"model={self.model_identifier}, "
            f"security={self.security_level.name})"
        )
