import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
import logging
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
from tests.zgp.conftest import (
    KEY,
    commission,
    commissioning_payload,
    encrypted_gp_packet,
)
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
from zigpy.device import Device, GreenPowerDevice, Status
import zigpy.endpoint
import zigpy.group
import zigpy.ota
from zigpy.store import StoredValue
import zigpy.types as t
import zigpy.zcl
from zigpy.zcl import (
    OtaQueryCacheClearedEvent,
    OtaQueryCacheUpdatedEvent,
    UnsupportedAttribute,
    foundation,
)
from zigpy.zcl.clusters.general import Basic, Identify, MultistateInput, OnOff, Ota
from zigpy.zcl.clusters.homeautomation import ElectricalMeasurement
from zigpy.zcl.clusters.measurement import TemperatureMeasurement
from zigpy.zcl.clusters.security import IasZone
from zigpy.zcl.clusters.smartenergy import Metering
from zigpy.zcl.foundation import Array, DataTypeId, Status as ZCLStatus, ZCLAttributeDef
from zigpy.zdo import types as zdo_t
from zigpy.zgp.commands import (
    GPClusterReport,
    GPGenericSwitchConfiguration,
    GPManufacturerSpecificAttributeReportingPayload,
    GPManufacturerSpecificMultiClusterReportingPayload,
)
from zigpy.zgp.types import (
    GP_ENDPOINT,
    GP_GROUP_ID,
    ApplicationID,
    DeviceID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SrcID,
    SwitchType,
)
from zigpy.zgp.util import synthetic_ieee

pytestmark = pytest.mark.usefixtures("auto_kill_aiosqlite")


async def make_app_with_db(database_file, device_resolver=None, commit_interval=None):
    if isinstance(database_file, pathlib.Path):
        database_file = str(database_file)

    config = {conf.CONF_DATABASE: database_file}
    if commit_interval is not None:
        config[conf.CONF_DB_COMMIT_INTERVAL] = commit_interval

    app = make_app(config)
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

    # Updates within `MIN_UPDATE_DELTA` of the stored value aren't saved, so go past it
    ts = time.time() + zigpy.appdb.MIN_UPDATE_DELTA + 1
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


