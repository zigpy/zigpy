from datetime import UTC, datetime
import logging
import pathlib
import sqlite3
from sqlite3.dump import _iterdump as iterdump

from aiosqlite.context import contextmanager
import pytest

from tests.async_mock import AsyncMock, MagicMock, patch
from tests.conftest import app, make_node_desc  # noqa: F401
from tests.test_appdb import make_app_with_db
import zigpy.appdb
import zigpy.appdb_schemas
import zigpy.endpoint
from zigpy.profiles import zha as zha_profile
import zigpy.types as t
import zigpy.zcl
from zigpy.zcl.clusters.general import Basic
from zigpy.zcl.foundation import BaseAttributeDefs, Status, ZCLAttributeDef
from zigpy.zdo import types as zdo_t

pytestmark = pytest.mark.usefixtures("auto_kill_aiosqlite")


@pytest.fixture
def test_db(tmp_path):
    def inner(filename):
        databases = pathlib.Path(__file__).parent / "databases"
        db_path = tmp_path / filename

        if filename.endswith(".db"):
            db_path.write_bytes((databases / filename).read_bytes())
            return str(db_path)

        conn = sqlite3.connect(str(db_path))

        sql = (databases / filename).read_text()
        conn.executescript(sql)

        conn.commit()
        conn.close()

        return str(db_path)

    return inner


def dump_db(path):
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        (user_version,) = cur.fetchone()

        sql = "\n".join(iterdump(conn))

    return user_version, sql


@pytest.mark.parametrize("open_twice", [False, True])
async def test_migration_from_3_to_4(open_twice, test_db):
    test_db_v3 = test_db("simple_v3.sql")

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()

        neighbors_before = list(cur.execute("SELECT * FROM neighbors"))
        assert len(neighbors_before) == 2
        assert all(len(row) == 8 for row in neighbors_before)

        node_descs_before = list(cur.execute("SELECT * FROM node_descriptors"))
        assert len(node_descs_before) == 2
        assert all(len(row) == 2 for row in node_descs_before)

    # Ensure migration works on first run, and after shutdown
    if open_twice:
        app = await make_app_with_db(test_db_v3)
        await app.shutdown()

    app = await make_app_with_db(test_db_v3)

    dev1 = app.get_device(nwk=0xBD4D)
    assert dev1.node_desc == zdo_t.NodeDescriptor(
        logical_type=zdo_t.LogicalType.Router,
        complex_descriptor_available=0,
        user_descriptor_available=0,
        reserved=0,
        aps_flags=0,
        frequency_band=zdo_t.NodeDescriptor.FrequencyBand.Freq2400MHz,
        mac_capability_flags=142,
        manufacturer_code=4476,
        maximum_buffer_size=82,
        maximum_incoming_transfer_size=82,
        server_mask=11264,
        maximum_outgoing_transfer_size=82,
        descriptor_capability_field=0,
    )
    assert len(app.topology.neighbors[dev1.ieee]) == 1
    assert app.topology.neighbors[dev1.ieee][0] == zdo_t.Neighbor(
        extended_pan_id=t.ExtendedPanId.convert("81:b1:12:dc:9f:bd:f4:b6"),
        ieee=t.EUI64.convert("ec:1b:bd:ff:fe:54:4f:40"),
        nwk=0x6D1C,
        reserved1=0,
        device_type=zdo_t.Neighbor.DeviceType.Router,
        rx_on_when_idle=1,
        relationship=zdo_t.Neighbor.RelationShip.Sibling,
        reserved2=0,
        permit_joining=2,
        depth=15,
        lqi=130,
    )

    dev2 = app.get_device(nwk=0x6D1C)
    assert dev2.node_desc == dev1.node_desc.replace(manufacturer_code=4456)
    assert len(app.topology.neighbors[dev2.ieee]) == 1
    assert app.topology.neighbors[dev2.ieee][0] == zdo_t.Neighbor(
        extended_pan_id=t.ExtendedPanId.convert("81:b1:12:dc:9f:bd:f4:b6"),
        ieee=t.EUI64.convert("00:0d:6f:ff:fe:a6:11:7a"),
        nwk=0xBD4D,
        reserved1=0,
        device_type=zdo_t.Neighbor.DeviceType.Router,
        rx_on_when_idle=1,
        relationship=zdo_t.Neighbor.RelationShip.Sibling,
        reserved2=0,
        permit_joining=2,
        depth=15,
        lqi=132,
    )

    await app.shutdown()

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()

        # Old tables are untouched
        assert neighbors_before == list(cur.execute("SELECT * FROM neighbors"))
        assert node_descs_before == list(cur.execute("SELECT * FROM node_descriptors"))

        # New tables exist
        neighbors_after = list(cur.execute("SELECT * FROM neighbors_v4"))
        assert len(neighbors_after) == 2
        assert all(len(row) == 12 for row in neighbors_after)

        node_descs_after = list(cur.execute("SELECT * FROM node_descriptors_v4"))
        assert len(node_descs_after) == 2
        assert all(len(row) == 14 for row in node_descs_after)


