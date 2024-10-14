from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import types
from typing import Any

import aiosqlite

import zigpy.appdb_schemas
import zigpy.backups
import zigpy.device
import zigpy.endpoint
import zigpy.exceptions
import zigpy.group
import zigpy.profiles
import zigpy.quirks
import zigpy.state
import zigpy.types as t
import zigpy.typing
import zigpy.util
from zigpy.zcl import ClusterType
from zigpy.zcl.clusters.general import Basic
from zigpy.zdo import types as zdo_t

LOGGER = logging.getLogger(__name__)

DB_VERSION = 13
DB_V = f"_v{DB_VERSION}"
MIN_SQLITE_VERSION = (3, 24, 0)

UNIX_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
DB_V_REGEX = re.compile(r"(?:_v\d+)?$")

MIN_UPDATE_DELTA = timedelta(seconds=30).total_seconds()


def _import_compatible_sqlite3(min_version: tuple[int, int, int]) -> types.ModuleType:
    """Loads an SQLite module with a library version matching the provided constraint."""

    import sqlite3

    try:
        import pysqlite3
    except ImportError:
        pysqlite3 = None

    for module in [sqlite3, pysqlite3]:
        if module is None:
            continue

        LOGGER.debug("SQLite version for %s: %s", module, module.sqlite_version)

        if module.sqlite_version_info >= min_version:
            return module
    min_ver = ".".join(map(str, min_version))

    raise RuntimeError(
        f"zigpy requires SQLite {min_ver} or newer. If your distribution does not"
        f" provide a more recent release, install pysqlite3 with"
        f" `pip install pysqlite3-binary`"
    )


sqlite3 = _import_compatible_sqlite3(min_version=MIN_SQLITE_VERSION)


def _register_sqlite_adapters():
    def adapt_ieee(eui64):
        return str(eui64)

    sqlite3.register_adapter(t.EUI64, adapt_ieee)
    sqlite3.register_adapter(t.ExtendedPanId, adapt_ieee)

    def convert_ieee(s):
        return t.EUI64.convert(s.decode())

    sqlite3.register_converter("ieee", convert_ieee)