@pytest.mark.parametrize(
    ("value", "storable"),
    [
        (None, True),
        (t.uint8_t(1), True),
        (t.uint64_t(2**63 - 1), True),
        (t.uint64_t(2**63), False),
        (t.int64s(-(2**63)), True),
        (True, True),
        (zdo_t.LogicalType.Router, True),
        (t.Single(1.5), True),
        (t.CharacterString("text"), True),
        (t.LVBytes(b"\x01\x02"), True),
        (t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"), True),
        (t.LVList[t.CharacterString, t.uint16_t](["a", "b"]), False),
        (t.KeyData(range(16)), False),
        (make_node_desc(), False),
    ],
)
def test_is_storable_value(value, storable) -> None:
    """Values SQLite cannot bind are detected."""
    zigpy.appdb._register_sqlite_adapters()
    assert zigpy.appdb._is_storable_value(value) is storable


async def test_unstorable_attribute_values_not_persisted(tmp_path, caplog) -> None:
    """An attribute value that cannot be stored does not prevent saving the rest."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    for ep_id in (1, 2):
        ep = dev.add_endpoint(ep_id)
        ep.status = zigpy.endpoint.Status.ZDO_INIT
        ep.profile_id = 260
        ep.device_type = profiles.zha.DeviceType.ON_OFF_SWITCH
        ep.add_input_cluster(MultistateInput.cluster_id)
        ep.add_input_cluster(OnOff.cluster_id)

    dev.model = "some model"
    dev.manufacturer = "some manufacturer"

    # The device save stores the attribute cache in bulk. A list is stored typed but
    # one that does not fit its attribute's type cannot be stored at all.
    multistate = dev.endpoints[1].multistate_input
    multistate.update_attribute(MultistateInput.AttributeDefs.present_value, 2)
    multistate.update_attribute(
        MultistateInput.AttributeDefs.state_text,
        Array(
            type=DataTypeId.string,
            value=t.LVList[t.CharacterString, t.uint16_t](["a", "b"]),
        ),
    )
    multistate.update_attribute(MultistateInput.AttributeDefs.number_of_states, ["x"])
    dev.endpoints[1].on_off.update_attribute(OnOff.AttributeDefs.on_off, 1)
    dev.endpoints[2].on_off.update_attribute(OnOff.AttributeDefs.on_off, 0)

    with caplog.at_level(logging.DEBUG, logger="zigpy.appdb"):
        await dev.initialize()
        await app._dblistener._callback_handlers.join()

        # Attribute events are stored individually
        dev = app.get_device(ieee=dev.ieee)
        multistate = dev.endpoints[1].multistate_input

        with mock_attribute_reads(
            multistate,
            {
                MultistateInput.AttributeDefs.state_text: Array(
                    type=DataTypeId.string,
                    value=t.LVList[t.CharacterString, t.uint16_t](["c", "d"]),
                ),
                MultistateInput.AttributeDefs.description: "some description",
            },
        ):
            await multistate.read_attributes(
                [
                    MultistateInput.AttributeDefs.state_text,
                    MultistateInput.AttributeDefs.description,
                ]
            )

        multistate.update_attribute(MultistateInput.AttributeDefs.present_value, ["y"])
        await app._dblistener._callback_handlers.join()

    assert (
        "[aa:bb:cc:dd:11:22:33:44:1:0x0012] Not persisting attribute 0x004a"
        in caplog.text
    )
    assert "Not persisting attribute event" in caplog.text
    assert not any(
        isinstance(record.exc_info and record.exc_info[1], sqlite3.ProgrammingError)
        for record in caplog.records
    )

    await app.shutdown()

    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee=dev.ieee)

    # Everything but the unstorable values is persisted, including the second endpoint
    multistate2 = dev2.endpoints[1].multistate_input
    assert multistate2.get_cached_value("present_value") == 2
    assert multistate2.get_cached_value("state_text") == Array(
        type=DataTypeId.string,
        value=t.LVList[t.CharacterString, t.uint16_t](["c", "d"]),
    )
    assert multistate2.get_cached_value("description") == "some description"
    assert dev2.endpoints[1].on_off.get_cached_value("on_off") == 1
    assert dev2.endpoints[2].on_off.get_cached_value("on_off") == 0

    with pytest.raises(KeyError):
        multistate2.get_cached_value("number_of_states")

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


async def test_inactive_endpoints_round_trip(tmp_path) -> None:
    """A device listing inactive endpoints is persisted and reloads intact."""

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    dev = app.add_device(nwk=0x1234, ieee=ieee)
    dev.node_desc = make_node_desc()

    # Endpoint 2 is listed as active but has no simple descriptor, zigpy/zigpy#1894
    async def mock_active_ep_req(nwk):
        return [zdo_t.Status.SUCCESS, nwk, [1, 2]]

    async def mock_simple_desc_req(nwk, endpoint_id):
        if endpoint_id == 2:
            return [zdo_t.Status.NOT_ACTIVE, nwk, None]

        return [
            zdo_t.Status.SUCCESS,
            nwk,
            zdo_t.SizePrefixedSimpleDescriptor(
                endpoint=1,
                profile=profiles.zha.PROFILE_ID,
                device_type=profiles.zha.DeviceType.ON_OFF_SWITCH,
                device_version=1,
                input_clusters=[Basic.cluster_id],
                output_clusters=[OnOff.cluster_id],
            ),
        ]

    dev.zdo.Active_EP_req = mock_active_ep_req
    dev.zdo.Simple_Desc_req = mock_simple_desc_req

    with patch(
        "zigpy.endpoint.Endpoint.get_model_info",
        AsyncMock(return_value=("Model", "Manufacturer")),
    ):
        await dev.initialize()

    assert dev.is_initialized
    await app.shutdown()

    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee)

    assert list(dev2.original_signature[SIG_ENDPOINTS]) == [1]
    assert dev2.endpoints[1].profile_id == profiles.zha.PROFILE_ID
    assert dev2.endpoints[1].device_type == profiles.zha.DeviceType.ON_OFF_SWITCH
    assert list(dev2.endpoints[1].in_clusters) == [Basic.cluster_id]
    assert list(dev2.endpoints[1].out_clusters) == [OnOff.cluster_id]

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

    app2.devices[ieee] = shadow

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
            f"SELECT value, data_type FROM attributes_cache{zigpy.appdb.DB_V} WHERE attr_id = :attr_id AND manufacturer_code IS NULL",
            {"attr_id": Basic.AttributeDefs.model.id},
        )
        row = await cursor.fetchone()

        # Values set by `update_attribute` have no wire representation
        assert row == ("Model 2", None)


async def _make_app_with_clusters(db, cluster_ids):
    """Create an app with a single persisted device with input clusters on endpoint 1."""
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP

    for cluster_id in cluster_ids:
        ep.add_input_cluster(cluster_id)

    app.device_initialized(dev)

    return app, dev


def _read_attr_row(db, cluster_id, attr_id):
    with contextlib.closing(sqlite3.connect(db)) as conn:
        return conn.execute(
            f"SELECT value, data_type FROM attributes_cache{zigpy.appdb.DB_V}"
            " WHERE cluster_id = ? AND attr_id = ?",
            (cluster_id, attr_id),
        ).fetchone()


def _insert_typed_attr_row(db, ieee, cluster_id, attr_id, data_type, data) -> None:
    with contextlib.closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            f"INSERT INTO attributes_cache{zigpy.appdb.DB_V}"
            " (ieee, endpoint_id, cluster_type, cluster_id, attr_id, manufacturer_code,"
            " status, value, data_type, last_updated)"
            " VALUES (?, 1, 0, ?, ?, NULL, 0, ?, ?, 0)",
            (str(ieee), cluster_id, attr_id, data, data_type),
        )


async def _update_attribute(cluster, attr_id, value) -> None:
    cluster.update_attribute(attr_id, value)


async def _read_attribute(cluster, attr_def, value) -> None:
    with mock_attribute_reads(cluster, {attr_def: value}):
        await cluster.read_attributes([attr_def])


async def _report_attribute(cluster, attr_def, value) -> None:
    await mock_attribute_report(cluster, {attr_def: value})


async def _write_attribute(cluster, attr_def, value) -> None:
    with mock_attribute_writes(cluster, {attr_def: ZCLStatus.SUCCESS}):
        await cluster.write_attributes({attr_def: value})


TYPED_ATTRIBUTE_VALUES = [
    (OnOff, OnOff.AttributeDefs.start_up_on_off, OnOff.StartUpOnOff.Toggle),
    (Basic, Basic.AttributeDefs.model, Basic.AttributeDefs.model.type("Model")),
    (
        IasZone,
        IasZone.AttributeDefs.cie_addr,
        t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
    ),
    (
        MultistateInput,
        MultistateInput.AttributeDefs.state_text,
        Array(
            type=DataTypeId.string,
            value=t.LVList[t.CharacterString, t.uint16_t](["a", "b"]),
        ),
    ),
]


@pytest.mark.parametrize(
    "receive", [_read_attribute, _report_attribute, _write_attribute]
)
@pytest.mark.parametrize(("cluster", "attr_def", "value"), TYPED_ATTRIBUTE_VALUES)
async def test_attribute_values_stored_typed(
    tmp_path, receive, cluster, attr_def, value
) -> None:
    """Values that went over the wire are stored as their ZCL data type."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [cluster.cluster_id])

    await receive(dev.endpoints[1].in_clusters[cluster.cluster_id], attr_def, value)
    await app.shutdown()

    assert _read_attr_row(db, cluster.cluster_id, attr_def.id) == (
        value.serialize(),
        attr_def.zcl_type,
    )

    app2 = await make_app_with_db(db)
    cluster2 = app2.get_device(dev.ieee).endpoints[1].in_clusters[cluster.cluster_id]
    loaded = cluster2.get_cached_value(attr_def)

    assert loaded == value
    assert type(loaded) is type(value)

    await app2.shutdown()


@pytest.mark.parametrize(("cluster", "attr_def", "value"), TYPED_ATTRIBUTE_VALUES)
async def test_attribute_values_stored_typed_on_device_save(
    tmp_path, cluster, attr_def, value
) -> None:
    """The attribute cache is stored typed when a new device is saved in bulk."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(cluster.cluster_id)

    # The device is not in the database yet, only the device save can store it
    await _read_attribute(ep.in_clusters[cluster.cluster_id], attr_def, value)
    app.device_initialized(dev)
    await app.shutdown()

    assert _read_attr_row(db, cluster.cluster_id, attr_def.id) == (
        value.serialize(),
        attr_def.zcl_type,
    )


@pytest.mark.parametrize(
    "value",
    [
        2150,
        # A quirk-scaled value does not fit the attribute's type
        21.5,
    ],
)
async def test_updated_attribute_values_stored_untyped(tmp_path, value) -> None:
    """Values set by quirks have no wire representation and are stored as-is."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [TemperatureMeasurement.cluster_id])

    attr_def = TemperatureMeasurement.AttributeDefs.measured_value
    dev.endpoints[1].temperature.update_attribute(attr_def, value)
    await app.shutdown()

    assert _read_attr_row(db, TemperatureMeasurement.cluster_id, attr_def.id) == (
        value,
        None,
    )

    app2 = await make_app_with_db(db)
    loaded = (
        app2.get_device(dev.ieee).endpoints[1].temperature.get_cached_value(attr_def)
    )
    assert loaded == value
    assert type(loaded) is type(value)

    await app2.shutdown()


class LocalDataBasicCluster(Basic):
    """Answers reads from its own cache, like zha-quirks' `LocalDataCluster`."""

    _skip_registry = True

    async def read_attributes_raw(self, attributes, manufacturer=None, **kwargs):
        records = [
            foundation.ReadAttributeRecord(
                attr, ZCLStatus.SUCCESS, foundation.TypeValue()
            )
            for attr in attributes
        ]

        for record in records:
            record.value.value = self._attr_cache.get(record.attrid)

        return (records,)


@pytest.mark.parametrize("value", [5, t.uint8_t(5)], ids=["int", "uint8_t"])
async def test_local_data_cluster_reads_stored_untyped(tmp_path, value) -> None:
    """Reads answered by a quirk without a data type are not wire data."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])

    ep = dev.endpoints[1]
    cluster = ep.add_input_cluster(Basic.cluster_id, LocalDataBasicCluster(ep))
    attr_def = Basic.AttributeDefs.app_version
    cluster._update_attribute(attr_def.id, value)

    # The first read caches the converted value, the second one reads that back
    for _ in range(2):
        await cluster.read_attributes([attr_def], allow_cache=False)

    await app.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, attr_def.id) == (5, None)

    app2 = await make_app_with_db(db)
    assert app2.get_device(dev.ieee).endpoints[1].basic.get(attr_def.name) == 5
    await app2.shutdown()


async def test_collection_read_from_wire_stored_typed(tmp_path) -> None:
    """A collection read from a device is cached and stored as a collection."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [MultistateInput.cluster_id])

    cluster = dev.endpoints[1].multistate_input
    attr_def = MultistateInput.AttributeDefs.state_text
    expected = Array(
        type=DataTypeId.string,
        value=t.LVList[t.CharacterString, t.uint16_t](["a", "b"]),
    )

    rsp, rest = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema.deserialize(
        attr_def.id.serialize()
        + ZCLStatus.SUCCESS.serialize()
        + DataTypeId.array.serialize()
        + expected.serialize()
    )
    assert rest == b""

    with patch.object(cluster, "read_attributes_raw", AsyncMock(return_value=rsp)):
        success, failure = await cluster.read_attributes([attr_def])

    assert success == {attr_def: expected}
    assert failure == {}
    assert cluster.get(attr_def.name) == expected

    await app.shutdown()

    assert _read_attr_row(db, MultistateInput.cluster_id, attr_def.id) == (
        expected.serialize(),
        DataTypeId.array,
    )

    app2 = await make_app_with_db(db)
    assert (
        app2.get_device(dev.ieee).endpoints[1].multistate_input.get(attr_def.name)
        == expected
    )
    await app2.shutdown()


@pytest.mark.parametrize(
    ("cluster", "attr_def", "legacy_value", "loaded_value"),
    [
        (OnOff, OnOff.AttributeDefs.start_up_on_off, 2, 2),
        (Basic, Basic.AttributeDefs.model, "Model", "Model"),
        # The old SQLite adapter stored EUI64 values as strings
        (
            IasZone,
            IasZone.AttributeDefs.cie_addr,
            "aa:bb:cc:dd:11:22:33:44",
            t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
        ),
        # A string that is not an address was set by a quirk and is kept
        (IasZone, IasZone.AttributeDefs.cie_addr, "unknown", "unknown"),
        (IasZone, IasZone.AttributeDefs.cie_addr, "", ""),
        (IasZone, IasZone.AttributeDefs.cie_addr, "aa:bb", "aa:bb"),
        (
            TemperatureMeasurement,
            TemperatureMeasurement.AttributeDefs.measured_value,
            21.5,
            21.5,
        ),
    ],
)
async def test_legacy_attribute_values_loaded_untyped(
    tmp_path, cluster, attr_def, legacy_value, loaded_value
) -> None:
    """Untyped rows from older databases load as-is and are not rewritten."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [cluster.cluster_id])
    await app.shutdown()

    with contextlib.closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            f"INSERT INTO attributes_cache{zigpy.appdb.DB_V}"
            " (ieee, endpoint_id, cluster_type, cluster_id, attr_id, manufacturer_code,"
            " status, value, last_updated) VALUES (?, 1, 0, ?, ?, NULL, 0, ?, 0)",
            (str(dev.ieee), cluster.cluster_id, attr_def.id, legacy_value),
        )

    app2 = await make_app_with_db(db)
    cluster2 = app2.get_device(dev.ieee).endpoints[1].in_clusters[cluster.cluster_id]
    loaded = cluster2.get_cached_value(attr_def)

    assert loaded == loaded_value
    assert type(loaded) is type(loaded_value)

    await app2.shutdown()

    assert _read_attr_row(db, cluster.cluster_id, attr_def.id) == (legacy_value, None)


@pytest.mark.parametrize(
    "attr_id",
    [
        # A definition whose type changed, e.g. by a quirk, converts the stored value
        Basic.AttributeDefs.zcl_version.id,
        # An attribute without a definition is decoded with its stored type
        0x7777,
    ],
)
async def test_typed_attribute_value_type_mismatch(tmp_path, attr_id) -> None:
    """Typed rows that do not match the current attribute definition still load."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    _insert_typed_attr_row(
        db, dev.ieee, Basic.cluster_id, attr_id, DataTypeId.uint16, b"\x05\x00"
    )

    app2 = await make_app_with_db(db)
    basic2 = app2.get_device(dev.ieee).endpoints[1].basic

    # Attributes without a definition are only reachable through the legacy cache
    assert basic2._attr_cache.get(attr_id) == 5

    await app2.shutdown()


