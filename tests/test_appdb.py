import asyncio
from datetime import datetime, timezone
import pathlib
import sqlite3
import sys
import threading
import time

import aiosqlite
import freezegun
import pytest

from zigpy import profiles
import zigpy.appdb
import zigpy.application
import zigpy.config as conf
from zigpy.const import SIG_ENDPOINTS, SIG_MANUFACTURER, SIG_MODEL
from zigpy.device import Device, Status
import zigpy.endpoint
import zigpy.ota
from zigpy.quirks import CustomDevice
import zigpy.types as t
import zigpy.zcl
from zigpy.zcl.foundation import Status as ZCLStatus
from zigpy.zdo import types as zdo_t

from tests.async_mock import AsyncMock, MagicMock, patch
from tests.conftest import App
from tests.test_backups import (  # noqa: F401; pylint: disable=unused-variable
    backup_factory,
)


@pytest.fixture(autouse=True)
def auto_kill_aiosqlite():
    """aiosqlite's background thread does not let pytest exit when a failure occurs"""
    yield

    for thread in threading.enumerate():
        if not isinstance(thread, aiosqlite.core.Connection):
            continue

        try:
            conn = thread._conn
        except ValueError:
            pass
        else:
            try:
                conn.close()
            except zigpy.appdb.sqlite3.ProgrammingError:
                pass

        thread._running = False


async def make_app(database_file):
    if isinstance(database_file, pathlib.Path):
        database_file = str(database_file)

    p2 = patch("zigpy.topology.Topology.scan_loop", AsyncMock())
    with patch("zigpy.ota.OTA.initialize", AsyncMock()), p2:
        app = await App.new(
            conf.ZIGPY_SCHEMA(
                {
                    conf.CONF_DATABASE: database_file,
                    conf.CONF_DEVICE: {conf.CONF_DEVICE_PATH: "/dev/null"},
                }
            )
        )
    return app


def make_ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


class FakeCustomDevice(CustomDevice):
    replacement = {
        "endpoints": {
            # Endpoint exists on original device
            1: {
                "input_clusters": [0, 1, 3, 0x0008],
                "output_clusters": [6],
            },
            # Endpoint is created only at runtime by the quirk
            99: {
                "input_clusters": [0, 1, 3, 0x0008],
                "output_clusters": [6],
                "profile_id": 65535,
                "device_type": 123,
            },
        }
    }


def mock_dev_init(initialize: bool):
    """Device schedule_initialize mock factory."""

    def _initialize(self):
        if initialize:
            self.node_desc = zdo_t.NodeDescriptor(0, 1, 2, 3, 4, 5, 6, 7, 8)

    return _initialize


def fake_get_device(device):
    if device.endpoints.get(1) is not None and device[1].profile_id == 65535:
        return FakeCustomDevice(device.application, device.ieee, device.nwk, device)
    return device


