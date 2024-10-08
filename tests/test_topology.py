from __future__ import annotations

import asyncio
import contextlib
from unittest import mock

import pytest

from tests.conftest import App, make_ieee, make_neighbor, make_route
import zigpy.config as conf
import zigpy.device
import zigpy.endpoint
import zigpy.profiles
import zigpy.topology
import zigpy.types as t
import zigpy.zdo.types as zdo_t


@pytest.fixture(autouse=True)
def remove_request_delay():
    with mock.patch("zigpy.topology.REQUEST_DELAY", new=(0, 0)):
        yield


@pytest.fixture
def topology(make_initialized_device):
    app = App(
        {
            conf.CONF_DEVICE: {conf.CONF_DEVICE_PATH: "/dev/null"},
            conf.CONF_TOPO_SKIP_COORDINATOR: True,
        }
    )

    coordinator = make_initialized_device(app)
    coordinator.nwk = 0x0000

    app.state.node_info.nwk = coordinator.nwk
    app.state.node_info.ieee = coordinator.ieee
    app.state.node_info.logical_type = zdo_t.LogicalType.Coordinator

    return zigpy.topology.Topology(app)


@contextlib.contextmanager
def patch_device_tables(
    device: zigpy.device.Device,
    neighbors: list | BaseException | zdo_t.Status,
    routes: list | BaseException | zdo_t.Status,
):
    def mgmt_lqi_req(StartIndex: t.uint8_t):
        status = zdo_t.Status.SUCCESS
        entries = 0
        start_index = 0
        table: list[zdo_t.Neighbor] = []

        if isinstance(neighbors, zdo_t.Status):
            status = neighbors
        elif isinstance(neighbors, BaseException):
            raise neighbors
        else:
            entries = len(neighbors)
            start_index = StartIndex
            table = neighbors[StartIndex : StartIndex + 3]

        return list(
            {
                "Status": status,
                "Neighbors": zdo_t.Neighbors(
                    Entries=entries,
                    StartIndex=start_index,
                    NeighborTableList=table,
                ),
            }.values()
        )

    def mgmt_rtg_req(StartIndex: t.uint8_t):
        status = zdo_t.Status.SUCCESS
        entries = 0
        start_index = 0
        table: list[zdo_t.Route] = []

        if isinstance(routes, zdo_t.Status):
            status = routes
        elif isinstance(routes, BaseException):
            raise routes
        else:
            entries = len(routes)
            start_index = StartIndex
            table = routes[StartIndex : StartIndex + 3]

        return list(
            {
                "Status": status,
                "Routes": zdo_t.Routes(
                    Entries=entries,
                    StartIndex=start_index,
                    RoutingTableList=table,
                ),
            }.values()
        )

    lqi_req_patch = mock.patch.object(
        device.zdo,
        "Mgmt_Lqi_req",
        mock.AsyncMock(side_effect=mgmt_lqi_req, spec_set=device.zdo.Mgmt_Lqi_req),
    )
    rtg_req_patch = mock.patch.object(
        device.zdo,
        "Mgmt_Rtg_req",
        mock.AsyncMock(side_effect=mgmt_rtg_req, spec_set=device.zdo.Mgmt_Rtg_req),
    )

    with lqi_req_patch, rtg_req_patch:
        yield


async def test_scan_no_devices(topology) -> None:
    await topology.scan()

    assert not topology.neighbors
    assert not topology.routes


@pytest.mark.parametrize(
    ("neighbors", "routes"),
    [
        ([], asyncio.TimeoutError()),
        ([], []),
        (asyncio.TimeoutError(), asyncio.TimeoutError()),
    ],
)
async def test_scan_failures(
    topology, make_initialized_device, neighbors, routes
) -> None:
    dev = make_initialized_device(topology._app)

    with patch_device_tables(dev, neighbors=neighbors, routes=routes):
        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 1 if not neighbors else 3
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 1 if not routes else 3

    assert not topology.neighbors[dev.ieee]
    assert not topology.routes[dev.ieee]


async def test_neighbors_not_supported(topology, make_initialized_device) -> None:
    dev = make_initialized_device(topology._app)

    with patch_device_tables(dev, neighbors=zdo_t.Status.NOT_SUPPORTED, routes=[]):
        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 1
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 1

        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 1
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 2