@pytest.mark.parametrize(
    ("attr_id", "data_type", "data"),
    [
        # Out of range for `uint8`
        (Basic.AttributeDefs.zcl_version.id, DataTypeId.uint16, b"\x2c\x01"),
        (Basic.AttributeDefs.zcl_version.id, DataTypeId.string, b"\x03abc"),
        # Too long for `uint8`
        (Basic.AttributeDefs.zcl_version.id, DataTypeId.data16, b"\x01\x02"),
        # Not a member of `t.Bool` or of an enum
        (Basic.AttributeDefs.device_enabled.id, DataTypeId.string, b"\x03abc"),
        (Basic.AttributeDefs.power_source.id, DataTypeId.string, b"\x03abc"),
        # Written for a definition without a ZCL data type
        (Basic.AttributeDefs.zcl_version.id, DataTypeId.unk, b"\x01\x02"),
        (0x7777, DataTypeId.unk, b"\x01\x02"),
    ],
)
async def test_typed_attribute_value_cannot_be_loaded(
    tmp_path, attr_id, data_type, data
) -> None:
    """A stored value that cannot be loaded is deleted, the rest still load."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    dev.endpoints[1].basic.update_attribute(Basic.AttributeDefs.model, "Model")
    await app.shutdown()

    _insert_typed_attr_row(db, dev.ieee, Basic.cluster_id, attr_id, data_type, data)

    app2 = await make_app_with_db(db)
    basic2 = app2.get_device(dev.ieee).endpoints[1].basic

    # Attributes without a definition are only reachable through the legacy cache
    assert basic2._attr_cache.get(attr_id) is None
    assert basic2.get(Basic.AttributeDefs.model.name) == "Model"
    await app2.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, attr_id) is None


async def test_typed_attribute_value_fits_quirk_definition(tmp_path) -> None:
    """A stored value that only fits a quirk's definition is loaded and kept."""

    class WideBasicCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            zcl_version = ZCLAttributeDef(id=0x0000, type=t.uint16_t)

    def replace_basic(device):
        ep = device.endpoints[1]
        ep.add_input_cluster(Basic.cluster_id, WideBasicCluster(ep))
        return device

    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    attr_id = Basic.AttributeDefs.zcl_version.id
    _insert_typed_attr_row(
        db, dev.ieee, Basic.cluster_id, attr_id, DataTypeId.uint16, b"\x2c\x01"
    )

    # The bare cluster cannot convert the value but the quirk's cluster can
    app2 = await make_app_with_db(db, device_resolver=replace_basic)
    assert app2.get_device(dev.ieee).endpoints[1].basic.get("zcl_version") == 300
    await app2.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, attr_id) == (
        b"\x2c\x01",
        DataTypeId.uint16,
    )


@pytest.mark.parametrize(
    ("receive", "row"),
    [
        (
            lambda basic: mock_attribute_report(basic, {0x7777: t.uint16_t(5)}),
            (b"\x05\x00", DataTypeId.uint16),
        ),
        (lambda basic: _update_attribute(basic, 0x7777, 5), (5, None)),
    ],
)
async def test_unknown_attribute_stored(tmp_path, receive, row) -> None:
    """An unknown attribute is stored with its wire type, if it has one."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])

    await receive(dev.endpoints[1].basic)
    await app.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, 0x7777) == row

    app2 = await make_app_with_db(db)
    basic2 = app2.get_device(dev.ieee).endpoints[1].basic
    assert basic2._attr_cache.get(0x7777) == 5

    await app2.shutdown()


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


GP_SOURCE_ID = SrcID(0x0040F4E4)


@pytest.mark.parametrize(
    "attrs",
    [
        {},
        {
            "device_id": DeviceID.GenericSwitch,
            "gpd_manufacturer_id": t.uint16_t(0x1021),
            "gpd_model_id": t.uint16_t(0x0002),
            "commands": [GPDCommandID.Press1of1, GPDCommandID.Release1of1],
            "server_cluster_ids": [t.uint16_t(0x0006)],
            "client_cluster_ids": [t.uint16_t(0x0008), t.uint16_t(0x0300)],
            "switch_configuration": GPGenericSwitchConfiguration(
                num_contacts=2, switch_type=SwitchType.Button, _reserved=0
            ),
            "mac_seq_num_capability": True,
            "rx_on_capability": True,
            "fixed_location": True,
            "security_key": t.KeyData(range(16)),
            "security_key_type": SecurityKeyType.IndividualKey,
            "security_level": SecurityLevel.FullFrameCounterAndMIC,
            "frame_counter": t.uint32_t(99),
            "extra_commissioning_payload": b"qerh7pox@GP0001\xcb",
            "last_seen": datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC),
        },
    ],
)
async def test_gp_device_round_trip(tmp_path, attrs):
    """A commissioned GPD is restored with all fields intact."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=GP_SOURCE_ID
    )

    for name, value in attrs.items():
        setattr(device, name, value)

    app.device_initialized(device)
    await app.shutdown()

    app2 = await make_app_with_db(db)
    restored = app2.devices[device.ieee]

    assert isinstance(restored, GreenPowerDevice)
    assert restored.nwk == device.nwk
    assert restored.last_seen == device.last_seen
    assert restored.get_signature() == device.get_signature()

    for name in (
        "rx_on_capability",
        "fixed_location",
        "security_key",
        "security_key_type",
        "security_level",
        "frame_counter",
        "extra_commissioning_payload",
    ):
        assert getattr(restored, name) == getattr(device, name)

    await app2.shutdown()


@pytest.mark.parametrize(
    ("cluster", "is_server", "attr_def", "value"),
    [
        (
            Metering,
            True,
            Metering.AttributeDefs.current_summ_delivered,
            t.uint48_t(1234),
        ),
        (
            ElectricalMeasurement,
            True,
            ElectricalMeasurement.AttributeDefs.rms_voltage,
            t.uint16_t(230),
        ),
        (OnOff, False, OnOff.AttributeDefs.on_off, t.Bool.true),
    ],
)
async def test_gp_device_attribute_round_trip(
    tmp_path, cluster, is_server, attr_def, value
):
    """Attributes of a GPD's clusters are restored, under no endpoint."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=GP_SOURCE_ID
    )

    if is_server:
        device.server_cluster_ids = [cluster.cluster_id]
    else:
        device.client_cluster_ids = [cluster.cluster_id]

    device.add_clusters()
    app.device_initialized(device)

    clusters = (
        device.endpoints[None].in_clusters
        if is_server
        else device.endpoints[None].out_clusters
    )
    # A GPD has no ZCL sequence number and cannot receive a Default Response
    await mock_attribute_report(
        clusters[cluster.cluster_id],
        {attr_def: value},
        tsn=0,
        disable_default_response=True,
    )
    await app.shutdown()

    with contextlib.closing(sqlite3.connect(db)) as conn:
        assert conn.execute(
            f"SELECT endpoint_id, value, data_type FROM attributes_cache{zigpy.appdb.DB_V}"
        ).fetchall() == [(None, value.serialize(), attr_def.zcl_type)]

    app2 = await make_app_with_db(db)
    endpoint = app2.devices[device.ieee].endpoints[None]
    clusters2 = endpoint.in_clusters if is_server else endpoint.out_clusters

    assert clusters2[cluster.cluster_id].get_cached_value(attr_def) == value

    await app2.shutdown()


GP_VOLTAGE = foundation.Attribute(
    attrid=ElectricalMeasurement.AttributeDefs.rms_voltage.id,
    value=foundation.TypeValue(type=DataTypeId.uint16, value=t.uint16_t(230)),
)


@pytest.mark.parametrize(
    ("command_id", "command"),
    [
        (
            GPDCommandID.ManufacturerSpecificReporting,
            GPManufacturerSpecificAttributeReportingPayload(
                manufacturer_code=0x105E,
                cluster_id=ElectricalMeasurement.cluster_id,
                attributes=[GP_VOLTAGE],
            ),
        ),
        (
            GPDCommandID.ManufacturerSpecificMultiClusterReporting,
            GPManufacturerSpecificMultiClusterReportingPayload(
                manufacturer_code=0x105E,
                reports=[
                    GPClusterReport(
                        cluster_id=ElectricalMeasurement.cluster_id,
                        attribute=GP_VOLTAGE,
                    )
                ],
            ),
        ),
    ],
)
async def test_gp_attribute_report_persists(tmp_path, command_id, command):
    """A GPD attribute report is cached on its cluster and restored on restart."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=GP_SOURCE_ID
    )
    device.server_cluster_ids = [ElectricalMeasurement.cluster_id]
    device.add_clusters()
    app.device_initialized(device)

    app.gp_packet_received(
        t.ZigbeeGpPacket(
            application_id=ApplicationID.SrcID,
            src_id=GP_SOURCE_ID,
            command_id=command_id,
            payload=t.SerializableBytes(command.serialize()),
            frame_counter=t.uint32_t(1),
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
        )
    )
    await app.shutdown()

    app2 = await make_app_with_db(db)
    cluster = (
        app2.devices[device.ieee]
        .endpoints[None]
        .in_clusters[ElectricalMeasurement.cluster_id]
    )

    assert (
        cluster.get_cached_value(ElectricalMeasurement.AttributeDefs.rms_voltage) == 230
    )

    await app2.shutdown()


async def test_gp_frame_counter_persists_per_press(tmp_path):
    """Every accepted GPDF persists the advanced frame counter.

    Without it, the stored counter is frozen at the join-time value and the
    replay-protection baseline reverts to stale on every restart.
    """
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=GP_SOURCE_ID
    )
    device.security_level = SecurityLevel.NoSecurity
    device.security_key_type = SecurityKeyType.NoKey
    device.frame_counter = t.uint32_t(99)
    app.device_initialized(device)

    app.gp_packet_received(
        t.ZigbeeGpPacket(
            application_id=ApplicationID.SrcID,
            src_id=GP_SOURCE_ID,
            command_id=GPDCommandID.Toggle,
            frame_counter=t.uint32_t(150),
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
        )
    )
    await app.shutdown()

    app2 = await make_app_with_db(db)
    assert app2.devices[device.ieee].frame_counter == 150  # not the stale 99
    await app2.shutdown()


async def test_gp_device_remove(tmp_path):
    """A removed GPD is absent after reopen."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=GP_SOURCE_ID
    )
    device.security_level = SecurityLevel.NoSecurity
    device.security_key_type = SecurityKeyType.NoKey
    app.device_initialized(device)
    await app.remove(device.ieee)
    await app.shutdown()

    app2 = await make_app_with_db(db)
    assert device.ieee not in app2.devices
    await app2.shutdown()


async def commission_with_key(app, key: bytes, frame_counter: int) -> None:
    await app.green_power.permit_join(time_s=60)
    await commission(
        app,
        GP_SOURCE_ID,
        commissioning_payload(
            security_level=SecurityLevel.Encrypted,
            key_type=SecurityKeyType.IndividualKey,
            key=key,
            outgoing_counter=10,
        ),
        frame_counter=frame_counter,
    )


async def test_gp_device_recommission_updates_security_key(tmp_path):
    """A GPD re-commissioned with another key after a restart is saved with it."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    await commission_with_key(app, KEY, frame_counter=1)
    await app.shutdown()

    app2 = await make_app_with_db(db)
    await commission_with_key(app2, bytes(range(16, 32)), frame_counter=2)
    await app2.shutdown()

    app3 = await make_app_with_db(db)
    restored = app3.devices[synthetic_ieee(GP_SOURCE_ID)]
    assert restored.security_key == t.KeyData(range(16, 32))
    await app3.shutdown()