async def test_migration_0_to_5(test_db):
    test_db_v0 = test_db("zigbee_20190417_v0.db")

    with sqlite3.connect(test_db_v0) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM devices")
        (num_devices_before_migration,) = cur.fetchone()

    assert num_devices_before_migration == 27

    app1 = await make_app_with_db(test_db_v0)
    await app1.shutdown()
    assert len(app1.devices) == 27

    app2 = await make_app_with_db(test_db_v0)
    await app2.shutdown()

    # All 27 devices migrated
    assert len(app2.devices) == 27


async def test_migration_missing_neighbors_v3(test_db):
    test_db_v3 = test_db("simple_v3.sql")

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE neighbors")

        # Ensure the table doesn't exist
        with pytest.raises(sqlite3.OperationalError):
            cur.execute("SELECT * FROM neighbors")

    # Migration won't fail even though the database version number is 3
    app = await make_app_with_db(test_db_v3)
    await app.shutdown()

    # Version was upgraded
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        assert cur.fetchone() == (zigpy.appdb.DB_VERSION,)


@pytest.mark.parametrize("corrupt_device", [False, True])
async def test_migration_bad_attributes(test_db, corrupt_device):
    test_db_bad_attrs = test_db("bad_attrs_v3.db")

    with sqlite3.connect(test_db_bad_attrs) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM devices")
        (num_devices_before_migration,) = cur.fetchone()

        cur.execute("SELECT count(*) FROM endpoints")
        (num_ep_before_migration,) = cur.fetchone()

    if corrupt_device:
        with sqlite3.connect(test_db_bad_attrs) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM endpoints WHERE ieee='60:a4:23:ff:fe:02:39:7b'")
            cur.execute("SELECT changes()")
            (deleted_eps,) = cur.fetchone()
    else:
        deleted_eps = 0

    # Migration will handle invalid attributes entries
    app = await make_app_with_db(test_db_bad_attrs)
    await app.shutdown()

    assert len(app.devices) == num_devices_before_migration
    assert (
        sum(len(d.non_zdo_endpoints) for d in app.devices.values())
        == num_ep_before_migration - deleted_eps
    )

    app2 = await make_app_with_db(test_db_bad_attrs)
    await app2.shutdown()

    # All devices still exist
    assert len(app2.devices) == num_devices_before_migration
    assert (
        sum(len(d.non_zdo_endpoints) for d in app2.devices.values())
        == num_ep_before_migration - deleted_eps
    )

    with sqlite3.connect(test_db_bad_attrs) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")

        # Ensure the final database schema version number does not decrease
        assert cur.fetchone()[0] >= zigpy.appdb.DB_VERSION


async def test_migration_missing_node_descriptor(test_db, caplog):
    test_db_v3 = test_db("simple_v3.sql")
    ieee = "ec:1b:bd:ff:fe:54:4f:40"

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM node_descriptors WHERE ieee=?", [ieee])

    with caplog.at_level(logging.WARNING):
        # The invalid device will still be loaded, for now
        app = await make_app_with_db(test_db_v3)

    assert len(app.devices) == 2

    bad_dev = app.devices[t.EUI64.convert(ieee)]
    assert bad_dev.node_desc is None

    await app.shutdown()

    # The migration did not fabricate a node descriptor for the device
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM node_descriptors{zigpy.appdb.DB_V} WHERE ieee=?", [ieee]
        )

        assert not cur.fetchall()


