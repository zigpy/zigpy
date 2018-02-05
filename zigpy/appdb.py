import logging
import sqlite3

import zigpy.device
import zigpy.endpoint
import zigpy.profiles
import zigpy.types as t


LOGGER = logging.getLogger(__name__)


def _sqlite_adapters():
    def adapt_ieee(eui64):
        return repr(eui64)
    sqlite3.register_adapter(t.EUI64, adapt_ieee)

    def convert_ieee(s):
        ieee = [t.uint8_t(p, base=16) for p in s.split(b':')]
        return t.EUI64(ieee)
    sqlite3.register_converter("ieee", convert_ieee)


class PersistingListener:
    def __init__(self, database_file, application):
        self._database_file = database_file
        _sqlite_adapters()
        self._db = sqlite3.connect(database_file,
                                   detect_types=sqlite3.PARSE_DECLTYPES)
        self._cursor = self._db.cursor()

        self._create_table_devices()
        self._create_table_endpoints()
        self._create_table_clusters()
        self._create_table_output_clusters()
        self._create_table_attributes()

        self._application = application

    def execute(self, *args, **kwargs):
        return self._cursor.execute(*args, **kwargs)

    def device_joined(self, device):
        self._save_device(device)

    def device_initialized(self, device):
        self._save_device(device)

    def device_left(self, device):
        pass

    def device_removed(self, device):
        self._remove_device(device)

    def attribute_updated(self, cluster, attrid, value):
        self._save_attribute(
            cluster.endpoint.device.ieee,
            cluster.endpoint.endpoint_id,
            cluster.cluster_id,
            attrid,
            value,
        )

    def _create_table(self, table_name, spec):
        self.execute("CREATE TABLE IF NOT EXISTS %s %s" % (table_name, spec))

    def _create_index(self, index_name, table, columns):
        self.execute("CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(%s)" % (
            index_name, table, columns
        ))

    def _create_table_devices(self):
        self._create_table("devices", "(ieee ieee, nwk, status)")
        self._create_index("ieee_idx", "devices", "ieee")

    def _create_table_endpoints(self):
        self._create_table(
            "endpoints",
            "(ieee ieee, endpoint_id, profile_id, device_type device_type, status)",
        )
        self._create_index("endpoint_idx", "endpoints", "ieee, endpoint_id")

    def _create_table_clusters(self):
        self._create_table("clusters", "(ieee ieee, endpoint_id, cluster)")
        self._create_index(
            "cluster_idx",
            "clusters",
            "ieee, endpoint_id, cluster",
        )

    def _create_table_output_clusters(self):
        self._create_table("output_clusters", "(ieee ieee, endpoint_id, cluster)")
        self._create_index(
            "output_cluster_idx",
            "output_clusters",
            "ieee, endpoint_id, cluster",
        )

    def _create_table_attributes(self):
        self._create_table(
            "attributes",
            "(ieee ieee, endpoint_id, cluster, attrid, value)",
        )
        self._create_index(
            "attribute_idx",
            "attributes",
            "ieee, endpoint_id, cluster, attrid"
        )

    def _remove_device(self, device):
        self.execute("DELETE FROM attributes WHERE ieee = ?", (device.ieee, ))
        self.execute("DELETE FROM clusters WHERE ieee = ?", (device.ieee, ))
        self.execute("DELETE FROM output_clusters WHERE ieee = ?", (device.ieee, ))
        self.execute("DELETE FROM endpoints WHERE ieee = ?", (device.ieee, ))
        self.execute("DELETE FROM devices WHERE ieee = ?", (device.ieee, ))
        self._db.commit()

    def _save_device(self, device):
        q = "INSERT OR REPLACE INTO devices (ieee, nwk, status) VALUES (?, ?, ?)"
        self.execute(q, (device.ieee, device.nwk, device.status))
        self._save_endpoints(device)
        for epid, ep in device.endpoints.items():
            if epid == 0:
                # ZDO
                continue
            self._save_input_clusters(ep)
            self._save_output_clusters(ep)
        self._db.commit()

    def _save_endpoints(self, device):
        q = "INSERT OR REPLACE INTO endpoints VALUES (?, ?, ?, ?, ?)"
        endpoints = []
        for epid, ep in device.endpoints.items():
            if epid == 0:
                continue  # Skip zdo
            device_type = getattr(ep, 'device_type', None)
            eprow = (
                device.ieee,
                ep.endpoint_id,
                getattr(ep, 'profile_id', None),
                device_type,
                ep.status,
            )
            endpoints.append(eprow)
        self._cursor.executemany(q, endpoints)
        self._db.commit()

    def _save_input_clusters(self, endpoint):
        q = "INSERT OR REPLACE INTO clusters VALUES (?, ?, ?)"
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.in_clusters.values()
        ]
        self._cursor.executemany(q, clusters)
        self._db.commit()

    def _save_output_clusters(self, endpoint):
        q = "INSERT OR REPLACE INTO output_clusters VALUES (?, ?, ?)"
        clusters = [
            (endpoint.device.ieee, endpoint.endpoint_id, cluster.cluster_id)
            for cluster in endpoint.out_clusters.values()
        ]
        self._cursor.executemany(q, clusters)
        self._db.commit()

    def _save_attribute(self, ieee, endpoint_id, cluster_id, attrid, value):
        q = "INSERT OR REPLACE INTO attributes VALUES (?, ?, ?, ?, ?)"
        self.execute(q, (ieee, endpoint_id, cluster_id, attrid, value))
        self._db.commit()

    def _scan(self, table):
        return self.execute("SELECT * FROM %s" % (table, ))

    def load(self):
        LOGGER.debug("Loading application state from %s", self._database_file)
        for (ieee, nwk, status) in self._scan("devices"):
            dev = self._application.add_device(ieee, nwk)
            dev.status = zigpy.device.Status(status)

        for (ieee, epid, profile_id, device_type, status) in self._scan("endpoints"):
            dev = self._application.get_device(ieee)
            ep = dev.add_endpoint(epid)
            ep.profile_id = profile_id
            try:
                if profile_id == 260:
                    device_type = zigpy.profiles.zha.DeviceType(device_type)
                elif profile_id == 49246:
                    device_type = zigpy.profiles.zll.DeviceType(device_type)
            except ValueError:
                pass
            ep.device_type = device_type
            ep.status = zigpy.endpoint.Status(status)

        for (ieee, endpoint_id, cluster) in self._scan("clusters"):
            dev = self._application.get_device(ieee)
            ep = dev.endpoints[endpoint_id]
            ep.add_input_cluster(cluster)

        for (ieee, endpoint_id, cluster) in self._scan("output_clusters"):
            dev = self._application.get_device(ieee)
            ep = dev.endpoints[endpoint_id]
            ep.add_output_cluster(cluster)

        for (ieee, endpoint_id, cluster, attrid, value) in self._scan("attributes"):
            dev = self._application.get_device(ieee)
            ep = dev.endpoints[endpoint_id]
            clus = ep.in_clusters[cluster]
            clus._attr_cache[attrid] = value


class ClusterPersistingListener:
    def __init__(self, applistener, cluster):
        self._applistener = applistener
        self._cluster = cluster

    def attribute_updated(self, attrid, value):
        self._applistener.attribute_updated(self._cluster, attrid, value)

    def cluster_command(self, *args, **kwargs):
        pass

    def zdo_command(self, *args, **kwargs):
        pass