async def test_gp_commissioned_device_restored(tmp_path):
    """A GPD commissioned by the sink keeps its security state and group on restart."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    await commission_with_key(app, KEY, frame_counter=1)
    device = app.devices[synthetic_ieee(GP_SOURCE_ID)]

    # A press advances the security frame counter
    app.gp_packet_received(
        encrypted_gp_packet(GP_SOURCE_ID, 11, bytes([GPDCommandID.Toggle]))
    )
    assert device.frame_counter == 11
    await app.shutdown()

    app2 = await make_app_with_db(db)
    app2.subscribe_to_multicast_group = AsyncMock(
        wraps=app2.subscribe_to_multicast_group
    )
    await app2.green_power.startup()

    restored = app2.devices[device.ieee]
    assert isinstance(restored, GreenPowerDevice)
    assert restored.get_signature() == device.get_signature()
    assert restored.security_key == t.KeyData(KEY)
    assert restored.security_key_type == SecurityKeyType.IndividualKey
    assert restored.security_level == SecurityLevel.Encrypted
    assert restored.frame_counter == 11

    # The sink joins the GP group again to receive the GPD's notifications
    assert app2.subscribe_to_multicast_group.mock_calls == [
        call(GP_GROUP_ID, endpoint_id=GP_ENDPOINT)
    ]

    await app2.shutdown()


def _add_joined_device(app):
    """Join and initialize a device with a single input cluster on endpoint 1."""
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)
    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    clus = ep.add_input_cluster(0)
    app.device_initialized(dev)

    return dev, ep, clus


async def _read_attr_value(db, attr_id=0):
    """Open a separate connection and read the current committed value."""
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(
            f"SELECT value FROM attributes_cache{zigpy.appdb.DB_V} WHERE attr_id = ?",
            (attr_id,),
        )
        row = await cursor.fetchone()
        return None if row is None else row[0]


async def _read_count(db, table, where="", params=()):
    """Open a separate connection and count committed rows in `table`."""
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM {table}{zigpy.appdb.DB_V} {where}", params
        )
        row = await cursor.fetchone()
        return row[0]


async def _wait_until(predicate, message, timeout=5.0):
    """Poll `predicate` until it is truthy, or fail with `message`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        if await predicate():
            return
        if loop.time() >= deadline:
            raise AssertionError(f"{message} (within {timeout}s)")
        await asyncio.sleep(0.01)


async def _wait_for_count(db, table, expected, where="", params=(), message=None):
    """Poll a separate connection until `table` holds `expected` committed rows."""

    async def _matches():
        return await _read_count(db, table, where, params) == expected

    await _wait_until(
        _matches, message or f"{table} did not reach {expected} committed row(s)"
    )


async def _wait_for_attr_value(db, expected, attr_id=0, message=None):
    """Poll a separate connection until attribute `attr_id` is committed."""

    async def _matches():
        return await _read_attr_value(db, attr_id) == expected

    await _wait_until(
        _matches, message or f"attribute {attr_id} did not reach {expected!r}"
    )


async def _write_uncommitted(listener, group_id=1):
    """Write a row without committing it, leaving a transaction open."""
    await listener.execute(
        f"INSERT INTO groups{zigpy.appdb.DB_V} VALUES (?, ?)", (group_id, "test")
    )
    assert listener._db.in_transaction


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_database_commit_interval(tmp_path):
    """Test that configured database_commit_interval defers writes."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=0.5)
    listener = app._dblistener

    _, _, clus = _add_joined_device(app)

    # Update an attribute. This schedules a commit on the worker queue.
    clus.update_attribute(0, 42)

    # Wait for the worker to actually run `_save_attribute`, which is what arms
    # the delayed-commit timer. A bare `sleep(0)` is not enough: the handler's
    # SQL runs on aiosqlite's connection thread, which the loop cannot wait for,
    # so the assertions below would pass vacuously against an empty table.
    await listener._callback_handlers.join()
    assert listener._db.in_transaction
    assert listener._commit_task is not None

    # The timer has not fired, so a separate reader must not see the update.
    assert await _read_attr_value(db) is None

    # Poll rather than budget for the deferred flush.
    await _wait_for_attr_value(db, 42, message="deferred commit did not land")

    await app.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_database_commit_interval_shutdown_forces_commit(tmp_path):
    """Test that shutting down the application forces pending commits immediately."""
    db = tmp_path / "test.db"
    # Set a very long commit interval so it does not auto-commit during the test
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    _, _, clus = _add_joined_device(app)
    clus.update_attribute(0, 99)

    # Wait for `_save_attribute` to run and arm the 10s timer.
    await listener._callback_handlers.join()
    assert listener._db.in_transaction

    # Verify it has not yet committed
    assert await _read_attr_value(db) is None

    # Shutdown should force-commit
    await app.shutdown()

    # Verify it is now committed
    assert await _read_attr_value(db) == 99


async def test_commit_does_not_land_mid_handler(tmp_path):
    """A deferred commit must never persist a partial handler."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=0.05)
    listener = app._dblistener

    # Wrap `_db.commit` to count calls: the invariant under test is *when* `commit()`
    # is called
    commit_calls = []
    original_commit = listener._db.commit

    async def _spy_commit():
        commit_calls.append(asyncio.get_running_loop().time())
        await original_commit()

    listener._db.commit = _spy_commit

    handler_first_statement_done = asyncio.Event()
    handler_may_finish = asyncio.Event()
    handler_finished = asyncio.Event()

    async def _synthetic_two_statement_handler():
        # First statement, then arm the deferred commit. The 0.05s timer will fire
        # while we wait below.
        await _write_uncommitted(listener)
        await listener._commit()
        handler_first_statement_done.set()

        # Block until the test releases us, well past the commit interval. The timer
        # fires during this wait and enqueues `_flush_commit`, which cannot run
        # because we're still holding the worker. Waiting on an event rather than
        # sleeping keeps the assertions below independent of wall-clock scheduling.
        await handler_may_finish.wait()
        handler_finished.set()

    listener._synthetic_two_statement_handler = _synthetic_two_statement_handler
    listener.enqueue("_synthetic_two_statement_handler")

    # Wait for the handler to reach its first statement and arm the timer.
    await asyncio.wait_for(handler_first_statement_done.wait(), timeout=5.0)

    # Wait long enough that the 0.05s timer has fired (it enqueues `_flush_commit`,
    # which is still queued behind the handler).
    await asyncio.sleep(0.10)
    assert not handler_finished.is_set(), (
        "handler should still be blocked — worker is busy running it"
    )
    assert len(commit_calls) == 0, (
        f"deferred commit must not land mid-handler — found {len(commit_calls)} "
        "commit calls before the handler returned"
    )

    # Release the handler, then wait for the enqueued `_flush_commit` to run on the
    # worker. `join()` waits until the worker has drained the queue, so
    # `_flush_commit` has run and committed.
    handler_may_finish.set()
    await asyncio.wait_for(handler_finished.wait(), timeout=5.0)
    await listener._callback_handlers.join()

    assert len(commit_calls) == 1, (
        f"expected exactly one commit from `_flush_commit` after the handler "
        f"returned, got {len(commit_calls)}"
    )

    # Clean up the synthetic handler so it doesn't leak.
    del listener._synthetic_two_statement_handler

    await app.shutdown()