@pytest.mark.parametrize(
    ("fail_on_sql", "fail_on_count"),
    [
        ("INSERT INTO node_descriptors_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", 0),
        ("INSERT INTO neighbors_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", 5),
        ("SELECT ieee, endpoint_id, cluster FROM output_clusters", 0),
        (
            "INSERT INTO neighbors_v5 (device_ieee, extended_pan_id, ieee, nwk,"
            " device_type, rx_on_when_idle, relationship, reserved1, permit_joining,"
            " reserved2, depth, lqi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            5,
        ),
    ],
)
async def test_migration_failure(fail_on_sql, fail_on_count, test_db):
    test_db_bad_attrs = test_db("bad_attrs_v3.db")

    before = dump_db(test_db_bad_attrs)
    assert before[0] == 3

    count = 0
    sql_seen = False
    execute = zigpy.appdb.PersistingListener.execute

    def patched_execute(self, sql, *args, **kwargs):
        nonlocal count, sql_seen

        if sql == fail_on_sql:
            sql_seen = True

            if count == fail_on_count:
                raise sqlite3.ProgrammingError("Uh oh")

            count += 1

        return execute(self, sql, *args, **kwargs)

    with patch("zigpy.appdb.PersistingListener.execute", new=patched_execute):
        with pytest.raises(sqlite3.ProgrammingError):
            await make_app_with_db(test_db_bad_attrs)

    assert sql_seen

    after = dump_db(test_db_bad_attrs)
    assert before == after


async def test_migration_failure_version_mismatch(test_db):
    """Test migration failure when the `user_version` and table versions don't match."""

    test_db_v3 = test_db("simple_v3.sql")

    # Migrate it to the latest version
    app = await make_app_with_db(test_db_v3)
    await app.shutdown()

    # Downgrade it back to v7
    with sqlite3.connect(test_db_v3) as conn:
        conn.execute("PRAGMA user_version=7")

    # Startup now fails due to the version mismatch
    with pytest.raises(zigpy.exceptions.CorruptDatabase):
        await make_app_with_db(test_db_v3)


async def test_migration_downgrade_warning(test_db, caplog):
    """Test V4 re-migration which was forcibly downgraded to v3."""

    test_db_v3 = test_db("simple_v3.sql")

    # Migrate it to the latest version
    app = await make_app_with_db(test_db_v3)
    await app.shutdown()

    # Upgrade it beyond our current version
    with sqlite3.connect(test_db_v3) as conn:
        conn.execute("CREATE TABLE future_table_v100(column)")
        conn.execute("PRAGMA user_version=100")

    # Startup now logs an error due to the "downgrade"
    with caplog.at_level(logging.ERROR):
        app2 = await make_app_with_db(test_db_v3)
        await app2.shutdown()

    assert "Downgrading zigpy" in caplog.text

    # Ensure the version was not touched
    with sqlite3.connect(test_db_v3) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == 100


@pytest.mark.parametrize("with_bad_neighbor", [False, True])
async def test_v4_to_v5_migration_bad_neighbors(test_db, with_bad_neighbor):
    """V4 migration has no `neighbors_v4` foreign key and no `ON DELETE CASCADE`"""

    test_db_v4 = test_db("simple_v3_to_v4.sql")

    with sqlite3.connect(test_db_v4) as conn:
        cur = conn.cursor()

        if with_bad_neighbor:
            # Row refers to an invalid device, left behind by a bad `DELETE`
            cur.execute(
                """
                INSERT INTO neighbors_v4
                VALUES (
                    '11:aa:bb:cc:dd:ee:ff:00',
                    '22:aa:bb:cc:dd:ee:ff:00',
                    '33:aa:bb:cc:dd:ee:ff:00',
                    12345,
                    1,1,2,0,2,0,15,132
                )
            """
            )

        (num_v4_neighbors,) = cur.execute(
            "SELECT count(*) FROM neighbors_v4"
        ).fetchone()

    app = await make_app_with_db(test_db_v4)
    await app.shutdown()

    with sqlite3.connect(test_db_v4) as conn:
        (num_new_neighbors,) = cur.execute(
            f"SELECT count(*) FROM neighbors{zigpy.appdb.DB_V}"
        ).fetchone()

    # Only the invalid row was not migrated
    if with_bad_neighbor:
        assert num_new_neighbors == num_v4_neighbors - 1
    else:
        assert num_new_neighbors == num_v4_neighbors


