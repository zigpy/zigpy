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
        delay_minutes = app.config[zigpy.config.CONF_TOPO_SCAN_PERIOD]
        self._scan_period = delay_minutes * 60
        self._scan_task: Optional[asyncio.Task] = None
        self._timestamp: float = 0

    @property
    def timestamp(self) -> float:
        """Return timestamp of successful build."""
        return self._timestamp

    @classmethod
    def new(cls, app: zigpy.typing.ControllerApplicationType) -> "Topology":
        """Create Topology instance."""

        topo = cls(app)
        if app.config[zigpy.config.CONF_TOPO_SCAN_ENABLED]:
            asyncio.create_task(topo.scan_loop())
        return topo

    async def scan_loop(self) -> None:
        """Delay scan by creating a task."""

        while True:
            await asyncio.sleep(self._scan_period)
            if not self._scan_task or self._scan_task.done():
                LOGGER.debug("Starting scheduled neighbor scan")
                await self.scan()

    async def scan(self) -> None:
        """Preempt Topology scan and reschedule."""

        if self._scan_task and not self._scan_task.done():
            LOGGER.debug("Cancelling old scanning task")
            self._scan_task.cancel()

        self._scan_task = asyncio.create_task(self._scan())
        try:
            await self._scan_task
        except asyncio.CancelledError:
            LOGGER.warning("Cancelled topology scanning task")

    async def _scan(self) -> None:
        """Scan topology."""

        devices_to_scan = [
            dev
            for dev in self._app.devices.values()
            if dev.node_desc is not None and not dev.node_desc.is_end_device
        ]
        for device in devices_to_scan:
            if (
                self._app.config[zigpy.config.CONF_TOPO_SKIP_COORDINATOR]
                and device.nwk == 0x0000
            ):
                continue
            if not device.neighbors.supported:
                continue
            LOGGER.debug(
                "Scanning neighbors of %s/0x%04x device", device.ieee, device.nwk
            )
            await device.neighbors.scan()
            await asyncio.sleep(DELAY_INTER_DEVICE)
        LOGGER.debug("Finished scanning neighbors for all devices")
        self._timestamp = time.time()
