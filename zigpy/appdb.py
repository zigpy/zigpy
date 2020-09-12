import logging
import sqlite3

import zigpy.device
import zigpy.endpoint
import zigpy.profiles
import zigpy.quirks
import zigpy.types as t
from zigpy.zcl.clusters.general import Basic
from zigpy.zdo import types as zdo_t

LOGGER = logging.getLogger(__name__)

DB_VERSION = 0x0003


def _sqlite_adapters():
    def adapt_ieee(eui64):
        return str(eui64)

    sqlite3.register_adapter(t.EUI64, adapt_ieee)
    sqlite3.register_adapter(t.ExtendedPanId, adapt_ieee)

    def convert_ieee(s):
        return t.EUI64.convert(s.decode())

    sqlite3.register_converter("ieee", convert_ieee)


class PersistingListener:
    def __init__(self, database_file, application):
        self._database_file = database_file
        _sqlite_adapters()
        self._db = sqlite3.connect(database_file, detect_types=sqlite3.PARSE_DECLTYPES)
        self._cursor = self._db.cursor()

        self._enable_foreign_keys()
        self._create_table_devices()
        self._create_table_endpoints()
        self._create_table_clusters()
        self._create_table_neighbors()
        self._create_table_node_descriptors()
        self._create_table_output_clusters()
        self._create_table_attributes()
        self._create_table_groups()
        self._create_table_group_members()
        self._create_table_relays()

        self._application = application

    def execute(self, *args, **kwargs):
        return self._cursor.execute(*args, **kwargs)

    def device_joined(self, device):
        pass

    def raw_device_initialized(self, device):
        self._save_device(device)

    def device_initialized(self, device):
        pass

    def device_left(self, device):
        pass

    def device_removed(self, device):
        self._remove_device(device)

    def device_relays_updated(self, device, relays):
        """Device relay list is updated."""
        if relays is None:
            self._save_device_relays_clear(device.ieee)
            return

        self._save_device_relays_update(device.ieee, t.Relays(relays).serialize())

    def attribute_updated(self, cluster, attrid, value):
        if cluster.endpoint.device.status != zigpy.device.Status.ENDPOINTS_INIT:
            return

        self._save_attribute(
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_id,
            attrid,
            value,
        )

    def node_descriptor_updated(self, device):
        self._save_node_descriptor(device)
        self._db.commit()

    def neighbors_updated(self, neighbors):
        self.execute("DELETE FROM neighbors WHERE device_ieee = ?", (neighbors.ieee,))
        for nei in neighbors.neighbors:
            epid, ieee, nwk, struct, prm, depth, lqi = nei.neighbor.as_dict().values()
            self.execute(
                "INSERT INTO neighbors VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (neighbors.ieee, epid, ieee, nwk, struct.packed, prm, depth, lqi),
            )
        self._db.commit()

    def group_added(self, group):
        q = "INSERT OR REPLACE INTO groups VALUES (?, ?)"
        self.execute(q, (group.group_id, group.name))
        self._db.commit()

    def group_member_added(self, group, ep):
        q = "INSERT OR REPLACE INTO group_members VALUES (?, ?, ?)"
        self.execute(q, (group.group_id, *ep.unique_id))
        self._db.commit()

    def group_member_removed(self, group, ep):
        q = """DELETE FROM group_members WHERE group_id=?
                                               AND ieee=?
                                               AND endpoint_id=?"""
        self.execute(q, (group.group_id, *ep.unique_id))
        self._db.commit()

    def group_removed(self, group):
        q = "DELETE FROM groups WHERE group_id=?"
        self.execute(q, (group.group_id,))
        self._db.commit()

    def _create_table(self, table_name, spec):
        self.execute("CREATE TABLE IF NOT EXISTS %s %s" % (table_name, spec))
        self.execute("PRAGMA user_version = %s" % (DB_VERSION,))

    def _create_index(self, index_name, table, columns):
        self.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(%s)"
            % (index_name, table, columns)
        )

    def _create_table_devices(self):
        self._create_table("devices", "(ieee ieee, nwk, status)")
        self._create_index("ieee_idx", "devices", "ieee")

    def _create_table_endpoints(self):
        self._create_table(
            "endpoints",
            (
                "(ieee ieee, endpoint_id, profile_id, device_type device_type, status, "
                "FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE)"
            ),
        )
        self._create_index("endpoint_idx", "endpoints", "ieee, endpoint_id")

    def _create_table_clusters(self):
        self._create_table(
            "clusters",
            (
                "(ieee ieee, endpoint_id, cluster, "
                "FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints(ieee, endpoint_id)"
                " ON DELETE CASCADE)"
            ),
        )
        self._create_index("cluster_idx", "clusters", "ieee, endpoint_id, cluster")

    def _create_table_neighbors(self):
        idx_name = "neighbors_idx"
        idx_table = "neighbors"
        idx_cols = "device_ieee"
        self._create_table(
            idx_table,
            (
                "(device_ieee ieee NOT NULL, extended_pan_id ieee NOT NULL,"
                "ieee ieee NOT NULL, nwk INTEGER NOT NULL, struct INTEGER NOT NULL, "
                "permit_joining INTEGER NOT NULL, depth INTEGER NOT NULL, "
                "lqi INTEGER NOT NULL, "
                "FOREIGN KEY(device_ieee) REFERENCES devices(ieee) ON DELETE CASCADE)"
            ),
        )
        self.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_table}({idx_cols})"
        )

    def _create_table_node_descriptors(self):
        self._create_table(
            "node_descriptors",
            (
                "(ieee ieee, value, "
                "FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE)"
            ),
        )
        self._create_index("node_descriptors_idx", "node_descriptors", "ieee")

    def _create_table_output_clusters(self):
        self._create_table(
            "output_clusters",
            (
                "(ieee ieee, endpoint_id, cluster, "
                "FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints(ieee, endpoint_id)"
                " ON DELETE CASCADE)"
            ),
        )
        self._create_index(
            "output_cluster_idx", "output_clusters", "ieee, endpoint_id, cluster"
        )

    def _create_table_attributes(self):
        self._create_table(
            "attributes",
            (
                "(ieee ieee, endpoint_id, cluster, attrid, value, "
                "FOREIGN KEY(ieee) "
                "REFERENCES devices(ieee) "
                "ON DELETE CASCADE)"
            ),
        )
        self._create_index(
            "attribute_idx", "attributes", "ieee, endpoint_id, cluster, attrid"
        )

    def _create_table_groups(self):
        self._create_table("groups", "(group_id, name)")
        self._create_index("group_idx", "groups", "group_id")

    def _create_table_group_members(self):
        self._create_table(
            "group_members",
            """(group_id, ieee ieee, endpoint_id,
                FOREIGN KEY(group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY(ieee, endpoint_id)
                REFERENCES endpoints(ieee, endpoint_id) ON DELETE CASCADE)""",
        )
        self._create_index(
            "group_members_idx", "group_members", "group_id, ieee, endpoint_id"
        )

    def _create_table_relays(self):
        self._create_table(
            "relays",
            """(ieee ieee, relays,
                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE)""",
        )
        self._create_index("relays_idx", "relays", "ieee")

    def _enable_foreign_keys(self):
        self.execute("PRAGMA foreign_keys = ON")

    def _remove_device(self, device):
        queries = (
            "DELETE FROM attributes WHERE ieee = ?",
            "DELETE FROM neighbors WHERE ieee = ?",
            "DELETE FROM node_descriptors WHERE ieee = ?",
            "DELETE FROM clusters WHERE ieee = ?",
            "DELETE FROM output_clusters WHERE ieee = ?",
            "DELETE FROM group_members WHERE ieee = ?",
            "DELETE FROM endpoints WHERE ieee = ?",
            "DELETE FROM devices WHERE ieee = ?",
        )
        for query in queries:
            self.execute(query, (device.ieee,))
        self._db.commit()

    def _save_device(self, device):
        if device.status != zigpy.device.Status.ENDPOINTS_INIT:
            LOGGER.warning(
                "Not saving uninitialized %s/%s device: %s",
                device.ieee,
                device.nwk,
                device.status,
            )
            return
        q = "INSERT OR REPLACE INTO devices (ieee, nwk, status) VALUES (?, ?, ?)"
        self.execute(q, (device.ieee, device.nwk, device.status))
        self._save_node_descriptor(device)
        if isinstance(device, zigpy.quirks.CustomDevice):
            self._db.commit()
            return
        self._save_endpoints(device)
        for epid, ep in device.endpoints.items():
            if epid == 0:
                # ZDO
                continue
            self._save_input_clusters(ep)
            self._save_attribute_cache(ep)
            self._save_output_clusters(ep)
        self._db.commit()

    def _save_endpoints(self, device):
        q = "INSERT OR REPLACE INTO endpoints VALUES (?, ?, ?, ?, ?)"
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
        self._cursor.executemany(q, endpoints)

    def _save_node_descriptor(self, device):
        if (
            device.status != zigpy.device.Status.ENDPOINTS_INIT
            or not device.node_desc.is_valid
        ):
            return
        q = "INSERT OR REPLACE INTO node_descriptors VALUES (?, ?)"
        self.execute(q, (device.ieee, device.node_desc.serialize()))

    def _save_input_clusters(self, endpoint):
        q = "INSERT OR REPLACE INTO clusters VALUES (?, ?, ?)"
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.in_clusters.values()
        ]
        self._cursor.executemany(q, clusters)

    def _save_attribute_cache(self, ep):
        q = "INSERT OR REPLACE INTO attributes VALUES (?, ?, ?, ?, ?)"
        clusters = [
            (ep.device.ieee, ep.endpoint_id, cluster.cluster_id, attrid, value)
            for cluster in ep.in_clusters.values()
            for attrid, value in cluster._attr_cache.items()
        ]
        self._cursor.executemany(q, clusters)

    def _save_output_clusters(self, endpoint):
        q = "INSERT OR REPLACE INTO output_clusters VALUES (?, ?, ?)"
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.out_clusters.values()
        ]
        self._cursor.executemany(q, clusters)

    def _save_attribute(self, ieee, endpoint_id, cluster_id, attrid, value):
        q = "INSERT OR REPLACE INTO attributes VALUES (?, ?, ?, ?, ?)"
        self.execute(q, (ieee, endpoint_id, cluster_id, attrid, value))
        self._db.commit()

    def _save_device_relays_update(self, ieee, value):
        q = "INSERT OR REPLACE INTO relays VALUES (?, ?)"
        self.execute(q, (ieee, value))
        self._db.commit()

    def _save_device_relays_clear(self, ieee):
        self.execute("DELETE FROM relays WHERE ieee = ?", (ieee,))
        self._db.commit()

    def _scan(self, table, filter=None):
        if filter is None:
            return self.execute("SELECT * FROM %s" % (table,))
        return self.execute("SELECT * FROM %s WHERE %s" % (table, filter))

    async def load(self) -> None:
        LOGGER.debug("Loading application state from %s", self._database_file)
        await self._load_devices()
        await self._load_node_descriptors()
        await self._load_endpoints()
        await self._load_clusters()

        async def _load_attributes(filter: str = None) -> None:
            for (ieee, endpoint_id, cluster, attrid, value) in self._scan(
                "attributes", filter
            ):
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

        await _load_attributes("attrid=4 OR attrid=5")

        for device in self._application.devices.values():
            device = zigpy.quirks.get_device(device)
            self._application.devices[device.ieee] = device

        await _load_attributes()
        await self._load_groups()
        await self._load_group_members()
        await self._load_relays()
        await self._load_neighbors()
        await self._finish_loading()

    async def _load_devices(self):
        for (ieee, nwk, status) in self._scan("devices"):
            dev = self._application.add_device(ieee, nwk)
            dev.status = zigpy.device.Status(status)

    async def _load_node_descriptors(self):
        for (ieee, value) in self._scan("node_descriptors"):
            dev = self._application.get_device(ieee)
            dev.node_desc = zdo_t.NodeDescriptor.deserialize(value)[0]

    async def _load_endpoints(self):
        for (ieee, epid, profile_id, device_type, status) in self._scan("endpoints"):
            dev = self._application.get_device(ieee)
            ep = dev.add_endpoint(epid)
            ep.profile_id = profile_id
            ep.device_type = device_type
            if profile_id == 260:
                ep.device_type = zigpy.profiles.zha.DeviceType(device_type)
            elif profile_id == 49246:
                ep.device_type = zigpy.profiles.zll.DeviceType(device_type)
            ep.status = zigpy.endpoint.Status(status)

    async def _load_clusters(self):
        for (ieee, endpoint_id, cluster) in self._scan("clusters"):
            dev = self._application.get_device(ieee)
            ep = dev.endpoints[endpoint_id]
            ep.add_input_cluster(cluster)

        for (ieee, endpoint_id, cluster) in self._scan("output_clusters"):
            dev = self._application.get_device(ieee)
            ep = dev.endpoints[endpoint_id]
            ep.add_output_cluster(cluster)

    async def _load_groups(self):
        for (group_id, name) in self._scan("groups"):
            self._application.groups.add_group(group_id, name, suppress_event=True)

    async def _load_group_members(self):
        for (group_id, ieee, ep_id) in self._scan("group_members"):
            group = self._application.groups[group_id]
            group.add_member(
                self._application.get_device(ieee).endpoints[ep_id], suppress_event=True
            )

    async def _load_relays(self):
        for (ieee, value) in self._scan("relays"):
            dev = self._application.get_device(ieee)
            dev.relays = t.Relays.deserialize(value)[0]

    async def _load_neighbors(self):
        for (dev_ieee, epid, ieee, nwk, struct, prm, depth, lqi) in self._scan(
            "neighbors"
        ):
            dev = self._application.get_device(dev_ieee)
            nei = zdo_t.Neighbor(epid, ieee, nwk, struct, prm, depth, lqi)
            dev.neighbors.add_neighbor(nei)

    async def _finish_loading(self):
        for dev in self._application.devices.values():
            dev.add_context_listener(self)
            dev.neighbors.add_context_listener(self)
