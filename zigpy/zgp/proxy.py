"""Green Power Proxy Table management.

Tracks which GP Proxy devices are forwarding frames for which GPDs.
The coordinator (GP Sink) maintains this state to understand the
network topology of GP frame forwarding.

The coordinator does not directly write proxy tables on remote devices.
Instead, it sends GP Pairing commands that instruct proxies to update
their own local tables. This module tracks the expected state from
the sink's perspective.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime

from zigpy.zgp.types import CommunicationMode, SecurityLevel

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class GPProxyTableEntry:
    """An entry representing a proxy's knowledge of a GPD.

    Tracks which GP Proxy device is forwarding frames for a given GPD
    source ID, along with the security and communication parameters.
    """

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
    """Manages the coordinator's view of GP Proxy forwarding state.

    Tracks which proxy NWK addresses have forwarded frames for which
    GPD source IDs. This information is useful for:
    - Understanding which proxies are in range of a GPD
    - Choosing unicast targets for GP Response commands
    - Diagnosing connectivity issues
    """

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
        """Add or update a proxy table entry.

        Called when a GP Notification is received from a proxy,
        indicating the proxy is forwarding for this GPD.

        Args:
            source_id: GPD source identifier.
            proxy_nwk: NWK address of the forwarding proxy.
            communication_mode: Communication mode in use.
            security_level: Security level of the GPD.
            frame_counter: Latest frame counter seen.

        Returns:
            The created or updated entry.

        """
        key = (source_id, proxy_nwk)
        entry = self._entries.get(key)

        if entry is not None:
            entry.touch()
            if frame_counter > entry.frame_counter:
                entry.frame_counter = frame_counter
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
        """Remove all entries for a given GPD source ID.

        Called when a GPD is decommissioned.

        Args:
            source_id: GPD source identifier.

        Returns:
            Number of entries removed.

        """
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
        """Remove all entries for a given proxy NWK address.

        Called when a proxy device leaves the network.

        Args:
            proxy_nwk: NWK address of the proxy.

        Returns:
            Number of entries removed.

        """
        keys_to_remove = [key for key in self._entries if key[1] == proxy_nwk]
        for key in keys_to_remove:
            del self._entries[key]
        return len(keys_to_remove)

    def get_proxies_for_device(self, source_id: int) -> list[int]:
        """Get NWK addresses of all proxies forwarding for a GPD.

        Args:
            source_id: GPD source identifier.

        Returns:
            List of proxy NWK addresses.

        """
        return [key[1] for key in self._entries if key[0] == source_id]

    def get_devices_for_proxy(self, proxy_nwk: int) -> list[int]:
        """Get source IDs of all GPDs forwarded by a proxy.

        Args:
            proxy_nwk: NWK address of the proxy.

        Returns:
            List of GPD source IDs.

        """
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
        return f"GPProxyTable({len(self._entries)} entries)"
