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

DB_VERSION = 5
DB_V = f"_v{DB_VERSION}"


def _sqlite_adapters():
    def adapt_ieee(eui64):
        return str(eui64)

    aiosqlite.register_adapter(t.EUI64, adapt_ieee)
    aiosqlite.register_adapter(t.ExtendedPanId, adapt_ieee)

    def convert_ieee(s):
        return t.EUI64.convert(s.decode())

    aiosqlite.register_converter("ieee", convert_ieee)


class PersistingListener(zigpy.util.CatchingTaskMixin):
    def __init__(
        self,
        connection: aiosqlite.Connection,
        application: zigpy.typing.ControllerApplicationType,
    ) -> None:
        _sqlite_adapters()
        self._db = connection
        self._application = application
        self._callback_handlers = asyncio.Queue()
        self.running = False
        self._worker_task = asyncio.create_task(self._worker())

    async def initialize_tables(self) -> None:
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._run_migrations()
        await self._db.commit()

    @classmethod
    async def new(
        cls, database_file: str, app: zigpy.typing.ControllerApplicationType
    ) -> "PersistingListener":
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
            LOGGER.warning(
                "Discarding %s event",
                cb_name,
            )
            return
        self._callback_handlers.put_nowait((cb_name, args))

    def execute(self, *args, **kwargs):
        return self._db.execute(*args, **kwargs)

    def device_joined(self, device: zigpy.typing.DeviceType) -> None:
        pass

    def raw_device_initialized(self, device: zigpy.typing.DeviceType) -> None:
        self.enqueue("_save_device", device)

    def device_initialized(self, device: zigpy.typing.DeviceType) -> None:
        pass

    def device_left(self, device: zigpy.typing.DeviceType) -> None:
        pass

    def device_removed(self, device: zigpy.typing.DeviceType) -> None:
        self.enqueue("_remove_device", device)

    def device_relays_updated(
        self, device: zigpy.typing.DeviceType, relays: bytes
    ) -> None:
        """Device relay list is updated."""
        if relays is None:
            self.enqueue("_save_device_relays_clear", device.ieee)
            return

        self.enqueue(
            "_save_device_relays_update", device.ieee, t.Relays(relays).serialize()
        )

    def attribute_updated(
        self, cluster: zigpy.typing.ClusterType, attrid: int, value: Any
    ) -> None:
        if cluster.endpoint.device.status != zigpy.device.Status.ENDPOINTS_INIT:
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

    async def _remove_device(self, device: zigpy.typing.DeviceType) -> None:
        for table in (
            "attributes",
            "neighbors",
            "node_descriptors",
            "clusters",
            "output_clusters",
            "group_members",
            "endpoints",
            "devices",
        ):
            await self.execute(
                f"DELETE FROM {table}{DB_V} WHERE ieee = ?", (device.ieee,)
            )

        await self._db.commit()

    async def _save_device(self, device: zigpy.typing.DeviceType) -> None:
        if device.status != zigpy.device.Status.ENDPOINTS_INIT:
            LOGGER.warning(
                "Not saving uninitialized %s/%s device: %s",
                device.ieee,
                device.nwk,
                device.status,
            )
            return
        if not device.node_desc.is_valid:
            LOGGER.debug(
                "[0x%04x]: does not have a valid node descriptor, not saving in appdb",
                device.nwk,
            )
            return

        try:
            q = f"INSERT INTO devices{DB_V} (ieee, nwk, status) VALUES (?, ?, ?)"
            await self.execute(q, (device.ieee, device.nwk, device.status))
        except sqlite3.IntegrityError:
            LOGGER.debug("Device %s already exists. Updating it.", device.ieee)
            q = f"UPDATE devices{DB_V} SET nwk=?, status=? WHERE ieee=?"
            await self.execute(q, (device.nwk, device.status, device.ieee))

        await self._save_node_descriptor(device)
        if isinstance(device, zigpy.quirks.CustomDevice):
            await self._db.commit()
            return

        await self._save_endpoints(device)
        for epid, ep in device.endpoints.items():
            if epid == 0:
                # ZDO
                continue
            await self._save_input_clusters(ep)
            await self._save_attribute_cache(ep)
            await self._save_output_clusters(ep)
        await self._db.commit()

    async def _save_endpoints(self, device: zigpy.typing.DeviceType) -> None:
        endpoints = []
        for epid, ep in device.endpoints.items():
            if epid == 0:
                continue  # Skip zdo
            device_type = getattr(ep, "device_type", None)
            eprow = (
                device.ieee,
                ep.endpoint_id,
                getattr(ep, "profile_id", None),
                device_type,
                ep.status,
            )
            endpoints.append(eprow)

        q = f"INSERT OR REPLACE INTO endpoints{DB_V} VALUES (?, ?, ?, ?, ?)"
        await self._db.executemany(q, endpoints)

    async def _save_node_descriptor(self, device: zigpy.typing.DeviceType) -> None:
        await self.execute(
            f"INSERT OR REPLACE INTO node_descriptors{DB_V}"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (device.ieee,) + device.node_desc.as_tuple(),
        )

    async def _save_input_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.in_clusters.values()
        ]
        q = f"INSERT OR REPLACE INTO clusters{DB_V} VALUES (?, ?, ?)"
        await self._db.executemany(q, clusters)

    async def _save_attribute_cache(self, ep: zigpy.typing.EndpointType) -> None:
        clusters = [
            (ep.device.ieee, ep.endpoint_id, cluster.cluster_id, attrid, value)
            for cluster in ep.in_clusters.values()
            for attrid, value in cluster._attr_cache.items()
        ]
        q = f"INSERT OR REPLACE INTO attributes{DB_V} VALUES (?, ?, ?, ?, ?)"
        await self._db.executemany(q, clusters)

    async def _save_output_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.out_clusters.values()
        ]
        q = f"INSERT OR REPLACE INTO output_clusters{DB_V} VALUES (?, ?, ?)"
        await self._db.executemany(q, clusters)

    async def _save_attribute(
        self, ieee: t.EUI64, endpoint_id: int, cluster_id: int, attrid: int, value: Any
    ) -> None:
        q = f"INSERT OR REPLACE INTO attributes{DB_V} VALUES (?, ?, ?, ?, ?)"
        await self.execute(q, (ieee, endpoint_id, cluster_id, attrid, value))
        await self._db.commit()

    async def _save_device_relays_update(self, ieee: t.EUI64, value: bytes) -> None:
        q = f"INSERT OR REPLACE INTO relays{DB_V} VALUES (?, ?)"
        await self.execute(q, (ieee, value))
        await self._db.commit()

    async def _save_device_relays_clear(self, ieee: t.EUI64) -> None:
        await self.execute(f"DELETE FROM relays{DB_V} WHERE ieee = ?", (ieee,))
        await self._db.commit()

    async def load(self) -> None:
        LOGGER.debug("Loading application state from %s")
        await self._load_devices()
        await self._load_node_descriptors()
        await self._load_endpoints()
        await self._load_clusters()

        await self._load_attributes("attrid=4 OR attrid=5")

        for device in self._application.devices.values():
            device = zigpy.quirks.get_device(device)
            self._application.devices[device.ieee] = device

        await self._load_attributes()
        await self._load_groups()
        await self._load_group_members()
        await self._load_relays()
        await self._load_neighbors()
        await self._cleanup()
        await self._finish_loading()

    async def _load_attributes(self, filter: str = None) -> None:
        if filter:
            query = f"SELECT * FROM attributes{DB_V} WHERE {filter}"
        else:
            query = f"SELECT * FROM attributes{DB_V}"
        async with self.execute(query) as cursor:
            async for (ieee, endpoint_id, cluster, attrid, value) in cursor:
                dev = self._application.get_device(ieee)
                if endpoint_id in dev.endpoints:
                    ep = dev.endpoints[endpoint_id]
                    if cluster in ep.in_clusters:
                        clus = ep.in_clusters[cluster]
                        clus._attr_cache[attrid] = value
                        LOGGER.debug(
                            "[0x%04x:%s:0x%04x] Attribute id: %s value: %s",
                            dev.nwk,
                            endpoint_id,
                            cluster,
                            attrid,
                            value,
                        )
                        if cluster == Basic.cluster_id and attrid == 4:
                            if isinstance(value, bytes):
                                value = value.split(b"\x00")[0]
                                dev.manufacturer = value.decode().strip()
                            else:
                                dev.manufacturer = value
                        if cluster == Basic.cluster_id and attrid == 5:
                            if isinstance(value, bytes):
                                value = value.split(b"\x00")[0]
                                dev.model = value.decode().strip()
                            else:
                                dev.model = value

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
                ep.device_type = device_type
                if profile_id == zigpy.profiles.zha.PROFILE_ID:
                    ep.device_type = zigpy.profiles.zha.DeviceType(device_type)
                elif profile_id == zigpy.profiles.zll.PROFILE_ID:
                    ep.device_type = zigpy.profiles.zll.DeviceType(device_type)
                ep.status = zigpy.endpoint.Status(status)

    async def _load_clusters(self) -> None:
        async with self.execute(f"SELECT * FROM clusters{DB_V}") as cursor:
            async for (ieee, endpoint_id, cluster) in cursor:
                dev = self._application.get_device(ieee)
                ep = dev.endpoints[endpoint_id]
                ep.add_input_cluster(cluster)

        async with self.execute(f"SELECT * FROM output_clusters{DB_V}") as cursor:
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
                dev.relays = t.Relays.deserialize(value)[0]

    async def _load_neighbors(self) -> None:
        async with self.execute(f"SELECT * FROM neighbors{DB_V}") as cursor:
            async for ieee, *fields in cursor:
                dev = self._application.get_device(ieee)
                neighbor = zdo_t.Neighbor(*fields)
                assert neighbor.is_valid
                dev.neighbors.add_neighbor(neighbor)

    async def _finish_loading(self):
        for dev in self._application.devices.values():
            dev.add_context_listener(self)
            dev.neighbors.add_context_listener(self)

    async def _cleanup(self) -> None:
        """Validate and clean-up broken devices."""

        # Clone the list of devices so the dict doesn't change size during iteration
        for device in list(self._application.devices.values()):
            if device.nwk == 0x0000:
                continue

            # Remove devices without any non-ZDO endpoints or no node descriptor
            if set(device.endpoints) - {0x00} and device.node_desc.is_valid:
                continue

            LOGGER.warning(
                "Removing incomplete device %s (%s, %s)",
                device.ieee,
                device.node_desc,
                device.endpoints,
            )

            # Remove the device from ControllerApplication as well
            self._application.devices.pop(device.ieee)
            await self._remove_device(device)

    async def _run_migrations(self):
        """Migrates the database to the newest schema."""

        async with self.execute("PRAGMA user_version") as cursor:
            (db_version,) = await cursor.fetchone()

        LOGGER.debug("Current database version is v%s", db_version)

        if db_version == 0:
            # If this is a brand new database, just load the current schema
            await self._db.executescript(zigpy.appdb_schemas.SCHEMAS[DB_VERSION])
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

        for from_db_version, (migration, to_db_version) in {
            0: (self._migrate_to_v4, 4),
            1: (self._migrate_to_v4, 4),
            2: (self._migrate_to_v4, 4),
            3: (self._migrate_to_v4, 4),
            4: (self._migrate_to_v5, 5),
        }.items():
            if db_version > from_db_version:
                continue

            LOGGER.info("Migrating database from v%d to v%d", db_version, to_db_version)

            await self.execute("BEGIN TRANSACTION")
            await migration()
            await self.execute(f"PRAGMA user_version={to_db_version}")
            await self.execute("COMMIT")

            db_version = to_db_version

    async def _migrate_to_v4(self):
        """Schema v4 expanded the node descriptor and neighbor table columns"""
        await self._db.executescript(zigpy.appdb_schemas.SCHEMAS[4])

        # Delete all existing v4 entries, in case a user downgraded and is upgrading
        await self.execute("DELETE FROM node_descriptors_v4")
        await self.execute("DELETE FROM neighbors_v4")

        # Migrate node descriptors
        async with self.execute("SELECT * FROM node_descriptors") as cur:
            async for dev_ieee, value in cur:
                node_desc, rest = zdo_t.NodeDescriptor.deserialize(value)
                assert not rest

                await self.execute(
                    "INSERT INTO node_descriptors_v4"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (dev_ieee,) + node_desc.as_tuple(),
                )

        try:
            # The `neighbors` table was added in v3 but the version number was not
            # incremented. It will cause the subsequent migration to fail. Instead,
            # allow the table creation logic that is run after the migrations to
            # create the missing table.
            await self.execute("SELECT * FROM neighbors")
        except aiosqlite.OperationalError:
            pass
        else:
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
                        "INSERT INTO neighbors_v4" " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (dev_ieee,) + neighbor.as_tuple(),
                    )

    async def _migrate_to_v5(self):
        """Schema v5 introduced global table version suffixes and removed stale rows"""
        await self._db.executescript(zigpy.appdb_schemas.SCHEMAS[5])

        # Copy the devices table first, it should have no conflicts
        await self.execute("DELETE FROM devices_v5")
        await self.execute("INSERT INTO devices_v5 SELECT * FROM devices")

        # Insertion order matters for foreign key constraints but any rows that fail
        # to insert due to constraint violations can be discarded
        for old_table, new_table in {
            "endpoints": "endpoints_v5",
            "clusters": "clusters_v5",
            "output_clusters": "output_clusters_v5",
            "groups": "groups_v5",
            "group_members": "group_members_v5",
            "relays": "relays_v5",
            "attributes": "attributes_v5",
            # These were migrated in v4
            "neighbors_v4": "neighbors_v5",
            "node_descriptors_v4": "node_descriptors_v5",
        }.items():
            # Delete existing entries, in case a user downgraded
            await self.execute(f"DELETE FROM {new_table}")

            async with self.execute(f"SELECT * from {old_table}") as cursor:
                async for row in cursor:
                    placeholders = ",".join("?" * len(row))

                    try:
                        await self.execute(
                            f"INSERT INTO {new_table} VALUES({placeholders})", row
                        )
                    except aiosqlite.IntegrityError as e:
                        LOGGER.warning(
                            "Failed to migrate row %s%s: %s", old_table, row, e
                        )
