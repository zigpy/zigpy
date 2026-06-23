import asyncio
from datetime import UTC, datetime, timedelta
import pathlib
import sqlite3
import time

import aiosqlite
import freezegun
import pytest

from tests.async_mock import AsyncMock, MagicMock, call, patch
from tests.conftest import (
    make_app,
    make_ieee,
    make_node_desc,
    mock_attribute_reads,
    mock_attribute_report,
    mock_attribute_writes,
)
from tests.test_backups import backup_factory  # noqa: F401
from zigpy import profiles
import zigpy.appdb
import zigpy.application
import zigpy.config as conf
from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_NODE_DESC,
)
from zigpy.device import Device, Status
import zigpy.endpoint
import zigpy.ota
import zigpy.types as t
import zigpy.zcl
from zigpy.zcl import (
    OtaQueryCacheClearedEvent,
    OtaQueryCacheUpdatedEvent,
    UnsupportedAttribute,
)
from zigpy.zcl.clusters.general import Basic, Identify, OnOff, Ota
from zigpy.zcl.foundation import Status as ZCLStatus, ZCLAttributeDef
from zigpy.zdo import types as zdo_t

pytestmark = pytest.mark.usefixtures("auto_kill_aiosqlite")


async def make_app_with_db(database_file, device_resolver=None):
    if isinstance(database_file, pathlib.Path):
        database_file = str(database_file)

    app = make_app({conf.CONF_DATABASE: database_file})
    if device_resolver is not None:
        app.register_device_resolver(device_resolver)
    await app._load_db()

    return app


def add_ep99_resolver(device):
    """Resolver that adds clusters to ep1 and a runtime-only ep99 on a clone."""
    if device.endpoints.get(1) is None or device[1].profile_id != 65535:
        return device

    new = device.clone()
    for ep_id in (1, 99):
        if ep_id in new.endpoints:
            ep = new.endpoints[ep_id]
        else:
            ep = new.add_endpoint(ep_id)
            ep.status = zigpy.endpoint.Status.ZDO_INIT
            ep.profile_id = 65535
            ep.device_type = 123
        for cluster_id in (0, 1, 3, 0x0008):
            ep.add_input_cluster(cluster_id)
        ep.add_output_cluster(6)
    return new


def mock_dev_init(initialize: bool):
    """Device schedule_initialize mock factory."""

    def _initialize(self):
        if initialize:
            self.node_desc = zdo_t.NodeDescriptor(0, 1, 2, 3, 4, 5, 6, 7, 8)

    return _initialize


def _mk_rar(attrid, value, status=0):
    r = zigpy.zcl.foundation.ReadAttributeRecord()
    r.attrid = attrid
    r.status = status
    r.value = zigpy.zcl.foundation.TypeValue()
    r.value.value = value
    return r


async def test_no_database(tmp_path):
    with patch("zigpy.appdb.PersistingListener.new", AsyncMock()) as db_mock:
        db_mock.return_value.load.side_effect = AsyncMock()
        await make_app_with_db(None)
    assert db_mock.return_value.load.call_count == 0

    db = tmp_path / "test.db"
    with patch("zigpy.appdb.PersistingListener.new", AsyncMock()) as db_mock:
        db_mock.return_value.load.side_effect = AsyncMock()
        await make_app_with_db(db)
    assert db_mock.return_value.load.call_count == 1


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_database(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
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
    in_clus = ep.add_input_cluster(0)
    out_clus = ep.add_output_cluster(0)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 49246
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    app.device_initialized(dev)

    in_clus.update_attribute(0, 99)
    in_clus.update_attribute(4, b"Custom")
    in_clus.update_attribute(5, b"Model")
    in_clus.listener_event("cluster_command", 0)
    in_clus.listener_event("general_command")

    out_clus.update_attribute(0, 99)

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
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    ep.profile_id = 65535
    app.register_device_resolver(add_ep99_resolver)
    app.device_initialized(dev)
    assert 99 in app.get_device(custom_ieee).endpoints
    dev = app.get_device(custom_ieee)
    # A re-announce must not re-persist the quirk's virtual endpoints
    app.device_initialized(dev)
    dev.relays = relays_2
    dev.endpoints[1].level.update_attribute(0x0011, 17)
    dev.endpoints[99].level.update_attribute(0x0011, 17)
    assert dev.endpoints[1].in_clusters[0x0008]._attr_cache[0x0011] == 17
    assert dev.endpoints[99].in_clusters[0x0008]._attr_cache[0x0011] == 17
    custom_dev_last_seen = dev.last_seen
    assert isinstance(custom_dev_last_seen, float)

    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db, device_resolver=add_ep99_resolver)
    dev = app2.get_device(ieee)
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[2].device_type == 0xFFFD
    assert dev.endpoints[2].in_clusters[0].get(0x0000) == 99
    assert dev.endpoints[2].in_clusters[0].get(0x0004) == b"Custom"
    assert dev.endpoints[2].in_clusters[0].get(0x0005) == b"Model"
    assert dev.endpoints[2].out_clusters[0].cluster_id == 0x0000
    assert dev.endpoints[2].out_clusters[0].get(0) == 99
    assert dev.endpoints[2].manufacturer == "Custom"
    assert dev.endpoints[2].model == "Model"
    assert dev.endpoints[3].device_type == profiles.zll.DeviceType.COLOR_LIGHT
    assert dev.relays == relays_1
    # The timestamp won't be restored exactly but it is more than close enough
    assert abs(dev.last_seen - dev_last_seen) < 0.01

    dev = app2.get_device(custom_ieee)
    # This virtual attribute is added by the quirk, there is no corresponding cluster
    # stored in the database, nor is there a corresponding endpoint 99
    assert dev.endpoints[1].in_clusters[0x0008].get(0x0011) == 17
    assert dev.endpoints[99].in_clusters[0x0008].get(0x0011) == 17
    assert dev.relays == relays_2
    assert abs(dev.last_seen - custom_dev_last_seen) < 0.01
    dev.relays = None

    app.handle_leave(99, ieee)
    await app2.shutdown()

    app3 = await make_app_with_db(db)
    assert ieee in app3.devices

    async def mockleave(*args, **kwargs):
        return [0]

    app3.devices[ieee].zdo.leave = mockleave
    await app3.remove(ieee)
    for _i in range(1, 20):
        await asyncio.sleep(0)
    assert ieee not in app3.devices
    await app3.shutdown()

    app4 = await make_app_with_db(db)
    assert ieee not in app4.devices
    dev = app4.get_device(custom_ieee)
    assert dev.relays is None
    await app4.shutdown()


