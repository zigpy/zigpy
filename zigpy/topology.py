"""Topology builder."""

from __future__ import annotations

import asyncio
import collections
import itertools
import logging
import random
import typing

import zigpy.config
import zigpy.device
import zigpy.types as t
import zigpy.util
import zigpy.zdo.types as zdo_t

LOGGER = logging.getLogger(__name__)
REQUEST_DELAY = (1.0, 1.5)

if typing.TYPE_CHECKING:
    import zigpy.application


RETRY_SLOW = zigpy.util.retryable_request(tries=3, delay=1)


class ScanNotSupported(Exception):
    pass


INVALID_NEIGHBOR_IEEES = {
    t.EUI64.convert("00:00:00:00:00:00:00:00"),
    t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff"),
}


class Topology(zigpy.util.ListenableMixin):
    """Topology scanner."""

    def __init__(self, app: zigpy.application.ControllerApplication) -> None:
        """Instantiate."""
        self._app: zigpy.application.ControllerApplication = app
        self._listeners: dict = {}
        self._scan_task: asyncio.Task | None = None
        self._scan_loop_task: asyncio.Task | None = None

        # Keep track of devices that do not support scanning
        self._neighbors_unsupported: set[t.EUI64] = set()
        self._routes_unsupported: set[t.EUI64] = set()

        self.neighbors: dict[t.EUI64, list[zdo_t.Neighbor]] = collections.defaultdict(
            list
        )
        self.routes: dict[t.EUI64, list[zdo_t.Route]] = collections.defaultdict(list)

    def start_periodic_scans(self, period: float) -> None:
        self.stop_periodic_scans()
        self._scan_loop_task = asyncio.create_task(self._scan_loop(period))

    def stop_periodic_scans(self) -> None:
        if self._scan_loop_task is not None:
            self._scan_loop_task.cancel()

    async def _scan_loop(self, period: float) -> None:
        """Delay scan by creating a task."""

        while True:
            await asyncio.sleep(period)

            # Don't run a scheduled scan if a scan is already running
            if self._scan_task is not None and not self._scan_task.done():
                continue

            LOGGER.debug("Starting scheduled neighbor scan")

            try:
                await self.scan()
            except asyncio.CancelledError:
                # We explicitly catch a cancellation here to ensure the scan loop will
                # not be interrupted if a manual scan is initiated
                LOGGER.debug("Topology scan cancelled")
            except (Exception, asyncio.CancelledError):
                LOGGER.debug("Topology scan failed", exc_info=True)

    async def scan(
        self, devices: typing.Iterable[zigpy.device.Device] | None = None
    ) -> None:
        """Preempt Topology scan and reschedule."""

        if self._scan_task and not self._scan_task.done():
            LOGGER.debug("Cancelling old scanning task")
            self._scan_task.cancel()

        self._scan_task = asyncio.create_task(self._scan(devices))
        await self._scan_task

    async def _scan_table(
        self, scan_request: typing.Callable, entries_attr: str
    ) -> list[typing.Any]:
        """Scan a device table by sending ZDO requests."""

        index = 0
        table = []

        while True:
            status, rsp = await RETRY_SLOW(scan_request)(index)

            if status != zdo_t.Status.SUCCESS:
                raise ScanNotSupported

            entries = getattr(rsp, entries_attr)

            table.extend(entries)
            index += len(entries)

            # We intentionally sleep after every request, even the last one, to simplify
            # delay logic when scanning many devices in quick succession
            await asyncio.sleep(random.uniform(*REQUEST_DELAY))

            if index >= rsp.Entries or not entries:
                break

        return table

    async def _scan_neighbors(
        self, device: zigpy.device.Device
    ) -> list[zdo_t.Neighbor]:
        if device.ieee in self._neighbors_unsupported:
            return []

        LOGGER.debug("Scanning neighbors of %s", device)

        try:
            table = await self._scan_table(device.zdo.Mgmt_Lqi_req, "NeighborTableList")
        except ScanNotSupported:
            table = []
            self._neighbors_unsupported.add(device.ieee)

        return [n for n in table if n.ieee not in INVALID_NEIGHBOR_IEEES]

    async def _scan_routes(self, device: zigpy.device.Device) -> list[zdo_t.Route]:
        if device.ieee in self._routes_unsupported:
            return []

        LOGGER.debug("Scanning routing table of %s", device)

        try:
            table = await self._scan_table(device.zdo.Mgmt_Rtg_req, "RoutingTableList")
        except ScanNotSupported:
            table = []
            self._routes_unsupported.add(device.ieee)

        return table

    async def _scan(
        self, devices: typing.Iterable[zigpy.device.Device] | None = None
    ) -> None:
        """Scan topology."""

        if devices is None:
            # We iterate over a copy of the devices as opposed to the live dictionary
            devices = list(self._app.devices.values())

        for index, device in enumerate(devices):
            LOGGER.debug(
                "Scanning topology (%d/%d) of %s", index + 1, len(devices), device
            )

            # Ignore devices that aren't routers
            if device.node_desc is None or not (
                device.node_desc.is_router or device.node_desc.is_coordinator
            ):
                continue

            # Ignore devices that do not support scanning tables
            if (
                device.ieee in self._neighbors_unsupported
                and device.ieee in self._routes_unsupported
            ):
                continue

            # Some coordinators have issues when performing loopback scans
            if (
                self._app.config[zigpy.config.CONF_TOPO_SKIP_COORDINATOR]
                and device is self._app._device
            ):
                continue

            try:
                self.neighbors[device.ieee] = await self._scan_neighbors(device)
            except Exception as e:  # noqa: BLE001
                LOGGER.debug("Failed to scan neighbors of %s", device, exc_info=e)
            else:
                LOGGER.info(
                    "Scanned neighbors of %s: %s", device, self.neighbors[device.ieee]
                )

            self.listener_event(
                "neighbors_updated", device.ieee, self.neighbors[device.ieee]
            )

            try:
                # Filter out inactive routes
                routes = await self._scan_routes(device)
                self.routes[device.ieee] = [
                    route
                    for route in routes
                    if route.RouteStatus != zdo_t.RouteStatus.Inactive
                ]
            except Exception as e:  # noqa: BLE001
                LOGGER.debug("Failed to scan routes of %s", device, exc_info=e)
            else:
                LOGGER.info(
                    "Scanned routes of %s: %s", device, self.routes[device.ieee]
                )

            self.listener_event("routes_updated", device.ieee, self.routes[device.ieee])

        LOGGER.debug("Finished scanning neighbors for all devices")
        await self._find_unknown_devices(neighbors=self.neighbors, routes=self.routes)

    async def _find_unknown_devices(
        self,
        *,
        neighbors: dict[t.EUI64, list[zdo_t.Neighbor]],
        routes: dict[t.EUI64, list[zdo_t.Route]],
    ) -> None:
        """Discover unknown devices discovered during topology scanning"""
        # Build a list of unknown devices from the topology scan
        unknown_nwks = set()

        for neighbor in itertools.chain.from_iterable(neighbors.values()):
            try:
                self._app.get_device(nwk=neighbor.nwk)
            except KeyError:
                unknown_nwks.add(neighbor.nwk)

        for route in itertools.chain.from_iterable(routes.values()):
            # Ignore inactive or pending routes
            if route.RouteStatus != zdo_t.RouteStatus.Active:
                continue

            for nwk in (route.DstNWK, route.NextHop):
                try:
                    self._app.get_device(nwk=nwk)
                except KeyError:
                    unknown_nwks.add(nwk)

        # Try to discover any unknown devices
        for nwk in unknown_nwks:
            LOGGER.debug("Found unknown device nwk=%s", nwk)
            await self._app._discover_unknown_device(nwk)
            await asyncio.sleep(random.uniform(*REQUEST_DELAY))
