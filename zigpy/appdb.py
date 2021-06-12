import asyncio
import logging
import sqlite3
from typing import Any

import aiosqlite

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

DB_VERSION = 4


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

    log = LOGGER.log

    async def initialize_tables(self) -> None:
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._create_table_devices()
        await self._create_table_endpoints()
        await self._create_table_clusters()
        await self._create_table_neighbors()
        await self._create_table_node_descriptors()
        await self._create_table_output_clusters()
        await self._create_table_attributes()
        await self._create_table_groups()
        await self._create_table_group_members()
        await self._create_table_relays()
        await self._run_migrations()
        await self._db.execute("PRAGMA user_version = %s" % (DB_VERSION,))
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
            LOGGER.warning("Discarding %s event", cb_name)
            return
        self._callback_handlers.put_nowait((cb_name, args))

    def execute(self, *args, **kwargs):
        return self._db.execute(*args, **kwargs)

    def device_joined(self, device: zigpy.typing.DeviceType) -> None:
        self.enqueue("_update_device_nwk", device.ieee, device.nwk)

    async def _update_device_nwk(self, ieee: t.EUI64, nwk: t.NWK) -> None:
        await self.execute("UPDATE devices SET nwk=? WHERE ieee=?", (nwk, ieee))
        await self._db.commit()

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
            "DELETE FROM neighbors_v4 WHERE device_ieee = ?", (neighbors.ieee,)
        )

        rows = [(neighbors.ieee,) + n.neighbor.as_tuple() for n in neighbors.neighbors]

        await self._db.executemany(
            "INSERT INTO neighbors_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        await self._db.commit()

    def group_added(self, group: zigpy.group.Group) -> None:
        """Group is added."""
        self.enqueue("_group_added", group)

    async def _group_added(self, group: zigpy.group.Group) -> None:
        q = "INSERT OR REPLACE INTO groups VALUES (?, ?)"
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
        q = "INSERT OR REPLACE INTO group_members VALUES (?, ?, ?)"
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
        q = """DELETE FROM group_members WHERE group_id=?
                                               AND ieee=?
                                               AND endpoint_id=?"""
        await self.execute(q, (group.group_id, *ep.unique_id))
        await self._db.commit()

    def group_removed(self, group: zigpy.group.Group) -> None:
        """Called when a group is removed."""
        self.enqueue("_group_removed", group)

    async def _group_removed(self, group: zigpy.group.Group) -> None:
        q = "DELETE FROM groups WHERE group_id=?"
        await self.execute(q, (group.group_id,))
        await self._db.commit()

    async def _create_table(self, table_name: str, spec: str) -> None:
        await self.execute("CREATE TABLE IF NOT EXISTS %s %s" % (table_name, spec))

    async def _create_index(
        self, index_name: str, table: str, columns: str, unique: bool = True
    ) -> None:
        if unique:
            query = "CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(%s)"
        else:
            query = "CREATE INDEX IF NOT EXISTS %s ON %s(%s)"
        await self.execute(query % (index_name, table, columns))

    async def _create_table_devices(self) -> None:
        await self._create_table("devices", "(ieee ieee, nwk, status)")
        await self._create_index("ieee_idx", "devices", "ieee")

    async def _create_table_endpoints(self) -> None:
        await self._create_table(
            "endpoints",
            (
                "(ieee ieee, endpoint_id, profile_id, device_type device_type, status, "
                "FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE)"
            ),
        )
        await self._create_index("endpoint_idx", "endpoints", "ieee, endpoint_id")

    async def _create_table_clusters(self) -> None:
        await self._create_table(
            "clusters",
            (
                "(ieee ieee, endpoint_id, cluster, "
                "FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints(ieee, endpoint_id)"
                " ON DELETE CASCADE)"
            ),
        )
        await self._create_index(
            "cluster_idx", "clusters", "ieee, endpoint_id, cluster"
        )

    async def _create_table_neighbors(self) -> None:
        idx_name = "neighbors_idx_v4"
        idx_table = "neighbors_v4"
        idx_cols = "device_ieee"
        await self._create_table(
            idx_table,
            """(
                device_ieee ieee NOT NULL,
                extended_pan_id ieee NOT NULL,
                ieee ieee NOT NULL,
                nwk INTEGER NOT NULL,
                device_type INTEGER NOT NULL,
                rx_on_when_idle INTEGER NOT NULL,
                relationship INTEGER NOT NULL,
                reserved1 INTEGER NOT NULL,
                permit_joining INTEGER NOT NULL,
                reserved2 INTEGER NOT NULL,
                depth INTEGER NOT NULL,
                lqi INTEGER NOT NULL
            )""",
        )
        await self._create_index(idx_name, idx_table, idx_cols, unique=False)

    async def _create_table_node_descriptors(self) -> None:
        await self._create_table(
            "node_descriptors_v4",
            """(
                ieee ieee,

                logical_type INTEGER NOT NULL,
                complex_descriptor_available INTEGER NOT NULL,
                user_descriptor_available INTEGER NOT NULL,
                reserved INTEGER NOT NULL,
                aps_flags INTEGER NOT NULL,
                frequency_band INTEGER NOT NULL,
                mac_capability_flags INTEGER NOT NULL,
                manufacturer_code INTEGER NOT NULL,
                maximum_buffer_size INTEGER NOT NULL,
                maximum_incoming_transfer_size INTEGER NOT NULL,
                server_mask INTEGER NOT NULL,
                maximum_outgoing_transfer_size INTEGER NOT NULL,
                descriptor_capability_field INTEGER NOT NULL,

                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE
            )""",
        )
        await self._create_index(
            "node_descriptors_idx_v4", "node_descriptors_v4", "ieee"
        )

    async def _create_table_output_clusters(self) -> None:
        await self._create_table(
            "output_clusters",
            (
                "(ieee ieee, endpoint_id, cluster, "
                "FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints(ieee, endpoint_id)"
                " ON DELETE CASCADE)"
            ),
        )
        await self._create_index(
            "output_cluster_idx", "output_clusters", "ieee, endpoint_id, cluster"
        )

    async def _create_table_attributes(self) -> None:
        await self._create_table(
            "attributes",
            (
                "(ieee ieee, endpoint_id, cluster, attrid, value, "
                "FOREIGN KEY(ieee) "
                "REFERENCES devices(ieee) "
                "ON DELETE CASCADE)"
            ),
        )
        await self._create_index(
            "attribute_idx", "attributes", "ieee, endpoint_id, cluster, attrid"
        )

    async def _create_table_groups(self) -> None:
        await self._create_table("groups", "(group_id, name)")
        await self._create_index("group_idx", "groups", "group_id")

    async def _create_table_group_members(self) -> None:
        await self._create_table(
            "group_members",
            """(group_id, ieee ieee, endpoint_id,
                FOREIGN KEY(group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY(ieee, endpoint_id)
                REFERENCES endpoints(ieee, endpoint_id) ON DELETE CASCADE)""",
        )
        await self._create_index(
            "group_members_idx", "group_members", "group_id, ieee, endpoint_id"
        )

    async def _create_table_relays(self) -> None:
        await self._create_table(
            "relays",
            """(ieee ieee, relays,
                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE)""",
        )
        await self._create_index("relays_idx", "relays", "ieee")

    async def _remove_device(self, device: zigpy.typing.DeviceType) -> None:
        queries = (
            "DELETE FROM attributes WHERE ieee = ?",
            "DELETE FROM neighbors_v4 WHERE ieee = ?",
            "DELETE FROM node_descriptors_v4 WHERE ieee = ?",
            "DELETE FROM clusters WHERE ieee = ?",
            "DELETE FROM output_clusters WHERE ieee = ?",
            "DELETE FROM group_members WHERE ieee = ?",
            "DELETE FROM endpoints WHERE ieee = ?",
            "DELETE FROM devices WHERE ieee = ?",
        )
        for query in queries:
            await self.execute(query, (device.ieee,))
        await self._db.commit()

    async def _save_device(self, device: zigpy.typing.DeviceType) -> None:
        try:
            q = "INSERT INTO devices (ieee, nwk, status) VALUES (?, ?, ?)"
            await self.execute(q, (device.ieee, device.nwk, device.status))
        except sqlite3.IntegrityError:
            LOGGER.debug("Device %s already exists. Updating it.", device.ieee)
            q = "UPDATE devices SET nwk=?, status=? WHERE ieee=?"
            await self.execute(q, (device.nwk, device.status, device.ieee))

        if device.has_node_descriptor:
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
        q = "INSERT OR REPLACE INTO endpoints VALUES (?, ?, ?, ?, ?)"
        endpoints = []
        for ep in device.non_zdo_endpoints:
            device_type = getattr(ep, "device_type", None)
            eprow = (
                device.ieee,
                ep.endpoint_id,
                getattr(ep, "profile_id", None),
                device_type,
                ep.status,
            )
            endpoints.append(eprow)
        await self._db.executemany(q, endpoints)

    async def _save_node_descriptor(self, device: zigpy.typing.DeviceType) -> None:
        await self.execute(
            "INSERT OR REPLACE INTO node_descriptors_v4"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (device.ieee,) + device.node_desc.as_tuple(),
        )

    async def _save_input_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        q = "INSERT OR REPLACE INTO clusters VALUES (?, ?, ?)"
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.in_clusters.values()
        ]
        await self._db.executemany(q, clusters)

    async def _save_attribute_cache(self, ep: zigpy.typing.EndpointType) -> None:
        q = "INSERT OR REPLACE INTO attributes VALUES (?, ?, ?, ?, ?)"
        clusters = [
            (ep.device.ieee, ep.endpoint_id, cluster.cluster_id, attrid, value)
            for cluster in ep.in_clusters.values()
            for attrid, value in cluster._attr_cache.items()
        ]
        await self._db.executemany(q, clusters)

    async def _save_output_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        q = "INSERT OR REPLACE INTO output_clusters VALUES (?, ?, ?)"
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.out_clusters.values()
        ]
        await self._db.executemany(q, clusters)

    async def _save_attribute(
        self, ieee: t.EUI64, endpoint_id: int, cluster_id: int, attrid: int, value: Any
    ) -> None:
        q = "INSERT OR REPLACE INTO attributes VALUES (?, ?, ?, ?, ?)"
        await self.execute(q, (ieee, endpoint_id, cluster_id, attrid, value))
        await self._db.commit()

    async def _save_device_relays_update(self, ieee: t.EUI64, value: bytes) -> None:
        q = "INSERT OR REPLACE INTO relays VALUES (?, ?)"
        await self.execute(q, (ieee, value))
        await self._db.commit()

    async def _save_device_relays_clear(self, ieee: t.EUI64) -> None:
        await self.execute("DELETE FROM relays WHERE ieee = ?", (ieee,))
        await self._db.commit()

    async def load(self) -> None:
        LOGGER.debug("Loading application state")
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
        await self._finish_loading()

    async def _load_attributes(self, filter: str = None) -> None:
        if filter:
            query = f"SELECT * FROM attributes WHERE {filter}"
        else:
            query = "SELECT * FROM attributes"
        async with self.execute(query) as cursor:
            async for (ieee, endpoint_id, cluster, attrid, value) in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid attributes row: %r",
                        (ieee, endpoint_id, cluster, attrid, value),
                    )
                    continue

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
        async with self.execute("SELECT * FROM devices") as cursor:
            async for (ieee, nwk, status) in cursor:
                dev = self._application.add_device(ieee, nwk)
                dev.status = zigpy.device.Status(status)

    async def _load_node_descriptors(self) -> None:
        async with self.execute("SELECT * FROM node_descriptors_v4") as cursor:
            async for (ieee, *fields) in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid node_descriptors_v4 row: %r",
                        (ieee,) + tuple(fields),
                    )
                    continue

                dev.node_desc = zdo_t.NodeDescriptor(*fields)
                assert dev.node_desc.is_valid

    async def _load_endpoints(self) -> None:
        async with self.execute("SELECT * FROM endpoints") as cursor:
            async for (ieee, epid, profile_id, device_type, status) in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid endpoints row: %r",
                        (ieee, epid, profile_id, device_type, status),
                    )
                    continue

                ep = dev.add_endpoint(epid)
                ep.profile_id = profile_id
                ep.device_type = device_type
                if profile_id == zigpy.profiles.zha.PROFILE_ID:
                    ep.device_type = zigpy.profiles.zha.DeviceType(device_type)
                elif profile_id == zigpy.profiles.zll.PROFILE_ID:
                    ep.device_type = zigpy.profiles.zll.DeviceType(device_type)
                ep.status = zigpy.endpoint.Status(status)

    async def _load_clusters(self) -> None:
        async with self.execute("SELECT * FROM clusters") as cursor:
            async for (ieee, endpoint_id, cluster) in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid clusters row: %r",
                        (ieee, endpoint_id, cluster),
                    )
                    continue

                ep = dev.endpoints[endpoint_id]
                ep.add_input_cluster(cluster)

        async with self.execute("SELECT * FROM output_clusters") as cursor:
            async for (ieee, endpoint_id, cluster) in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid output_clusters row: %r",
                        (ieee, endpoint_id, cluster),
                    )
                    continue

                ep = dev.endpoints[endpoint_id]
                ep.add_output_cluster(cluster)

    async def _load_groups(self) -> None:
        async with self.execute("SELECT * FROM groups") as cursor:
            async for (group_id, name) in cursor:
                self._application.groups.add_group(group_id, name, suppress_event=True)

    async def _load_group_members(self) -> None:
        async with self.execute("SELECT * FROM group_members") as cursor:
            async for (group_id, ieee, ep_id) in cursor:
                try:
                    group = self._application.groups[group_id]
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid group_members row: %r",
                        (group_id, ieee, ep_id),
                    )
                    continue

                group.add_member(dev.endpoints[ep_id], suppress_event=True)

    async def _load_relays(self) -> None:
        async with self.execute("SELECT * FROM relays") as cursor:
            async for (ieee, value) in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning("Skipping invalid relays row: %r", (ieee, value))
                    continue

                dev.relays = t.Relays.deserialize(value)[0]

    async def _load_neighbors(self) -> None:
        async with self.execute("SELECT * FROM neighbors_v4") as cursor:
            async for ieee, *fields in cursor:
                try:
                    dev = self._application.get_device(ieee)
                except KeyError:
                    LOGGER.warning(
                        "Skipping invalid neighbors_v4 row: %r", (ieee,) + tuple(fields)
                    )
                    continue

                neighbor = zdo_t.Neighbor(*fields)
                assert neighbor.is_valid
                dev.neighbors.add_neighbor(neighbor)

    async def _finish_loading(self):
        for dev in self._application.devices.values():
            dev.add_context_listener(self)
            dev.neighbors.add_context_listener(self)

    async def _run_migrations(self):
        async with self._db.execute("PRAGMA user_version") as cursor:
            (db_version,) = await cursor.fetchone()

        # If this is a new database, do not run migrations. They will fail due to
        # missing tables
        if db_version == 0:
            return

        # Version 4 introduced migrations and expanded tables
        if db_version < 4:
            await self.execute("BEGIN TRANSACTION")
            await self.execute("PRAGMA user_version = 4")

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
                            "INSERT INTO neighbors_v4"
                            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (dev_ieee,) + neighbor.as_tuple(),
                        )

            await self.execute("COMMIT")