@patch("zigpy.device.Device.schedule_group_membership_scan", MagicMock())
async def _test_null_padded(tmp_path, test_manufacturer=None, test_model=None):
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
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
    clus.update_attribute(4, test_manufacturer)
    clus.update_attribute(5, test_model)
    clus.listener_event("cluster_command", 0)
    clus.listener_event("zdo_command")
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db)
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
    app = await make_app_with_db(db)
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
    app2 = await make_app_with_db(db)
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

    app3 = await make_app_with_db(db)
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

    app4 = await make_app_with_db(db)
    dev4 = app4.get_device(ieee)
    assert group_id in app4.groups
    assert not app4.groups[group_id]
    assert group_id not in dev4.endpoints[1].member_of
    app4.groups.pop(group_id)
    await app4.shutdown()
    del app4, dev4

    app5 = await make_app_with_db(db)
    assert not app5.groups
    await app5.shutdown()


@pytest.mark.parametrize("dev_init", [True, False])
async def test_attribute_update(tmp_path, dev_init):
    """Test attribute update for initialized and uninitialized devices."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
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
    clus = ep.add_input_cluster(0x0000)
    ep.add_output_cluster(0x0001)
    clus.update_attribute(0x0004, test_manufacturer)
    clus.update_attribute(0x0005, test_model)
    app.device_initialized(dev)
    await app.shutdown()

    attr_update_time = clus._attr_cache.get_last_updated(
        Basic.AttributeDefs.manufacturer
    )

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db)
    dev = app2.get_device(ieee)
    assert dev.is_initialized == dev_init
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP

    clus = dev.endpoints[3].in_clusters[0x0000]
    assert clus._attr_cache[0x0004] == test_manufacturer
    assert clus._attr_cache[0x0005] == test_model

    assert (
        attr_update_time
        - clus._attr_cache.get_last_updated(Basic.AttributeDefs.manufacturer)
    ) < timedelta(seconds=0.1)

    await app2.shutdown()


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_attribute_update_short_interval(tmp_path):
    """Test updating an attribute twice in a short interval."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0x0000)
    ep.add_output_cluster(0x0001)
    clus.update_attribute(0x0004, "Custom")
    clus.update_attribute(0x0005, "Model")
    app.device_initialized(dev)

    # wait for the device initialization to write attribute cache to db
    await asyncio.sleep(0.01)

    # update an attribute twice in a short interval
    clus.update_attribute(0x4000, "1.0")
    attr_update_time_first = clus._attr_cache.get_last_updated(
        Basic.AttributeDefs.sw_build_id
    )

    # update attribute again 10 seconds later
    fake_time = datetime.now(UTC) + timedelta(seconds=10)
    with freezegun.freeze_time(fake_time):
        clus.update_attribute(0x4000, "2.0")

    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db)
    dev = app2.get_device(ieee)

    clus = dev.endpoints[3].in_clusters[0x0000]
    assert clus._attr_cache[0x4000] == "2.0"  # verify second attribute update was saved

    # verify the first update attribute time was not overwritten, as it was within the short interval
    assert (
        attr_update_time_first
        - clus._attr_cache.get_last_updated(Basic.AttributeDefs.sw_build_id)
    ) < timedelta(seconds=0.1)

    await app2.shutdown()


@patch("zigpy.topology.REQUEST_DELAY", (0, 0))
@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_topology(tmp_path):
    """Test neighbor loading."""

    ext_pid = t.EUI64.convert("aa:bb:cc:dd:ee:ff:01:02")

    neighbor1 = zdo_t.Neighbor(
        extended_pan_id=ext_pid,
        ieee=make_ieee(1),
        nwk=0x1111,
        device_type=zdo_t.Neighbor.DeviceType.EndDevice,
        rx_on_when_idle=1,
        relationship=zdo_t.Neighbor.Relationship.Child,
        reserved1=0,
        permit_joining=0,
        reserved2=0,
        depth=15,
        lqi=250,
    )

    neighbor2 = zdo_t.Neighbor(
        extended_pan_id=ext_pid,
        ieee=make_ieee(2),
        nwk=0x1112,
        device_type=zdo_t.Neighbor.DeviceType.EndDevice,
        rx_on_when_idle=1,
        relationship=zdo_t.Neighbor.Relationship.Child,
        reserved1=0,
        permit_joining=0,
        reserved2=0,
        depth=15,
        lqi=250,
    )

    route1 = zdo_t.Route(
        DstNWK=0x1234,
        RouteStatus=zdo_t.RouteStatus.Active,
        MemoryConstrained=0,
        ManyToOne=0,
        RouteRecordRequired=0,
        Reserved=0,
        NextHop=0x6789,
    )

    route2 = zdo_t.Route(
        DstNWK=0x1235,
        RouteStatus=zdo_t.RouteStatus.Active,
        MemoryConstrained=0,
        ManyToOne=0,
        RouteRecordRequired=0,
        Reserved=0,
        NextHop=0x6790,
    )

    ieee = make_ieee(0)
    nwk = 0x9876

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    app.handle_join(nwk, ieee, 0x0000)

    dev = app.get_device(ieee)
    dev.node_desc = zdo_t.NodeDescriptor(
        logical_type=zdo_t.LogicalType.Router,
        complex_descriptor_available=0,
        user_descriptor_available=0,
        reserved=0,
        aps_flags=0,
        frequency_band=zdo_t.NodeDescriptor.FrequencyBand.Freq2400MHz,
        mac_capability_flags=zdo_t.NodeDescriptor.MACCapabilityFlags.AllocateAddress,
        manufacturer_code=4174,
        maximum_buffer_size=82,
        maximum_incoming_transfer_size=82,
        server_mask=0,
        maximum_outgoing_transfer_size=82,
        descriptor_capability_field=zdo_t.NodeDescriptor.DescriptorCapability.NONE,
    )

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = 260
    ep1.device_type = 0x1234
    app.device_initialized(dev)

    p1 = patch.object(
        app.topology,
        "_scan_neighbors",
        new=AsyncMock(return_value=[neighbor1, neighbor2]),
    )

    p2 = patch.object(
        app.topology,
        "_scan_routes",
        new=AsyncMock(return_value=[route1, route2]),
    )

    with p1, p2:
        await app.topology.scan()

    assert len(app.topology.neighbors[ieee]) == 2
    assert neighbor1 in app.topology.neighbors[ieee]
    assert neighbor2 in app.topology.neighbors[ieee]

    assert len(app.topology.routes[ieee]) == 2
    assert route1 in app.topology.routes[ieee]
    assert route2 in app.topology.routes[ieee]

    await app.shutdown()
    del dev

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db)
    app2.get_device(ieee)

    assert len(app2.topology.neighbors[ieee]) == 2
    assert neighbor1 in app2.topology.neighbors[ieee]
    assert neighbor2 in app2.topology.neighbors[ieee]

    assert len(app2.topology.routes[ieee]) == 2
    assert route1 in app2.topology.routes[ieee]
    assert route2 in app2.topology.routes[ieee]

    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_rejoin(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
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
    clus.update_attribute(4, "Custom")
    clus.update_attribute(5, "Model")
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db)
    dev = app2.get_device(ieee)
    assert dev.nwk == nwk
    assert dev.endpoints[1].device_type == profiles.zha.DeviceType.PUMP
    assert dev.endpoints[1].in_clusters[0]._attr_cache[4] == "Custom"
    assert dev.endpoints[1].in_clusters[0]._attr_cache[5] == "Model"
    assert dev.endpoints[1].manufacturer == "Custom"
    assert dev.endpoints[1].model == "Model"

    # device rejoins with a new NWK (persisted via the `device_joined` event)
    app2.handle_join(nwk + 1, ieee, 0)
    await app2.shutdown()

    app3 = await make_app_with_db(db)
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
    app = await make_app_with_db(db)
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
        clus.update_attribute(0, 99)
        clus.update_attribute(4, b"Custom")
        clus.update_attribute(5, b"Model")
        await app.shutdown()
        assert mock_attr_save.call_count == 3

        clus.update_attribute(0, 100)
        for _i in range(100):
            await asyncio.sleep(0)
        assert mock_attr_save.call_count == 3


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_invalid_node_desc(tmp_path):
    """Devices without a valid node descriptor should not save the node descriptor."""

    ieee_1 = make_ieee(1)
    nwk_1 = 0x1111

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
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
    app2 = await make_app_with_db(db)
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
        "zigpy.appdb.PersistingListener._raw_device_initialized",
        wraps=zigpy.appdb.PersistingListener._raw_device_initialized,
    ) as save_mock:
        db_listener = await zigpy.appdb.PersistingListener.new(db, app_mock)

        for _ in range(3):
            db_listener.raw_device_initialized(dev_1)
        await db_listener.shutdown()

    assert save_mock.await_count == 3