async def test_no_database(tmp_path):
    with patch("zigpy.appdb.PersistingListener.new", AsyncMock()) as db_mock:
        db_mock.return_value.load.side_effect = AsyncMock()
        await make_app(None)
    assert db_mock.return_value.load.call_count == 0

    db = tmp_path / "test.db"
    with patch("zigpy.appdb.PersistingListener.new", AsyncMock()) as db_mock:
        db_mock.return_value.load.side_effect = AsyncMock()
        await make_app(db)
    assert db_mock.return_value.load.call_count == 1


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_database(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    relays_1 = [t.NWK(0x1234), t.NWK(0x2345)]
    relays_2 = [t.NWK(0x3456), t.NWK(0x4567)]
    app.handle_join(99, ieee, 0)
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep = dev.add_endpoint(2)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = 0xFFFD  # Invalid
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 49246
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    app.device_initialized(dev)
    clus._update_attribute(0, 99)
    clus._update_attribute(4, bytes("Custom", "ascii"))
    clus._update_attribute(5, bytes("Model", "ascii"))
    clus.listener_event("cluster_command", 0)
    clus.listener_event("general_command")
    dev.relays = relays_1
    signature = dev.get_signature()
    assert ep.endpoint_id in signature[SIG_ENDPOINTS]
    assert SIG_MANUFACTURER not in signature
    assert SIG_MODEL not in signature
    dev.manufacturer = "Custom"
    dev.model = "Model"
    assert dev.get_signature()[SIG_MANUFACTURER] == "Custom"
    assert dev.get_signature()[SIG_MODEL] == "Model"

    ts = time.time()
    dev.last_seen = ts
    dev_last_seen = dev.last_seen
    assert isinstance(dev.last_seen, float)
    assert abs(dev.last_seen - ts) < 0.01

    # Test a CustomDevice
    custom_ieee = make_ieee(1)
    app.handle_join(199, custom_ieee, 0)
    dev = app.get_device(custom_ieee)
    app.device_initialized(dev)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    ep.profile_id = 65535
    with patch("zigpy.quirks.get_device", fake_get_device):
        app.device_initialized(dev)
    assert isinstance(app.get_device(custom_ieee), FakeCustomDevice)
    assert isinstance(app.get_device(custom_ieee), CustomDevice)
    dev = app.get_device(custom_ieee)
    app.device_initialized(dev)
    dev.relays = relays_2
    dev.endpoints[1].level._update_attribute(0x0011, 17)
    dev.endpoints[99].level._update_attribute(0x0011, 17)
    assert dev.endpoints[1].in_clusters[0x0008]._attr_cache[0x0011] == 17
    assert dev.endpoints[99].in_clusters[0x0008]._attr_cache[0x0011] == 17
    custom_dev_last_seen = dev.last_seen
    assert isinstance(custom_dev_last_seen, float)

    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    with patch("zigpy.quirks.get_device", fake_get_device):
        app2 = await make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[2].device_type == 0xFFFD
    assert dev.endpoints[2].in_clusters[0]._attr_cache[0] == 99
    assert dev.endpoints[2].in_clusters[0]._attr_cache[4] == bytes("Custom", "ascii")
    assert dev.endpoints[2].in_clusters[0]._attr_cache[5] == bytes("Model", "ascii")
    assert dev.endpoints[2].manufacturer == "Custom"
    assert dev.endpoints[2].model == "Model"
    assert dev.endpoints[2].out_clusters[1].cluster_id == 1
    assert dev.endpoints[3].device_type == profiles.zll.DeviceType.COLOR_LIGHT
    assert dev.relays == relays_1
    # The timestamp won't be restored exactly but it is more than close enough
    assert abs(dev.last_seen - dev_last_seen) < 0.01

    dev = app2.get_device(custom_ieee)
    # This virtual attribute is added by the quirk, there is no corresponding cluster
    # stored in the database, nor is there a corresponding endpoint 99
    assert dev.endpoints[1].in_clusters[0x0008]._attr_cache[0x0011] == 17
    assert dev.endpoints[99].in_clusters[0x0008]._attr_cache[0x0011] == 17
    assert dev.relays == relays_2
    assert abs(dev.last_seen - custom_dev_last_seen) < 0.01
    dev.relays = None

    app.handle_leave(99, ieee)
    await app2.shutdown()

    app3 = await make_app(db)
    assert ieee in app3.devices

    async def mockleave(*args, **kwargs):
        return [0]

    app3.devices[ieee].zdo.leave = mockleave
    await app3.remove(ieee)
    for i in range(1, 20):
        await asyncio.sleep(0)
    assert ieee not in app3.devices
    await app3.shutdown()

    app4 = await make_app(db)
    assert ieee not in app4.devices
    dev = app4.get_device(custom_ieee)
    assert dev.relays is None
    await app4.shutdown()


@patch("zigpy.device.Device.schedule_group_membership_scan", MagicMock())
async def _test_null_padded(tmp_path, test_manufacturer=None, test_model=None):
    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    with patch(
        "zigpy.device.Device.schedule_initialize",
        new=mock_dev_init(True),
    ):
        app.handle_join(99, ieee, 0)
        app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)
    clus._update_attribute(4, test_manufacturer)
    clus._update_attribute(5, test_model)
    clus.listener_event("cluster_command", 0)
    clus.listener_event("zdo_command")
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[3].in_clusters[0]._attr_cache[4] == test_manufacturer
    assert dev.endpoints[3].in_clusters[0]._attr_cache[5] == test_model
    await app2.shutdown()

    return dev


