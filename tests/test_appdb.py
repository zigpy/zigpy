import os

import pytest

import zigpy.types as t
from zigpy.application import ControllerApplication
from zigpy import profiles


def make_app(database_file):
    return ControllerApplication(database_file)


@pytest.fixture
def ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


@pytest.mark.asyncio
async def test_database(tmpdir, ieee):
    db = os.path.join(str(tmpdir), 'test.db')
    app = make_app(db)
    # TODO: Leaks a task on dev.initialize, I think?
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
    app.listener_event('device_initialized', dev)
    clus._update_attribute(0, 99)
    clus.listener_event('cluster_command', 0)
    clus.listener_event('zdo_command')

    # Everything should've been saved - check that it re-loads
    app2 = make_app(db)
    dev = app2.get_device(ieee)
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[2].device_type == 0xfffd
    assert dev.endpoints[2].in_clusters[0]._attr_cache[0] == 99
    assert dev.endpoints[2].out_clusters[1].cluster_id == 1
    assert dev.endpoints[3].device_type == profiles.zll.DeviceType.COLOR_LIGHT

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