@pytest.mark.parametrize("dev_init", [True, False])
async def test_unsupported_attribute(tmp_path, dev_init):
    """Test adding unsupported attributes for initialized and uninitialized devices."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
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
    in_clus = ep.add_input_cluster(0)
    out_clus = ep.add_output_cluster(0)
    in_clus.update_attribute(4, "Custom")
    in_clus.update_attribute(5, "Model")
    app.device_initialized(dev)

    in_clus.add_unsupported_attribute(Basic.AttributeDefs.location_desc.id)
    in_clus.add_unsupported_attribute("physical_env")

    out_clus.add_unsupported_attribute(Basic.AttributeDefs.location_desc.id)
    await app.shutdown()

    # Everything should've been saved - check that it re-loads
    app2 = await make_app_with_db(db)
    dev = app2.get_device(ieee)
    assert dev.is_initialized == dev_init
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert (
        dev.endpoints[3]
        .out_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)
    )
    assert (
        dev.endpoints[3]
        .in_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)
    )
    assert (
        dev.endpoints[3]
        .in_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.physical_env)
    )
    await app2.shutdown()

    # Now lets remove an unsupported attribute and make sure it is removed
    app3 = await make_app_with_db(db)
    dev = app3.get_device(ieee)
    assert dev.is_initialized == dev_init
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP

    in_cluster = dev.endpoints[3].in_clusters[0]

    # `location_desc` on the in cluster flips from unsupported to unsupported
    assert in_cluster._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)
    in_cluster.update_attribute(Basic.AttributeDefs.location_desc, "Not Removed")
    assert not in_cluster._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)

    assert in_cluster.get(Basic.AttributeDefs.location_desc.id) == "Not Removed"
    assert in_cluster._attr_cache.is_unsupported(Basic.AttributeDefs.physical_env)

    out_cluster = dev.endpoints[3].out_clusters[0]
    out_cluster.update_attribute(Basic.AttributeDefs.location_desc, "test")
    await app3.shutdown()

    # Everything should've been saved - check that it re-loads
    app4 = await make_app_with_db(db)
    dev = app4.get_device(ieee)
    assert dev.is_initialized == dev_init
    assert dev.endpoints[3].device_type == profiles.zha.DeviceType.PUMP
    assert (
        dev.endpoints[3].in_clusters[0].get(Basic.AttributeDefs.location_desc)
        == "Not Removed"
    )

    assert (
        not dev.endpoints[3]
        .in_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)
    )
    assert (
        not dev.endpoints[3]
        .out_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)
    )
    assert (
        not dev.endpoints[3]
        .in_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)
    )
    assert (
        dev.endpoints[3]
        .in_clusters[0]
        ._attr_cache.is_unsupported(Basic.AttributeDefs.physical_env)
    )
    await app4.shutdown()


async def test_device_without_node_descriptor_not_persisted(tmp_path) -> None:
    """A device whose node descriptor was never read persists without one."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    dev = app.add_device(nwk=0x1234, ieee=ieee)
    assert dev.node_desc is None

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(Basic.cluster_id)

    app.device_initialized(dev)
    await app.shutdown()

    with sqlite3.connect(str(db)) as conn:
        cur = conn.cursor()

        # The device itself was persisted
        cur.execute(
            f"SELECT ieee FROM devices{zigpy.appdb.DB_V} WHERE ieee=?", [str(ieee)]
        )
        assert len(cur.fetchall()) == 1

        # ...but no node descriptor row was written for it
        cur.execute(
            f"SELECT * FROM node_descriptors{zigpy.appdb.DB_V} WHERE ieee=?",
            [str(ieee)],
        )
        assert not cur.fetchall()