async def test_write_after_flush_is_committed(tmp_path):
    """A write after a completed flush must re-arm the timer and be committed."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=0.05)
    listener = app._dblistener

    # First write: arm the timer.
    _, _, clus = _add_joined_device(app)
    clus.update_attribute(0, 1)

    # Wait for the first flush to land by polling for the value.
    await listener._callback_handlers.join()
    await _wait_for_attr_value(db, 1, message="first flush did not land")

    # Second write after the first flush — arms a new timer.
    clus.update_attribute(0, 2)

    # Wait for the worker to run `_save_attribute` and arm the timer.
    await listener._callback_handlers.join()

    # The second write must not be committed yet. Assert on the listener's own
    # state rather than on the DB: reading over a fresh connection can take
    # longer than the 0.05s interval on a loaded runner, which would make a DB
    # assertion here a race against the timer rather than a real check.
    assert listener._db.in_transaction
    assert listener._commit_task is not None

    # Wait for the second flush by polling for the value.
    await _wait_for_attr_value(db, 2, message="second flush did not land")

    await app.shutdown()


async def test_force_commit_commits_pending_writes(tmp_path):
    """`_commit(force=True)` commits immediately, including deferred writes."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    _, _, clus = _add_joined_device(app)

    # `handle_join` and `device_initialized` each enqueue their own handlers, so
    # wait for the worker to drain all of them before issuing the attribute write
    await listener._callback_handlers.join()

    clus.update_attribute(0, 7)
    await listener._callback_handlers.join()
    assert listener._db.in_transaction
    assert await _read_attr_value(db) is None

    # A force commit (e.g. from a network backup) commits the deferred write too
    await listener._commit(force=True)
    assert not listener._db.in_transaction
    assert await _read_attr_value(db) == 7

    # The timer is not cancelled, and finds nothing left to flush
    assert listener._commit_task is not None
    assert not listener._commit_task.done()
    await listener._flush_commit()
    assert not listener._db.in_transaction

    await app.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_reinterview_does_not_commit_mid_handler(tmp_path):
    """A re-interview's delete of the old device does not commit a handler halfway."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    old_dev, _, _ = _add_joined_device(app)
    async with asyncio.timeout(5):
        await listener._callback_handlers.join()
    ep_where = "WHERE ieee = ? AND endpoint_id = ?"
    old_ep_row = {"where": ep_where, "params": (str(old_dev.ieee), 1)}
    new_ep_row = {"where": ep_where, "params": (str(old_dev.ieee), 2)}
    assert await _read_count(db, "endpoints", **old_ep_row) == 1

    # Hold the worker inside a handler, after the first of its writes
    other_ieee = t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11")
    other_row = {"where": "WHERE ieee = ?", "params": (str(other_ieee),)}
    handler_started = asyncio.Event()
    handler_may_finish = asyncio.Event()

    async def _two_statement_handler():
        await listener.execute(
            f"INSERT INTO devices{zigpy.appdb.DB_V} (ieee) VALUES (?)",
            (other_ieee,),
        )
        handler_started.set()
        await handler_may_finish.wait()

    listener._two_statement_handler = _two_statement_handler
    listener.enqueue("_two_statement_handler")
    async with asyncio.timeout(5):
        await handler_started.wait()

    # Re-interview the device into a different signature while the handler is held
    shadow = Device(app, old_dev.ieee, old_dev.nwk)
    shadow.node_desc = make_node_desc()
    shadow.status = Status.ENDPOINTS_INIT
    ep = shadow.add_endpoint(2)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(Basic.cluster_id)

    app.devices[old_dev.ieee] = shadow

    async with asyncio.timeout(5):
        await app._device_reinterviewed(old_dev, shadow)

    # Nothing is committed in the middle of the handler: neither its first write
    # nor the delete of the old device
    assert await _read_count(db, "devices", **other_row) == 0
    assert await _read_count(db, "endpoints", **old_ep_row) == 1
    assert await _read_count(db, "endpoints", **new_ep_row) == 0

    # Once the handler finishes, the delete is committed along with the new device
    handler_may_finish.set()
    async with asyncio.timeout(5):
        await listener._callback_handlers.join()

    assert await _read_count(db, "devices", **other_row) == 1
    assert await _read_count(db, "endpoints", **old_ep_row) == 0
    assert await _read_count(db, "endpoints", **new_ep_row) == 1

    del listener._two_statement_handler
    await app.shutdown()

    # The re-interviewed device replaced the old one
    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(old_dev.ieee)
    assert list(dev2.non_zdo_endpoints) == [dev2.endpoints[2]]
    assert Basic.cluster_id in dev2.endpoints[2].in_clusters
    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_ota_query_cache_delete_is_deferred_like_save(tmp_path):
    """`_delete_ota_query_cache_entry` should defer its commit, matching
    `_save_ota_query_cache_entry` — the OTA query cache is a low-value cache
    (rebuilt on the next query), so neither operation needs force=True.
    """
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    # Set up a real device so the FK constraints are satisfied.
    dev, _, _ = _add_joined_device(app)
    ieee = dev.ieee

    # Wait for the device row to appear (the worker has finished processing
    # `_raw_device_initialized`, which force-commits).
    await _wait_for_count(
        db,
        "devices",
        1,
        where="WHERE ieee = ?",
        params=(str(ieee),),
        message="device row did not appear in DB",
    )

    # Insert an OTA query cache row directly.
    await listener.execute(
        f"INSERT INTO ota_query_cache{zigpy.appdb.DB_V} "
        f"(ieee, endpoint_id, manufacturer_code, image_type, "
        f" current_file_version, hardware_version, last_updated) "
        f"VALUES (?, 1, 0, 0, 1, NULL, 0)",
        (str(ieee),),
    )
    await listener._commit(force=True)

    # Confirm the row exists.
    assert await _read_count(db, "ota_query_cache") == 1

    # Enqueue the delete via the event listener (the real path).
    event = OtaQueryCacheClearedEvent(
        device_ieee=ieee,
        endpoint_id=1,
    )
    listener.on_ota_query_cache_cleared(event)
    # Wait for the worker to run the delete handler. `join()` is exact (it
    # blocks until the queue is empty), unlike `sleep(0)` which only yields
    # the event loop and cannot wait on aiosqlite's connection thread.
    await listener._callback_handlers.join()

    # The delete was issued but the commit is deferred — a separate reader
    # should still see the row until the timer fires (10s, well past the test).
    assert await _read_count(db, "ota_query_cache") == 1, (
        "delete should be deferred, not committed yet"
    )

    # Force-flush so the test's shutdown doesn't get confused.
    await listener._commit(force=True)
    assert await _read_count(db, "ota_query_cache") == 0

    await app.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_pairing_and_removal_are_forced(tmp_path):
    """Pairing and removal are rare, user-visible events — they must use
    `force=True` so a crash within `database_commit_interval` doesn't
    silently drop a freshly-paired device or resurrect a removed one.

    We verify this by setting a very long commit interval (10s) and checking
    that the device row appears in the DB immediately after `device_initialized`
    (proving force-commit) and disappears immediately after `device_removed`
    (proving force-commit on removal).
    """
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)

    # `_add_joined_device` triggers device initialization (pairing).
    dev, _, _ = _add_joined_device(app)
    device_row = {"where": "WHERE ieee = ?", "params": (str(dev.ieee),)}

    # Poll the DB — the device row must appear *immediately*, not after 10s.
    # If `_raw_device_initialized_internal` deferred the commit, this would
    # time out.
    await _wait_for_count(
        db,
        "devices",
        1,
        **device_row,
        message=(
            "paired device must be committed immediately (force=True) — "
            "did not appear in DB"
        ),
    )

    # Now remove the device. The row must disappear *immediately*.
    # We call the listener's `device_removed` directly to avoid the network
    # side effects of `app.remove()`.
    app._dblistener.device_removed(dev)
    await _wait_for_count(
        db,
        "devices",
        0,
        **device_row,
        message=(
            "removed device must be committed immediately (force=True) — "
            "row still in DB"
        ),
    )

    await app.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_group_operations_are_forced(tmp_path):
    """Group add/remove and group membership add/remove are rare, user-visible
    events — they must use `force=True` so a crash within
    `database_commit_interval` doesn't silently drop a freshly-created group,
    resurrect a removed one, or lose a membership change.

    We verify this by setting a very long commit interval (10s) and checking
    that each operation is visible in the DB immediately after the event is
    enqueued.
    """
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    # Set up a real device so group member FK constraints are satisfied.
    dev, ep, _ = _add_joined_device(app)
    member_row = {
        "where": "WHERE group_id = 42 AND ieee = ?",
        "params": (str(dev.ieee),),
    }
    group_row = {"where": "WHERE group_id = 42"}

    # Wait for the device row to be committed.
    await _wait_for_count(
        db,
        "devices",
        1,
        where="WHERE ieee = ?",
        params=(str(dev.ieee),),
        message="device row did not appear in DB",
    )

    # Add a group — must be visible immediately (force-commit).
    group = zigpy.group.Group(42, name="test-group")
    listener.group_added(group)
    await _wait_for_count(
        db,
        "groups",
        1,
        **group_row,
        message=(
            "added group must be committed immediately (force=True) — "
            "did not appear in DB"
        ),
    )

    # Add a group member — must be visible immediately.
    listener.group_member_added(group, ep)
    await _wait_for_count(
        db,
        "group_members",
        1,
        **member_row,
        message=(
            "added group member must be committed immediately (force=True) — "
            "did not appear in DB"
        ),
    )

    # Remove the group member — must disappear immediately.
    listener.group_member_removed(group, ep)
    await _wait_for_count(
        db,
        "group_members",
        0,
        **member_row,
        message=(
            "removed group member must be committed immediately (force=True) — "
            "row still in DB"
        ),
    )

    # Remove the group — must disappear immediately.
    listener.group_removed(group)
    await _wait_for_count(
        db,
        "groups",
        0,
        **group_row,
        message=(
            "removed group must be committed immediately (force=True) — row still in DB"
        ),
    )

    await app.shutdown()


async def test_flush_commit_noop_when_nothing_pending(tmp_path):
    """`_flush_commit` should be a no-op when there are no pending commits."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    # With nothing pending, `_flush_commit` should return without committing
    assert not listener._db.in_transaction
    listener._db.commit = AsyncMock(wraps=listener._db.commit)
    await listener._flush_commit()
    listener._db.commit.assert_not_awaited()

    await app.shutdown()


async def test_flush_commit_rearms_timer_on_failure(tmp_path):
    """A failed flush must re-arm the timer instead of stranding the writes."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    await _write_uncommitted(listener)
    commit = listener._db.commit
    listener._db.commit = AsyncMock(side_effect=RuntimeError("boom"))

    await listener._flush_commit()

    # The writes are still pending and a new timer is armed to retry them,
    # rather than waiting for the next write or for shutdown.
    assert listener._db.in_transaction
    assert listener._commit_task is not None
    assert not listener._commit_task.done()

    listener._db.commit = commit
    await app.shutdown()
    assert await _read_count(db, "groups") == 1


async def test_force_commit_rearms_timer_on_failure(tmp_path):
    """A failed forced commit must arm the timer to retry the commit."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    await _write_uncommitted(listener)
    assert listener._commit_task is None
    commit = listener._db.commit
    listener._db.commit = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await listener._commit(force=True)

    # The pending writes get a timer instead of waiting for the next write or for
    # shutdown
    assert listener._db.in_transaction
    assert listener._commit_task is not None
    assert not listener._commit_task.done()

    listener._db.commit = commit
    await app.shutdown()
    assert await _read_count(db, "groups") == 1


async def test_failed_commit_without_interval_does_not_arm_timer(tmp_path):
    """With deferral disabled, a failed commit just propagates, as before."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=0)
    listener = app._dblistener

    listener._db.commit = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await listener._commit()

    assert listener._commit_task is None

    listener._db.commit = AsyncMock()
    await app.shutdown()


async def test_shutdown_survives_failed_commit(tmp_path, caplog):
    """A commit failure during shutdown must be logged, not propagated."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    await _write_uncommitted(listener)
    listener._db.commit = AsyncMock(side_effect=RuntimeError("boom"))

    # `app.shutdown()` swallows listener errors, so call the listener directly
    await listener.shutdown()

    assert "Failed to commit pending changes during shutdown" in caplog.text
    assert not listener._db._thread.is_alive()
    assert await _read_count(db, "groups") == 0


