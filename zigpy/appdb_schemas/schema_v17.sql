PRAGMA user_version = 17;

-- devices: every device, Zigbee or Green Power. Rows that apply to both kinds of
-- device reference this table, rows specific to one kind reference its own table
DROP TABLE IF EXISTS devices_v17;
CREATE TABLE devices_v17 (
    ieee ieee NOT NULL
);

CREATE UNIQUE INDEX devices_idx_v17
    ON devices_v17(ieee);


-- Zigbee devices
DROP TABLE IF EXISTS zigbee_devices_v17;
CREATE TABLE zigbee_devices_v17 (
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,
    status INTEGER NOT NULL,
    last_seen REAL NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX zigbee_devices_idx_v17
    ON zigbee_devices_v17(ieee);


-- endpoints
DROP TABLE IF EXISTS endpoints_v17;
CREATE TABLE endpoints_v17 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    device_type INTEGER NOT NULL,
    status INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES zigbee_devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX endpoint_idx_v17
    ON endpoints_v17(ieee, endpoint_id);


-- clusters
DROP TABLE IF EXISTS clusters_v17;
CREATE TABLE clusters_v17 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster_type INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v17(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX clusters_idx_v17
    ON clusters_v17(ieee, endpoint_id, cluster_type, cluster_id);


-- attributes
DROP TABLE IF EXISTS attributes_cache_v17;
CREATE TABLE attributes_cache_v17 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster_type INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    attr_id INTEGER NOT NULL,
    manufacturer_code INTEGER,
    -- NULL is not considered equal to itself in unique indexes, so we need a non-NULL
    -- column to use in the unique index
    manufacturer_code_idx INTEGER NOT NULL GENERATED ALWAYS AS (IFNULL(manufacturer_code, -2)) STORED,
    status INTEGER,
    -- The ZCL data type of a serialized `value`. Untyped values are stored as-is.
    data_type INTEGER,
    value BLOB,
    last_updated REAL NOT NULL,

    -- Quirks can create "virtual" clusters and endpoints that won't be present in the
    -- DB but whose values still need to be cached
    FOREIGN KEY(ieee)
        REFERENCES devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX attributes_cache_idx_v17
    ON attributes_cache_v17(ieee, endpoint_id, cluster_type, cluster_id, attr_id, manufacturer_code_idx);


-- neighbors
DROP TABLE IF EXISTS neighbors_v17;
CREATE TABLE neighbors_v17 (
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
        REFERENCES zigbee_devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE INDEX neighbors_idx_v17
    ON neighbors_v17(device_ieee);


-- routes
DROP TABLE IF EXISTS routes_v17;
CREATE TABLE routes_v17 (
    device_ieee ieee NOT NULL,
    dst_nwk INTEGER NOT NULL,
    route_status INTEGER NOT NULL,
    memory_constrained INTEGER NOT NULL,
    many_to_one INTEGER NOT NULL,
    route_record_required INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    next_hop INTEGER NOT NULL
);

CREATE INDEX routes_idx_v17
    ON routes_v17(device_ieee);


-- node descriptors
DROP TABLE IF EXISTS node_descriptors_v17;
CREATE TABLE node_descriptors_v17 (
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
        REFERENCES zigbee_devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX node_descriptors_idx_v17
    ON node_descriptors_v17(ieee);


-- groups
DROP TABLE IF EXISTS groups_v17;
CREATE TABLE groups_v17 (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL
);

CREATE UNIQUE INDEX groups_idx_v17
    ON groups_v17(group_id);


-- group members
DROP TABLE IF EXISTS group_members_v17;
CREATE TABLE group_members_v17 (
    group_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,

    FOREIGN KEY(group_id)
        REFERENCES groups_v17(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v17(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX group_members_idx_v17
    ON group_members_v17(group_id, ieee, endpoint_id);


-- relays
DROP TABLE IF EXISTS relays_v17;
CREATE TABLE relays_v17 (
    ieee ieee NOT NULL,
    relays BLOB NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES zigbee_devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX relays_idx_v17
    ON relays_v17(ieee);


-- network backups
DROP TABLE IF EXISTS network_backups_v17;
CREATE TABLE network_backups_v17 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_json TEXT NOT NULL
);


-- OTA query cache: stores fields from the last query_next_image command per device
DROP TABLE IF EXISTS ota_query_cache_v17;
CREATE TABLE ota_query_cache_v17 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    manufacturer_code INTEGER NOT NULL,
    image_type INTEGER NOT NULL,
    current_file_version INTEGER NOT NULL,
    hardware_version INTEGER,
    last_updated REAL NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v17(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX ota_query_cache_idx_v17
    ON ota_query_cache_v17(ieee, endpoint_id);


-- Green Power devices
DROP TABLE IF EXISTS gp_devices_v17;
CREATE TABLE gp_devices_v17 (
    ieee ieee NOT NULL,
    application_id INTEGER NOT NULL,
    src_id INTEGER,
    device_id INTEGER,
    gpd_manufacturer_id INTEGER,
    gpd_model_id INTEGER,
    commands TEXT NOT NULL,
    server_cluster_ids TEXT NOT NULL,
    client_cluster_ids TEXT NOT NULL,
    switch_configuration INTEGER,
    mac_seq_num_capability INTEGER NOT NULL,
    rx_on_capability INTEGER NOT NULL,
    fixed_location INTEGER NOT NULL,
    -- Trailing data that comes after the `GPCommissioningPayload`
    extra_commissioning_payload BLOB,
    security_key BLOB,
    security_key_type INTEGER,
    security_level INTEGER,
    frame_counter INTEGER,
    last_seen REAL NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v17(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX gp_devices_idx_v17
    ON gp_devices_v17(ieee);
