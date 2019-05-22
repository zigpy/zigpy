import os
from unittest import mock

import pytest

import zigpy.types as t
from zigpy.application import ControllerApplication
from zigpy import profiles
from zigpy.quirks import CustomDevice
from zigpy.device import Device, Status
import zigpy.ota
import zigpy.zcl
from zigpy.zcl.foundation import Status as ZCLStatus
from zigpy.zdo import types as zdo_t


def make_app(database_file):
    with mock.patch('zigpy.ota.OTA', mock.MagicMock(spec_set=zigpy.ota.OTA)):
        app = ControllerApplication(database_file)
    return app


def make_ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


class FakeCustomDevice(CustomDevice):
    def __init__(self, application, ieee, nwk, replaces):
        super().__init__(application, ieee, nwk, replaces)


async def _initialize(self):
    self.status = Status.ENDPOINTS_INIT
    self.initializing = False
    self._application.device_initialized(self)


def fake_get_device(device):
    if device.endpoints.get(1) is not None and device[1].profile_id == 65535:
        return FakeCustomDevice(device.application, make_ieee(1), 199,
                                Device(device.application, make_ieee(1), 199))
    return device


@pytest.mark.asyncio
async def test_database(tmpdir, monkeypatch):
    monkeypatch.setattr(Device, '_initialize', _initialize)
    db = os.path.join(str(tmpdir), 'test.db')
    app = make_app(db)
    # TODO: Leaks a task on dev.initialize, I think?
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    dev.node_desc, _ = zdo_t.NodeDescriptor.deserialize(b'1234567890123')
    ep = dev.add_endpoint(1)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep = dev.add_endpoint(2)
    ep.profile_id = 260
    ep.device_type = 0xfffd  # Invalid
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    ep = dev.add_endpoint(3)
    ep.profile_id = 49246
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    app.device_initialized(dev)
    clus._update_attribute(0, 99)
    clus._update_attribute(4, bytes('Custom', 'ascii'))
    clus._update_attribute(5, bytes('Model', 'ascii'))
    clus.listener_event('cluster_command', 0)
    clus.listener_event('zdo_command')

    # Test a CustomDevice
    custom_ieee = make_ieee(1)
    app.handle_join(199, custom_ieee, 0)
    dev = app.get_device(custom_ieee)
    app.device_initialized(dev)
    ep = dev.add_endpoint(1)
    ep.profile_id = 65535
    with mock.patch('zigpy.quirks.get_device', fake_get_device):
        app.device_initialized(dev)
    assert isinstance(app.get_device(custom_ieee), FakeCustomDevice)
    assert isinstance(app.get_device(custom_ieee), CustomDevice)
    assert ep.endpoint_id in dev.get_signature()
    app.device_initialized(app.get_device(custom_ieee))

    # Everything should've been saved - check that it re-loads
    with mock.patch('zigpy.quirks.get_device', fake_get_device):
        app2 = make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[2].device_type == 0xfffd
    assert dev.endpoints[2].in_clusters[0]._attr_cache[0] == 99
    assert dev.endpoints[2].in_clusters[0]._attr_cache[4] == bytes('Custom', 'ascii')
    assert dev.endpoints[2].in_clusters[0]._attr_cache[5] == bytes('Model', 'ascii')
    assert dev.endpoints[2].manufacturer == 'Custom'
    assert dev.endpoints[2].model == 'Model'
    assert dev.endpoints[2].out_clusters[1].cluster_id == 1
    assert dev.endpoints[3].device_type == profiles.zll.DeviceType.COLOR_LIGHT
    dev = app2.get_device(custom_ieee)

    app.handle_leave(99, ieee)

    app2 = make_app(db)
    assert ieee in app2.devices

    async def mockleave(*args, **kwargs):
        return [0]

    app2.devices[ieee].zdo.leave = mockleave
    await app2.remove(ieee)
    assert ieee not in app2.devices

    app3 = make_app(db)
    assert ieee not in app3.devices

    os.unlink(db)