@pytest.mark.parametrize("with_quirk_attribute", [False, True])
async def test_v4_to_v6_migration_missing_endpoints(test_db, with_quirk_attribute):
    """V5's schema was too rigid and failed to migrate endpoints created by quirks"""

    test_db_v3 = test_db("simple_v3.sql")

    if with_quirk_attribute:
        with sqlite3.connect(test_db_v3) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO attributes
                VALUES (
                    '00:0d:6f:ff:fe:a6:11:7a',
                    123,
                    456,
                    789,
                    'test'
                )
            """
            )

    def resolver(dev):
        if dev.ieee == t.EUI64.convert("00:0d:6f:ff:fe:a6:11:7a"):
            ep = dev.add_endpoint(123)
            ep.add_input_cluster(456)

        return dev

    # Migrate to v5 and then v6
    app = await make_app_with_db(test_db_v3, device_resolver=resolver)

    if with_quirk_attribute:
        dev = app.get_device(ieee=t.EUI64.convert("00:0d:6f:ff:fe:a6:11:7a"))
        assert dev.endpoints[123].in_clusters[456]._attr_cache[789] == "test"

    await app.shutdown()


async def test_v5_to_v7_migration(test_db):
    test_db_v5 = test_db("simple_v5.sql")

    app = await make_app_with_db(test_db_v5)
    await app.shutdown()


async def test_migration_missing_tables(app):
    conn = MagicMock()
    conn.close = AsyncMock()

    appdb = zigpy.appdb.PersistingListener(conn, app)

    appdb._get_table_versions = AsyncMock(
        return_value={"table1_v1": "1", "table1": "", "table2_v1": "1"}
    )

    mock_execute = AsyncMock()
    appdb.execute = contextmanager(mock_execute)

    appdb._db._execute = AsyncMock()

    # Migrations must explicitly specify all old tables, even if they will be untouched
    with pytest.raises(RuntimeError):
        await appdb._migrate_tables(
            {
                "table1_v1": "table1_v2",
                # "table2_v1": "table2_v2",
            }
        )

    # The untouched table will never be queried
    await appdb._migrate_tables({"table1_v1": "table1_v2", "table2_v1": None})

    # table1_v1 is queried (pragma + select), table2_v1 is not
    assert any("table1_v1" in call.args[0] for call in mock_execute.call_args_list)
    assert not any("table2_v1" in call.args[0] for call in mock_execute.call_args_list)

    await appdb.shutdown()


async def test_migrate_tables_integrity_error_raises(tmp_path):
    """Test that _migrate_tables re-raises IntegrityError with errors='raise'."""
    db_path = tmp_path / "test.db"
    app = await make_app_with_db(db_path)

    # Create two simple tables, pre-populate the destination with a conflicting row
    await app._dblistener.execute(
        "CREATE TABLE src_v1 (id INTEGER PRIMARY KEY, val TEXT)"
    )
    await app._dblistener.execute(
        "CREATE TABLE dst_v2 (id INTEGER PRIMARY KEY, val TEXT)"
    )
    await app._dblistener.execute("INSERT INTO src_v1 VALUES (1, 'hello')")
    await app._dblistener.execute("INSERT INTO dst_v2 VALUES (1, 'conflict')")

    app._dblistener._get_table_versions = AsyncMock(return_value={"src_v1": "1"})

    with pytest.raises(sqlite3.IntegrityError):
        await app._dblistener._migrate_tables({"src_v1": "dst_v2"})

    await app.shutdown()


async def test_last_seen_initial_migration(test_db):
    test_db_v5 = test_db("simple_v5.sql")

    # To preserve the old behavior, `0` will not be exposed to ZHA, only `None`
    app = await make_app_with_db(test_db_v5)
    dev = app.get_device(nwk=0xBD4D)

    assert dev.last_seen is None
    dev.last_seen = datetime.now(UTC)
    assert isinstance(dev.last_seen, float)
    await app.shutdown()

    # But the device's `last_seen` will still update properly when it's actually set
    app = await make_app_with_db(test_db_v5)
    assert isinstance(app.get_device(nwk=0xBD4D).last_seen, float)
    await app.shutdown()


def test_db_version_is_latest_schema_version():
    assert max(zigpy.appdb_schemas.SCHEMAS.keys()) == zigpy.appdb.DB_VERSION


async def test_last_seen_migration_v8_to_v9(test_db):
    test_db_v8 = test_db("simple_v8.sql")

    app = await make_app_with_db(test_db_v8)
    assert int(app.get_device(nwk=0xE01E).last_seen) == 1651119830
    await app.shutdown()


async def test_unknown_manufacturer_code_migration(test_db, caplog):
    test_db_prod = test_db("zigbee_puddly2.db")

    # Count cached rows before migration
    with sqlite3.connect(test_db_prod) as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM attributes_cache_v13")
        before_cached = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM unsupported_attributes_v13")
        before_unsupported = cur.fetchone()[0]

        # Some rows exist in both tables
        cur.execute(
            "SELECT COUNT(*) FROM attributes_cache_v13 a JOIN unsupported_attributes_v13 u USING (ieee, endpoint_id, cluster_type, cluster_id, attr_id)"
        )

        before_overlap = cur.fetchone()[0]
        before_total = before_cached + before_unsupported - before_overlap

    app = await make_app_with_db(test_db_prod)
    await app.shutdown()

    # Count rows after migration
    with sqlite3.connect(test_db_prod) as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM attributes_cache{zigpy.appdb.DB_V}")
        after_total = cur.fetchone()[0]

        assert after_total == before_total


@pytest.mark.filterwarnings(
    r"ignore:Attribute .* has `is_manufacturer_specific`"
    r":DeprecationWarning"
)
async def test_manufacturer_code_migration_uses_device_manufacturer_id(test_db):
    """Test that attributes on manufacturer-specific clusters get the device's manufacturer_id."""

    # Simple quirk for Third Reality night light with is_manufacturer_specific=True.
    # The real device (f4:42:50:c3:96:14:00:00) has cached attrs 2-5 on 0xFC00 and
    # attr 4 is also in unsupported_attributes_v13.
    class TestCluster(zigpy.zcl.Cluster):
        cluster_id = 0xFC00
        _skip_registry = True

        class AttributeDefs(BaseAttributeDefs):
            test_attr = ZCLAttributeDef(
                id=0x0002,
                type=t.uint8_t,
                is_manufacturer_specific=True,
            )
            unsupported_attr = ZCLAttributeDef(
                id=0x0004,
                type=t.uint8_t,
                is_manufacturer_specific=True,
            )

    def resolver(device):
        if device.model != "3RSNL02043Z":
            return device

        new = device.clone()
        for ep in new.non_zdo_endpoints:
            old = ep.in_clusters.pop(TestCluster.cluster_id, None)
            if old is None:
                continue
            cluster = TestCluster(ep, is_server=True)
            ep.add_input_cluster(cluster.cluster_id, cluster)
            cluster._attr_cache_internal = old._attr_cache.clone(cluster)
        return new

    test_db_path = test_db("zigbee_puddly2.db")
    third_reality_ieee = "f4:42:50:c3:96:14:00:00"

    app = await make_app_with_db(test_db_path, device_resolver=resolver)

    # Check that cached attributes on 0xFC00 got the device's manufacturer_id
    with sqlite3.connect(test_db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT manufacturer_code
            FROM attributes_cache{zigpy.appdb.DB_V}
            WHERE cluster_id = 0xFC00 AND attr_id = 0x0002
            """,
        )
        rows = cur.fetchall()

    assert rows == [(0x130D,), (0x130D,), (0x130D,)]

    # The unsupported manufacturer-specific attr also got the correct manufacturer code
    with sqlite3.connect(test_db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT manufacturer_code, status
            FROM attributes_cache{zigpy.appdb.DB_V}
            WHERE ieee = ? AND cluster_id = 0xFC00 AND attr_id = 0x0004
            """,
            (third_reality_ieee,),
        )
        row = cur.fetchone()

    assert row == (0x130D, Status.UNSUPPORTED_ATTRIBUTE)

    # Confirm it's loaded as unsupported in the device's attribute cache
    dev = app.get_device(ieee=t.EUI64.convert(third_reality_ieee))
    cluster = dev.endpoints[1].in_clusters[0xFC00]
    assert cluster.is_attribute_unsupported(TestCluster.AttributeDefs.unsupported_attr)

    # Attr 0x0003 has no definition in our quirk but exists in the DB. It should be
    # stored in the legacy cache regardless.
    with pytest.raises(KeyError):
        cluster.find_attribute(0x0003)

    assert 0x0003 in cluster._attr_cache._legacy_cache
    assert cluster._attr_cache.get(0x0003) == 20

    await app.shutdown()


