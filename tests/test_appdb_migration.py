import pathlib
import sqlite3

import pytest

import zigpy.appdb
import zigpy.types as t
from zigpy.zdo import types as zdo_t

from tests.test_appdb import make_app


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


async def test_migration_bad_attributes(test_db):
    test_db_bad_attrs = test_db("bad_attrs_v3.db")

    # Migration will handle invalid attributes entries
    app = await make_app(test_db_bad_attrs)
    await app.pre_shutdown()

    # Version was upgraded
    with sqlite3.connect(test_db_bad_attrs) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        assert cur.fetchone() == (zigpy.appdb.DB_VERSION,)

    # All devices still exist
    app2 = await make_app(test_db_bad_attrs)
    await app2.pre_shutdown()

    assert len(app2.devices) == 29
    assert sum(len(d.endpoints) - 1 for d in app2.devices.values()) == 54
    assert sum(len(d.endpoints) - 1 for d in app2.devices.values()) == 54