async def test_appdb_refuses_to_save_quirked_device(tmp_path) -> None:
    """Only a bare device may be persisted, a quirked one is refused."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    # A populated `original_signature` marks a device that has entered quirk
    # resolution and must never be written to the database.
    dev.original_signature = dev.get_signature()

    with pytest.raises(
        ValueError, match="A device with quirks cannot be saved to the database"
    ):
        await app._dblistener._raw_device_initialized_internal(dev)

    await app.shutdown()


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_load_unsupp_attr_wrong_cluster(tmp_path):
    """Test loading unsupported attribute from the wrong cluster."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus.update_attribute(4, "Custom")
    clus.update_attribute(5, "Model")
    app.device_initialized(dev)
    await app.shutdown()
    del clus
    del ep
    del dev

    # add unsupported attr for missing endpoint
    app = await make_app_with_db(db)
    dev = app.get_device(ieee)
    ep = dev.endpoints[3]
    clus = ep.add_input_cluster(2)
    clus.add_unsupported_attribute(0)
    await app.shutdown()
    del clus
    del ep
    del dev

    # reload
    app = await make_app_with_db(db)
    await app.shutdown()


@patch.object(Device, "schedule_initialize", new=mock_dev_init(True))
async def test_load_unsupp_attr_missing_endpoint(tmp_path):
    """Test loading unsupported attribute from the wrong cluster."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)

    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0x0000)
    ep.add_output_cluster(0x0001)
    clus.update_attribute(0x0004, "Custom")
    clus.update_attribute(0x0005, "Model")

    ep = dev.add_endpoint(4)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0x0006)
    app.device_initialized(dev)

    # Make an attribute unsupported
    clus.add_unsupported_attribute(0x0000)

    await app.shutdown()
    del clus
    del ep
    del dev

    def remove_cluster(device):
        device.endpoints.pop(4)
        return device

    # Simulate a resolver (quirk) that removes the entire endpoint
    app = await make_app_with_db(db, device_resolver=remove_cluster)

    dev = app.get_device(ieee)
    assert 4 not in dev.endpoints
    await app.shutdown()


async def test_last_seen(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee=ieee)
    ep = dev.add_endpoint(3)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    ep.add_output_cluster(1)
    clus.update_attribute(4, "Custom")
    clus.update_attribute(5, "Model")
    app.device_initialized(dev)

    old_last_seen = dev.last_seen
    await app.shutdown()

    # The `last_seen` of a joined device persists
    app = await make_app_with_db(db)
    dev = app.get_device(ieee=ieee)
    await app.shutdown()

    next_last_seen = dev.last_seen
    assert abs(next_last_seen - old_last_seen) < 0.01

    app = await make_app_with_db(db)
    dev = app.get_device(ieee=ieee)

    # Last-seen is only written to the db every 30s (no write case)
    now = datetime.fromtimestamp(dev.last_seen + 5, UTC)
    with freezegun.freeze_time(now):
        dev.last_seen = datetime.now(UTC)

    await app.shutdown()

    app = await make_app_with_db(db)
    dev = app.get_device(ieee=ieee)
    assert dev.last_seen == next_last_seen  # no change
    await app.shutdown()

    app = await make_app_with_db(db)
    dev = app.get_device(ieee=ieee)

    # Last-seen is only written to the db every 30s (write case)
    now = datetime.fromtimestamp(dev.last_seen + 35, UTC)
    with freezegun.freeze_time(now):
        dev.last_seen = datetime.now(UTC)

    await app.shutdown()

    # And it will be updated when the database next loads
    app = await make_app_with_db(db)
    dev = app.get_device(ieee=ieee)
    assert dev.last_seen >= next_last_seen + 35  # updated
    await app.shutdown()


async def test_appdb_network_backups(tmp_path, backup_factory):  # noqa: F811
    db = tmp_path / "test.db"

    backup = backup_factory()

    app1 = await make_app_with_db(db)
    app1.backups.add_backup(backup)
    await app1.shutdown()

    # The backup is reloaded from the database as well
    app2 = await make_app_with_db(db)
    assert len(app2.backups.backups) == 1
    assert app2.backups.backups[0] == backup

    new_backup = backup_factory()
    new_backup.network_info.network_key.tx_counter += 10000

    app2.backups.add_backup(new_backup)
    await app2.shutdown()

    # The database will contain only the single backup
    app3 = await make_app_with_db(db)
    assert len(app3.backups.backups) == 1
    assert app3.backups.backups[0] == new_backup
    assert app3.backups.backups[0] != backup
    await app3.shutdown()


async def test_appdb_network_backups_format_change(tmp_path, backup_factory):  # noqa: F811
    db = tmp_path / "test.db"

    backup = backup_factory()
    backup.as_dict = MagicMock(return_value={"some new key": 1, **backup.as_dict()})

    app1 = await make_app_with_db(db)
    app1.backups.add_backup(backup)
    await app1.shutdown()

    # The backup is reloaded from the database as well
    app2 = await make_app_with_db(db)
    assert len(app2.backups.backups) == 1
    assert app2.backups.backups[0] == backup

    new_backup = backup_factory()
    new_backup.network_info.network_key.tx_counter += 10000

    app2.backups.add_backup(new_backup)
    await app2.shutdown()

    # The database will contain only the single backup
    with patch("zigpy.backups.BackupManager.add_backup") as mock_add_backup:
        app3 = await make_app_with_db(db)
        await app3.shutdown()

    assert mock_add_backup.mock_calls == [call(new_backup, suppress_event=True)]


async def test_appdb_persist_coordinator_info(tmp_path):  # noqa: F811
    db = tmp_path / "test.db"

    with patch(
        "zigpy.appdb.PersistingListener._save_attribute_cache",
        wraps=zigpy.appdb.PersistingListener._save_attribute_cache,
    ) as mock_save_attr_cache:
        app = await make_app_with_db(db)
        await app.initialize()
        await app.shutdown()

    # The cache is saved from a clone of the device, so the endpoint is a different
    # object than the live coordinator's, but it is the same endpoint
    assert len(mock_save_attr_cache.mock_calls) == 1
    (saved_endpoint,) = mock_save_attr_cache.mock_calls[0].args
    assert saved_endpoint.endpoint_id == 1


async def test_appdb_attribute_clear(tmp_path):
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    basic = ep.add_input_cluster(Basic.cluster_id)
    app.device_initialized(dev)

    basic.update_attribute(Basic.AttributeDefs.zcl_version.id, 0x12)

    await app.shutdown()

    # Upon reload, the attribute exists and is in the cache
    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee=dev.ieee)
    assert (
        dev2.endpoints[1].basic._attr_cache[Basic.AttributeDefs.zcl_version.id] == 0x12
    )

    # Clear an existing attribute
    dev2.endpoints[1].basic.update_attribute(Basic.AttributeDefs.zcl_version.id, None)

    # Clear an attribute not in the cache
    dev2.endpoints[1].basic.update_attribute(Basic.AttributeDefs.manufacturer.id, None)

    assert Basic.AttributeDefs.zcl_version.id not in dev2.endpoints[1].basic._attr_cache
    await asyncio.sleep(0.1)
    await app2.shutdown()

    # The attribute has been removed from the database
    app3 = await make_app_with_db(db)
    dev3 = app3.get_device(ieee=dev.ieee)
    assert Basic.AttributeDefs.zcl_version.id not in dev3.endpoints[1].basic._attr_cache
    await app3.shutdown()


async def test_appdb_resolver_sees_populated_attributes(tmp_path) -> None:
    """Test the resolver is given a fully attribute-populated device on load."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    basic = ep.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model.id, "Some Model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer.id, "Some Manufacturer")

    ota = ep.add_output_cluster(Ota.cluster_id)
    ota.update_attribute(Ota.AttributeDefs.current_file_version.id, 0x12345678)

    app.device_initialized(dev)
    await app.shutdown()

    seen = {}

    def resolver(device):
        ota_cluster = device.endpoints[1].out_clusters[Ota.cluster_id]
        seen["firmware"] = ota_cluster.get(Ota.AttributeDefs.current_file_version.id)
        seen["manufacturer"] = device.manufacturer
        seen["model"] = device.model
        return device

    app2 = await make_app_with_db(db, device_resolver=resolver)

    assert seen["firmware"] == 0x12345678
    assert seen["manufacturer"] == "Some Manufacturer"
    assert seen["model"] == "Some Model"

    await app2.shutdown()


