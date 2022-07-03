PRAGMA user_version = 10;

-- devices
DROP TABLE IF EXISTS devices_v10;
CREATE TABLE devices_v10 (
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,
    status INTEGER NOT NULL,
    last_seen REAL NOT NULL
);

CREATE UNIQUE INDEX devices_idx_v10
    ON devices_v10(ieee);


-- endpoints
DROP TABLE IF EXISTS endpoints_v10;
CREATE TABLE endpoints_v10 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    device_type INTEGER NOT NULL,
    status INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v10(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX endpoint_idx_v10
    ON endpoints_v10(ieee, endpoint_id);


-- clusters
DROP TABLE IF EXISTS in_clusters_v10;
CREATE TABLE in_clusters_v10 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v10(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX in_clusters_idx_v10
    ON in_clusters_v10(ieee, endpoint_id, cluster);


-- neighbors
DROP TABLE IF EXISTS neighbors_v10;
CREATE TABLE neighbors_v10 (
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

    FOREIGN KEY(device_ieee)
        REFERENCES devices_v10(ieee)
        ON DELETE CASCADE
);

CREATE INDEX neighbors_idx_v10
    ON neighbors_v10(device_ieee);


-- node descriptors
DROP TABLE IF EXISTS node_descriptors_v10;
CREATE TABLE node_descriptors_v10 (
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

    FOREIGN KEY(ieee)
        REFERENCES devices_v10(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX node_descriptors_idx_v10
    ON node_descriptors_v10(ieee);


-- output clusters
DROP TABLE IF EXISTS out_clusters_v10;
CREATE TABLE out_clusters_v10 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v10(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX out_clusters_idx_v10
    ON out_clusters_v10(ieee, endpoint_id, cluster);


-- attributes
DROP TABLE IF EXISTS attributes_cache_v10;
CREATE TABLE attributes_cache_v10 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,
    attrid INTEGER NOT NULL,
    value BLOB NOT NULL,

    -- Quirks can create "virtual" clusters and endpoints that won't be present in the
    -- DB but whose values still need to be cached
    FOREIGN KEY(ieee)
        REFERENCES devices_v10(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX attributes_idx_v10
    ON attributes_cache_v10(ieee, endpoint_id, cluster, attrid);


-- groups
DROP TABLE IF EXISTS groups_v10;
CREATE TABLE groups_v10 (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL
);

CREATE UNIQUE INDEX groups_idx_v10
    ON groups_v10(group_id);


-- group members
DROP TABLE IF EXISTS group_members_v10;
CREATE TABLE group_members_v10 (
    group_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,

    FOREIGN KEY(group_id)
        REFERENCES groups_v10(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v10(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX group_members_idx_v10
    ON group_members_v10(group_id, ieee, endpoint_id);


-- relays
DROP TABLE IF EXISTS relays_v10;
CREATE TABLE relays_v10 (
    ieee ieee NOT NULL,
    relays BLOB NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v10(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX relays_idx_v10
    ON relays_v10(ieee);


-- unsupported attributes
DROP TABLE IF EXISTS unsupported_attributes_v10;
CREATE TABLE unsupported_attributes_v10 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,
    attrid INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v10(ieee)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id, cluster)
        REFERENCES in_clusters_v10(ieee, endpoint_id, cluster)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX unsupported_attributes_idx_v10
    ON unsupported_attributes_v10(ieee, endpoint_id, cluster, attrid);


-- network backups
DROP TABLE IF EXISTS network_backups_v10;
CREATE TABLE network_backups_v10 (
    backup_time REAL NOT NULL,
    backup_json TEXT NOT NULL
);

CREATE UNIQUE INDEX network_backups_backup_time_idx_v10
    ON network_backups_v10(backup_time);
