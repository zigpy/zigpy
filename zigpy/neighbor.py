"""Neighbor list container."""
import asyncio
import functools
import logging
import random
import time
from typing import Iterator, List, Optional

import zigpy.exceptions
import zigpy.types
from zigpy.typing import DeviceType
import zigpy.util
import zigpy.zdo.types

LOGGER = logging.getLogger(__name__)
NeighborListType = List[zigpy.zdo.types.Neighbor]
REQUEST_DELAY = (1.0, 1.5)


class Neighbor:
    """Neighbor entry."""

    def __init__(self, neighbor: zigpy.zdo.types.Neighbor, device: DeviceType):
        """Initialize neighbor instance."""
        self._device = device
        self._neighbor = neighbor

    @property
    def device(self) -> zigpy.typing.DeviceType:
        """Return zigpy device corresponding to this neighbor."""
        return self._device

    @property
    def neighbor(self) -> zigpy.zdo.types.Neighbor:
        """Return neighbor."""
        return self._neighbor


class Neighbors(zigpy.util.ListenableMixin, zigpy.util.LocalLogMixin):
    """Neighbor list for a device."""

    def __init__(self, device: DeviceType) -> None:
        """Initialize instance."""
        self._device = device
        self._neighbors: NeighborListType = []
        self._staging: NeighborListType = []
        self._supported: bool = True
        self._listeners = {}
        self.last_scan = None

    def append(self, *args, **kwargs) -> None:
        """Append method."""
        return self.neighbors.append(*args, **kwargs)

    def __getitem__(self, *args, **kwargs) -> Neighbor:
        """Get item method."""
        return self.neighbors.__getitem__(*args, **kwargs)

    def __setitem__(self, *args, **kwargs) -> None:
        """Set item method."""
        return self.neighbors.__setitem__(*args, **kwargs)

    def __len__(self) -> int:
        """Len item method."""
        return self.neighbors.__len__()

    def __iter__(self) -> Iterator:
        """Iter item method."""
        return self.neighbors.__iter__()

    @property
    def ieee(self) -> zigpy.types.EUI64:
        """Return IEEE of the device."""
        return self._device.ieee

    @property
    def neighbors(self) -> NeighborListType:
        """Return our list of Neighbors."""
        return self._neighbors

    @property
    def supported(self) -> bool:
        """Return True if Mgmt_lqi_req is supported."""
        return self._supported

    def log(self, lvl: int, msg: str, *args, **kwargs) -> None:
        msg = "[0x%04x] " + msg
        args = (self._device.nwk,) + args
        return LOGGER.log(lvl, msg, *args, **kwargs)

    async def scan(self) -> Optional[NeighborListType]:
        """Scan device for neighbors."""
        try:
            return await self._scan()
        except (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException):
            return None

    async def _scan(self) -> NeighborListType:
        """Scan device."""

        idx = 0
        self._staging = []

        while True:
            status, rsp = await self._device.zdo.Mgmt_Lqi_req(idx, tries=3, delay=1)
            self.debug("request status: %s. response: %s", status, rsp)
            if status != zigpy.zdo.types.Status.SUCCESS:
                self._supported = False
                self.debug("does not support 'Mgmt_Lqi_req'")
                return

            for neighbor in rsp.neighbor_table_list:
                if str(neighbor.ieee) in (
                    "00:00:00:00:00:00:00:00",
                    "ff:ff:ff:ff:ff:ff:ff:ff",
                ):
                    self.debug("ignoring invalid neighbor: %s", neighbor.ieee)
                    idx += 1
                    continue

                self.stage_neighbor(neighbor)
                idx += 1

            if idx >= rsp.entries or not rsp.neighbor_table_list:
                break

            await asyncio.sleep(random.uniform(*REQUEST_DELAY))
            self.debug("Querying next starting at %s", idx)

        self.debug("Done scanning. Total %s neighbours", len(self._staging))
        self.done_staging()
        self.listener_event("neighbors_updated")
        return self._neighbors

    def _add_neighbor(self, staged: bool, neighbor: zigpy.zdo.types.Neighbor) -> None:
        """Add neighbor."""

        nei = Neighbor(neighbor, self._device.application.devices.get(neighbor.ieee))
        if staged:
            self._staging.append(nei)
            return
        self._neighbors.append(nei)

    add_neighbor = functools.partialmethod(_add_neighbor, False)
    stage_neighbor = functools.partialmethod(_add_neighbor, True)

    def done_staging(self) -> None:
        """Switch staging."""
        self._neighbors = self._staging
        self._staging = None
        self.last_scan = time.time()
