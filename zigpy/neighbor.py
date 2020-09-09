"""Neighbor list container."""
import asyncio
import logging
import random
from typing import List, Optional

import zigpy.exceptions
import zigpy.types
from zigpy.typing import DeviceType
import zigpy.util
import zigpy.zdo.types

LOGGER = logging.getLogger(__name__)
NeighborListType = List[zigpy.zdo.types.Neighbor]


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
        self._listeners = {}

    @property
    def ieee(self) -> zigpy.types.EUI64:
        """Return IEEE of the device."""
        return self._device.ieee

    @property
    def neighbors(self) -> NeighborListType:
        """Return our list of Neighbors."""
        return self._neighbors

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

        new_neighbors = []
        idx = 0

        while True:
            status, rsp = await self._device.zdo.Mgmt_Lqi_req(idx, tries=3, delay=1)
            self.debug("request status: %s. response: %s", status, rsp)
            if status != zigpy.zdo.types.Status.SUCCESS:
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

                nei = Neighbor(
                    neighbor, self._device.application.devices.get(neighbor.ieee)
                )
                new_neighbors.append(nei)
                idx += 1

            if idx >= rsp.entries or not rsp.neighbor_table_list:
                break

            await asyncio.sleep(random.uniform(1.0, 1.5))
            self.debug("Querying next starting at %s", idx)

        self.debug("Done scanning. Total %s neighbours", len(new_neighbors))
        self._neighbors = new_neighbors
        self.listener_event("neighbors_updated")
        return new_neighbors
