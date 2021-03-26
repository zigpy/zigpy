import pathlib
import sqlite3

import pytest

import zigpy.types as t
from zigpy.zdo import types as zdo_t

from tests.async_mock import AsyncMock, patch
from tests.test_appdb import make_app


@pytest.fixture
def test_db_v3(tmpdir):
    db_path = str(tmpdir / "zigbee.db")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    sql = (pathlib.Path(__file__).parent / "database_v3.sql").read_text()

    for statement in sql.split(";"):
        cur.execute(statement)

    conn.commit()
    conn.close()

    yield db_path


@pytest.mark.parametrize("open_twice", [False, True])
async def test_migration_3_to_4(open_twice, test_db_v3):
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        neighbors_rows_before = list(cur.execute("SELECT * FROM neighbors"))

    assert len(neighbors_rows_before) == 2
    assert all([len(row) == 8 for row in neighbors_rows_before])

    # Ensure migration works on first run, and after shutdown
    if open_twice:
        app = await make_app(test_db_v3)
        await app.pre_shutdown()

    app = await make_app(test_db_v3)

    dev1 = app.get_device(nwk=0xBD4D)
    dev2 = app.get_device(nwk=0x6D1C)

    assert len(dev1.neighbors) == 1
    assert len(dev2.neighbors) == 1

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
        neighbors_rows_after = list(cur.execute("SELECT * FROM neighbors"))

    assert len(neighbors_rows_after) == 2
    assert all([len(row) == 12 for row in neighbors_rows_after])


async def test_migration_rollback(test_db_v3):
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        neighbors_rows_before = list(cur.execute("SELECT * FROM neighbors"))
        assert len(neighbors_rows_before) == 2

    # It will fail once
    with patch(
        "zigpy.appdb.PersistingListener._create_table_neighbors",
        AsyncMock(side_effect=[RuntimeError()]),
    ):
        with pytest.raises(RuntimeError):
            app = await make_app(test_db_v3)

    # Ensure nothing was touched
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        neighbors_rows_after = list(cur.execute("SELECT * FROM neighbors"))

    assert neighbors_rows_before == neighbors_rows_after

    # The second time it will work
    app = await make_app(test_db_v3)
    await app.pre_shutdown()

    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        neighbors_rows_success = list(cur.execute("SELECT * FROM neighbors"))

    assert neighbors_rows_before != neighbors_rows_success


async def test_migration_missing_neighbors_v3(test_db_v3):
    with sqlite3.connect(test_db_v3) as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE neighbors")

        # Ensure the table doesn't exist
        with pytest.raises(sqlite3.OperationalError):
            cur.execute("SELECT * FROM neighbors")

    # Migration won't fail even though the database version number is 3
    app = await make_app(test_db_v3)
    await app.pre_shutdown()