@pytest.mark.filterwarnings(
    r"ignore:Attribute .* has `is_manufacturer_specific`"
    r":DeprecationWarning"
)
async def test_data_migration_ambiguous_attributes(tmp_path):
    """Test data migration disambiguation when find_attributes returns multiple."""

    class DisambiguatedCluster(zigpy.zcl.Cluster):
        cluster_id = 0xFC01
        _skip_registry = True

        class AttributeDefs(BaseAttributeDefs):
            standard_attr = ZCLAttributeDef(
                id=0x0010, type=t.uint8_t, is_manufacturer_specific=False
            )
            manuf_attr = ZCLAttributeDef(
                id=0x0010, type=t.uint8_t, is_manufacturer_specific=True
            )

    class AmbiguousCluster(zigpy.zcl.Cluster):
        cluster_id = 0xFC02
        _skip_registry = True

        class AttributeDefs(BaseAttributeDefs):
            attr_a = ZCLAttributeDef(
                id=0x0020, type=t.uint8_t, is_manufacturer_specific=True
            )
            attr_b = ZCLAttributeDef(
                id=0x0020, type=t.uint8_t, manufacturer_code=0x1111
            )
            attr_c = ZCLAttributeDef(
                id=0x0020, type=t.uint8_t, manufacturer_code=0x2222
            )

    def resolver(device):
        if device.model != "model":
            return device

        new = device.clone()
        for ep in new.non_zdo_endpoints:
            for custom_cls in (DisambiguatedCluster, AmbiguousCluster):
                old = ep.in_clusters.pop(custom_cls.cluster_id, None)
                if old is None:
                    continue
                cluster = custom_cls(ep, is_server=True)
                ep.add_input_cluster(cluster.cluster_id, cluster)
                cluster._attr_cache_internal = old._attr_cache.clone(cluster)
        return new

    db_path = str(tmp_path / "test.db")

    app = await make_app_with_db(db_path)

    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))
    dev.node_desc = make_node_desc(manufacturer_code=0xABCD)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = zha_profile.PROFILE_ID
    ep.device_type = zha_profile.DeviceType.PUMP

    ep.add_input_cluster(Basic.cluster_id)
    ep.add_input_cluster(DisambiguatedCluster.cluster_id)
    ep.add_input_cluster(AmbiguousCluster.cluster_id)

    basic = dev.endpoints[1].basic
    basic.update_attribute(Basic.AttributeDefs.manufacturer, "manufacturer")
    basic.update_attribute(Basic.AttributeDefs.model, "model")

    app.device_initialized(dev)
    await app.shutdown()

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            f"INSERT INTO attributes_cache{zigpy.appdb.DB_V}"
            " (ieee, endpoint_id, cluster_type, cluster_id,"
            "  attr_id, manufacturer_code, status, value, last_updated)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            [
                # Unmigrated row from v13->v14 (disambiguated cluster)
                (str(dev.ieee), 1, 0, 0xFC01, 0x0010, -1, b"\x42", 0),
                # Unmigrated row from v13->v14 (ambiguous cluster)
                (str(dev.ieee), 1, 0, 0xFC02, 0x0020, -1, b"\x99", 0),
                # Manually read through the UI after v13->v14, duplicating the above
                # but with a newer value
                (str(dev.ieee), 1, 0, 0xFC01, 0x0010, 0xABCD, b"\x43", 1.0),
            ],
        )
        conn.commit()

    app = await make_app_with_db(db_path, device_resolver=resolver)
    dev = app.get_device(ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"))

    # Migration runs during load
    disambiguated = dev.endpoints[1].in_clusters[0xFC01]
    ambiguous = dev.endpoints[1].in_clusters[0xFC02]

    # 2 candidates (1 manuf + 1 non-manuf): picked manuf-specific.
    # Uses the newer value from the already-resolved row, not stale/unmigrated value.
    assert disambiguated.get("manuf_attr") == b"\x43"
    assert disambiguated.get("standard_attr") is None

    # 3 candidates: ambiguous, skipped
    assert ambiguous.get("attr_a") is None
    assert ambiguous.get("attr_b") is None
    assert ambiguous.get("attr_c") is None

    await app.shutdown()

    with sqlite3.connect(db_path) as conn:
        # The disambiguated unmigrated row was deleted (a row with 0xABCD already existed)
        rows = conn.execute(
            f"SELECT manufacturer_code FROM attributes_cache{zigpy.appdb.DB_V}"
            " WHERE ieee = ? AND cluster_id = ? AND attr_id = ?",
            (str(dev.ieee), 0xFC01, 0x0010),
        ).fetchall()
        assert rows == [(0xABCD,)]

        # The ambiguous unmigrated row is still present
        rows = conn.execute(
            f"SELECT manufacturer_code FROM attributes_cache{zigpy.appdb.DB_V}"
            " WHERE ieee = ? AND cluster_id = ? AND attr_id = ?",
            (str(dev.ieee), 0xFC02, 0x0020),
        ).fetchall()
        assert rows == [(-1,)]