async def test_shutdown_closes_database_on_failure(tmp_path):
    """The connection must be closed even if shutdown fails after the commit."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    listener._set_isolation_level = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await listener.shutdown()

    assert not listener._db._thread.is_alive()


async def test_shutdown_joins_thread_when_close_fails(tmp_path):
    """The worker thread must be joined even if closing the connection fails."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    conn = app._dblistener._db

    # Fail aiosqlite's own close step, which still stops the worker thread. The
    # connection is closed first so that it isn't leaked.
    original_execute = conn._execute

    async def failing_execute(fn, *args, **kwargs):
        result = await original_execute(fn, *args, **kwargs)

        if fn == conn._connection.close:
            raise sqlite3.OperationalError("boom")

        return result

    conn._execute = failing_execute
    conn._thread.join = MagicMock(wraps=conn._thread.join)

    with pytest.raises(sqlite3.OperationalError):
        await app._dblistener.shutdown()

    conn._thread.join.assert_called_once_with()
    assert not conn._thread.is_alive()


async def test_shutdown_rolls_back_persistently_failing_commit(tmp_path, caplog):
    """A commit that keeps failing must not prevent the connection from closing."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db, commit_interval=10.0)
    listener = app._dblistener

    # With foreign key checks deferred, a dangling endpoint fails only at `COMMIT`,
    # and keeps failing on every retry
    await listener.execute("PRAGMA defer_foreign_keys = ON")
    await listener.execute(
        f"INSERT INTO endpoints{zigpy.appdb.DB_V} VALUES (?, ?, ?, ?, ?)",
        (t.EUI64.convert("00:11:22:33:44:55:66:77"), 1, 260, 0, 0),
    )

    await listener.shutdown()

    assert "Failed to commit pending changes during shutdown" in caplog.text
    assert not listener._db._thread.is_alive()
    assert await _read_count(db, "endpoints") == 0


async def test_load_with_green_power_device(tmp_path):
    """A GPD in `app.devices` has no endpoints whose attribute cache needs clearing."""
    db = tmp_path / "test.db"
    app = make_app({conf.CONF_DATABASE: str(db)})
    gpd = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    app.devices[gpd.ieee] = gpd

    await app._load_db()

    assert app.devices[gpd.ieee] is gpd

    await app.shutdown()


STORE_COUNT = StoredValue(namespace="quirk:test", key="count", type=int)


def _count_store_rows(db, ieee=None) -> int:
    with sqlite3.connect(db) as conn:
        if ieee is None:
            cur = conn.execute(f"SELECT COUNT(*) FROM device_store{zigpy.appdb.DB_V}")
        else:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM device_store{zigpy.appdb.DB_V} WHERE ieee = ?",
                (str(ieee),),
            )
        return cur.fetchone()[0]


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_round_trip(tmp_path):
    """Store values set before and after initialization survive a reload."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)

    dev = app.get_device(ieee)
    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(0)

    # Set before the device is initialized, persisted by the full save
    dev.store.namespace("tuya").set("1", {"a": [1, 2.5, None, "x"]}, version=3)
    app.device_initialized(dev)

    # Set after, persisted by the event
    dev.store[STORE_COUNT] = 42
    tuya_item = dev.store.namespace("tuya").item("1")
    await app.shutdown()

    app2 = await make_app_with_db(db)
    dev2 = app2.get_device(ieee)

    assert dev2.store[STORE_COUNT] == 42
    assert dev2.store.last_updated(STORE_COUNT).timestamp() == pytest.approx(
        dev.store.last_updated(STORE_COUNT).timestamp()
    )

    item = dev2.store.namespace("tuya").item("1")
    assert item.value == {"a": [1, 2.5, None, "x"]}
    assert item.version == 3
    assert item.last_updated.timestamp() == pytest.approx(
        tuya_item.last_updated.timestamp()
    )

    # Update and delete persist as well
    dev2.store[STORE_COUNT] = 43
    del dev2.store.namespace("tuya")["1"]
    await app2.shutdown()

    app3 = await make_app_with_db(db)
    dev3 = app3.get_device(ieee)

    assert dev3.store[STORE_COUNT] == 43
    assert "1" not in dev3.store.namespace("tuya")
    assert _count_store_rows(db) == 1

    await app3.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_removed_with_device(tmp_path):
    """Removing a device drops its store rows and in-memory store."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev, _, _ = _add_joined_device(app)
    dev.store[STORE_COUNT] = 1
    await app._dblistener._callback_handlers.join()

    assert _count_store_rows(db, dev.ieee) == 1

    app._dblistener.device_removed(dev)
    await app._dblistener._callback_handlers.join()

    assert _count_store_rows(db, dev.ieee) == 0

    await app.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_visible_to_resolver(tmp_path):
    """Quirks resolving a device at load time can read its store."""
    seen = []

    def resolver(device):
        seen.append(device.store.get(STORE_COUNT))
        return device

    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    dev, _, _ = _add_joined_device(app)
    dev.store[STORE_COUNT] = 7
    await app.shutdown()

    app2 = await make_app_with_db(db, device_resolver=resolver)

    assert seen == [7]

    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_set_before_device_saved(tmp_path, caplog):
    """A value set before the device row exists is skipped quietly, then saved."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ieee = make_ieee()
    app.handle_join(99, ieee, 0)
    dev = app.get_device(ieee)

    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger="zigpy.appdb"):
        dev.store[STORE_COUNT] = 5
        await app._dblistener._callback_handlers.join()

    # SQL errors from the worker are only logged at debug level
    assert not [r for r in caplog.records if r.name == "zigpy.appdb" and r.exc_info]
    assert _count_store_rows(db, ieee) == 0

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(0)
    app.device_initialized(dev)
    await app.shutdown()

    assert _count_store_rows(db, ieee) == 1

    app2 = await make_app_with_db(db)
    assert app2.get_device(ieee).store[STORE_COUNT] == 5
    await app2.shutdown()


async def test_device_store_survives_reinterview(tmp_path) -> None:
    """A re-interview deletes the old device row, but its store is written back."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    nwk = t.NWK(0x1234)
    dev = app.add_device(nwk=nwk, ieee=ieee)
    dev.node_desc = make_node_desc()
    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = 260
    ep1.device_type = profiles.zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)
    app.device_initialized(dev)
    dev.store[STORE_COUNT] = 3
    await app.shutdown()

    app2 = await make_app_with_db(db)
    old_dev = app2.get_device(ieee)
    assert old_dev.store[STORE_COUNT] == 3

    shadow = Device(app2, ieee, nwk)
    shadow.node_desc = make_node_desc()
    shadow.status = Status.ENDPOINTS_INIT
    ep2 = shadow.add_endpoint(2)
    ep2.status = zigpy.endpoint.Status.ZDO_INIT
    ep2.profile_id = 260
    ep2.device_type = profiles.zha.DeviceType.PUMP
    ep2.add_input_cluster(Basic.cluster_id)

    app2.devices[ieee] = shadow

    await app2._device_reinterviewed(old_dev, shadow)
    new_dev = app2.get_device(ieee)
    assert new_dev is not old_dev
    assert new_dev.store is old_dev.store
    await app2.shutdown()

    assert _count_store_rows(db, ieee) == 1

    app3 = await make_app_with_db(db)
    assert app3.get_device(ieee).store[STORE_COUNT] == 3
    await app3.shutdown()


def _add_reinterview_device(app, ieee, nwk):
    """Add an initialized device with a single endpoint, as a re-interview finds it."""
    dev = app.add_device(nwk=nwk, ieee=ieee)
    dev.node_desc = make_node_desc()
    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = 260
    ep1.device_type = profiles.zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)
    app.device_initialized(dev)

    return dev


def _discover_like(shadow):
    """Fill in a shadow the way a successful discovery of the device above would."""
    shadow.node_desc = make_node_desc()
    shadow.status = Status.ENDPOINTS_INIT
    ep = shadow.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(Basic.cluster_id)


async def _wait_for_removal(app, ieee):
    for _ in range(100):
        if ieee not in app.devices:
            return
        await asyncio.sleep(0)
    pytest.fail("The removed device was never unregistered")


@pytest.mark.parametrize("order", ["discovery_first", "leave_first", "discovery_fails"])
async def test_reinterview_device_removed_with_leave_pending(tmp_path, order):
    """A device removed during re-interview stays removed, whenever its leave completes.

    `remove()` keeps the shadow registered until the leave request completes, so a
    discovery that finishes first must not save the device to the database again, and
    one that fails must not restore the old device.
    """
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    dev = _add_reinterview_device(app, ieee, t.NWK(0x1234))

    discovery_started = asyncio.Event()
    finish_discovery = asyncio.Event()
    finish_leave = asyncio.Event()

    async def mock_discover(shadow):
        discovery_started.set()
        await finish_discovery.wait()

        if order == "discovery_fails":
            raise TimeoutError

        _discover_like(shadow)

    async def mock_leave(*args, **kwargs):
        await finish_leave.wait()

    with (
        patch.object(Device, "_discover", mock_discover),
        patch("zigpy.zdo.ZDO.leave", mock_leave),
        patch.object(app, "listener_event", wraps=app.listener_event),
    ):
        reinterview = asyncio.create_task(dev.reinterview())
        await discovery_started.wait()

        await app.remove(ieee)

        if order == "leave_first":
            finish_leave.set()
            await _wait_for_removal(app, ieee)
            finish_discovery.set()
            await reinterview
        else:
            finish_discovery.set()
            await reinterview

            # The old device is not registered again while the leave is pending
            assert app.devices.get(ieee) is not dev

            finish_leave.set()
            await _wait_for_removal(app, ieee)

        events = [c.args[0] for c in app.listener_event.mock_calls]
        assert "device_reinterviewed" not in events
        assert call("device_reinterview_failure", dev) in app.listener_event.mock_calls

    assert ieee not in app.devices
    await app.shutdown()

    # The removed device does not come back from the database
    app2 = await make_app_with_db(db)
    assert ieee not in app2.devices
    await app2.shutdown()


async def test_reinterview_device_removed_during_db_delete(tmp_path):
    """A removal that starts while the old device is deleted from the DB wins.

    The shadow is still registered then, and stays so until the leave completes.
    """
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    dev = _add_reinterview_device(app, ieee, t.NWK(0x1234))

    finish_leave = asyncio.Event()

    async def mock_discover(shadow):
        _discover_like(shadow)

    async def mock_leave(*args, **kwargs):
        await finish_leave.wait()

    remove_device = app._dblistener._remove_device
    removing = False

    async def remove_during_delete(device, **kwargs):
        nonlocal removing
        await remove_device(device, **kwargs)

        # Only the re-interview's delete: the removal queues one of its own
        if not removing:
            removing = True
            await app.remove(ieee)

    with (
        patch.object(Device, "_discover", mock_discover),
        patch("zigpy.zdo.ZDO.leave", mock_leave),
        patch.object(app._dblistener, "_remove_device", remove_during_delete),
        patch.object(app, "listener_event", wraps=app.listener_event),
    ):
        await dev.reinterview()

        finish_leave.set()
        await _wait_for_removal(app, ieee)

        events = [c.args[0] for c in app.listener_event.mock_calls]
        assert "device_reinterviewed" not in events
        assert call("device_reinterview_failure", dev) in app.listener_event.mock_calls

    await app.shutdown()

    app2 = await make_app_with_db(db)
    assert ieee not in app2.devices
    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_closed_on_remove(tmp_path):
    """Removing a device deletes its rows, and later writes do not recreate them."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev, _, _ = _add_joined_device(app)
    dev.store[STORE_COUNT] = 1
    old_store = dev.store
    await app._dblistener._callback_handlers.join()
    assert _count_store_rows(db, dev.ieee) == 1

    dev.zdo.leave = AsyncMock()
    await app.remove(dev.ieee)

    # Written while the leave request is still pending
    dev.store[STORE_COUNT] = 2
    assert dev.store[STORE_COUNT] == 1

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert dev.ieee not in app.devices
    assert dev.ieee not in app.device_stores

    # Written through a reference that outlived the device
    old_store[STORE_COUNT] = 3
    assert old_store.closed
    assert STORE_COUNT not in old_store

    await app.shutdown()
    assert _count_store_rows(db, dev.ieee) == 0