async def test_attribute_reads_persist(tmp_path) -> None:
    """Test that attribute reads are persisted to the database."""

    class CustomBasicCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            # This attribute intentionally collides with `model`
            custom_attr = ZCLAttributeDef(
                id=0x0004, type=t.uint8_t, manufacturer_code=0x1234
            )

    def replace_basic(device):
        new = device.clone()
        ep = new.endpoints[1]
        old = ep.in_clusters.pop(Basic.cluster_id, None)
        cluster = CustomBasicCluster(ep, is_server=True)
        ep.add_input_cluster(cluster.cluster_id, cluster)
        if old is not None:
            cluster._attr_cache_internal = old._attr_cache.clone(cluster)
        return new

    db = tmp_path / "test.db"
    app = await make_app_with_db(db, device_resolver=replace_basic)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    basic = ep.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model, "some model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "some manufacturer")

    await dev.initialize()

    dev = app.get_device(ieee=dev.ieee)
    assert isinstance(dev.endpoints[1].basic, CustomBasicCluster)

    with mock_attribute_reads(
        dev.endpoints[1].basic,
        {
            CustomBasicCluster.AttributeDefs.product_label: "some label",
            CustomBasicCluster.AttributeDefs.serial_number: ZCLStatus.UNSUPPORTED_ATTRIBUTE,
            CustomBasicCluster.AttributeDefs.custom_attr: 0xAB,
        },
    ):
        await dev.endpoints[1].basic.read_attributes(
            [
                CustomBasicCluster.AttributeDefs.product_label,
                CustomBasicCluster.AttributeDefs.serial_number,
                CustomBasicCluster.AttributeDefs.custom_attr,
            ]
        )

    await app.shutdown()

    # Load it back from disk
    app2 = await make_app_with_db(db, device_resolver=replace_basic)
    dev2 = app2.get_device(t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.product_label
        )
        == "some label"
    )

    with pytest.raises(UnsupportedAttribute):
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.serial_number
        )

    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.custom_attr
        )
        == 0xAB
    )

    await app2.shutdown()


async def test_appdb_custom_device_subclass_round_trip(tmp_path) -> None:
    """A resolver returning a `Device` subclass round-trips."""

    class CustomBasicCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            # Virtual attribute populated by the quirk, never read from the device
            virtual_attr = ZCLAttributeDef(id=0x8001, type=t.uint8_t)

    class QuirkedDevice(Device):
        """Minimal stand-in for a zha-device-handlers CustomDevice."""

        def __init__(self, application, ieee, nwk, *, replaces):
            super().__init__(application, ieee, nwk)
            self.lqi = replaces.lqi
            self.rssi = replaces.rssi
            self.last_seen = replaces.last_seen
            self.relays = replaces.relays
            self.original_signature = replaces.original_signature
            self.status = replaces.status
            self.node_desc = replaces.node_desc
            self.manufacturer = replaces.manufacturer
            self.model = replaces.model

            for endpoint in replaces.non_zdo_endpoints:
                new_ep = self.add_endpoint(endpoint.endpoint_id)
                new_ep.status = endpoint.status
                new_ep.profile_id = endpoint.profile_id
                new_ep.device_type = endpoint.device_type

                for cluster in endpoint.in_clusters.values():
                    if cluster.cluster_id == Basic.cluster_id:
                        new_cluster = CustomBasicCluster(new_ep, is_server=True)
                        new_ep.add_input_cluster(new_cluster.cluster_id, new_cluster)
                    else:
                        new_cluster = new_ep.add_input_cluster(cluster.cluster_id)
                    new_cluster._attr_cache_internal = cluster._attr_cache.clone(
                        new_cluster
                    )

                for cluster in endpoint.out_clusters.values():
                    new_cluster = new_ep.add_output_cluster(cluster.cluster_id)
                    new_cluster._attr_cache_internal = cluster._attr_cache.clone(
                        new_cluster
                    )

    def resolver(device):
        if device.model != "some model":
            return device
        return QuirkedDevice(
            device.application, device.ieee, device.nwk, replaces=device
        )

    db = tmp_path / "test.db"
    app = await make_app_with_db(db, device_resolver=resolver)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    basic = ep.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model, "some model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "some manufacturer")

    dev.model = "some model"
    dev.manufacturer = "some manufacturer"

    app.device_initialized(dev)

    dev = app.get_device(ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    # The resolver replaced the bare device with its subclass and custom cluster
    assert isinstance(dev, QuirkedDevice)
    assert isinstance(dev.endpoints[1].basic, CustomBasicCluster)

    # State copied from the bare device survives resolution
    assert dev.endpoints[1].basic.get_cached_value(Basic.AttributeDefs.model) == (
        "some model"
    )

    # A virtual attribute set by the quirk at runtime is persisted
    dev.endpoints[1].basic.update_attribute(
        CustomBasicCluster.AttributeDefs.virtual_attr, 42
    )

    await app.shutdown()

    # Reload from disk: the resolver runs again and the subclass + virtual attr return
    app2 = await make_app_with_db(db, device_resolver=resolver)
    dev2 = app2.get_device(ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    assert isinstance(dev2, QuirkedDevice)
    assert isinstance(dev2.endpoints[1].basic, CustomBasicCluster)
    assert dev2.endpoints[1].basic.get_cached_value(Basic.AttributeDefs.model) == (
        "some model"
    )
    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.virtual_attr
        )
        == 42
    )

    await app2.shutdown()


