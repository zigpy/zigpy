import os

import pytest

from zigpy import profiles
import zigpy.application
from zigpy.config import CONF_DATABASE, ZIGPY_SCHEMA
from zigpy.device import Device, Status
import zigpy.ota
from zigpy.quirks import CustomDevice
import zigpy.types as t
import zigpy.zcl
from zigpy.zcl.foundation import Status as ZCLStatus
from zigpy.zdo import types as zdo_t

from tests.async_mock import AsyncMock, MagicMock, patch


async def make_app(database_file):
    class App(zigpy.application.ControllerApplication):
        async def shutdown(self):
            pass

        async def startup(self, auto_form=False):
            pass

        async def request(
            self,
            device,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=True,
            use_ieee=False,
        ):
            pass

        async def permit_ncp(self, time_s=60):
            pass

        async def probe(self, config):
            return True

    with patch("zigpy.ota.OTA.initialize", AsyncMock()):
        app = await App.new(ZIGPY_SCHEMA({CONF_DATABASE: database_file}))
    return app


def make_ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


class FakeCustomDevice(CustomDevice):
    replacement = {
        "endpoints": {1: {"input_clusters": [0, 1, 3], "output_clusters": [6]}}
    }


def mock_dev_init(status: Status):
    """Device schedule_initialize mock factory."""

    def _initialize(self):
        self.status = status
        self.initializing = False
        self.node_desc = zdo_t.NodeDescriptor(0, 1, 2, 3, 4, 5, 6, 7, 8)

    return _initialize


def fake_get_device(device):
    if device.endpoints.get(1) is not None and device[1].profile_id == 65535:
        return FakeCustomDevice(device.application, device.ieee, device.nwk, device)
    return device


async def test_no_database(tmpdir):
    with patch("zigpy.appdb.PersistingListener") as db_mock:
        db_mock.return_value.load.side_effect = AsyncMock()
        await make_app(None)
    assert db_mock.return_value.load.call_count == 0

    db = os.path.join(str(tmpdir), "test.db")
    with patch("zigpy.appdb.PersistingListener") as db_mock:
        db_mock.return_value.load.side_effect = AsyncMock()
        await make_app(db)
    assert db_mock.return_value.load.call_count == 1


async def test_database(tmpdir, monkeypatch):
    monkeypatch.setattr(
        Device, "schedule_initialize", mock_dev_init(Status.ENDPOINTS_INIT)
    )
    db = os.path.join(str(tmpdir), "test.db")
    app = await make_app(db)
    ieee = make_ieee()
    relays_1 = [t.NWK(0x1234), t.NWK(0x2345)]
    relays_2 = [t.NWK(0x3456), t.NWK(0x4567)]
    app.handle_join(99, ieee, 0)
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep = dev.add_endpoint(2)
    ep.profile_id = 260
    ep.device_type = 0xFFFD  # Invalid
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    ep = dev.add_endpoint(3)
    ep.profile_id = 49246
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    app.device_initialized(dev)
    clus._update_attribute(0, 99)
    clus._update_attribute(4, bytes("Custom", "ascii"))
    clus._update_attribute(5, bytes("Model", "ascii"))
    clus.listener_event("cluster_command", 0)
    clus.listener_event("general_command")
    dev.relays = relays_1

    # Test a CustomDevice
    custom_ieee = make_ieee(1)
    app.handle_join(199, custom_ieee, 0)
    dev = app.get_device(custom_ieee)
    app.device_initialized(dev)
    ep = dev.add_endpoint(1)
    ep.profile_id = 65535
    with patch("zigpy.quirks.get_device", fake_get_device):
        app.device_initialized(dev)
    assert isinstance(app.get_device(custom_ieee), FakeCustomDevice)
    assert isinstance(app.get_device(custom_ieee), CustomDevice)
    assert ep.endpoint_id in dev.get_signature()
    app.device_initialized(app.get_device(custom_ieee))
    dev.relays = relays_2

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

    dev = app2.get_device(custom_ieee)
    assert dev.relays == relays_2
    dev.relays = None

    app.handle_leave(99, ieee)

    app2 = await make_app(db)
    assert ieee in app2.devices

    async def mockleave(*args, **kwargs):
        return [0]

    app2.devices[ieee].zdo.leave = mockleave
    await app2.remove(ieee)
    assert ieee not in app2.devices

    app3 = await make_app(db)
    assert ieee not in app3.devices
    dev = app2.get_device(custom_ieee)
    assert dev.relays is None

    os.unlink(db)