def _test_null_padded(tmpdir, test_manufacturer=None, test_model=None):
    db = os.path.join(str(tmpdir), 'test.db')
    app = make_app(db)
    # TODO: Leaks a task on dev.initialize, I think?
    ieee = make_ieee()
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
    clus.listener_event('cluster_command', 0)
    clus.listener_event('zdo_command')

    # Everything should've been saved - check that it re-loads
    app2 = make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[3].in_clusters[0]._attr_cache[4] == test_manufacturer
    assert dev.endpoints[3].in_clusters[0]._attr_cache[5] == test_model

    os.unlink(db)

    return dev


def test_appdb_load_null_padded_manuf(tmpdir):
    manufacturer = b'Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07'
    model = b'Mock Model'
    dev = _test_null_padded(tmpdir, manufacturer, model)

    assert dev.endpoints[3].manufacturer == 'Mock Manufacturer'
    assert dev.endpoints[3].model == 'Mock Model'


def test_appdb_load_null_padded_model(tmpdir):
    manufacturer = b'Mock Manufacturer'
    model = b'Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    dev = _test_null_padded(tmpdir, manufacturer, model)

    assert dev.endpoints[3].manufacturer == 'Mock Manufacturer'
    assert dev.endpoints[3].model == 'Mock Model'


def test_appdb_load_null_padded_manuf_model(tmpdir):
    manufacturer = b'Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07'
    model = b'Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    dev = _test_null_padded(tmpdir, manufacturer, model)

    assert dev.endpoints[3].manufacturer == 'Mock Manufacturer'
    assert dev.endpoints[3].model == 'Mock Model'


def test_appdb_str_model(tmpdir):
    manufacturer = 'Mock Manufacturer'
    model = 'Mock Model'
    dev = _test_null_padded(tmpdir, manufacturer, model)

    assert dev.endpoints[3].manufacturer == 'Mock Manufacturer'
    assert dev.endpoints[3].model == 'Mock Model'


@pytest.mark.asyncio
async def test_node_descriptor_updated(tmpdir, monkeypatch):
    monkeypatch.setattr(Device, '_initialize', _initialize)
    db = os.path.join(str(tmpdir), 'test_nd.db')
    app = make_app(db)
    nd_ieee = make_ieee(2)
    app.handle_join(299, nd_ieee, 0)

    dev = app.get_device(nd_ieee)
    ep = dev.add_endpoint(1)
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    app.device_initialized(dev)

    node_desc = zdo_t.NodeDescriptor.deserialize(b'abcdefghijklm')[0]

    async def mock_get_node_descriptor():
        dev.node_desc = node_desc
        return node_desc
    dev.get_node_descriptor = mock.MagicMock()
    dev.get_node_descriptor.side_effect = mock_get_node_descriptor
    await dev.refresh_node_descriptor()

    assert dev.get_node_descriptor.call_count == 1

    app2 = make_app(db)
    dev = app2.get_device(nd_ieee)
    assert dev.node_desc.is_valid
    assert dev.node_desc.serialize() == b'abcdefghijklm'

    os.unlink(db)


@pytest.mark.asyncio
async def test_groups(tmpdir, monkeypatch):
    monkeypatch.setattr(Device, '_initialize', _initialize)

    group_id, group_name = 0x1221, "app db Test Group 0x1221"

    async def mock_request(*args, **kwargs):
        return [ZCLStatus.SUCCESS, group_id]
    monkeypatch.setattr(zigpy.zcl.Cluster, 'request', mock_request)

    db = os.path.join(str(tmpdir), 'test.db')
    app = make_app(db)
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
    app2 = make_app(db)
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
    app3 = make_app(db)
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
    app4 = make_app(db)
    dev4 = app4.get_device(ieee)
    assert group_id not in app4.groups
    assert group_id not in dev4.endpoints[1].member_of
