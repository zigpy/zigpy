"""Test Topology class."""

import asyncio
import logging
import time

from asynctest import CoroutineMock, mock
import pytest
import zigpy.config
import zigpy.neighbor
import zigpy.topology


@pytest.fixture
def device_1():
    dev = mock.MagicMock()
    dev.ieee = mock.sentinel.ieee_1
    dev.nwk = 0x1111
    dev.neighbors.scan = CoroutineMock()
    return dev


@pytest.fixture
def device_2():
    dev = mock.MagicMock()
    dev.ieee = mock.sentinel.ieee_2
    dev.nwk = 0x2222
    dev.neighbors.scan = CoroutineMock()
    return dev


@pytest.fixture
def device_3():
    dev = mock.MagicMock()
    dev.ieee = mock.sentinel.ieee_3
    dev.nwk = 0x3333
    dev.neighbors.scan = CoroutineMock()
    dev.neighbors.supported = False
    return dev


@pytest.fixture
def topology_f(device_1, device_2, device_3):
    app = mock.MagicMock()
    app.devices = {
        device_1.ieee: device_1,
        device_2.ieee: device_2,
        device_3.ieee: device_3,
    }
    app.config = {zigpy.config.CONF_TOPO_SCAN_PERIOD: 0}

    with mock.patch("zigpy.topology.DELAY_INTER_DEVICE", 0):
        yield zigpy.topology.Topology(app)


async def test_schedule_scan(device_1, device_2, topology_f):
    """Test scheduling a scan."""

    with mock.patch.object(topology_f, "scan_loop", new=CoroutineMock()) as scan_loop:
        topology_f.async_schedule_scan()
        for i in range(5):
            await asyncio.sleep(0)
    assert scan_loop.await_count == 1


async def test_scan(device_1, device_2, topology_f, caplog):
    """Test scanning."""

    assert topology_f.timestamp < time.time()
    ts = topology_f.timestamp
    with caplog.at_level(logging.DEBUG):
        await topology_f.scan()
    assert device_1.neighbors.scan.await_count == 1
    assert device_2.neighbors.scan.await_count == 1
    assert topology_f.timestamp != ts
    assert "Scanning" in caplog.text


async def test_scan_preempts(device_1, device_2, topology_f, caplog):
    """Test scanning."""

    with caplog.at_level(logging.DEBUG):
        await asyncio.gather(topology_f.scan(), topology_f.scan())
    assert "Cancelling old" in caplog.text
    assert "Cancelled topology" in caplog.text
    assert topology_f.current