async def test_quirk_virtual_endpoints_not_persisted(tmp_path) -> None:
    """Re-finalizing a quirked device must not persist its virtual endpoints."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db, device_resolver=add_ep99_resolver)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    dev = app.add_device(nwk=0x1234, ieee=ieee)
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 65535
    ep.device_type = profiles.zll.DeviceType.COLOR_LIGHT
    ep.add_input_cluster(0)

    # The bare device is finalized; the resolver adds virtual endpoint 99
    app.device_initialized(dev)
    quirked = app.get_device(ieee)
    assert 99 in quirked.endpoints

    # A re-announce of the already-finalized (quirked) device
    app.device_initialized(quirked)

    await app.shutdown()

    # Only the bare endpoint should have been persisted
    with sqlite3.connect(str(db)) as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT endpoint_id FROM endpoints{zigpy.appdb.DB_V} ORDER BY endpoint_id"
        )
        endpoint_ids = [row[0] for row in cur.fetchall()]

    assert endpoint_ids == [1]

    # On reload, `original_signature` reflects only the bare device
    app2 = await make_app_with_db(db, device_resolver=add_ep99_resolver)
    dev2 = app2.get_device(ieee)

    # The resolver still reconstructs ep99 at runtime
    assert 99 in dev2.endpoints
    # ...but it never made it into the persisted signature
    assert list(dev2.original_signature[SIG_ENDPOINTS]) == [1]

    await app2.shutdown()


async def test_reinterview_changed_signature_round_trip(tmp_path) -> None:
    """A reinterview that changes the device's whole signature is persisted cleanly."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    nwk = t.NWK(0x1234)
    dev = app.add_device(nwk=nwk, ieee=ieee)
    dev.node_desc = make_node_desc()

    # Original signature: endpoints 1 and 2
    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = 260
    ep1.device_type = profiles.zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)
    ep1.add_input_cluster(OnOff.cluster_id)

    ep2 = dev.add_endpoint(2)
    ep2.status = zigpy.endpoint.Status.ZDO_INIT
    ep2.profile_id = 260
    ep2.device_type = profiles.zha.DeviceType.PUMP
    ep2.add_input_cluster(Identify.cluster_id)

    app.device_initialized(dev)
    await app.shutdown()

    # Reload: the original structure is intact
    app2 = await make_app_with_db(db)
    old_dev = app2.get_device(ieee)
    assert 1 in old_dev.endpoints
    assert 2 in old_dev.endpoints
    assert list(old_dev.original_signature[SIG_ENDPOINTS]) == [1, 2]

    # Re-interview into an entirely different signature: a single endpoint 3
    shadow = Device(app2, ieee, nwk)
    shadow.node_desc = make_node_desc()
    shadow.status = Status.ENDPOINTS_INIT
    ep3 = shadow.add_endpoint(3)
    ep3.status = zigpy.endpoint.Status.ZDO_INIT
    ep3.profile_id = 260
    ep3.device_type = profiles.zha.DeviceType.PUMP
    ep3.add_input_cluster(Basic.cluster_id)

    await app2._device_reinterviewed(old_dev, shadow)
    await app2.shutdown()

    # Reload: only the new structure survives; the old endpoints are gone
    app3 = await make_app_with_db(db)
    dev3 = app3.get_device(ieee)
    assert 1 not in dev3.endpoints
    assert 2 not in dev3.endpoints
    assert 3 in dev3.endpoints
    assert Basic.cluster_id in dev3.endpoints[3].in_clusters
    assert list(dev3.original_signature[SIG_ENDPOINTS]) == [3]

    await app3.shutdown()


async def test_attribute_reports_persist(tmp_path) -> None:
    """Test that attribute reports are persisted to the database."""

    class CustomBasicCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            # This attribute intentionally collides with `model`
            custom_attr = ZCLAttributeDef(
                id=0x0004, type=t.uint8_t, manufacturer_code=0x1234
            )

    def replace_basic(device):
        new = device.clone()
        ep = new.endpoints[1]
        old = ep.in_clusters.pop(Basic.cluster_id, None)
        cluster = CustomBasicCluster(ep, is_server=True)
        ep.add_input_cluster(cluster.cluster_id, cluster)
        if old is not None:
            cluster._attr_cache_internal = old._attr_cache.clone(cluster)
        return new

    db = tmp_path / "test.db"
    app = await make_app_with_db(db, device_resolver=replace_basic)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    basic = ep.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model, "some model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "some manufacturer")

    await dev.initialize()

    dev = app.get_device(ieee=dev.ieee)
    assert isinstance(dev.endpoints[1].basic, CustomBasicCluster)

    await mock_attribute_report(
        dev.endpoints[1].basic,
        {CustomBasicCluster.AttributeDefs.product_label: "some label"},
    )

    await mock_attribute_report(
        dev.endpoints[1].basic,
        {CustomBasicCluster.AttributeDefs.custom_attr: 0xAB},
    )

    await app.shutdown()

    # Load it back from disk
    app2 = await make_app_with_db(db, device_resolver=replace_basic)
    dev2 = app2.get_device(t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.product_label
        )
        == "some label"
    )

    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.custom_attr
        )
        == 0xAB
    )

    await app2.shutdown()