@patch("zigpy.device.Device.schedule_group_membership_scan", MagicMock())
async def _test_null_padded(tmpdir, test_manufacturer=None, test_model=None):
    db = os.path.join(str(tmpdir), "test.db")
    app = await make_app(db)
    ieee = make_ieee()
    with patch(
        "zigpy.device.Device.schedule_initialize",
        new=mock_dev_init(Status.ENDPOINTS_INIT),
    ):
        app.handle_join(99, ieee, 0)
        app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)
    clus._update_attribute(4, test_manufacturer)
    clus._update_attribute(5, test_model)
    clus.listener_event("cluster_command", 0)
    clus.listener_event("zdo_command")

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[3].in_clusters[0]._attr_cache[4] == test_manufacturer
    assert dev.endpoints[3].in_clusters[0]._attr_cache[5] == test_model

    os.unlink(db)

    return dev


async def test_appdb_load_null_padded_manuf(tmpdir):
    manufacturer = b"Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07"
    model = b"Mock Model"
    dev = await _test_null_padded(tmpdir, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


async def test_appdb_load_null_padded_model(tmpdir):
    manufacturer = b"Mock Manufacturer"
    model = b"Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    dev = await _test_null_padded(tmpdir, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


async def test_appdb_load_null_padded_manuf_model(tmpdir):
    manufacturer = b"Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07"
    model = b"Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    dev = await _test_null_padded(tmpdir, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


async def test_appdb_str_model(tmpdir):
    manufacturer = "Mock Manufacturer"
    model = "Mock Model"
    dev = await _test_null_padded(tmpdir, manufacturer, model)

    assert dev.manufacturer == "Mock Manufacturer"
    assert dev.model == "Mock Model"
    assert dev.endpoints[3].manufacturer == "Mock Manufacturer"
    assert dev.endpoints[3].model == "Mock Model"


@pytest.mark.parametrize(
    "status, success",
    ((Status.ENDPOINTS_INIT, True), (Status.ZDO_INIT, False), (Status.NEW, False)),
)
async def test_node_descriptor_updated(tmpdir, status, success):
    db = os.path.join(str(tmpdir), "test_nd.db")
    app = await make_app(db)
    nd_ieee = make_ieee(2)
    with patch.object(Device, "schedule_initialize", new=mock_dev_init(status)):
        app.handle_join(299, nd_ieee, 0)

    dev = app.get_device(nd_ieee)
    ep = dev.add_endpoint(1)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)

    node_desc = zdo_t.NodeDescriptor.deserialize(b"abcdefghijklm")[0]

    async def mock_get_node_descriptor():
        dev.node_desc = node_desc
        return node_desc

    dev.get_node_descriptor = MagicMock()
    dev.get_node_descriptor.side_effect = mock_get_node_descriptor
    await dev.refresh_node_descriptor()

    assert dev.get_node_descriptor.call_count == 1

    app2 = await make_app(db)
    if success:
        dev = app2.get_device(nd_ieee)
        assert dev.status == status
        assert dev.node_desc.is_valid
        assert dev.node_desc.serialize() == b"abcdefghijklm"
    else:
        assert nd_ieee not in app2.devices

    os.unlink(db)