async def test_routes_not_supported(topology, make_initialized_device) -> None:
    dev = make_initialized_device(topology._app)

    with patch_device_tables(dev, neighbors=[], routes=zdo_t.Status.NOT_SUPPORTED):
        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 1
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 1

        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 2
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 1


async def test_routes_and_neighbors_not_supported(
    topology, make_initialized_device
) -> None:
    dev = make_initialized_device(topology._app)

    with patch_device_tables(
        dev, neighbors=zdo_t.Status.NOT_SUPPORTED, routes=zdo_t.Status.NOT_SUPPORTED
    ):
        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 1
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 1

        await topology.scan()

        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 1
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 1


async def test_scan_end_device(topology, make_initialized_device) -> None:
    dev = make_initialized_device(topology._app)
    dev.node_desc.logical_type = zdo_t.LogicalType.EndDevice

    with patch_device_tables(dev, neighbors=[], routes=[]):
        await topology.scan()

        # The device will not be scanned because it is not a router
        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 0
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 0


async def test_scan_explicit_device(topology, make_initialized_device) -> None:
    dev1 = make_initialized_device(topology._app)
    dev2 = make_initialized_device(topology._app)

    with patch_device_tables(dev1, neighbors=[], routes=[]):
        with patch_device_tables(dev2, neighbors=[], routes=[]):
            await topology.scan(devices=[dev2])

            # Only the second device was scanned
            assert len(dev1.zdo.Mgmt_Lqi_req.mock_calls) == 0
            assert len(dev1.zdo.Mgmt_Rtg_req.mock_calls) == 0
            assert len(dev2.zdo.Mgmt_Lqi_req.mock_calls) == 1
            assert len(dev2.zdo.Mgmt_Rtg_req.mock_calls) == 1


async def test_scan_router_many(topology, make_initialized_device) -> None:
    dev = make_initialized_device(topology._app)

    with patch_device_tables(
        dev,
        neighbors=[
            make_neighbor(ieee=make_ieee(2 + i), nwk=0x1234 + i) for i in range(100)
        ],
        routes=[
            make_route(dest_nwk=0x1234 + i, next_hop=0x1234 + i) for i in range(100)
        ],
    ):
        await topology.scan()

        # We only permit three scans per request
        assert len(dev.zdo.Mgmt_Lqi_req.mock_calls) == 34
        assert len(dev.zdo.Mgmt_Rtg_req.mock_calls) == 34

    assert topology.neighbors[dev.ieee] == [
        make_neighbor(ieee=make_ieee(2 + i), nwk=0x1234 + i) for i in range(100)
    ]
    assert topology.routes[dev.ieee] == [
        make_route(dest_nwk=0x1234 + i, next_hop=0x1234 + i) for i in range(100)
    ]


async def test_scan_skip_coordinator(topology, make_initialized_device) -> None:
    coordinator = topology._app._device
    assert coordinator.nwk == 0x0000

    with patch_device_tables(coordinator, neighbors=[], routes=[]):
        await topology.scan()

        assert len(coordinator.zdo.Mgmt_Lqi_req.mock_calls) == 0
        assert len(coordinator.zdo.Mgmt_Rtg_req.mock_calls) == 0

    assert not topology.neighbors[coordinator.ieee]
    assert not topology.routes[coordinator.ieee]


async def test_scan_coordinator(topology) -> None:
    app = topology._app
    app.config[conf.CONF_TOPO_SKIP_COORDINATOR] = False

    coordinator = app._device
    coordinator.node_desc.logical_type = zdo_t.LogicalType.Coordinator
    assert coordinator.nwk == 0x0000

    with patch_device_tables(
        coordinator,
        neighbors=[
            make_neighbor(ieee=make_ieee(2), nwk=0x1234),
        ],
        routes=[
            make_route(dest_nwk=0x1234, next_hop=0x1234),
        ],
    ):
        await topology.scan()

        assert len(coordinator.zdo.Mgmt_Lqi_req.mock_calls) == 1
        assert len(coordinator.zdo.Mgmt_Rtg_req.mock_calls) == 1

    assert topology.neighbors[coordinator.ieee] == [
        make_neighbor(ieee=make_ieee(2), nwk=0x1234)
    ]
    assert topology.routes[coordinator.ieee] == [
        make_route(dest_nwk=0x1234, next_hop=0x1234)
    ]