async def test_attribute_writes_persist(tmp_path) -> None:
    """Test that attribute writes are persisted to the database."""

    class CustomBasicCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            # This attribute intentionally collides with `model`
            custom_attr = ZCLAttributeDef(
                id=0x0004, type=t.uint8_t, manufacturer_code=0x1234
            )

    def replace_basic(device):
        new = device.clone()
        ep = new.endpoints[1]
        old = ep.in_clusters.pop(Basic.cluster_id, None)
        cluster = CustomBasicCluster(ep, is_server=True)
        ep.add_input_cluster(cluster.cluster_id, cluster)
        if old is not None:
            cluster._attr_cache_internal = old._attr_cache.clone(cluster)
        return new

    db = tmp_path / "test.db"
    app = await make_app_with_db(db, device_resolver=replace_basic)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    basic = ep.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model, "some model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "some manufacturer")

    await dev.initialize()

    dev = app.get_device(ieee=dev.ieee)
    assert isinstance(dev.endpoints[1].basic, CustomBasicCluster)

    with mock_attribute_writes(
        dev.endpoints[1].basic,
        {
            CustomBasicCluster.AttributeDefs.product_label: ZCLStatus.SUCCESS,
            CustomBasicCluster.AttributeDefs.serial_number: ZCLStatus.UNSUPPORTED_ATTRIBUTE,
            CustomBasicCluster.AttributeDefs.custom_attr: ZCLStatus.SUCCESS,
        },
    ):
        await dev.endpoints[1].basic.write_attributes(
            {
                CustomBasicCluster.AttributeDefs.product_label: "some label",
                CustomBasicCluster.AttributeDefs.serial_number: "some serial",
                CustomBasicCluster.AttributeDefs.custom_attr: 0xAB,
            }
        )

    await app.shutdown()

    # Load it back from disk
    app2 = await make_app_with_db(db, device_resolver=replace_basic)
    dev2 = app2.get_device(t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.product_label
        )
        == "some label"
    )

    with pytest.raises(UnsupportedAttribute):
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.serial_number
        )

    assert (
        dev2.endpoints[1].basic.get_cached_value(
            CustomBasicCluster.AttributeDefs.custom_attr
        )
        == 0xAB
    )

    await app2.shutdown()


async def test_attribute_cache_null_manufacturer_code_uniqueness(tmp_path):
    """Test that NULL manufacturer_code is treated as unique in the attribute cache."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    dev = app.add_device(ieee=ieee, nwk=0x1234)
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = profiles.zha.PROFILE_ID
    ep.device_type = profiles.zha.DeviceType.ON_OFF_SWITCH

    basic = ep.add_input_cluster(Basic.cluster_id)
    app.device_initialized(dev)

    # Write an attribute with NULL manufacturer_code twice
    basic.update_attribute(Basic.AttributeDefs.model, "Model 1")
    basic.update_attribute(Basic.AttributeDefs.model, "Model 2")

    await app.shutdown()

    # Verify there is only one row in the database
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM attributes_cache{zigpy.appdb.DB_V} WHERE attr_id = :attr_id AND manufacturer_code IS NULL",
            {"attr_id": Basic.AttributeDefs.model.id},
        )
        row = await cursor.fetchone()
        assert row[0] == 1

        # And the value is the latest one
        cursor = await conn.execute(
            f"SELECT value FROM attributes_cache{zigpy.appdb.DB_V} WHERE attr_id = :attr_id AND manufacturer_code IS NULL",
            {"attr_id": Basic.AttributeDefs.model.id},
        )
        row = await cursor.fetchone()
        assert row[0] == "Model 2"


async def test_device_signature_ignores_quirks(tmp_path) -> None:
    """Test that `device.original_signature` is populated before quirks modify the device."""

    def quirk_resolver(device):
        # A resolver that modifies a clone, leaving the bare device intact
        new = device.clone()
        ep99 = new.add_endpoint(99)
        ep99.status = zigpy.endpoint.Status.ZDO_INIT
        ep99.profile_id = profiles.zha.PROFILE_ID
        ep99.device_type = 0xFF
        ep99.add_input_cluster(Basic.cluster_id)
        new.endpoints[1].add_input_cluster(Identify.cluster_id)
        new.endpoints[1].out_clusters.pop(OnOff.cluster_id, None)
        return new

    expected_signature = {
        SIG_MANUFACTURER: "some manufacturer",
        SIG_MODEL: "some model",
        SIG_NODE_DESC: {
            "logical_type": zdo_t.LogicalType.Router,
            "complex_descriptor_available": 0,
            "user_descriptor_available": 0,
            "reserved": 0,
            "aps_flags": 0,
            "frequency_band": zdo_t.NodeDescriptor.FrequencyBand.Freq2400MHz,
            "mac_capability_flags": zdo_t.NodeDescriptor.MACCapabilityFlags.AllocateAddress,
            "manufacturer_code": 4174,
            "maximum_buffer_size": 82,
            "maximum_incoming_transfer_size": 82,
            "server_mask": 0,
            "maximum_outgoing_transfer_size": 82,
            "descriptor_capability_field": zdo_t.NodeDescriptor.DescriptorCapability.NONE,
        },
        SIG_ENDPOINTS: {
            1: {
                SIG_EP_PROFILE: 260,
                SIG_EP_TYPE: profiles.zha.DeviceType.PUMP,
                SIG_EP_INPUT: [Basic.cluster_id],
                SIG_EP_OUTPUT: [OnOff.cluster_id],
            },
        },
    }

    db = tmp_path / "test.db"
    app = await make_app_with_db(db, device_resolver=quirk_resolver)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    ep.add_output_cluster(OnOff.cluster_id)

    basic = ep.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model, "some model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "some manufacturer")

    dev.model = "some model"
    dev.manufacturer = "some manufacturer"

    # When a device joins at runtime, `device_initialized` applies quirks
    app.device_initialized(dev)
    dev = app.get_device(t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    # The quirk modified the device object
    assert 99 in dev.endpoints
    assert Identify.cluster_id in dev.endpoints[1].in_clusters
    assert OnOff.cluster_id not in dev.endpoints[1].out_clusters

    # But the original signature was captured before quirks were applied
    assert dev.original_signature == expected_signature

    await app.shutdown()

    # Also verify loading from the database preserves the original signature
    app2 = await make_app_with_db(db, device_resolver=quirk_resolver)
    dev2 = app2.get_device(t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    # The quirk modified the device object
    assert 99 in dev2.endpoints
    assert Identify.cluster_id in dev2.endpoints[1].in_clusters
    assert OnOff.cluster_id not in dev2.endpoints[1].out_clusters

    # The original signature is still preserved
    assert dev2.original_signature == expected_signature

    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_ota_query_cache_persistence(tmp_path):
    """Test that OTA query cache is persisted and restored from the database."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(0)  # Basic cluster, exercises non-OTA skip in load
    ota_cluster = ep.add_output_cluster(Ota.cluster_id)
    app.device_initialized(dev)

    # With hardware_version
    cmd = Ota.QueryNextImageCommand(
        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
        manufacturer_code=0x1234,
        image_type=0x5678,
        current_file_version=0x000A0001,
    )
    cmd.hardware_version = 3
    ota_cluster.last_query_cmd = cmd
    ota_cluster.emit(
        OtaQueryCacheUpdatedEvent.event_type,
        OtaQueryCacheUpdatedEvent(
            device_ieee=str(ieee),
            endpoint_id=1,
            cluster_type=ota_cluster.cluster_type,
            cluster_id=ota_cluster.cluster_id,
            manufacturer_code=cmd.manufacturer_code,
            image_type=cmd.image_type,
            current_file_version=cmd.current_file_version,
            hardware_version=cmd.hardware_version,
        ),
    )
    await app.shutdown()

    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee)
    ota2 = dev2.endpoints[1].out_clusters[Ota.cluster_id]

    assert ota2.last_query_cmd is not None
    assert ota2.last_query_cmd.manufacturer_code == 0x1234
    assert ota2.last_query_cmd.image_type == 0x5678
    assert ota2.last_query_cmd.current_file_version == 0x000A0001
    assert ota2.last_query_cmd.hardware_version == 3
    assert dev2.get_last_ota_query_cmd() is ota2.last_query_cmd

    # Update to a command without hardware_version
    new_cmd = Ota.QueryNextImageCommand(
        field_control=Ota.QueryNextImageCommand.FieldControl(0),
        manufacturer_code=0xAAAA,
        image_type=0xBBBB,
        current_file_version=0x00000042,
    )
    ota2.last_query_cmd = new_cmd
    ota2.emit(
        OtaQueryCacheUpdatedEvent.event_type,
        OtaQueryCacheUpdatedEvent(
            device_ieee=str(ieee),
            endpoint_id=1,
            cluster_type=ota2.cluster_type,
            cluster_id=ota2.cluster_id,
            manufacturer_code=new_cmd.manufacturer_code,
            image_type=new_cmd.image_type,
            current_file_version=new_cmd.current_file_version,
            hardware_version=getattr(new_cmd, "hardware_version", None),
        ),
    )
    await app2.shutdown()

    app3 = await make_app_with_db(db)
    dev3 = app3.get_device(ieee)
    ota3 = dev3.endpoints[1].out_clusters[Ota.cluster_id]

    assert ota3.last_query_cmd is not None
    assert ota3.last_query_cmd.manufacturer_code == 0xAAAA
    assert ota3.last_query_cmd.current_file_version == 0x00000042
    assert not hasattr(ota3.last_query_cmd, "hardware_version") or (
        ota3.last_query_cmd.hardware_version is None
    )

    await app3.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_ota_query_cache_event_save(tmp_path):
    """Test that the OtaQueryCacheUpdatedEvent triggers a DB save."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ota_cluster = ep.add_output_cluster(Ota.cluster_id)
    app.device_initialized(dev)

    # Simulate the event that _handle_query_next_image would emit
    event = OtaQueryCacheUpdatedEvent(
        device_ieee=str(ieee),
        endpoint_id=1,
        cluster_type=ota_cluster.cluster_type,
        cluster_id=ota_cluster.cluster_id,
        manufacturer_code=0x1111,
        image_type=0x2222,
        current_file_version=0x00000099,
        hardware_version=7,
    )

    ota_cluster.emit(OtaQueryCacheUpdatedEvent.event_type, event)
    await app.shutdown()

    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee)
    ota2 = dev2.endpoints[1].out_clusters[Ota.cluster_id]

    assert ota2.last_query_cmd is not None
    assert ota2.last_query_cmd.manufacturer_code == 0x1111
    assert ota2.last_query_cmd.image_type == 0x2222
    assert ota2.last_query_cmd.current_file_version == 0x00000099
    assert ota2.last_query_cmd.hardware_version == 7

    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_ota_query_cache_cleared_after_update(tmp_path):
    """Test that OTA query cache is deleted from DB when cleared after an update."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ota_cluster = ep.add_output_cluster(Ota.cluster_id)
    app.device_initialized(dev)

    # Save a query cmd
    ota_cluster.last_query_cmd = Ota.QueryNextImageCommand(
        field_control=Ota.QueryNextImageCommand.FieldControl(0),
        manufacturer_code=0x1234,
        image_type=0x5678,
        current_file_version=0x00000001,
    )
    app.device_initialized(dev)

    # Clear the cache (as update_firmware does after a successful OTA)
    ota_cluster.last_query_cmd = None
    ota_cluster.emit(
        OtaQueryCacheClearedEvent.event_type,
        OtaQueryCacheClearedEvent(
            device_ieee=str(ieee),
            endpoint_id=1,
        ),
    )
    await app.shutdown()

    # Reload: the cleared cache should not be restored
    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee)
    ota2 = dev2.endpoints[1].out_clusters[Ota.cluster_id]
    assert ota2.last_query_cmd is None
    assert dev2.get_last_ota_query_cmd() is None

    await app2.shutdown()