async def test_gp_device_store_round_trip(tmp_path):
    """Green Power devices have a store, saved with the device and removed with it."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    # Set before commissioning saves the device row
    gp_ieee = synthetic_ieee(GP_SOURCE_ID)
    app.device_stores[gp_ieee][STORE_COUNT] = 1
    await commission_with_key(app, KEY, frame_counter=1)
    device = app.devices[gp_ieee]
    assert device.store[STORE_COUNT] == 1
    await app.shutdown()

    app2 = await make_app_with_db(db)
    restored = app2.devices[gp_ieee]
    assert isinstance(restored, GreenPowerDevice)
    assert restored.store[STORE_COUNT] == 1

    restored.store[STORE_COUNT] = 2
    await app2._dblistener._callback_handlers.join()
    await app2.shutdown()

    app3 = await make_app_with_db(db)
    assert app3.devices[gp_ieee].store[STORE_COUNT] == 2

    app3.green_power.unpair = AsyncMock()
    await app3.remove(gp_ieee)
    assert gp_ieee not in app3.devices
    assert app3.device_stores[gp_ieee].closed
    await app3._dblistener._callback_handlers.join()
    assert _count_store_rows(db, gp_ieee) == 0

    # Commissioned again, the GPD gets a new, empty store, also in join listeners
    joined_stores = []
    listener = MagicMock()
    listener.device_joined = lambda device: joined_stores.append(device.store)
    app3.add_listener(listener)

    await commission_with_key(app3, KEY, frame_counter=20)
    recommissioned = app3.devices[gp_ieee]
    assert joined_stores == [recommissioned.store]
    assert not recommissioned.store.closed
    assert STORE_COUNT not in recommissioned.store

    recommissioned.store[STORE_COUNT] = 3
    await app3.shutdown()

    app4 = await make_app_with_db(db)
    assert app4.devices[gp_ieee].store[STORE_COUNT] == 3
    await app4.shutdown()


@pytest.mark.parametrize("used_before_removal", [True, False])
@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_not_inherited_after_rejoin(tmp_path, used_before_removal):
    """Writes through a removed device never reach a device re-added with its IEEE."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev, _, _ = _add_joined_device(app)

    if used_before_removal:
        dev.store[STORE_COUNT] = 1

    dev.zdo.leave = AsyncMock()
    await app.remove(dev.ieee)

    # The first write may only happen while the leave request is pending
    dev.store[STORE_COUNT] = 2

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert dev.ieee not in app.devices

    # A device object that never used its store before removal
    stale = Device(app, dev.ieee, dev.nwk)
    dev.store[STORE_COUNT] = 3
    stale.store[STORE_COUNT] = 4
    assert dev.store.closed
    assert stale.store is dev.store
    assert STORE_COUNT not in stale.store

    # The same device joins again and gets an empty store
    app.handle_join(dev.nwk, dev.ieee, 0)
    new_dev = app.get_device(dev.ieee)
    assert new_dev is not dev
    assert not new_dev.store.closed
    assert STORE_COUNT not in new_dev.store

    # Old references still cannot write
    dev.store[STORE_COUNT] = 5
    stale.store[STORE_COUNT] = 6
    assert STORE_COUNT not in new_dev.store

    ep = new_dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = profiles.zha.DeviceType.PUMP
    ep.add_input_cluster(0)
    app.device_initialized(new_dev)
    new_dev.store[STORE_COUNT] = 7
    await app.shutdown()

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            f"SELECT namespace, key, value FROM device_store{zigpy.appdb.DB_V}"
            " WHERE ieee = ?",
            (str(dev.ieee),),
        ).fetchall()

    assert rows == [("quirk:test", "count", "7")]


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_not_saved_for_removed_device(tmp_path):
    """A device save queued after removal started does not write the closed store."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev, _, _ = _add_joined_device(app)
    dev.store[STORE_COUNT] = 1
    await app._dblistener._callback_handlers.join()

    app.device_stores.close(dev.ieee)
    app._dblistener.device_removed(dev)
    app._dblistener.raw_device_initialized(dev)
    await app._dblistener._callback_handlers.join()

    assert _count_store_rows(db, dev.ieee) == 0

    await app.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_undecodable_row_skipped(tmp_path, caplog):
    """A row that is not valid JSON is skipped instead of failing the whole load."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    dev, _, _ = _add_joined_device(app)
    dev.store[STORE_COUNT] = 1
    dev.store.namespace("quirk:test")["other"] = 2
    await app.shutdown()

    with sqlite3.connect(db) as conn:
        conn.execute(
            f"UPDATE device_store{zigpy.appdb.DB_V} SET value = '{{' WHERE key = 'other'"
        )

    with caplog.at_level(logging.WARNING):
        app2 = await make_app_with_db(db)

    assert "Skipping undecodable store value quirk:test/other" in caplog.text
    dev2 = app2.get_device(dev.ieee)
    assert dev2.store[STORE_COUNT] == 1
    assert "other" not in dev2.store.namespace("quirk:test")

    await app2.shutdown()


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_device_store_bound_at_construction(tmp_path):
    """A device object that never used its store keeps the one it was created with."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)

    dev, _, _ = _add_joined_device(app)
    untouched = Device(app, dev.ieee, dev.nwk)

    dev.zdo.leave = AsyncMock()
    await app.remove(dev.ieee)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    app.handle_join(dev.nwk, dev.ieee, 0)
    new_dev = app.get_device(dev.ieee)

    # First access only after the device was added again
    untouched.store[STORE_COUNT] = 1

    assert untouched.store.closed
    assert STORE_COUNT not in new_dev.store

    await app.shutdown()


GROUP_STATE = StoredValue(namespace="zigpy.groups", key="allocation", type=dict)


def _network_store_rows(db) -> list[tuple]:
    """Read the committed network store rows through a separate connection."""
    with contextlib.closing(sqlite3.connect(db)) as conn:
        return list(
            conn.execute(
                f"SELECT namespace, key, value, version FROM network_store{zigpy.appdb.DB_V}"
                " ORDER BY namespace, key"
            )
        )


@patch("zigpy.device.Device.schedule_initialize", new=mock_dev_init(True))
async def test_network_store_round_trip(tmp_path):
    """Network values survive a restart and are loaded before devices are resolved."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    dev, _, _ = _add_joined_device(app)

    app.network_store[GROUP_STATE] = {"next": 5}
    app.network_store.namespace("other").set("k", [1, None], version=3)
    app.network_store.namespace("other")["gone"] = 1
    del app.network_store.namespace("other")["gone"]
    last_updated = app.network_store.last_updated(GROUP_STATE)

    # Network values do not follow devices
    app._dblistener.device_removed(dev)
    await app.shutdown()

    seen = []

    def resolver(device):
        seen.append(device.application.network_store.get(GROUP_STATE))
        return device

    app2 = await make_app_with_db(db, device_resolver=resolver)

    # The device row was removed, so add one to see what its resolution can read
    assert seen == []
    assert app2.network_store[GROUP_STATE] == {"next": 5}
    assert app2.network_store.last_updated(GROUP_STATE).timestamp() == pytest.approx(
        last_updated.timestamp()
    )

    item = app2.network_store.namespace("other").item("k")
    assert item.value == [1, None]
    assert item.version == 3
    assert "gone" not in app2.network_store.namespace("other")

    _add_joined_device(app2)
    app2.network_store[GROUP_STATE] = {"next": 6}
    await app2.shutdown()

    seen.clear()
    app3 = await make_app_with_db(db, device_resolver=resolver)

    assert seen == [{"next": 6}]
    assert app3.network_store[GROUP_STATE] == {"next": 6}
    assert _network_store_rows(db) == [
        ("other", "k", "[1, null]", 3),
        ("zigpy.groups", "allocation", '{"next": 6}', 1),
    ]

    await app3.shutdown()