@mock.patch("zigpy.application.ControllerApplication._discover_unknown_device")
async def test_discover_new_devices(
    discover_unknown_device, topology, make_initialized_device
) -> None:
    dev1 = make_initialized_device(topology._app)
    dev2 = make_initialized_device(topology._app)

    await topology._find_unknown_devices(
        neighbors={
            dev1.ieee: [
                # Existing devices
                make_neighbor(ieee=dev1.ieee, nwk=dev1.nwk),
                make_neighbor(ieee=dev2.ieee, nwk=dev2.nwk),
                # Unknown device
                make_neighbor(
                    ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"), nwk=0xFF00
                ),
            ],
            dev2.ieee: [],
        },
        routes={
            dev1.ieee: [
                # Existing devices
                make_route(dest_nwk=dev1.nwk, next_hop=dev1.nwk),
                make_route(dest_nwk=dev2.nwk, next_hop=dev2.nwk),
                # Via existing devices
                make_route(dest_nwk=0xFF01, next_hop=dev2.nwk),
                make_route(dest_nwk=dev2.nwk, next_hop=0xFF02),
                # Inactive route
                make_route(
                    dest_nwk=0xFF03, next_hop=0xFF04, status=zdo_t.RouteStatus.Inactive
                ),
            ],
            dev2.ieee: [],
        },
    )

    assert len(discover_unknown_device.mock_calls) == 3
    assert mock.call(0xFF00) in discover_unknown_device.mock_calls
    assert mock.call(0xFF01) in discover_unknown_device.mock_calls
    assert mock.call(0xFF02) in discover_unknown_device.mock_calls


@mock.patch("zigpy.topology.Topology._scan")
async def test_scan_start_concurrent(mock_scan, topology):
    concurrency = 0
    max_concurrency = 0

    async def _scan(_):
        nonlocal concurrency
        nonlocal max_concurrency

        concurrency += 1
        max_concurrency = max(concurrency, max_concurrency)

        try:
            await asyncio.sleep(0.01)
        finally:
            concurrency -= 1
            max_concurrency = max(concurrency, max_concurrency)

    mock_scan.side_effect = _scan

    topology.start_periodic_scans(0.1)
    topology.start_periodic_scans(0.1)
    topology.start_periodic_scans(0.1)
    topology.start_periodic_scans(0.1)
    topology.start_periodic_scans(0.1)

    scan1 = asyncio.create_task(topology.scan())
    scan2 = asyncio.create_task(topology.scan())

    await asyncio.sleep(0.01)

    with pytest.raises(asyncio.CancelledError):
        await scan1

    await scan2

    # Wait for a "scan" to finish
    await asyncio.sleep(0.15)
    await topology._scan_task
    topology.stop_periodic_scans()

    # Only a single one was actually running
    assert max_concurrency == 1

    topology.stop_periodic_scans()

    await asyncio.sleep(0)

    # All of the tasks have been stopped
    assert topology._scan_task.done()
    assert topology._scan_loop_task.done()


@mock.patch("zigpy.topology.Topology.scan", side_effect=RuntimeError())
async def test_periodic_scan_failure(mock_scan, topology):
    topology.start_periodic_scans(0.01)
    await asyncio.sleep(0.1)
    topology.stop_periodic_scans()


async def test_periodic_scan_priority(topology):
    async def _scan(_):
        await asyncio.sleep(0.5)

    with mock.patch.object(topology, "_scan", side_effect=_scan) as mock_scan:
        scan_task = asyncio.create_task(topology.scan())
        await asyncio.sleep(0.1)

        # Start a periodic scan. It won't have time to run yet, the old scan is running
        topology.start_periodic_scans(0.05)

        # Wait for the original scan to finish
        await scan_task

        # Start another scan, interrupting the periodic scan
        await asyncio.sleep(0.15)
        await topology.scan()

        # Now we can cancel the periodic scan
        topology.stop_periodic_scans()
        await asyncio.sleep(0)

    # Our two manual scans succeeded and the periodic one was attempted
    assert len(mock_scan.mock_calls) == 3