async def test_ota_query_cache_skips_quirk_removed_endpoint(tmp_path):
    """Test that OTA cache load skips entries for endpoints removed by a resolver."""

    def remove_ep2(device):
        device.endpoints.pop(2, None)
        return device

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)
    dev.model = "ota model"
    dev.manufacturer = "ota manufacturer"

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = 260
    ep1.device_type = profiles.zha.DeviceType.PUMP
    basic = ep1.add_input_cluster(Basic.cluster_id)
    basic.update_attribute(Basic.AttributeDefs.model, "ota model")
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "ota manufacturer")

    ep2 = dev.add_endpoint(2)
    ep2.status = zigpy.endpoint.Status.ZDO_INIT
    ep2.profile_id = 260
    ep2.device_type = profiles.zha.DeviceType.PUMP
    ota_cluster = ep2.add_output_cluster(Ota.cluster_id)

    ota_cluster.last_query_cmd = Ota.QueryNextImageCommand(
        field_control=Ota.QueryNextImageCommand.FieldControl(0),
        manufacturer_code=0x1234,
        image_type=0x5678,
        current_file_version=0x00000001,
    )

    app.device_initialized(dev)
    await app.shutdown()

    # Reload: resolver removes endpoint 2, OTA cache load should skip it
    app2 = await make_app_with_db(db, device_resolver=remove_ep2)
    dev2 = app2.get_device(t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    assert 2 not in dev2.endpoints
    assert dev2.get_last_ota_query_cmd() is None

    await app2.shutdown()


async def test_get_last_ota_query_cmd_returns_none(tmp_path):
    """Test that get_last_ota_query_cmd returns None when no query has been cached."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_output_cluster(Ota.cluster_id)
    app.device_initialized(dev)

    assert dev.get_last_ota_query_cmd() is None

    await app.shutdown()
