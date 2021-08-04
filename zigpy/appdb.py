from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Any

import aiosqlite

import zigpy.appdb_schemas
import zigpy.device
import zigpy.endpoint
import zigpy.group
import zigpy.neighbor
import zigpy.profiles
import zigpy.quirks
import zigpy.types as t
import zigpy.typing
import zigpy.util
from zigpy.zcl.clusters.general import Basic
from zigpy.zdo import types as zdo_t

LOGGER = logging.getLogger(__name__)

DB_VERSION = 6
DB_V = f"_v{DB_VERSION}"


def _register_sqlite_adapters():
    def adapt_ieee(eui64):
        return str(eui64)

    aiosqlite.register_adapter(t.EUI64, adapt_ieee)
    aiosqlite.register_adapter(t.ExtendedPanId, adapt_ieee)

    def convert_ieee(s):
        return t.EUI64.convert(s.decode())

    aiosqlite.register_converter("ieee", convert_ieee)


def decode_str_attribute(value: str | bytes) -> str:
    if isinstance(value, str):
        return value

    return value.split(b"\x00", 1)[0].decode("utf-8")


class PersistingListener(zigpy.util.CatchingTaskMixin):
    def __init__(
        self,
        connection: aiosqlite.Connection,
        application: zigpy.typing.ControllerApplicationType,
    ) -> None:
        _register_sqlite_adapters()

        self._db = connection
        self._application = application
        self._callback_handlers = asyncio.Queue()
        self.running = False
        self._worker_task = asyncio.create_task(self._worker())

    async def initialize_tables(self) -> None:
        async with self.execute("PRAGMA integrity_check") as cursor:
            rows = await cursor.fetchall()
            status = "\n".join(row[0] for row in rows)

            if status != "ok":
                LOGGER.error("SQLite database file is corrupted!\n%s", status)

        await self.execute("PRAGMA foreign_keys = ON")
        await self._run_migrations()

    @classmethod
    async def new(
        cls, database_file: str, app: zigpy.typing.ControllerApplicationType
    ) -> PersistingListener:
        """Create an instance of persisting listener."""
        sqlite_conn = await aiosqlite.connect(
            database_file, detect_types=sqlite3.PARSE_DECLTYPES
        )
        listener = cls(sqlite_conn, app)

        try:
            await listener.initialize_tables()
        except asyncio.CancelledError:
            raise
        except Exception:
            await listener.shutdown()
            raise

        listener.running = True
        return listener

    async def _worker(self) -> None:
        """Process request in the received order."""
        while True:
            cb_name, args = await self._callback_handlers.get()
            handler = getattr(self, cb_name)
            assert handler
            try:
                await handler(*args)
            except aiosqlite.Error as exc:
                LOGGER.debug(
                    "Error handling '%s' event with %s params: %s",
                    cb_name,
                    args,
                    str(exc),
                )
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                LOGGER.error(
                    "Unexpected error while processing %s(%s): %s", cb_name, args, ex
                )
            self._callback_handlers.task_done()

    async def shutdown(self) -> None:
        """Shutdown connection."""
        self.running = False
        await self._callback_handlers.join()
        if not self._worker_task.done():
            self._worker_task.cancel()
        await self._db.close()

    def enqueue(self, cb_name: str, *args) -> None:
        """Enqueue an async callback handler action."""
        if not self.running:
            LOGGER.warning("Discarding %s event", cb_name)
            return
        self._callback_handlers.put_nowait((cb_name, args))

    def execute(self, *args, **kwargs):
        return self._db.execute(*args, **kwargs)

    async def executescript(self, sql):
        """
        Naive replacement for `sqlite3.Cursor.executescript` that does not execute a
        `COMMIT` before running the script. This extra `COMMIT` breaks transactions that
        run scripts.
        """

        # XXX: This will break if you use a semicolon anywhere but at the end of a line
        for statement in sql.split(";"):
            await self.execute(statement)

    def device_joined(self, device: zigpy.typing.DeviceType) -> None:
        self.enqueue("_update_device_nwk", device.ieee, device.nwk)

    async def _update_device_nwk(self, ieee: t.EUI64, nwk: t.NWK) -> None:
        await self.execute(f"UPDATE devices{DB_V} SET nwk=? WHERE ieee=?", (nwk, ieee))
        await self._db.commit()

    def device_initialized(self, device: zigpy.typing.DeviceType) -> None:
        pass

    def device_left(self, device: zigpy.typing.DeviceType) -> None:
        pass

    def device_relays_updated(
        self, device: zigpy.typing.DeviceType, relays: t.Relays | None
    ) -> None:
        """Device relay list is updated."""
        self.enqueue("_save_device_relays", device.ieee, relays)

    async def _save_device_relays(self, ieee: t.EUI64, relays: t.Relays | None) -> None:
        if relays is None:
            await self.execute(f"DELETE FROM relays{DB_V} WHERE ieee = ?", (ieee,))
        else:
            q = f"INSERT OR REPLACE INTO relays{DB_V} VALUES (?, ?)"
            await self.execute(q, (ieee, relays.serialize()))

        await self._db.commit()

    def attribute_updated(
        self, cluster: zigpy.typing.ClusterType, attrid: int, value: Any
    ) -> None:
        if not cluster.endpoint.device.is_initialized:
            return

        self.enqueue(
            "_save_attribute",
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_id,
            attrid,
            value,
        )

    def neighbors_updated(self, neighbors: zigpy.neighbor.Neighbors) -> None:
        """Neighbor update from ZDO_Lqi_rsp."""
        self.enqueue("_neighbors_updated", neighbors)

    async def _neighbors_updated(self, neighbors: zigpy.neighbor.Neighbors) -> None:
        await self.execute(
            f"DELETE FROM neighbors{DB_V} WHERE device_ieee = ?", (neighbors.ieee,)
        )

        rows = [(neighbors.ieee,) + n.neighbor.as_tuple() for n in neighbors.neighbors]

        await self._db.executemany(
            f"INSERT INTO neighbors{DB_V} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        await self._db.commit()

    def group_added(self, group: zigpy.group.Group) -> None:
        """Group is added."""
        self.enqueue("_group_added", group)

    async def _group_added(self, group: zigpy.group.Group) -> None:
        q = f"INSERT OR REPLACE INTO groups{DB_V} VALUES (?, ?)"
        await self.execute(q, (group.group_id, group.name))
        await self._db.commit()

    def group_member_added(
        self, group: zigpy.group.Group, ep: zigpy.typing.EndpointType
    ) -> None:
        """Called when a group member is added."""
        self.enqueue("_group_member_added", group, ep)

    async def _group_member_added(
        self, group: zigpy.group.Group, ep: zigpy.typing.EndpointType
    ) -> None:
        q = f"INSERT OR REPLACE INTO group_members{DB_V} VALUES (?, ?, ?)"
        await self.execute(q, (group.group_id, *ep.unique_id))
        await self._db.commit()

    def group_member_removed(
        self, group: zigpy.group.Group, ep: zigpy.typing.EndpointType
    ) -> None:
        """Called when a group member is removed."""
        self.enqueue("_group_member_removed", group, ep)

    async def _group_member_removed(
        self, group: zigpy.group.Group, ep: zigpy.typing.EndpointType
    ) -> None:
        q = f"""DELETE FROM group_members{DB_V} WHERE group_id=?
                                                AND ieee=?
                                                AND endpoint_id=?"""
        await self.execute(q, (group.group_id, *ep.unique_id))
        await self._db.commit()

    def group_removed(self, group: zigpy.group.Group) -> None:
        """Called when a group is removed."""
        self.enqueue("_group_removed", group)

    async def _group_removed(self, group: zigpy.group.Group) -> None:
        q = f"DELETE FROM groups{DB_V} WHERE group_id=?"
        await self.execute(q, (group.group_id,))
        await self._db.commit()

    def device_removed(self, device: zigpy.typing.DeviceType) -> None:
        self.enqueue("_remove_device", device)

    async def _remove_device(self, device: zigpy.typing.DeviceType) -> None:
        await self.execute(f"DELETE FROM devices{DB_V} WHERE ieee = ?", (device.ieee,))
        await self._db.commit()

    def raw_device_initialized(self, device: zigpy.typing.DeviceType) -> None:
        self.enqueue("_save_device", device)

    async def _save_device(self, device: zigpy.typing.DeviceType) -> None:
        try:
            q = f"INSERT INTO devices{DB_V} (ieee, nwk, status) VALUES (?, ?, ?)"
            await self.execute(q, (device.ieee, device.nwk, device.status))
        except aiosqlite.IntegrityError:
            LOGGER.debug("Device %s already exists. Updating it.", device.ieee)
            q = f"UPDATE devices{DB_V} SET nwk=?, status=? WHERE ieee=?"
            await self.execute(q, (device.nwk, device.status, device.ieee))

        if device.node_desc is not None:
            await self._save_node_descriptor(device)

        if isinstance(device, zigpy.quirks.CustomDevice):
            await self._db.commit()
            return

        await self._save_endpoints(device)
        for ep in device.non_zdo_endpoints:
            await self._save_input_clusters(ep)
            await self._save_attribute_cache(ep)
            await self._save_output_clusters(ep)
        await self._db.commit()

    async def _save_endpoints(self, device: zigpy.typing.DeviceType) -> None:
        endpoints = []
        for ep in device.non_zdo_endpoints:
            eprow = (
                device.ieee,
                ep.endpoint_id,
                ep.profile_id,
                ep.device_type,
                ep.status,
            )
            endpoints.append(eprow)

        q = f"INSERT OR REPLACE INTO endpoints{DB_V} VALUES (?, ?, ?, ?, ?)"
        await self._db.executemany(q, endpoints)

    async def _save_node_descriptor(self, device: zigpy.typing.DeviceType) -> None:
        await self.execute(
            f"INSERT OR REPLACE INTO node_descriptors{DB_V}"
            f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (device.ieee,) + device.node_desc.as_tuple(),
        )

    async def _save_input_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.in_clusters.values()
        ]
        q = f"INSERT OR REPLACE INTO in_clusters{DB_V} VALUES (?, ?, ?)"
        await self._db.executemany(q, clusters)

    async def _save_attribute_cache(self, ep: zigpy.typing.EndpointType) -> None:
        clusters = [
            (ep.device.ieee, ep.endpoint_id, cluster.cluster_id, attrid, value)
            for cluster in ep.in_clusters.values()
            for attrid, value in cluster._attr_cache.items()
        ]
        q = f"INSERT OR REPLACE INTO attributes_cache{DB_V} VALUES (?, ?, ?, ?, ?)"
        await self._db.executemany(q, clusters)

    async def _save_output_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.out_clusters.values()
        ]
        q = f"INSERT OR REPLACE INTO out_clusters{DB_V} VALUES (?, ?, ?)"
        await self._db.executemany(q, clusters)

    async def _save_attribute(
        self, ieee: t.EUI64, endpoint_id: int, cluster_id: int, attrid: int, value: Any
    ) -> None:
        q = f"INSERT OR REPLACE INTO attributes_cache{DB_V} VALUES (?, ?, ?, ?, ?)"
        await self.execute(q, (ieee, endpoint_id, cluster_id, attrid, value))
        await self._db.commit()

    async def load(self) -> None:
        LOGGER.debug("Loading application state")
        await self._load_devices()
        await self._load_node_descriptors()
        await self._load_endpoints()
        await self._load_clusters()

        # Quirks require the manufacturer and model name to be populated
        await self._load_attributes("attrid=4 OR attrid=5")

        for device in self._application.devices.values():
            device = zigpy.quirks.get_device(device)
            self._application.devices[device.ieee] = device

        await self._load_attributes()
        await self._load_groups()
        await self._load_group_members()
        await self._load_relays()
        await self._load_neighbors()
        await self._register_device_listeners()

    async def _load_attributes(self, filter: str = None) -> None:
        if filter:
            query = f"SELECT * FROM attributes_cache{DB_V} WHERE {filter}"
        else:
            query = f"SELECT * FROM attributes_cache{DB_V}"

        async with self.execute(query) as cursor:
            async for (ieee, endpoint_id, cluster, attrid, value) in cursor:
                dev = self._application.get_device(ieee)

                # Some quirks create endpoints and clusters that do not exist
                if endpoint_id not in dev.endpoints:
                    continue

                ep = dev.endpoints[endpoint_id]

                if cluster not in ep.in_clusters:
                    continue

                ep.in_clusters[cluster]._attr_cache[attrid] = value

                LOGGER.debug(
                    "[0x%04x:%s:0x%04x] Attribute id: %s value: %s",
                    dev.nwk,
                    endpoint_id,
                    cluster,
                    attrid,
                    value,
                )

                # Populate the device's manufacturer and model attributes
                if cluster == Basic.cluster_id and attrid == 4:
                    dev.manufacturer = decode_str_attribute(value)
                elif cluster == Basic.cluster_id and attrid == 5:
                    dev.model = decode_str_attribute(value)

    async def _load_devices(self) -> None:
        async with self.execute(f"SELECT * FROM devices{DB_V}") as cursor:
            async for (ieee, nwk, status) in cursor:
                dev = self._application.add_device(ieee, nwk)
                dev.status = zigpy.device.Status(status)

    async def _load_node_descriptors(self) -> None:
        async with self.execute(f"SELECT * FROM node_descriptors{DB_V}") as cursor:
            async for (ieee, *fields) in cursor:
                dev = self._application.get_device(ieee)
                dev.node_desc = zdo_t.NodeDescriptor(*fields)
                assert dev.node_desc.is_valid

    async def _load_endpoints(self) -> None:
        async with self.execute(f"SELECT * FROM endpoints{DB_V}") as cursor:
            async for (ieee, epid, profile_id, device_type, status) in cursor:
                dev = self._application.get_device(ieee)
                ep = dev.add_endpoint(epid)
                ep.profile_id = profile_id
                ep.status = zigpy.endpoint.Status(status)

                if profile_id == zigpy.profiles.zha.PROFILE_ID:
                    ep.device_type = zigpy.profiles.zha.DeviceType(device_type)
                elif profile_id == zigpy.profiles.zll.PROFILE_ID:
                    ep.device_type = zigpy.profiles.zll.DeviceType(device_type)
                else:
                    ep.device_type = device_type

    async def _load_clusters(self) -> None:
        async with self.execute(f"SELECT * FROM in_clusters{DB_V}") as cursor:
            async for (ieee, endpoint_id, cluster) in cursor:
                dev = self._application.get_device(ieee)
                ep = dev.endpoints[endpoint_id]
                ep.add_input_cluster(cluster)

        async with self.execute(f"SELECT * FROM out_clusters{DB_V}") as cursor:
            async for (ieee, endpoint_id, cluster) in cursor:
                dev = self._application.get_device(ieee)
                ep = dev.endpoints[endpoint_id]
                ep.add_output_cluster(cluster)

    async def _load_groups(self) -> None:
        async with self.execute(f"SELECT * FROM groups{DB_V}") as cursor:
            async for (group_id, name) in cursor:
                self._application.groups.add_group(group_id, name, suppress_event=True)

    async def _load_group_members(self) -> None:
        async with self.execute(f"SELECT * FROM group_members{DB_V}") as cursor:
            async for (group_id, ieee, ep_id) in cursor:
                dev = self._application.get_device(ieee)
                group = self._application.groups[group_id]
                group.add_member(
                    dev.endpoints[ep_id],
                    suppress_event=True,
                )

    async def _load_relays(self) -> None:
        async with self.execute(f"SELECT * FROM relays{DB_V}") as cursor:
            async for (ieee, value) in cursor:
                dev = self._application.get_device(ieee)
                dev.relays, _ = t.Relays.deserialize(value)

    async def _load_neighbors(self) -> None:
        async with self.execute(f"SELECT * FROM neighbors{DB_V}") as cursor:
            async for ieee, *fields in cursor:
                dev = self._application.get_device(ieee)
                neighbor = zdo_t.Neighbor(*fields)
                assert neighbor.is_valid
                dev.neighbors.add_neighbor(neighbor)

    async def _register_device_listeners(self) -> None:
        for dev in self._application.devices.values():
            dev.add_context_listener(self)
            dev.neighbors.add_context_listener(self)

    async def _table_exists(self, name: str) -> bool:
        async with self.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
            [name],
        ) as cursor:
            (count,) = await cursor.fetchone()

        return bool(count)

    async def _run_migrations(self):
        """Migrates the database to the newest schema."""

        async with self.execute("PRAGMA user_version") as cursor:
            (db_version,) = await cursor.fetchone()

        LOGGER.debug("Current database version is v%s", db_version)

        # Very old databases did not set `user_version` but still should be migrated
        if db_version == 0 and not await self._table_exists("devices"):
            # If this is a brand new database, just load the current schema
            await self.executescript(zigpy.appdb_schemas.SCHEMAS[DB_VERSION])
            return
        elif db_version > DB_VERSION:
            LOGGER.error(
                "This zigpy release uses database schema v%s but the database is v%s."
                " Downgrading zigpy is *not* recommended and may result in data loss."
                " Use at your own risk.",
                DB_VERSION,
                db_version,
            )
            return

        # All migrations must succeed. If any fail, the database is not touched.
        await self.execute("BEGIN TRANSACTION")

        try:
            for migration, to_db_version in [
                (self._migrate_to_v4, 4),
                (self._migrate_to_v5, 5),
                (self._migrate_to_v6, 6),
            ]:
                if db_version >= min(to_db_version, DB_VERSION):
                    continue

                LOGGER.info(
                    "Migrating database from v%d to v%d", db_version, to_db_version
                )
                await self.executescript(zigpy.appdb_schemas.SCHEMAS[to_db_version])
                await migration()

                db_version = to_db_version
        except Exception:
            await self.execute("ROLLBACK")
            raise
        else:
            await self.execute("COMMIT")

    async def _migrate_tables(
        self, table_map: dict[str, str], *, errors: str = "raise"
    ):
        """Copy rows from one set of tables into another."""

        # Insertion order matters for foreign key constraints but any rows that fail
        # to insert due to constraint violations can be discarded
        for old_table, new_table in table_map.items():
            async with self.execute(f"SELECT * FROM {old_table}") as cursor:
                async for row in cursor:
                    placeholders = ",".join("?" * len(row))

                    try:
                        await self.execute(
                            f"INSERT INTO {new_table} VALUES ({placeholders})", row
                        )
                    except aiosqlite.IntegrityError as e:
                        if errors == "raise":
                            raise
                        elif errors == "warn":
                            LOGGER.warning(
                                "Failed to migrate row %s%s: %s", old_table, row, e
                            )
                        elif errors == "ignore":
                            pass
                        else:
                            raise ValueError(
                                f"Invalid value for `errors`: {errors}!r"
                            )  # noqa

    async def _migrate_to_v4(self):
        """Schema v4 expanded the node descriptor and neighbor table columns"""
        # The `node_descriptors` table was added in v1
        if await self._table_exists("node_descriptors"):
            async with self.execute("SELECT * FROM node_descriptors") as cur:
                async for dev_ieee, value in cur:
                    node_desc, rest = zdo_t.NodeDescriptor.deserialize(value)
                    assert not rest

                    await self.execute(
                        "INSERT INTO node_descriptors_v4"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (dev_ieee,) + node_desc.as_tuple(),
                    )

        # The `neighbors` table was added in v3 but the version number was not
        # incremented. It may not exist.
        if await self._table_exists("neighbors"):
            async with self.execute("SELECT * FROM neighbors") as cur:
                async for dev_ieee, epid, ieee, nwk, packed, prm, depth, lqi in cur:
                    neighbor = zdo_t.Neighbor(
                        extended_pan_id=epid,
                        ieee=ieee,
                        nwk=nwk,
                        permit_joining=prm,
                        depth=depth,
                        lqi=lqi,
                        reserved2=0b000000,
                        **zdo_t.Neighbor._parse_packed(packed),
                    )

                    await self.execute(
                        "INSERT INTO neighbors_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (dev_ieee,) + neighbor.as_tuple(),
                    )

    async def _migrate_to_v5(self):
        """Schema v5 introduced global table version suffixes and removed stale rows"""

        # Copy the devices table first, it should have no conflicts
        await self.execute("INSERT INTO devices_v5 SELECT * FROM devices")
        await self._migrate_tables(
            {
                "endpoints": "endpoints_v5",
                "clusters": "in_clusters_v5",
                "output_clusters": "out_clusters_v5",
                "groups": "groups_v5",
                "group_members": "group_members_v5",
                "relays": "relays_v5",
                "attributes": "attributes_cache_v5",
                # These were migrated in v4
                "neighbors_v4": "neighbors_v5",
                "node_descriptors_v4": "node_descriptors_v5",
            },
            errors="warn",
        )

    async def _migrate_to_v6(self):
        """Schema v6 relaxed the `attribute_cache` table schema to ignore endpoints"""

        # Copy the devices table first, it should have no conflicts
        await self.execute("INSERT INTO devices_v6 SELECT * FROM devices_v5")
        await self._migrate_tables(
            {
                "endpoints_v5": "endpoints_v6",
                "in_clusters_v5": "in_clusters_v6",
                "out_clusters_v5": "out_clusters_v6",
                "groups_v5": "groups_v6",
                "group_members_v5": "group_members_v6",
                "relays_v5": "relays_v6",
                "attributes_cache_v5": "attributes_cache_v6",
                "neighbors_v5": "neighbors_v6",
                "node_descriptors_v5": "node_descriptors_v6",
            }
        )

        # See if we can migrate any `attributes_cache` rows skipped by the v5 migration
        if await self._table_exists("attributes"):
            async with self.execute("SELECT count(*) FROM attributes") as cur:
                (num_attrs_v4,) = await cur.fetchone()

            async with self.execute("SELECT count(*) FROM attributes_cache_v6") as cur:
                (num_attrs_v6,) = await cur.fetchone()

            if num_attrs_v6 < num_attrs_v4:
                LOGGER.warning(
                    "Migrating up to %d rows skipped by v5 migration",
                    num_attrs_v4 - num_attrs_v6,
                )

                await self._migrate_tables(
                    {"attributes": "attributes_cache_v6"}, errors="ignore"
                )
