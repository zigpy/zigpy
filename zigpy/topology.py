"""Topology builder."""

from __future__ import annotations

import asyncio
import itertools
import logging
import random
import typing

import zigpy.config
import zigpy.neighbor
import zigpy.types as t
import zigpy.util
import zigpy.zdo.types as zdo_t

LOGGER = logging.getLogger(__name__)
REQUEST_DELAY = (1.0, 1.5)

if typing.TYPE_CHECKING:
    import zigpy.application


class ScanNotSupported(Exception):
    pass


INVALID_NEIGHBOR_IEEES = {
    t.EUI64.convert("00:00:00:00:00:00:00:00"),
    t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff"),
}


class Topology(zigpy.util.ListenableMixin):
    """Topology scanner."""

    def __init__(self, app: zigpy.application.ControllerApplication):
        """Instantiate."""
        self._app: zigpy.application.ControllerApplication = app
        self._listeners: dict = {}
        self._scan_period = app.config[zigpy.config.CONF_TOPO_SCAN_PERIOD] * 60
        self._scan_task: asyncio.Task | None = None

        # Keep track of devices that do not support scanning
        self._neighbors_unsupported: set[t.EUI64] = set()
        self._routes_unsupported: set[t.EUI64] = set()

        self.neighbors: dict[t.EUI64, list[zdo_t.Neighbor]] = {}
        self.routes: dict[t.EUI64, list[zdo_t.Route]] = {}

    @classmethod
    def new(cls, app: zigpy.application.ControllerApplication) -> Topology:
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

    async def _scan_table(
        self, scan_request: typing.Callable, entries_attr: str
    ) -> list[typing.Any]:
        """Scan a device table by sending ZDO requests."""

        index = 0
        table = []

        while True:
            status, rsp = await scan_request(index, tries=3, delay=1)

            if status != zdo_t.Status.SUCCESS:
                raise ScanNotSupported()

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

    async def _scan(self) -> None:
        """Scan topology."""

        devices = list(self._app.devices.values())

        for index, device in enumerate(devices):
            LOGGER.debug(
                "Scanning topology (%d/%d) of %s", index + 1, len(devices), device
            )

            # Ignore devices that aren't listening
            if (
                device.node_desc is None
                or not device.node_desc.is_receiver_on_when_idle
            ):
                continue

            # Ignore devices that do not support scanning tables
            if (
                device.ieee in self._neighbors_unsupported
                and device.iee in self.routes_unsupported
            ):
                continue

            # Some coordinators have issues when sending loopback scans to themselves
            if (
                self._app.config[zigpy.config.CONF_TOPO_SKIP_COORDINATOR]
                and device is self._app._device
            ):
                continue

            try:
                self.neighbors[device.ieee] = await self._scan_neighbors(device)
                LOGGER.info(
                    "Scanned neighbors for %s: %s", device, self.neighbors[device.ieee]
                )
            except Exception as e:
                LOGGER.warning("Failed to scan neighbors of %s: %r", device, e)

            self.listener_event(
                "neighbors_updated", device.ieee, self.neighbors[device.ieee]
            )

            try:
                self.routes[device.ieee] = await self._scan_routes(device)
                LOGGER.info(
                    "Scanned routes for %s: %s", device, self.routes[device.ieee]
                )
            except Exception as e:
                LOGGER.warning("Failed to scan routes of %s: %r", device, e)

            self.listener_event("routes_updated", device.ieee, self.routes[device.ieee])

        LOGGER.debug("Finished scanning neighbors for all devices")
        self._handle_unknown_devices()

    def _handle_unknown_devices(self) -> None:
        """Discover unknown devices discovered during topology scanning"""
        # Build a list of unknown devices from the topology scan
        unknown_nwks = set()
        unknown_devices = set()

        for neighbor in itertools.chain.from_iterable(self.neighbors.values()):
            try:
                self._app.get_device(ieee=neighbor.ieee)
            except KeyError:
                unknown_devices.add((neighbor.nwk, neighbor.ieee))

        for route in itertools.chain.from_iterable(self.routes.values()):
            # Ignore inactive or pending routes
            if route.RouteStatus != zdo_t.RouteStatus.Active:
                continue

            for nwk in (route.DstNWK, route.NextHop):
                try:
                    self._app.get_device(nwk=nwk)
                except KeyError:
                    unknown_nwks.add(nwk)

        # First, treat any unknown device as an explicit join
        for nwk, ieee in unknown_devices:
            LOGGER.warning("Discovered unknown device nwk=%s, ieee=%s", nwk, ieee)
            self.handle_join(nwk=nwk, ieee=ieee, parent_nwk=None)
            unknown_nwks.remove(nwk)

        # Then, discover any new devices with unknown NWK addresses
        for nwk in unknown_nwks:
            LOGGER.warning("Discovered unknown device nwk=%s", nwk)
            await self._app._discover_unknown_device(nwk)