async def test_groups(tmpdir, monkeypatch):
    monkeypatch.setattr(
        Device, "schedule_initialize", mock_dev_init(Status.ENDPOINTS_INIT)
    )

    group_id, group_name = 0x1221, "app db Test Group 0x1221"

    async def mock_request(*args, **kwargs):
        return [ZCLStatus.SUCCESS, group_id]

    monkeypatch.setattr(zigpy.zcl.Cluster, "request", mock_request)

    db = os.path.join(str(tmpdir), "test.db")
    app = await make_app(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(4)
    app.device_initialized(dev)

    ieee_b = make_ieee(2)
    app.handle_join(100, ieee_b, 0)
    dev_b = app.get_device(ieee_b)
    ep_b = dev_b.add_endpoint(2)
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
    assert group_id in ep.member_of

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
    await dev_b.remove_from_group(group_id)
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
    app4 = await make_app(db)
    dev4 = app4.get_device(ieee)
    assert group_id in app4.groups
    assert not app4.groups[group_id]
    assert group_id not in dev4.endpoints[1].member_of
    app4.groups.pop(group_id)

    app5 = await make_app(db)
    assert not app5.groups


@pytest.mark.parametrize(
    "status, success",
    ((Status.ENDPOINTS_INIT, True), (Status.ZDO_INIT, False), (Status.NEW, False)),
)
async def test_attribute_update(tmpdir, status, success):
    """Test attribute update for initialized and uninitialized devices."""

    db = os.path.join(str(tmpdir), "test.db")
    app = await make_app(db)
    ieee = make_ieee()
    with patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(status)):
        app.handle_join(99, ieee, 0)

    test_manufacturer = "Test Manufacturer"
    test_model = "Test Model"

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus._update_attribute(4, test_manufacturer)
    clus._update_attribute(5, test_model)
    app.device_initialized(dev)

    # Everything should've been saved - check that it re-loads
    app2 = await make_app(db)
    if success:
        dev = app2.get_device(ieee)
        assert dev.status == status
        assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
        assert dev.endpoints[3].in_clusters[0]._attr_cache[4] == test_manufacturer
        assert dev.endpoints[3].in_clusters[0]._attr_cache[5] == test_model
    else:
        assert ieee not in app2.devices

    os.unlink(db)


@patch.object(Device, "schedule_initialize", new=mock_dev_init(Status.ENDPOINTS_INIT))
async def test_neighbors(tmpdir):
    """Test neighbor loading."""

    ext_pid = t.EUI64.convert("aa:bb:cc:dd:ee:ff:01:02")
    ieee_1 = make_ieee(1)
    nwk_1 = 0x1111
    nei_1 = zdo_t.Neighbor(ext_pid, ieee_1, nwk_1, 0x16, 0, 15, 250)

    ieee_2 = make_ieee(2)
    nwk_2 = 0x2222
    nei_2 = zdo_t.Neighbor(ext_pid, ieee_2, nwk_2, 0x25, 0, 15, 250)

    ieee_3 = make_ieee(3)
    nwk_3 = 0x3333
    nei_3 = zdo_t.Neighbor(ext_pid, ieee_3, nwk_3, 0x25, 0, 15, 250)

    db = os.path.join(str(tmpdir), "test.db")
    app = await make_app(db)
    app.handle_join(nwk_1, ieee_1, 0)

    dev_1 = app.get_device(ieee_1)
    dev_1.node_desc = zdo_t.NodeDescriptor(2, 64, 128, 4174, 82, 82, 0, 82, 0)
    app.device_initialized(dev_1)

    # 2nd device
    app.handle_join(nwk_2, ieee_2, 0)
    dev_2 = app.get_device(ieee_2)
    dev_2.node_desc = zdo_t.NodeDescriptor(1, 64, 142, 4476, 82, 82, 0, 82, 0)
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


@patch(
    "zigpy.device.Device.schedule_initialize", new=mock_dev_init(Status.ENDPOINTS_INIT)
)
async def test_device_rejoin(tmpdir):
    db = os.path.join(str(tmpdir), "test.db")
    app = await make_app(db)
    ieee = make_ieee()
    nwk = 199
    app.handle_join(nwk, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.profile_id = 65535
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)
    clus._update_attribute(4, "Custom")
    clus._update_attribute(5, "Model")

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

    app3 = await make_app(db)
    dev = app3.get_device(ieee)
    assert dev.nwk == nwk + 1
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert 0 in dev.endpoints[1].in_clusters
    assert dev.endpoints[1].manufacturer == "Custom"
    assert dev.endpoints[1].model == "Model"
