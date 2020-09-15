"""Test Topology class."""

import asyncio
import logging
import time

import pytest

import zigpy.config
import zigpy.neighbor
import zigpy.topology

from .async_mock import AsyncMock, MagicMock, patch, sentinel


@pytest.fixture
def device_1():
    dev = MagicMock()
    dev.ieee = sentinel.ieee_1
    dev.node_desc.is_end_device = False
    dev.nwk = 0x1111
    dev.neighbors.scan = AsyncMock()
    return dev


@pytest.fixture
def device_2():
    dev = MagicMock()
    dev.ieee = sentinel.ieee_2
    dev.node_desc.is_end_device = False
    dev.nwk = 0x2222
    dev.neighbors.scan = AsyncMock()
    return dev


@pytest.fixture
def device_3():
    dev = MagicMock()
    dev.ieee = sentinel.ieee_3
    dev.node_desc.is_end_device = False
    dev.nwk = 0x3333
    dev.neighbors.scan = AsyncMock()
    dev.neighbors.supported = False
    return dev


@pytest.fixture
def topology_f(device_1, device_2, device_3):
    app = MagicMock()
    app.devices = {
        device_1.ieee: device_1,
        device_2.ieee: device_2,
        device_3.ieee: device_3,
    }
    app.config = {zigpy.config.CONF_TOPO_SCAN_PERIOD: 0}

    with patch("zigpy.topology.DELAY_INTER_DEVICE", 0):
        yield zigpy.topology.Topology(app)


async def test_new():
    """Test creating new instance."""

    app = MagicMock()
    app.config = {zigpy.config.CONF_TOPO_SCAN_PERIOD: 0}
    with patch("zigpy.topology.Topology.scan", new=AsyncMock()) as scan:
        zigpy.topology.Topology.new(app)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    assert scan.await_count >= 1


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
    assert device_1.neighbors.scan.await_count == 1
    assert device_2.neighbors.scan.await_count == 1
