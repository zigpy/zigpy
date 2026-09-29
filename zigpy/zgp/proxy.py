"""Green Power Proxy Table management.

Tracks which GP Proxy devices are forwarding frames for which GPDs, from the
sink's perspective. The coordinator does not write remote proxy tables directly;
it sends GP Pairing commands that instruct proxies to update their own.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import logging

from zigpy.zgp.types import CommunicationMode, SecurityLevel

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class GPProxyTableEntry:
    """A proxy's knowledge of a GPD: forwarding, security, and comm parameters."""

    source_id: int
    proxy_nwk: int
    communication_mode: CommunicationMode = CommunicationMode.UnicastLightweight
    security_level: SecurityLevel = SecurityLevel.NoSecurity
    frame_counter: int = 0
    first_seen: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        """Update last_seen timestamp."""
        self.last_seen = datetime.now(UTC)


class GPProxyTable:
    """The coordinator's view of which proxy NWKs forward for which GPD sourceIDs."""

    def __init__(self) -> None:
        # Key: (source_id, proxy_nwk) -> GPProxyTableEntry
        self._entries: dict[tuple[int, int], GPProxyTableEntry] = {}

    @property
    def entries(self) -> list[GPProxyTableEntry]:
        """Return all entries as a list."""
        return list(self._entries.values())

    def add_or_update(
        self,
        source_id: int,
        proxy_nwk: int,
        communication_mode: CommunicationMode = CommunicationMode.UnicastLightweight,
        security_level: SecurityLevel = SecurityLevel.NoSecurity,
        frame_counter: int = 0,
    ) -> GPProxyTableEntry:
        """Add or update the proxy table entry for a (sourceID, proxy) pair."""
        key = (source_id, proxy_nwk)
        entry = self._entries.get(key)

        if entry is not None:
            entry.touch()
            entry.frame_counter = max(entry.frame_counter, frame_counter)
            return entry

        entry = GPProxyTableEntry(
            source_id=source_id,
            proxy_nwk=proxy_nwk,
            communication_mode=communication_mode,
            security_level=security_level,
            frame_counter=frame_counter,
        )
        self._entries[key] = entry

        LOGGER.debug(
            "New proxy entry: GPD 0x%08X via proxy 0x%04X",
            source_id,
            proxy_nwk,
        )
        return entry

    def remove_by_source_id(self, source_id: int) -> int:
        """Remove all entries for a given GPD source ID, returning the count."""
        keys_to_remove = [key for key in self._entries if key[0] == source_id]
        for key in keys_to_remove:
            del self._entries[key]

        if keys_to_remove:
            LOGGER.debug(
                "Removed %d proxy entries for GPD 0x%08X",
                len(keys_to_remove),
                source_id,
            )
        return len(keys_to_remove)

    def remove_by_proxy(self, proxy_nwk: int) -> int:
        """Remove all entries for a given proxy NWK address, returning the count."""
        keys_to_remove = [key for key in self._entries if key[1] == proxy_nwk]
        for key in keys_to_remove:
            del self._entries[key]
        return len(keys_to_remove)

    def get_proxies_for_device(self, source_id: int) -> list[int]:
        """Get NWK addresses of all proxies forwarding for a GPD."""
        return [key[1] for key in self._entries if key[0] == source_id]

    def get_devices_for_proxy(self, proxy_nwk: int) -> list[int]:
        """Get source IDs of all GPDs forwarded by a proxy."""
        return [key[0] for key in self._entries if key[1] == proxy_nwk]

    def get_entry(self, source_id: int, proxy_nwk: int) -> GPProxyTableEntry | None:
        """Get a specific entry."""
        return self._entries.get((source_id, proxy_nwk))

    def clear(self) -> None:
        """Remove all entries."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        count = len(self._entries)
        return f"<{type(self).__name__} {count} {'entry' if count == 1 else 'entries'}>"
