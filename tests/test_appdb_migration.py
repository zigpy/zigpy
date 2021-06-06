import logging
import pathlib
import sqlite3

import pytest

import zigpy.appdb
import zigpy.types as t
from zigpy.zdo import types as zdo_t

from tests.async_mock import patch
from tests.test_appdb import auto_kill_aiosqlite, make_app  # noqa: F401


@pytest.fixture
def test_db(tmpdir):
    def inner(filename):
        databases = pathlib.Path(__file__).parent / "databases"
        db_path = pathlib.Path(tmpdir / filename)

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


@pytest.mark.parametrize("open_twice", [False, True])
async def test_migration_from_3_to_4(open_twice, test_db):
    test_db_v3 = test_db("simple_v3.sql")

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()

        neighbors_before = list(cur.execute("SELECT * FROM neighbors"))
        assert len(neighbors_before) == 2
        assert all([len(row) == 8 for row in neighbors_before])

        node_descs_before = list(cur.execute("SELECT * FROM node_descriptors"))
        assert len(node_descs_before) == 2
        assert all([len(row) == 2 for row in node_descs_before])

    # Ensure migration works on first run, and after shutdown
    if open_twice:
        app = await make_app(test_db_v3)
        await app.pre_shutdown()

    app = await make_app(test_db_v3)

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
    assert len(dev1.neighbors) == 1
    assert dev1.neighbors[0].neighbor == zdo_t.Neighbor(
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
    assert len(dev2.neighbors) == 1
    assert dev2.neighbors[0].neighbor == zdo_t.Neighbor(
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

    await app.pre_shutdown()

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()

        # Old tables are untouched
        assert neighbors_before == list(cur.execute("SELECT * FROM neighbors"))
        assert node_descs_before == list(cur.execute("SELECT * FROM node_descriptors"))

        # New tables exist
        neighbors_after = list(cur.execute("SELECT * FROM neighbors_v4"))
        assert len(neighbors_after) == 2
        assert all([len(row) == 12 for row in neighbors_after])

        node_descs_after = list(cur.execute("SELECT * FROM node_descriptors_v4"))
        assert len(node_descs_after) == 2
        assert all([len(row) == 14 for row in node_descs_after])


async def test_migration_0_to_5(test_db):
    test_db_v0 = test_db("zigbee_20190417_v0.db")

    with sqlite3.connect(test_db_v0) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM devices")
        (num_devices_before_migration,) = cur.fetchone()

    assert num_devices_before_migration == 27

    app1 = await make_app(test_db_v0)
    await app1.pre_shutdown()
    assert len(app1.devices) == 27

    app2 = await make_app(test_db_v0)
    await app2.pre_shutdown()

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
    app = await make_app(test_db_v3)
    await app.pre_shutdown()

    # Version was upgraded
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        assert cur.fetchone() == (zigpy.appdb.DB_VERSION,)


@pytest.mark.parametrize("force_version", [None, 3, 4, 9999])
@pytest.mark.parametrize("corrupt_device", [False, True])
async def test_migration_bad_attributes(test_db, force_version, corrupt_device):
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
    app = await make_app(test_db_bad_attrs)
    await app.pre_shutdown()

    assert len(app.devices) == num_devices_before_migration
    assert (
        sum(len(d.non_zdo_endpoints) for d in app.devices.values())
        == num_ep_before_migration - deleted_eps
    )

    # Version was upgraded (and then downgraded)
    with sqlite3.connect(test_db_bad_attrs) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        assert cur.fetchone() == (zigpy.appdb.DB_VERSION,)

        if force_version is not None:
            cur.execute(f"PRAGMA user_version={force_version}")

    app2 = await make_app(test_db_bad_attrs)
    await app2.pre_shutdown()

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
        assert cur.fetchone()[0] == max(zigpy.appdb.DB_VERSION, force_version or 0)


async def test_migration_missing_node_descriptor(test_db, caplog):
    test_db_v3 = test_db("simple_v3.sql")
    ieee = "ec:1b:bd:ff:fe:54:4f:40"

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM node_descriptors WHERE ieee=?", [ieee])

    with caplog.at_level(logging.WARNING):
        # The invalid device will still be loaded, for now
        app = await make_app(test_db_v3)

    assert "partially initialized" in caplog.text

    assert len(app.devices) == 2

    bad_dev = app.devices[t.EUI64.convert(ieee)]
    assert bad_dev.node_desc is None

    caplog.clear()

    # Saving the device should cause the node descriptor to not be saved
    await app._dblistener._save_device(bad_dev)
    await app.pre_shutdown()

    # The node descriptor is not in the database
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM node_descriptors{zigpy.appdb.DB_V} WHERE ieee=?", [ieee]
        )

        assert not cur.fetchall()


def dump_db(path):
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        (user_version,) = cur.fetchone()

        sql = "\n".join(conn.iterdump())

    return user_version, sql


@pytest.mark.parametrize(
    "fail_on_sql,fail_on_count",
    [
        ("INSERT INTO node_descriptors_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", 0),
        ("INSERT INTO neighbors_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", 5),
        ("SELECT * FROM output_clusters", 0),
        ("INSERT INTO neighbors_v5 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", 5),
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
            await make_app(test_db_bad_attrs)

    assert sql_seen

    after = dump_db(test_db_bad_attrs)
    assert before == after