async def test_network_store_version_rules_persisted(tmp_path):
    """A newer row is kept on disk, a stale one is dropped from it."""
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    ns = app.network_store.namespace("zigpy.groups")
    ns.set("allocation", {"next": 1}, version=2)
    ns.set("stale", 1, version=0)
    await app.shutdown()

    app2 = await make_app_with_db(db)
    stale = StoredValue(namespace="zigpy.groups", key="stale", type=int)

    assert GROUP_STATE not in app2.network_store
    assert app2.network_store.get(stale) is None
    await app2.shutdown()

    assert _network_store_rows(db) == [
        ("zigpy.groups", "allocation", '{"next": 1}', 2),
    ]


async def test_network_store_skips_undecodable_row(tmp_path, caplog):
    db = tmp_path / "test.db"
    app = await make_app_with_db(db)
    app.network_store[GROUP_STATE] = {"next": 1}
    await app.shutdown()

    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            f"INSERT INTO network_store{zigpy.appdb.DB_V} VALUES (?, ?, ?, ?, ?)",
            ("zigpy.groups", "broken", "{", 1, 0.0),
        )
        conn.commit()

    with caplog.at_level(logging.WARNING):
        app2 = await make_app_with_db(db)

    assert "Skipping undecodable store value zigpy.groups/broken of network" in (
        caplog.text
    )
    assert app2.network_store[GROUP_STATE] == {"next": 1}
    assert "broken" not in app2.network_store.namespace("zigpy.groups")

    await app2.shutdown()


async def test_network_store_without_database():
    """Without a database the network store is in memory."""
    app = make_app({})
    await app._load_db()

    assert app._dblistener is None

    app.network_store[GROUP_STATE] = {"next": 1}

    assert app.network_store[GROUP_STATE] == {"next": 1}


MIGRATED_VALUE = StoredValue(namespace="quirk:test", key="migrated", type=int)
OTHER_MIGRATED_VALUE = StoredValue(namespace="quirk:test", key="other", type=int)
MIGRATING_IEEE = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")


class MigratingBasic(Basic):
    """A quirk's Basic cluster that moved attributes 0x7777 and 0x7776 to the store."""

    _skip_registry = True

    def migrate_attribute_cache_row(self, row, value) -> bool:
        if row.attr_id == 0x7777:
            self.endpoint.device.store[MIGRATED_VALUE] = value
        elif row.attr_id == 0x7776:
            self.endpoint.device.store[OTHER_MIGRATED_VALUE] = value
        else:
            return False

        return True


class ManufacturerSpecificBasic(MigratingBasic):
    """Defines 0x7777, but as a manufacturer-specific attribute."""

    class AttributeDefs(Basic.AttributeDefs):
        custom = ZCLAttributeDef(id=0x7777, type=t.uint16_t, manufacturer_code=0x1234)


class FailingMigrationBasic(Basic):
    _skip_registry = True

    def migrate_attribute_cache_row(self, row, value) -> bool:
        raise RuntimeError("Broken migration")


def _quirk_resolver(cluster_cls):
    def resolver(device):
        if device.ieee != MIGRATING_IEEE:
            return device

        new = device.clone()
        ep = new.endpoints[1]
        ep.add_input_cluster(Basic.cluster_id, cluster_cls(ep, is_server=True))
        return new

    return resolver


def _insert_attr_row(
    db, attr_id, value, data_type=None, *, manufacturer_code=None, status=0
) -> None:
    with contextlib.closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            f"INSERT INTO attributes_cache{zigpy.appdb.DB_V}"
            " (ieee, endpoint_id, cluster_type, cluster_id, attr_id, manufacturer_code,"
            " status, value, data_type, last_updated)"
            " VALUES (?, 1, 0, ?, ?, ?, ?, ?, ?, 0)",
            (
                str(MIGRATING_IEEE),
                Basic.cluster_id,
                attr_id,
                manufacturer_code,
                status,
                value,
                data_type,
            ),
        )


@pytest.mark.parametrize(
    ("value", "data_type", "manufacturer_code"),
    [
        (b"\x05\x00", DataTypeId.uint16, None),
        # Rows from before data types were stored
        (5, None, None),
        # Rows from before manufacturer codes were stored
        (5, None, zigpy.zcl.helpers.UNMIGRATED_MANUFACTURER_CODE),
    ],
)
async def test_attribute_row_migrated(
    tmp_path, value, data_type, manufacturer_code
) -> None:
    """A quirk cluster moves the row of an attribute it no longer defines."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    _insert_attr_row(db, 0x7777, value, data_type, manufacturer_code=manufacturer_code)

    app2 = await make_app_with_db(db, device_resolver=_quirk_resolver(MigratingBasic))
    dev2 = app2.get_device(dev.ieee)

    assert dev2.store[MIGRATED_VALUE] == 5
    assert dev2.endpoints[1].basic._attr_cache.get(0x7777) is None

    await app2.shutdown()

    assert _count_store_rows(db, dev.ieee) == 1
    assert _read_attr_row(db, Basic.cluster_id, 0x7777) is None

    # Loading without the quirk, as after a downgrade, does not bring the row back
    app3 = await make_app_with_db(db)
    dev3 = app3.get_device(dev.ieee)

    assert dev3.endpoints[1].basic._attr_cache.get(0x7777) is None
    assert dev3.store[MIGRATED_VALUE] == 5

    await app3.shutdown()


@pytest.mark.parametrize(
    ("resolver", "migrated"),
    [
        (None, False),
        # A resolver that keeps the device applied no quirk
        (lambda device: device, False),
        (_quirk_resolver(Basic), True),
    ],
)
async def test_attribute_row_migration_only_for_quirked_devices(
    tmp_path, resolver, migrated
) -> None:
    """Only quirk-replaced devices migrate, once, and only rows with values."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    # Defined attribute
    _insert_attr_row(db, Basic.AttributeDefs.zcl_version.id, 3)
    # Undefined attributes, the first with a value
    _insert_attr_row(db, 0x7777, b"\x05\x00", DataTypeId.uint16)
    _insert_attr_row(db, 0x7778, None, status=ZCLStatus.UNSUPPORTED_ATTRIBUTE)
    _insert_attr_row(db, 0x7779, b"\x05", DataTypeId.unk)
    # An empty `unk` value decodes, but only its lost definition could interpret it
    _insert_attr_row(db, 0x777A, b"", DataTypeId.unk)

    with patch.object(
        zigpy.zcl.Cluster,
        "migrate_attribute_cache_row",
        autospec=True,
        return_value=False,
    ) as migrate:
        app2 = await make_app_with_db(db, device_resolver=resolver)

    basic2 = app2.get_device(dev.ieee).endpoints[1].basic

    if migrated:
        # Called on the quirked device's cluster in the second pass only
        migrate.assert_called_once()
        cluster, row, value = migrate.mock_calls[0].args
        assert cluster is basic2
        assert row.attr_id == 0x7777
        assert value == 5
    else:
        migrate.assert_not_called()

    # Rows that are not migrated load as before
    assert basic2.get(Basic.AttributeDefs.zcl_version.name) == 3
    assert basic2._attr_cache.get(0x7777) == 5

    await app2.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, 0x7777) == (
        b"\x05\x00",
        DataTypeId.uint16,
    )


async def test_attribute_row_migration_error(tmp_path, caplog) -> None:
    """A failing migration is logged and keeps the row."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    _insert_attr_row(db, Basic.AttributeDefs.zcl_version.id, 3)
    _insert_attr_row(db, 0x7777, 5)

    with caplog.at_level(logging.WARNING):
        app2 = await make_app_with_db(
            db, device_resolver=_quirk_resolver(FailingMigrationBasic)
        )

    assert "Failed to migrate attribute 0x7777" in caplog.text
    assert "Broken migration" in caplog.text

    basic2 = app2.get_device(dev.ieee).endpoints[1].basic
    assert basic2.get(Basic.AttributeDefs.zcl_version.name) == 3
    assert basic2._attr_cache.get(0x7777) == 5

    await app2.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, 0x7777) == (5, None)


async def test_attribute_rows_migrated(tmp_path) -> None:
    """Several rows of a device migrate in one load."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    _insert_attr_row(db, 0x7777, 5)
    _insert_attr_row(db, 0x7776, 6)

    app2 = await make_app_with_db(db, device_resolver=_quirk_resolver(MigratingBasic))

    app2.get_device(dev.ieee).store[MIGRATED_VALUE] = 7
    await app2.shutdown()

    assert _count_store_rows(db, dev.ieee) == 2
    assert _read_attr_row(db, Basic.cluster_id, 0x7777) is None
    assert _read_attr_row(db, Basic.cluster_id, 0x7776) is None

    app3 = await make_app_with_db(db)
    dev3 = app3.get_device(dev.ieee)
    assert dev3.store[MIGRATED_VALUE] == 7
    assert dev3.store[OTHER_MIGRATED_VALUE] == 6
    await app3.shutdown()


async def test_attribute_row_not_offered_if_defined_under_other_code(
    tmp_path,
) -> None:
    """An attribute ID the cluster still defines is not migrated, whatever the code."""
    db = tmp_path / "test.db"
    app, dev = await _make_app_with_clusters(db, [Basic.cluster_id])
    await app.shutdown()

    _insert_attr_row(db, 0x7777, 5)

    app2 = await make_app_with_db(
        db, device_resolver=_quirk_resolver(ManufacturerSpecificBasic)
    )
    assert MIGRATED_VALUE not in app2.get_device(dev.ieee).store
    await app2.shutdown()

    assert _read_attr_row(db, Basic.cluster_id, 0x7777) == (5, None)
