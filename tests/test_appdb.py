import os
from unittest import mock

import pytest

import zigpy.types as t
from zigpy.application import ControllerApplication
from zigpy import profiles


def make_app(database_file):
    return ControllerApplication(database_file)


def make_ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


class FakeCustomDevice:
    ieee = make_ieee(1)


def fake_get_device(device):
    if device[1].profile_id == 65535:
        return FakeCustomDevice()
    return device


@pytest.mark.asyncio
async def test_database(tmpdir):
    db = os.path.join(str(tmpdir), 'test.db')
    app = make_app(db)
    # TODO: Leaks a task on dev.initialize, I think?
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
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
    clus.listener_event('cluster_command', 0)
    clus.listener_event('zdo_command')

    # Test a CustomDevice
    custom_ieee = make_ieee(1)
    app.handle_join(199, custom_ieee, 0)
    dev = app.get_device(custom_ieee)
    ep = dev.add_endpoint(1)
    ep.profile_id = 65535
    with mock.patch('zigpy.quirks.get_device', fake_get_device):
        app.device_initialized(dev)
    assert isinstance(app.get_device(custom_ieee), FakeCustomDevice)

    # Everything should've been saved - check that it re-loads
    with mock.patch('zigpy.quirks.get_device', fake_get_device):
        app2 = make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[2].device_type == 0xfffd
    assert dev.endpoints[2].in_clusters[0]._attr_cache[0] == 99
    assert dev.endpoints[2].out_clusters[1].cluster_id == 1
    assert dev.endpoints[3].device_type == profiles.zll.DeviceType.COLOR_LIGHT
    dev = app2.get_device(custom_ieee)
    assert isinstance(dev, FakeCustomDevice)

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
