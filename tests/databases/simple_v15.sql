PRAGMA foreign_keys=OFF;
PRAGMA user_version=15;

BEGIN TRANSACTION;

CREATE TABLE devices_v15 (
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,
    status INTEGER NOT NULL,
    last_seen REAL NOT NULL
);
CREATE UNIQUE INDEX devices_idx_v15 ON devices_v15(ieee);

CREATE TABLE endpoints_v15 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    device_type INTEGER NOT NULL,
    status INTEGER NOT NULL,
    FOREIGN KEY(ieee) REFERENCES devices_v15(ieee) ON DELETE CASCADE
);
CREATE UNIQUE INDEX endpoint_idx_v15 ON endpoints_v15(ieee, endpoint_id);

CREATE TABLE clusters_v15 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster_type INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints_v15(ieee, endpoint_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX clusters_idx_v15 ON clusters_v15(ieee, endpoint_id, cluster_type, cluster_id);

CREATE TABLE attributes_cache_v15 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster_type INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    attr_id INTEGER NOT NULL,
    manufacturer_code INTEGER,
    manufacturer_code_idx INTEGER NOT NULL GENERATED ALWAYS AS (IFNULL(manufacturer_code, -2)) STORED,
    status INTEGER,
    value BLOB,
    last_updated REAL NOT NULL,
    FOREIGN KEY(ieee) REFERENCES devices_v15(ieee) ON DELETE CASCADE
);
CREATE UNIQUE INDEX attributes_cache_idx_v15 ON attributes_cache_v15(ieee, endpoint_id, cluster_type, cluster_id, attr_id, manufacturer_code_idx);

CREATE TABLE neighbors_v15 (
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
    lqi INTEGER NOT NULL,
    FOREIGN KEY(device_ieee) REFERENCES devices_v15(ieee) ON DELETE CASCADE
);
CREATE INDEX neighbors_idx_v15 ON neighbors_v15(device_ieee);

CREATE TABLE routes_v15 (
    device_ieee ieee NOT NULL,
    dst_nwk INTEGER NOT NULL,
    route_status INTEGER NOT NULL,
    memory_constrained INTEGER NOT NULL,
    many_to_one INTEGER NOT NULL,
    route_record_required INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    next_hop INTEGER NOT NULL
);
CREATE INDEX routes_idx_v15 ON routes_v15(device_ieee);

CREATE TABLE node_descriptors_v15 (
    ieee ieee NOT NULL,
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
    FOREIGN KEY(ieee) REFERENCES devices_v15(ieee) ON DELETE CASCADE
);
CREATE UNIQUE INDEX node_descriptors_idx_v15 ON node_descriptors_v15(ieee);

CREATE TABLE groups_v15 (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL
);
CREATE UNIQUE INDEX groups_idx_v15 ON groups_v15(group_id);

CREATE TABLE group_members_v15 (
    group_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    FOREIGN KEY(group_id) REFERENCES groups_v15(group_id) ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints_v15(ieee, endpoint_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX group_members_idx_v15 ON group_members_v15(group_id, ieee, endpoint_id);

CREATE TABLE relays_v15 (
    ieee ieee NOT NULL,
    relays BLOB NOT NULL,
    FOREIGN KEY(ieee) REFERENCES devices_v15(ieee) ON DELETE CASCADE
);
CREATE UNIQUE INDEX relays_idx_v15 ON relays_v15(ieee);

CREATE TABLE network_backups_v15 (
    id INTEGER NOT NULL,
    backup_json TEXT NOT NULL
);
CREATE UNIQUE INDEX network_backups_idx_v15 ON network_backups_v15(id);

CREATE TABLE ota_query_cache_v15 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    manufacturer_code INTEGER NOT NULL,
    image_type INTEGER NOT NULL,
    current_file_version INTEGER NOT NULL,
    hardware_version INTEGER,
    last_updated REAL NOT NULL,
    FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints_v15(ieee, endpoint_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ota_query_cache_idx_v15 ON ota_query_cache_v15(ieee, endpoint_id);

INSERT INTO devices_v15 VALUES('00:11:22:33:44:55:66:77', 1, 2, 0.0);

COMMIT;
