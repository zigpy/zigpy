"""Topology builder."""

import asyncio
import logging
import time
from typing import Dict, Optional

import zigpy.config
import zigpy.neighbor
import zigpy.types as t
import zigpy.typing
import zigpy.util

LOGGER = logging.getLogger(__name__)
DELAY_INTER_DEVICE = 3


class Topology(zigpy.util.ListenableMixin):
    """Topology scanner."""

    def __init__(self, app: zigpy.typing.ControllerApplicationType):
        """Instantiate."""
        self._app: zigpy.typing.ControllerApplicationType = app
        self._listeners: Dict = {}
        self._last_scanned: Optional[t.EUI64] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._timestamp: float = 0

    @property
    def current(self) -> Dict[t.EUI64, zigpy.neighbor.Neighbors]:
        """Return a dict of Neighbors for each device."""
        return {dev.ieee: dev.neighbors for dev in self._app.devices.values()}

    @property
    def timestamp(self) -> float:
        """Return timestamp of successful build."""
        return self._timestamp

    def async_schedule_scan(self) -> None:
        """Setup periodic scan of all devices."""
        loop = asyncio.get_running_loop()
        delay_minutes = self._app.config[zigpy.config.CONF_TOPO_SCAN_PERIOD]
        loop.call_later(delay_minutes * 60, self.scan)

    async def scan(self) -> None:
        """Preempt Topology scan and reschedule."""

        if self._scan_task and not self._scan_task.done():
            LOGGER.debug("Cancelling old scanning task")
            self._scan_task.cancel()

        self._scan_task = asyncio.create_task(self._scan())
        self.async_schedule_scan()
        try:
            await self._scan_task
        except asyncio.CancelledError:
            LOGGER.warning("Cancelled topology scanning task")

    async def _scan(self) -> None:
        """Scan topology."""
        for device in self._app.devices.values():
            if not device.neighbors.supported:
                continue
            LOGGER.debug(
                "Scanning neighbors of %s/0x%04x device", device.ieee, device.nwk
            )
            await device.neighbors.scan()
            await asyncio.sleep(DELAY_INTER_DEVICE)
        self._timestamp = time.time()