async def test_appdb_load_null_padded_manuf(tmp_path):
    manufacturer = b"Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07"
    model = b"Mock Model"
    dev = await _test_null_padded(tmp_path, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


async def test_appdb_load_null_padded_model(tmp_path):
    manufacturer = b"Mock Manufacturer"
    model = b"Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    dev = await _test_null_padded(tmp_path, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


async def test_appdb_load_null_padded_manuf_model(tmp_path):
    manufacturer = b"Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07"
    model = b"Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    dev = await _test_null_padded(tmp_path, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


async def test_appdb_str_model(tmp_path):
    manufacturer = "Mock Manufacturer"
    model = "Mock Model"
    dev = await _test_null_padded(tmp_path, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
@patch("zigpy.zcl.Cluster.request", new_callable=AsyncMock)
async def test_groups(mock_request, tmp_path):
    """Test group adding/removing."""

    group_id, group_name = 0x1221, "app db Test Group 0x1221"
    mock_request.return_value = [ZCLStatus.SUCCESS, group_id]

    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(4)
    app.device_initialized(dev)

    ieee_b = make_ieee(2)
    app.handle_join(100, ieee_b, 0)
    dev_b = app.get_device(ieee_b)
    ep_b = dev_b.add_endpoint(2)
    ep_b.status = zigpy.endpoint.Status.ZDO_INIT
    ep_b.profile_id = 260
    ep_b.device_type = profiles.zha.DeviceType.PUMP
    ep_b.add_input_cluster(4)
    app.device_initialized(dev_b)

    await ep.add_to_group(group_id, group_name)
    await ep_b.add_to_group(group_id, group_name)
    assert group_id in app.groups
    group = app.groups[group_id]
    assert group.name == group_name
    assert (dev.ieee, ep.endpoint_id) in group
    assert (dev_b.ieee, ep_b.endpoint_id) in group
    assert group_id in ep.member_of
    assert group_id in ep_b.member_of
    await app.shutdown()
    del app, dev, dev_b, ep, ep_b

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev2 = app2.get_device(ieee)
    assert group_id in app2.groups
    group = app2.groups[group_id]
    assert group.name == group_name
    assert (dev2.ieee, 1) in group
    assert group_id in dev2.endpoints[1].member_of

    dev2_b = app2.get_device(ieee_b)
    assert (dev2_b.ieee, 2) in group
    assert group_id in dev2_b.endpoints[2].member_of

    # check member removal
    await dev2_b.remove_from_group(group_id)
    await app2.shutdown()
    del app2, dev2, dev2_b

    app3 = await make_app(db)
    dev3 = app3.get_device(ieee)
    assert group_id in app3.groups
    group = app3.groups[group_id]
    assert group.name == group_name
    assert (dev3.ieee, 1) in group
    assert group_id in dev3.endpoints[1].member_of

    dev3_b = app3.get_device(ieee_b)
    assert (dev3_b.ieee, 2) not in group
    assert group_id not in dev3_b.endpoints[2].member_of

    # check group removal
    await dev3.remove_from_group(group_id)
    await app3.shutdown()
    del app3, dev3, dev3_b

    app4 = await make_app(db)
    dev4 = app4.get_device(ieee)
    assert group_id in app4.groups
    assert not app4.groups[group_id]
    assert group_id not in dev4.endpoints[1].member_of
    app4.groups.pop(group_id)
    await app4.shutdown()
    del app4, dev4

    app5 = await make_app(db)
    assert not app5.groups
    await app5.shutdown()


@pytest.mark.parametrize("dev_init", (True, False))
async def test_attribute_update(tmp_path, dev_init):
    """Test attribute update for initialized and uninitialized devices."""

    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    with patch(
        "zigpy.device.Device.schedule_initialize",
        new=mock_dev_init(initialize=dev_init),
    ):
        app.handle_join(99, ieee, 0)

    test_manufacturer = "Test Manufacturer"
    test_model = "Test Model"

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus._update_attribute(4, test_manufacturer)
    clus._update_attribute(5, test_model)
    app.device_initialized(dev)
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev = app2.get_device(ieee)
    assert dev.is_initialized == dev_init
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[3].in_clusters[0]._attr_cache[4] == test_manufacturer
    assert dev.endpoints[3].in_clusters[0]._attr_cache[5] == test_model

    await app2.shutdown()


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_neighbors(tmp_path):
    """Test neighbor loading."""

    ext_pid = t.EUI64.convert("aa:bb:cc:dd:ee:ff:01:02")
    ieee_1 = make_ieee(1)
    nwk_1 = 0x1111
    nei_1 = zdo_t.Neighbor(ext_pid, ieee_1, nwk_1, 2, 1, 1, 0, 0, 0, 15, 250)

    ieee_2 = make_ieee(2)
    nwk_2 = 0x2222
    nei_2 = zdo_t.Neighbor(ext_pid, ieee_2, nwk_2, 1, 1, 2, 0, 0, 0, 15, 250)

    ieee_3 = make_ieee(3)
    nwk_3 = 0x3333
    nei_3 = zdo_t.Neighbor(ext_pid, ieee_3, nwk_3, 1, 1, 2, 0, 0, 0, 15, 250)

    db = tmp_path / "test.db"
    app = await make_app(db)
    app.handle_join(nwk_1, ieee_1, 0)

    dev_1 = app.get_device(ieee_1)
    dev_1.node_desc = zdo_t.NodeDescriptor(2, 64, 128, 4174, 82, 82, 0, 82, 0)
    ep1 = dev_1.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = 260
    ep1.device_type = 0x1234
    app.device_initialized(dev_1)

    # 2nd device
    app.handle_join(nwk_2, ieee_2, 0)
    dev_2 = app.get_device(ieee_2)
    dev_2.node_desc = zdo_t.NodeDescriptor(1, 64, 142, 4476, 82, 82, 0, 82, 0)
    ep2 = dev_2.add_endpoint(1)
    ep2.status = zigpy.endpoint.Status.ZDO_INIT
    ep2.profile_id = 260
    ep2.device_type = 0x1234
    app.device_initialized(dev_2)

    neighbors = zdo_t.Neighbors(2, 0, [nei_2, nei_3])
    p1 = patch.object(
        dev_1.zdo,
        "request",
        new=AsyncMock(return_value=(zdo_t.Status.SUCCESS, neighbors)),
    )
    with p1:
        res = await dev_1.neighbors.scan()
        assert res

    neighbors = zdo_t.Neighbors(2, 0, [nei_1, nei_3])
    p1 = patch.object(
        dev_2.zdo,
        "request",
        new=AsyncMock(return_value=(zdo_t.Status.SUCCESS, neighbors)),
    )
    with p1:
        res = await dev_2.neighbors.scan()
        assert res

    await app.shutdown()
    del dev_1, dev_2

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev_1 = app2.get_device(ieee_1)
    dev_2 = app2.get_device(ieee_2)

    assert len(dev_1.neighbors) == 2
    assert dev_1.neighbors[0].device is dev_2
    assert dev_1.neighbors[1].device is None
    assert dev_1.neighbors[1].neighbor.ieee == ieee_3

    assert len(dev_2.neighbors.neighbors) == 2
    assert dev_2.neighbors[0].device is dev_1
    assert dev_2.neighbors[1].device is None
    assert dev_2.neighbors[1].neighbor.ieee == ieee_3
    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_rejoin(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    nwk = 199
    app.handle_join(nwk, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 65535
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)
    clus._update_attribute(4, "Custom")
    clus._update_attribute(5, "Model")
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    with patch("zigpy.quirks.get_device", fake_get_device):
        app2 = await make_app(db)
    dev = app2.get_device(ieee)
    assert dev.nwk == nwk
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[1].in_clusters[0]._attr_cache[4] == "Custom"
    assert dev.endpoints[1].in_clusters[0]._attr_cache[5] == "Model"
    assert dev.endpoints[1].manufacturer == "Custom"
    assert dev.endpoints[1].model == "Model"

    # device rejoins
    dev.nwk = nwk + 1
    with patch("zigpy.quirks.get_device", fake_get_device):
        app2.device_initialized(dev)
    await app2.shutdown()

    app3 = await make_app(db)
    dev = app3.get_device(ieee)
    assert dev.nwk == nwk + 1
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert 0 in dev.endpoints[1].in_clusters
    assert dev.endpoints[1].manufacturer == "Custom"
    assert dev.endpoints[1].model == "Model"
    await app3.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_stopped_appdb_listener(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)

    with patch("zigpy.appdb.PersistingListener._save_attribute") as mock_attr_save:
        clus._update_attribute(0, 99)
        clus._update_attribute(4, bytes("Custom", "ascii"))
        clus._update_attribute(5, bytes("Model", "ascii"))
        await app.shutdown()
        assert mock_attr_save.call_count == 3

        clus._update_attribute(0, 100)
        for i in range(100):
            await asyncio.sleep(0)
        assert mock_attr_save.call_count == 3


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_invalid_node_desc(tmp_path):
    """devices without a valid node descriptor should not save the node descriptor."""

    ieee_1 = make_ieee(1)
    nwk_1 = 0x1111

    db = tmp_path / "test.db"
    app = await make_app(db)
    app.handle_join(nwk_1, ieee_1, 0)

    dev_1 = app.get_device(ieee_1)
    dev_1.node_desc = None
    ep = dev_1.add_endpoint(1)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    app.device_initialized(dev_1)

    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev_2 = app2.get_device(ieee=ieee_1)
    assert dev_2.node_desc is None
    assert dev_2.nwk == dev_1.nwk
    assert dev_2.ieee == dev_1.ieee
    assert dev_2.status == dev_1.status

    await app2.shutdown()


async def test_appdb_worker_exception(tmp_path):
    """Exceptions should not kill the appdb worker."""

    app_mock = MagicMock(name="ControllerApplication")

    db = tmp_path / "test.db"

    ieee_1 = make_ieee(1)
    dev_1 = zigpy.device.Device(app_mock, ieee_1, 0x1111)
    dev_1.status = Status.ENDPOINTS_INIT
    dev_1.node_desc = MagicMock()
    dev_1.node_desc.is_valid = True
    dev_1.node_desc.serialize.side_effect = AttributeError

    with patch(
        "zigpy.appdb.PersistingListener._save_device",
        wraps=zigpy.appdb.PersistingListener._save_device,
    ) as save_mock:
        db_listener = await zigpy.appdb.PersistingListener.new(db, app_mock)

        for _ in range(3):
            db_listener.raw_device_initialized(dev_1)
        await db_listener.shutdown()

    assert save_mock.await_count == 3


@pytest.mark.parametrize("dev_init", (True, False))
async def test_unsupported_attribute(tmp_path, dev_init):
    """Test adding unsupported attributes for initialized and uninitialized devices."""

    db = tmp_path / "test.db"
    app = await make_app(db)
    ieee = make_ieee()
    with patch(
        "zigpy.device.Device.schedule_initialize",
        new=mock_dev_init(initialize=dev_init),
    ):
        app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus._update_attribute(4, "Custom")
    clus._update_attribute(5, "Model")
    app.device_initialized(dev)
    clus.add_unsupported_attribute(0x0010)
    clus.add_unsupported_attribute("physical_env")
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev = app2.get_device(ieee)
    assert dev.is_initialized == dev_init
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert 0x0010 in dev.endpoints[3].in_clusters[0].unsupported_attributes
    assert "location_desc" in dev.endpoints[3].in_clusters[0].unsupported_attributes
    assert 0x0011 in dev.endpoints[3].in_clusters[0].unsupported_attributes
    assert "physical_env" in dev.endpoints[3].in_clusters[0].unsupported_attributes

    await app2.shutdown()


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_load_unsupp_attr_wrong_cluster(tmp_path):
    """Test loading unsupported attribute from the wrong cluster."""

    db = tmp_path / "test.db"
    app = await make_app(db)

    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus._update_attribute(4, "Custom")
    clus._update_attribute(5, "Model")
    app.device_initialized(dev)
    await app.shutdown()
    del clus
    del ep
    del dev

    # add unsupported attr for missing endpoint
    app = await make_app(db)
    dev = app.get_device(ieee)
    ep = dev.endpoints[3]
    clus = ep.add_input_cluster(2)
    clus.add_unsupported_attribute(0)
    await app.shutdown()
    del clus
    del ep
    del dev

    # reload
    app = await make_app(db)
    await app.shutdown()


async def test_last_seen(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app(db)

    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee=ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus._update_attribute(4, "Custom")
    clus._update_attribute(5, "Model")
    app.device_initialized(dev)

    old_last_seen = dev.last_seen
    await app.shutdown()

    # The `last_seen` of a joined device persists
    app = await make_app(db)
    dev = app.get_device(ieee=ieee)
    await app.shutdown()

    next_last_seen = dev.last_seen
    assert abs(next_last_seen - old_last_seen) < 0.01

    app = await make_app(db)
    dev = app.get_device(ieee=ieee)

    # Last-seen is only written to the db every 30s (no write case)
    now = datetime.fromtimestamp(dev.last_seen + 5, timezone.utc)
    with freezegun.freeze_time(now):
        dev.update_last_seen()

    await app.shutdown()

    app = await make_app(db)
    dev = app.get_device(ieee=ieee)
    assert dev.last_seen == next_last_seen  # no change
    await app.shutdown()

    app = await make_app(db)
    dev = app.get_device(ieee=ieee)

    # Last-seen is only written to the db every 30s (write case)
    now = datetime.fromtimestamp(dev.last_seen + 35, timezone.utc)
    with freezegun.freeze_time(now):
        dev.update_last_seen()

    await app.shutdown()

    # And it will be updated when the database next loads
    app = await make_app(db)
    dev = app.get_device(ieee=ieee)
    assert dev.last_seen >= next_last_seen + 35  # updated
    await app.shutdown()


@pytest.mark.parametrize(
    "stdlib_version,use_sqlite",
    [
        ((1, 0, 0), False),
        ((2, 0, 0), False),
        ((3, 0, 0), False),
        ((3, 24, 0), True),
        ((4, 0, 0), True),
    ],
)
def test_pysqlite_load_success(stdlib_version, use_sqlite):
    """Test that the internal import SQLite helper picks the correct module."""
    pysqlite3 = MagicMock()
    pysqlite3.sqlite_version_info = (3, 30, 0)

    with patch.dict(sys.modules, {"pysqlite3": pysqlite3}), patch.object(
        sys.modules["sqlite3"], "sqlite_version_info", new=stdlib_version
    ):
        module = zigpy.appdb._import_compatible_sqlite3(zigpy.appdb.MIN_SQLITE_VERSION)

    if use_sqlite:
        assert module is sqlite3
    else:
        assert module is pysqlite3


@pytest.mark.parametrize(
    "stdlib_version,pysqlite3_version",
    [
        ((1, 0, 0), None),
        ((1, 0, 0), (1, 0, 1)),
    ],
)
def test_pysqlite_load_failure(stdlib_version, pysqlite3_version):
    """
    Test that the internal import SQLite helper will throw an error when no compatible
    module can be found.
    """

    if pysqlite3_version is not None:
        pysqlite3 = MagicMock()
        pysqlite3.sqlite_version_info = pysqlite3_version
        pysqlite3_patch = patch.dict(sys.modules, {"pysqlite3": pysqlite3})
    else:
        pysqlite3_patch = patch.dict(sys.modules, {"pysqlite3": None})

    with pysqlite3_patch, patch.object(
        sys.modules["sqlite3"], "sqlite_version_info", new=stdlib_version
    ):
        with pytest.raises(RuntimeError):
            zigpy.appdb._import_compatible_sqlite3(zigpy.appdb.MIN_SQLITE_VERSION)


async def test_appdb_network_backups(tmp_path, backup_factory):  # noqa: F811
    db = tmp_path / "test.db"

    backup = backup_factory()

    app1 = await make_app(db)
    app1.backups.add_backup(backup)
    await app1.shutdown()

    # The backup is reloaded from the database as well
    app2 = await make_app(db)
    assert len(app2.backups.backups) == 1
    assert app2.backups.backups[0] == backup

    new_backup = backup_factory()
    new_backup.network_info.network_key.tx_counter += 10000

    app2.backups.add_backup(new_backup)
    await app2.shutdown()

    # The database will contain only the single backup
    app3 = await make_app(db)
    assert len(app3.backups.backups) == 1
    assert app3.backups.backups[0] == new_backup
    assert app3.backups.backups[0] != backup
    await app3.shutdown()