def aiosqlite_connect(
    database: str, iter_chunk_size: int = 64, **kwargs
) -> aiosqlite.Connection:
    """Copy of the the `aiosqlite.connect` function that connects using either the built-in
    `sqlite3` module or the imported `pysqlite3` module.
    """

    return aiosqlite.Connection(
        connector=lambda: sqlite3.connect(str(database), **kwargs),
        iter_chunk_size=iter_chunk_size,
    )


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
        self._callback_handlers: asyncio.Queue = asyncio.Queue()
        self.running = False
        self._worker_task = asyncio.create_task(self._worker())

    async def initialize_tables(self) -> None:
        async with self.execute("PRAGMA integrity_check") as cursor:
            rows = await cursor.fetchall()
            status = "\n".join(row[0] for row in rows)

            if status != "ok":
                LOGGER.error(
                    "Zigbee database is corrupted, integrity check failed!\n%s", status
                )

        async with self.execute("PRAGMA foreign_key_check") as cursor:
            rows = await cursor.fetchall()

            if rows:
                LOGGER.error(
                    "Zigbee database is corrupted, foreign key check failed!\n%s", rows
                )

        # Truncate the SQLite journal file instead of deleting it after transactions
        await self._set_isolation_level(None)
        await self.execute("PRAGMA journal_mode = WAL")
        await self.execute("PRAGMA synchronous = normal")
        await self.execute("PRAGMA temp_store = memory")
        await self._set_isolation_level("DEFERRED")

        await self.execute("PRAGMA foreign_keys = ON")
        await self._run_migrations()

    @classmethod
    async def new(
        cls, database_file: str, app: zigpy.typing.ControllerApplicationType
    ) -> PersistingListener:
        """Create an instance of persisting listener."""
        sqlite_conn = await aiosqlite_connect(
            database_file,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level="DEFERRED",  # The default is "", an alias for "DEFERRED"
        )
        listener = cls(sqlite_conn, app)

        try:
            await listener.initialize_tables()
        except Exception:  # noqa: BLE001
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
            except sqlite3.Error as exc:
                LOGGER.debug(
                    "Error handling '%s' event with %s params: %s",
                    cb_name,
                    args,
                    str(exc),
                )
            except Exception as ex:  # noqa: BLE001
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

        # Delete the journal on shutdown
        await self._set_isolation_level(None)
        await self.execute("PRAGMA wal_checkpoint;")
        await self._set_isolation_level("DEFERRED")

        await self._db.close()

        # FIXME: aiosqlite's thread won't always be closed immediately
        await asyncio.get_running_loop().run_in_executor(None, self._db.join)

    def enqueue(self, cb_name: str, *args) -> None:
        """Enqueue an async callback handler action."""
        if not self.running:
            LOGGER.debug("Discarding %s event", cb_name)
            return
        self._callback_handlers.put_nowait((cb_name, args))

    async def _set_isolation_level(self, level: str | None):
        """Set the SQLite statement isolation level in a thread-safe way."""
        await self._db._execute(lambda: setattr(self._db, "isolation_level", level))

    def execute(self, *args, **kwargs):
        return self._db.execute(*args, **kwargs)

    async def executescript(self, sql):
        """Naive replacement for `sqlite3.Cursor.executescript` that does not execute a
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

    def device_last_seen_updated(
        self, device: zigpy.typing.DeviceType, last_seen: datetime
    ) -> None:
        """Device last_seen time is updated."""
        self.enqueue("_save_device_last_seen", device.ieee, last_seen)

    async def _save_device_last_seen(self, ieee: t.EUI64, last_seen: datetime) -> None:
        q = f"""UPDATE devices{DB_V}
                    SET last_seen=:ts
                    WHERE ieee=:ieee AND :ts - last_seen > :min_update_delta"""
        await self.execute(
            q,
            {
                "ts": last_seen.timestamp(),
                "ieee": ieee,
                "min_update_delta": MIN_UPDATE_DELTA,
            },
        )
        await self._db.commit()

    def device_relays_updated(
        self, device: zigpy.typing.DeviceType, relays: t.Relays | None
    ) -> None:
        """Device relay list is updated."""
        self.enqueue("_save_device_relays", device.ieee, relays)

    async def _save_device_relays(self, ieee: t.EUI64, relays: t.Relays | None) -> None:
        if relays is None:
            await self.execute(f"DELETE FROM relays{DB_V} WHERE ieee = ?", (ieee,))
        else:
            q = f"""INSERT INTO relays{DB_V} VALUES (:ieee, :relays)
                        ON CONFLICT (ieee)
                        DO UPDATE SET relays=excluded.relays WHERE relays != :relays"""
            await self.execute(q, {"ieee": ieee, "relays": relays.serialize()})

        await self._db.commit()

    def attribute_updated(
        self,
        cluster: zigpy.typing.ClusterType,
        attrid: int,
        value: Any,
        timestamp: datetime,
    ) -> None:
        self.enqueue(
            "_save_attribute",
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_type,
            cluster.cluster_id,
            attrid,
            value,
            timestamp,
        )

    def attribute_cleared(self, cluster: zigpy.typing.ClusterType, attrid: int) -> None:
        self.enqueue(
            "_clear_attribute",
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_type,
            cluster.cluster_id,
            attrid,
        )

    def unsupported_attribute_added(
        self, cluster: zigpy.typing.ClusterType, attrid: int
    ) -> None:
        self.enqueue(
            "_unsupported_attribute_added",
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_type,
            cluster.cluster_id,
            attrid,
        )

    async def _unsupported_attribute_added(
        self,
        ieee: t.EUI64,
        endpoint_id: int,
        cluster_type: ClusterType,
        cluster_id: int,
        attrid: int,
    ) -> None:
        q = f"""INSERT INTO unsupported_attributes{DB_V} VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (ieee, endpoint_id, cluster_type, cluster_id, attr_id)
                   DO NOTHING"""
        await self.execute(q, (ieee, endpoint_id, cluster_type, cluster_id, attrid))
        await self._db.commit()

    def unsupported_attribute_removed(
        self, cluster: zigpy.typing.ClusterType, attrid: int
    ) -> None:
        self.enqueue(
            "_unsupported_attribute_removed",
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_type,
            cluster.cluster_id,
            attrid,
        )

    async def _unsupported_attribute_removed(
        self,
        ieee: t.EUI64,
        endpoint_id: int,
        cluster_type: ClusterType,
        cluster_id: int,
        attrid: int,
    ) -> None:
        q = f"""DELETE FROM unsupported_attributes{DB_V} WHERE ieee = ?
                                                         AND endpoint_id = ?
                                                         AND cluster_type = ?
                                                         AND cluster_id = ?
                                                         AND attr_id = ?"""
        await self.execute(q, (ieee, endpoint_id, cluster_type, cluster_id, attrid))
        await self._db.commit()

    def neighbors_updated(self, ieee: t.EUI64, neighbors: list[zdo_t.Neighbor]) -> None:
        """Neighbor update from Mgmt_Lqi_req."""
        self.enqueue("_neighbors_updated", ieee, neighbors)

    async def _neighbors_updated(
        self, ieee: t.EUI64, neighbors: list[zdo_t.Neighbor]
    ) -> None:
        await self.execute(f"DELETE FROM neighbors{DB_V} WHERE device_ieee = ?", [ieee])

        rows = [(ieee, *neighbor.as_tuple()) for neighbor in neighbors]

        await self._db.executemany(
            f"INSERT INTO neighbors{DB_V} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        await self._db.commit()

    def routes_updated(self, ieee: t.EUI64, routes: list[zdo_t.Route]) -> None:
        """Route update from Mgmt_Rtg_req."""
        self.enqueue("_routes_updated", ieee, routes)

    async def _routes_updated(self, ieee: t.EUI64, routes: list[zdo_t.Route]) -> None:
        await self.execute(f"DELETE FROM routes{DB_V} WHERE device_ieee = ?", [ieee])

        rows = [(ieee, *route.as_tuple()) for route in routes]

        await self._db.executemany(
            f"INSERT INTO routes{DB_V} VALUES (?,?,?,?,?,?,?,?)", rows
        )
        await self._db.commit()

    def group_added(self, group: zigpy.group.Group) -> None:
        """Group is added."""
        self.enqueue("_group_added", group)

    async def _group_added(self, group: zigpy.group.Group) -> None:
        q = f"""INSERT INTO groups{DB_V} VALUES (?, ?)
                    ON CONFLICT (group_id)
                    DO UPDATE SET name=excluded.name"""
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
        q = f"""INSERT INTO group_members{DB_V} VALUES (?, ?, ?)
                    ON CONFLICT
                    DO NOTHING"""
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
        q = f"""INSERT INTO devices{DB_V} (ieee, nwk, status, last_seen)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (ieee)
                    DO UPDATE SET
                        nwk=excluded.nwk,
                        status=excluded.status,
                        last_seen=excluded.last_seen"""
        await self.execute(
            q,
            (
                device.ieee,
                device.nwk,
                device.status,
                (device._last_seen or UNIX_EPOCH).timestamp(),
            ),
        )

        if device.node_desc is not None:
            await self._save_node_descriptor(device)

        if isinstance(device, zigpy.quirks.BaseCustomDevice):
            await self._db.commit()
            return

        await self._save_endpoints(device)
        for ep in device.non_zdo_endpoints:
            await self._save_clusters(ep)
            await self._save_attribute_cache(ep)
            await self._save_unsupported_attributes(ep)
        await self._db.commit()

    async def _save_endpoints(self, device: zigpy.typing.DeviceType) -> None:
        rows = [
            (
                device.ieee,
                ep.endpoint_id,
                ep.profile_id,
                ep.device_type,
                ep.status,
            )
            for ep in device.non_zdo_endpoints
        ]

        q = f"""INSERT INTO endpoints{DB_V} VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (ieee, endpoint_id)
                    DO UPDATE SET
                        profile_id=excluded.profile_id,
                        device_type=excluded.device_type,
                        status=excluded.status"""

        await self._db.executemany(q, rows)

    async def _save_node_descriptor(self, device: zigpy.typing.DeviceType) -> None:
        q = f"""INSERT INTO node_descriptors{DB_V}
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (ieee)
                    DO UPDATE SET
                logical_type=excluded.logical_type,
                complex_descriptor_available=excluded.complex_descriptor_available,
                user_descriptor_available=excluded.user_descriptor_available,
                reserved=excluded.reserved,
                aps_flags=excluded.aps_flags,
                frequency_band=excluded.frequency_band,
                mac_capability_flags=excluded.mac_capability_flags,
                manufacturer_code=excluded.manufacturer_code,
                maximum_buffer_size=excluded.maximum_buffer_size,
                maximum_incoming_transfer_size=excluded.maximum_incoming_transfer_size,
                server_mask=excluded.server_mask,
                maximum_outgoing_transfer_size=excluded.maximum_outgoing_transfer_size,
                descriptor_capability_field=excluded.descriptor_capability_field"""

        await self.execute(q, (device.ieee, *device.node_desc.as_tuple()))

    async def _save_clusters(self, endpoint: zigpy.typing.EndpointType) -> None:
        clusters = [
            (
                endpoint.device.ieee,
                endpoint.endpoint_id,
                cluster.cluster_type,
                cluster.cluster_id,
            )
            for cluster in endpoint.clusters
        ]
        q = f"""INSERT INTO clusters{DB_V} VALUES (?, ?, ?, ?)
                    ON CONFLICT (ieee, endpoint_id, cluster_type, cluster_id)
                    DO NOTHING"""
        await self._db.executemany(q, clusters)

    async def _save_attribute_cache(self, ep: zigpy.typing.EndpointType) -> None:
        clusters = [
            (
                ep.device.ieee,
                ep.endpoint_id,
                cluster.cluster_type,
                cluster.cluster_id,
                attrid,
                value,
                cluster._attr_last_updated.get(attrid, UNIX_EPOCH).timestamp(),
            )
            for cluster in ep.clusters
            for attrid, value in cluster._attr_cache.items()
        ]
        q = f"""INSERT INTO attributes_cache{DB_V} VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (ieee, endpoint_id, cluster_type, cluster_id, attr_id)
                    DO UPDATE SET value=excluded.value, last_updated=excluded.last_updated"""
        await self._db.executemany(q, clusters)

    async def _save_unsupported_attributes(self, ep: zigpy.typing.EndpointType) -> None:
        clusters = [
            (
                ep.device.ieee,
                ep.endpoint_id,
                cluster.cluster_type,
                cluster.cluster_id,
                attr,
            )
            for cluster in ep.clusters
            for attr in cluster.unsupported_attributes
            if isinstance(attr, int)
        ]
        q = f"""INSERT INTO unsupported_attributes{DB_V} VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (ieee, endpoint_id, cluster_type, cluster_id, attr_id)
                    DO NOTHING"""
        await self._db.executemany(q, clusters)

    async def _save_attribute(
        self,
        ieee: t.EUI64,
        endpoint_id: int,
        cluster_type: ClusterType,
        cluster_id: int,
        attrid: int,
        value: Any,
        timestamp: datetime,
    ) -> None:
        q = f"""
            INSERT INTO attributes_cache{DB_V}
            VALUES (:ieee, :endpoint_id, :cluster_type, :cluster_id, :attr_id, :value, :timestamp)
                ON CONFLICT (ieee, endpoint_id, cluster_type, cluster_id, attr_id) DO UPDATE
                SET value=excluded.value, last_updated=excluded.last_updated
                WHERE
                    value != excluded.value
                    OR :timestamp - last_updated > :min_update_delta
            """
        await self.execute(
            q,
            {
                "ieee": ieee,
                "endpoint_id": endpoint_id,
                "cluster_type": cluster_type,
                "cluster_id": cluster_id,
                "attr_id": attrid,
                "value": value,
                "timestamp": timestamp.timestamp(),
                "min_update_delta": MIN_UPDATE_DELTA,
            },
        )
        await self._db.commit()

    async def _clear_attribute(
        self,
        ieee: t.EUI64,
        endpoint_id: int,
        cluster_type: ClusterType,
        cluster_id: int,
        attrid: int,
    ) -> None:
        q = f"""
            DELETE FROM attributes_cache{DB_V}
            WHERE
                ieee = :ieee
                AND endpoint_id = :endpoint_id
                AND cluster_type = :cluster_type
                AND cluster_id = :cluster_id
                AND attr_id = :attr_id
            """

        await self.execute(
            q,
            {
                "ieee": ieee,
                "endpoint_id": endpoint_id,
                "cluster_type": cluster_type,
                "cluster_id": cluster_id,
                "attr_id": attrid,
            },
        )
        await self._db.commit()

    def network_backup_created(self, backup: zigpy.backups.NetworkBackup) -> None:
        self.enqueue("_network_backup_created", json.dumps(backup.as_dict()))

    async def _network_backup_created(self, backup_json: str) -> None:
        q = f"""INSERT INTO network_backups{DB_V} VALUES (?, ?)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        backup_json=excluded.backup_json"""

        await self.execute(q, (None, backup_json))
        await self._db.commit()

    def network_backup_removed(self, backup: zigpy.backups.NetworkBackup) -> None:
        self.enqueue("_network_backup_removed", backup.backup_time)

    async def _network_backup_removed(self, backup_time: datetime) -> None:
        q = f"""DELETE FROM network_backups{DB_V}
                    WHERE json_extract(backup_json, '$.backup_time')=?"""

        await self.execute(q, (backup_time.isoformat(),))
        await self._db.commit()

    async def load(self) -> None:
        LOGGER.debug("Loading application state")
        await self._load_devices()
        await self._load_node_descriptors()
        await self._load_endpoints()
        await self._load_clusters()

        # Quirks require the manufacturer and model name to be populated
        await self._load_attributes(
            f"""
                cluster_type={ClusterType.Server}
            AND cluster_id={Basic.cluster_id}
            AND (
                   attr_id={Basic.AttributeDefs.manufacturer.id}
                OR attr_id={Basic.AttributeDefs.model.id}
            )
            """
        )

        for device in self._application.devices.values():
            device = zigpy.quirks.get_device(device)
            self._application.devices[device.ieee] = device

        await self._load_attributes()
        await self._load_unsupported_attributes()
        await self._load_groups()
        await self._load_group_members()
        await self._load_relays()
        await self._load_neighbors()
        await self._load_routes()
        await self._load_network_backups()
        await self._register_device_listeners()

    async def _load_attributes(self, filter: str | None = None) -> None:
        if filter:
            query = f"SELECT * FROM attributes_cache{DB_V} WHERE {filter}"
        else:
            query = f"SELECT * FROM attributes_cache{DB_V}"

        async with self.execute(query) as cursor:
            async for (
                ieee,
                endpoint_id,
                cluster_type,
                cluster_id,
                attr_id,
                value,
                last_updated,
            ) in cursor:
                dev = self._application.get_device(ieee)

                # Some quirks create endpoints and clusters that do not exist
                if endpoint_id not in dev.endpoints:
                    continue

                ep = dev.endpoints[endpoint_id]
                clusters = (
                    ep.in_clusters
                    if cluster_type == ClusterType.Server
                    else ep.out_clusters
                )

                if cluster_id not in clusters:
                    continue

                clusters[cluster_id]._attr_cache[attr_id] = value
                clusters[cluster_id]._attr_last_updated[attr_id] = (
                    datetime.fromtimestamp(last_updated, timezone.utc)
                )

                LOGGER.debug(
                    "[0x%04x:%s:0x%04x] Attribute id: %s value: %s",
                    dev.nwk,
                    endpoint_id,
                    cluster_id,
                    attr_id,
                    value,
                )

                # Populate the device's manufacturer and model attributes
                if (
                    cluster_id == Basic.cluster_id
                    and attr_id == Basic.AttributeDefs.manufacturer.id
                ):
                    dev.manufacturer = decode_str_attribute(value)
                elif (
                    cluster_id == Basic.cluster_id
                    and attr_id == Basic.AttributeDefs.model.id
                ):
                    dev.model = decode_str_attribute(value)

    async def _load_unsupported_attributes(self) -> None:
        """Load unsuppoted attributes."""

        async with self.execute(
            f"SELECT * FROM unsupported_attributes{DB_V}"
        ) as cursor:
            async for ieee, endpoint_id, cluster_type, cluster_id, attr_id in cursor:
                dev = self._application.get_device(ieee)

                try:
                    ep = dev.endpoints[endpoint_id]
                except KeyError:
                    continue

                clusters = (
                    ep.in_clusters
                    if cluster_type == ClusterType.Server
                    else ep.out_clusters
                )

                try:
                    cluster = clusters[cluster_id]
                except KeyError:
                    continue

                cluster.add_unsupported_attribute(attr_id, inhibit_events=True)

    async def _load_devices(self) -> None:
        async with self.execute(f"SELECT * FROM devices{DB_V}") as cursor:
            async for ieee, nwk, status, last_seen in cursor:
                dev = self._application.add_device(ieee, nwk)
                dev.status = zigpy.device.Status(status)

                if last_seen > 0:
                    dev.last_seen = last_seen

    async def _load_node_descriptors(self) -> None:
        async with self.execute(f"SELECT * FROM node_descriptors{DB_V}") as cursor:
            async for ieee, *fields in cursor:
                dev = self._application.get_device(ieee)
                dev.node_desc = zdo_t.NodeDescriptor(*fields)
                assert dev.node_desc.is_valid

    async def _load_endpoints(self) -> None:
        async with self.execute(f"SELECT * FROM endpoints{DB_V}") as cursor:
            async for ieee, epid, profile_id, device_type, status in cursor:
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
        async with self.execute(f"SELECT * FROM clusters{DB_V}") as cursor:
            async for ieee, endpoint_id, cluster_type, cluster_id in cursor:
                dev = self._application.get_device(ieee)
                ep = dev.endpoints[endpoint_id]

                if ClusterType(cluster_type) == ClusterType.Server:
                    ep.add_input_cluster(cluster_id)
                else:
                    ep.add_output_cluster(cluster_id)

    async def _load_groups(self) -> None:
        async with self.execute(f"SELECT * FROM groups{DB_V}") as cursor:
            async for group_id, name in cursor:
                self._application.groups.add_group(group_id, name, suppress_event=True)

    async def _load_group_members(self) -> None:
        async with self.execute(f"SELECT * FROM group_members{DB_V}") as cursor:
            async for group_id, ieee, ep_id in cursor:
                dev = self._application.get_device(ieee)
                group = self._application.groups[group_id]
                group.add_member(dev.endpoints[ep_id], suppress_event=True)

    async def _load_relays(self) -> None:
        async with self.execute(f"SELECT * FROM relays{DB_V}") as cursor:
            async for ieee, value in cursor:
                dev = self._application.get_device(ieee)
                relays, _ = t.Relays.deserialize(value)
                dev.relays = zigpy.util.filter_relays(relays)

    async def _load_neighbors(self) -> None:
        async with self.execute(f"SELECT * FROM neighbors{DB_V}") as cursor:
            async for ieee, *fields in cursor:
                neighbor = zdo_t.Neighbor(*fields)
                self._application.topology.neighbors[ieee].append(neighbor)

    async def _load_routes(self) -> None:
        async with self.execute(f"SELECT * FROM routes{DB_V}") as cursor:
            async for ieee, *fields in cursor:
                route = zdo_t.Route(*fields)
                self._application.topology.routes[ieee].append(route)

    async def _load_network_backups(self) -> None:
        self._application.backups.backups.clear()

        async with self.execute(
            f"SELECT * FROM network_backups{DB_V} ORDER BY id"
        ) as cursor:
            backups = []

            async for _id, backup_json in cursor:
                backup = zigpy.backups.NetworkBackup.from_dict(json.loads(backup_json))
                backups.append(backup)

        backups.sort(key=lambda b: b.backup_time)

        for backup in backups:
            self._application.backups.add_backup(backup, suppress_event=True)

    async def _register_device_listeners(self) -> None:
        for dev in self._application.devices.values():
            dev.add_context_listener(self)

    @contextlib.asynccontextmanager
    async def _transaction(self):
        await self.execute("BEGIN TRANSACTION")

        try:
            yield
        except Exception:  # noqa: BLE001
            await self.execute("ROLLBACK")
            raise
        else:
            await self.execute("COMMIT")

    async def _get_table_versions(self) -> dict[str, int]:
        tables = {}

        async with self.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            async for (name,) in cursor:
                # Ignore tables internal to SQLite
                if name.startswith("sqlite_"):
                    continue

                # The regex will always return a match
                match = DB_V_REGEX.search(name)
                assert match is not None

                tables[name] = int(match.group(0)[2:] or "0")

        return tables

    async def _table_exists(self, name: str) -> bool:
        return name in (await self._get_table_versions())

    async def _run_migrations(self) -> bool:
        """Migrates the database to the newest schema, returning True if migrations ran."""

        tables = await self._get_table_versions()
        tables_version = max(tables.values(), default=0)

        async with self.execute("PRAGMA user_version") as cursor:
            (db_version,) = await cursor.fetchone()

        LOGGER.debug(
            "Current database version is v%s (table version v%s)",
            db_version,
            tables_version,
        )

        # Table version suffixes were introduced in v4. If the table version suffix does
        # not match `user_version`, either zigpy was downgraded to a *really* old
        # version (July 2021), or it's corrupt. Running migrations could delete existing
        # table data, and since we cannot guarantee the schema is intact, fail early.
        if tables_version >= 4 and tables_version != db_version:
            raise zigpy.exceptions.CorruptDatabase(
                f"The `zigbee.db` database version ({db_version}) does not match its"
                f" max table version ({tables_version}). The database is inconsistent.",
            )

        if db_version == 0 and not tables:
            # If this is a brand new database, just load the current schema
            await self.executescript(zigpy.appdb_schemas.SCHEMAS[DB_VERSION])
            return False
        elif db_version > DB_VERSION:
            LOGGER.error(
                "This zigpy release uses database schema v%s but the database is v%s."
                " Downgrading zigpy is *not* recommended and may result in data loss."
                " Use at your own risk.",
                DB_VERSION,
                db_version,
            )
            return False

        # All migrations must succeed. If any fail, the database is not touched.
        async with self._transaction():
            for migration, to_db_version in [
                (self._migrate_to_v4, 4),
                (self._migrate_to_v5, 5),
                (self._migrate_to_v6, 6),
                (self._migrate_to_v7, 7),
                (self._migrate_to_v8, 8),
                (self._migrate_to_v9, 9),
                (self._migrate_to_v10, 10),
                (self._migrate_to_v11, 11),
                (self._migrate_to_v12, 12),
                (self._migrate_to_v13, 13),
            ]:
                if db_version >= min(to_db_version, DB_VERSION):
                    continue

                LOGGER.info(
                    "Migrating database from v%d to v%d", db_version, to_db_version
                )
                await self.executescript(zigpy.appdb_schemas.SCHEMAS[to_db_version])
                await migration()

                db_version = to_db_version

        return True

    async def _migrate_tables(
        self, table_map: dict[str, str], *, errors: str = "raise"
    ):
        """Copy rows from one set of tables into another."""

        # Extract the "old" table version suffix
        tables = await self._get_table_versions()
        old_table_name = list(table_map.keys())[0]
        old_version = tables[old_table_name]

        # Check which tables would not be migrated
        old_tables = [t for t, v in tables.items() if v == old_version]
        unmigrated_old_tables = [t for t in old_tables if t not in table_map]

        if unmigrated_old_tables:
            raise RuntimeError(
                f"The following tables were not migrated: {unmigrated_old_tables}"
            )

        # Insertion order matters for foreign key constraints but any rows that fail
        # to insert due to constraint violations can be discarded
        for old_table, new_table in table_map.items():
            # Ignore tables without a migration
            if new_table is None:
                continue

            async with self.execute(f"SELECT * FROM {old_table}") as cursor:
                async for row in cursor:
                    placeholders = ",".join("?" * len(row))

                    try:
                        await self.execute(
                            f"INSERT INTO {new_table} VALUES ({placeholders})", row
                        )
                    except sqlite3.IntegrityError as e:
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
                                f"Invalid value for `errors`: {errors!r}"
                            ) from e

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
                        (dev_ieee, *node_desc.as_tuple()),
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
                        (dev_ieee, *neighbor.as_tuple()),
                    )

    async def _migrate_to_v5(self):
        """Schema v5 introduced global table version suffixes and removed stale rows"""

        await self._migrate_tables(
            {
                "devices": "devices_v5",
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
                # Explicitly specify which tables will not be migrated
                "neighbors": None,
                "node_descriptors": None,
            },
            errors="warn",
        )

    async def _migrate_to_v6(self):
        """Schema v6 relaxed the `attribute_cache` table schema to ignore endpoints"""

        await self._migrate_tables(
            {
                "devices_v5": "devices_v6",
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
                    {
                        "attributes": "attributes_cache_v6",
                        "devices": None,
                        "endpoints": None,
                        "clusters": None,
                        "neighbors": None,
                        "node_descriptors": None,
                        "output_clusters": None,
                        "groups": None,
                        "group_members": None,
                        "relays": None,
                    },
                    errors="ignore",
                )

    async def _migrate_to_v7(self):
        """Schema v7 added the `unsupported_attributes` table."""

        await self._migrate_tables(
            {
                "devices_v6": "devices_v7",
                "endpoints_v6": "endpoints_v7",
                "in_clusters_v6": "in_clusters_v7",
                "out_clusters_v6": "out_clusters_v7",
                "groups_v6": "groups_v7",
                "group_members_v6": "group_members_v7",
                "relays_v6": "relays_v7",
                "attributes_cache_v6": "attributes_cache_v7",
                "neighbors_v6": "neighbors_v7",
                "node_descriptors_v6": "node_descriptors_v7",
            }
        )

    async def _migrate_to_v8(self):
        """Schema v8 added the `devices_v8.last_seen` column."""

        async with self.execute("SELECT * FROM devices_v7") as cursor:
            async for ieee, nwk, status in cursor:
                # Set the default `last_seen` to the unix epoch
                await self.execute(
                    "INSERT INTO devices_v8 VALUES (?, ?, ?, ?)",
                    (ieee, nwk, status, 0),
                )

        # Copy the devices table first, it should have no conflicts
        await self._migrate_tables(
            {
                "endpoints_v7": "endpoints_v8",
                "in_clusters_v7": "in_clusters_v8",
                "out_clusters_v7": "out_clusters_v8",
                "groups_v7": "groups_v8",
                "group_members_v7": "group_members_v8",
                "relays_v7": "relays_v8",
                "attributes_cache_v7": "attributes_cache_v8",
                "neighbors_v7": "neighbors_v8",
                "node_descriptors_v7": "node_descriptors_v8",
                "unsupported_attributes_v7": "unsupported_attributes_v8",
                "devices_v7": None,
            }
        )

    async def _migrate_to_v9(self):
        """Schema v9 changed the data type of the `devices_v8.last_seen` column."""

        await self.execute(
            """INSERT INTO devices_v9 (ieee, nwk, status, last_seen)
            SELECT ieee, nwk, status, last_seen / 1000.0 FROM devices_v8"""
        )

        await self._migrate_tables(
            {
                "endpoints_v8": "endpoints_v9",
                "in_clusters_v8": "in_clusters_v9",
                "out_clusters_v8": "out_clusters_v9",
                "groups_v8": "groups_v9",
                "group_members_v8": "group_members_v9",
                "relays_v8": "relays_v9",
                "attributes_cache_v8": "attributes_cache_v9",
                "neighbors_v8": "neighbors_v9",
                "node_descriptors_v8": "node_descriptors_v9",
                "unsupported_attributes_v8": "unsupported_attributes_v9",
                "devices_v8": None,
            }
        )

    async def _migrate_to_v10(self):
        """Schema v10 added a new `network_backups_v10` table."""

        await self._migrate_tables(
            {
                "devices_v9": "devices_v10",
                "endpoints_v9": "endpoints_v10",
                "in_clusters_v9": "in_clusters_v10",
                "out_clusters_v9": "out_clusters_v10",
                "groups_v9": "groups_v10",
                "group_members_v9": "group_members_v10",
                "relays_v9": "relays_v10",
                "attributes_cache_v9": "attributes_cache_v10",
                "neighbors_v9": "neighbors_v10",
                "node_descriptors_v9": "node_descriptors_v10",
                "unsupported_attributes_v9": "unsupported_attributes_v10",
            }
        )

    async def _migrate_to_v11(self):
        """Schema v11 added a new `routes_v11` table."""

        await self._migrate_tables(
            {
                "devices_v10": "devices_v11",
                "endpoints_v10": "endpoints_v11",
                "in_clusters_v10": "in_clusters_v11",
                "out_clusters_v10": "out_clusters_v11",
                "groups_v10": "groups_v11",
                "group_members_v10": "group_members_v11",
                "relays_v10": "relays_v11",
                "attributes_cache_v10": "attributes_cache_v11",
                "neighbors_v10": "neighbors_v11",
                "node_descriptors_v10": "node_descriptors_v11",
                "unsupported_attributes_v10": "unsupported_attributes_v11",
                "network_backups_v10": "network_backups_v11",
            }
        )

    async def _migrate_to_v12(self):
        """Schema v12 added a `timestamp` column to attribute updates."""

        await self._migrate_tables(
            {
                "devices_v11": "devices_v12",
                "endpoints_v11": "endpoints_v12",
                "in_clusters_v11": "in_clusters_v12",
                "neighbors_v11": "neighbors_v12",
                "routes_v11": "routes_v12",
                "node_descriptors_v11": "node_descriptors_v12",
                "out_clusters_v11": "out_clusters_v12",
                "groups_v11": "groups_v12",
                "group_members_v11": "group_members_v12",
                "relays_v11": "relays_v12",
                "unsupported_attributes_v11": "unsupported_attributes_v12",
                "network_backups_v11": "network_backups_v12",
                "attributes_cache_v11": None,
            }
        )

        async with self.execute("SELECT * FROM attributes_cache_v11") as cursor:
            async for ieee, endpoint_id, cluster_id, attrid, value in cursor:
                # Set the default `last_updated` to the unix epoch
                await self.execute(
                    "INSERT INTO attributes_cache_v12 VALUES (?, ?, ?, ?, ?, ?)",
                    (ieee, endpoint_id, cluster_id, attrid, value, 0),
                )

    async def _migrate_to_v13(self):
        """Schema v13 combines both cluster types and caching for all attributes."""

        await self._migrate_tables(
            {
                "devices_v12": "devices_v13",
                "endpoints_v12": "endpoints_v13",
                "neighbors_v12": "neighbors_v13",
                "routes_v12": "routes_v13",
                "node_descriptors_v12": "node_descriptors_v13",
                "groups_v12": "groups_v13",
                "group_members_v12": "group_members_v13",
                "relays_v12": "relays_v13",
                "network_backups_v12": "network_backups_v13",
                "in_clusters_v12": None,
                "out_clusters_v12": None,
                "unsupported_attributes_v12": None,
                "attributes_cache_v12": None,
            }
        )

        async with self.execute("SELECT * FROM in_clusters_v12") as cursor:
            async for ieee, endpoint_id, cluster_id in cursor:
                await self.execute(
                    "INSERT INTO clusters_v13 VALUES (?, ?, ?, ?)",
                    (ieee, endpoint_id, ClusterType.Server, cluster_id),
                )

        async with self.execute("SELECT * FROM out_clusters_v12") as cursor:
            async for ieee, endpoint_id, cluster_id in cursor:
                await self.execute(
                    "INSERT INTO clusters_v13 VALUES (?, ?, ?, ?)",
                    (ieee, endpoint_id, ClusterType.Client, cluster_id),
                )

        async with self.execute("SELECT * FROM unsupported_attributes_v12") as cursor:
            async for ieee, endpoint_id, cluster_id, attrid in cursor:
                await self.execute(
                    "INSERT INTO unsupported_attributes_v13 VALUES (?, ?, ?, ?, ?)",
                    (ieee, endpoint_id, ClusterType.Server, cluster_id, attrid),
                )

        async with self.execute("SELECT * FROM attributes_cache_v12") as cursor:
            async for (
                ieee,
                endpoint_id,
                cluster_id,
                attrid,
                value,
                last_updated,
            ) in cursor:
                await self.execute(
                    "INSERT INTO attributes_cache_v13 VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        ieee,
                        endpoint_id,
                        ClusterType.Server,
                        cluster_id,
                        attrid,
                        value,
                        last_updated,
                    ),
                )
