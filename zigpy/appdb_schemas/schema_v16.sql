PRAGMA user_version = 16;

-- devices
DROP TABLE IF EXISTS devices_v16;
CREATE TABLE devices_v16 (
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,
    status INTEGER NOT NULL,
    last_seen REAL NOT NULL
);

CREATE UNIQUE INDEX devices_idx_v16
    ON devices_v16(ieee);


-- endpoints
DROP TABLE IF EXISTS endpoints_v16;
CREATE TABLE endpoints_v16 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    device_type INTEGER NOT NULL,
    status INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v16(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX endpoint_idx_v16
    ON endpoints_v16(ieee, endpoint_id);


-- clusters
DROP TABLE IF EXISTS clusters_v16;
CREATE TABLE clusters_v16 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster_type INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v16(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX clusters_idx_v16
    ON clusters_v16(ieee, endpoint_id, cluster_type, cluster_id);


-- attributes
DROP TABLE IF EXISTS attributes_cache_v16;
CREATE TABLE attributes_cache_v16 (
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
    value BLOB,
    last_updated REAL NOT NULL,

    -- Quirks can create "virtual" clusters and endpoints that won't be present in the
    -- DB but whose values still need to be cached
    FOREIGN KEY(ieee)
        REFERENCES devices_v16(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX attributes_cache_idx_v16
    ON attributes_cache_v16(ieee, endpoint_id, cluster_type, cluster_id, attr_id, manufacturer_code_idx);


-- neighbors
DROP TABLE IF EXISTS neighbors_v16;
CREATE TABLE neighbors_v16 (
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
        REFERENCES devices_v16(ieee)
        ON DELETE CASCADE
);

CREATE INDEX neighbors_idx_v16
    ON neighbors_v16(device_ieee);


-- routes (per-device ZDO routing tables, scanned via Mgmt_Rtg_rsp)
DROP TABLE IF EXISTS routes_v16;
CREATE TABLE routes_v16 (
    device_ieee ieee NOT NULL,
    dst_nwk INTEGER NOT NULL,
    route_status INTEGER NOT NULL,
    memory_constrained INTEGER NOT NULL,
    many_to_one INTEGER NOT NULL,
    route_record_required INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    next_hop INTEGER NOT NULL
);

CREATE INDEX routes_idx_v16
    ON routes_v16(device_ieee);


-- node descriptors
DROP TABLE IF EXISTS node_descriptors_v16;
CREATE TABLE node_descriptors_v16 (
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
        REFERENCES devices_v16(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX node_descriptors_idx_v16
    ON node_descriptors_v16(ieee);


-- groups
DROP TABLE IF EXISTS groups_v16;
CREATE TABLE groups_v16 (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL
);

CREATE UNIQUE INDEX groups_idx_v16
    ON groups_v16(group_id);


-- group members
DROP TABLE IF EXISTS group_members_v16;
CREATE TABLE group_members_v16 (
    group_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,

    FOREIGN KEY(group_id)
        REFERENCES groups_v16(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v16(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX group_members_idx_v16
    ON group_members_v16(group_id, ieee, endpoint_id);


-- relays
DROP TABLE IF EXISTS relays_v16;
CREATE TABLE relays_v16 (
    ieee ieee NOT NULL,
    relays BLOB NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v16(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX relays_idx_v16
    ON relays_v16(ieee);


-- OTA query cache: stores fields from the last query_next_image command per device
DROP TABLE IF EXISTS ota_query_cache_v16;
CREATE TABLE ota_query_cache_v16 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    manufacturer_code INTEGER NOT NULL,
    image_type INTEGER NOT NULL,
    current_file_version INTEGER NOT NULL,
    hardware_version INTEGER,
    last_updated REAL NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v16(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX ota_query_cache_idx_v16
    ON ota_query_cache_v16(ieee, endpoint_id);


-- network backups, decomposed into one info row plus child rows per `backup_id`
DROP TABLE IF EXISTS network_info_v16;
CREATE TABLE network_info_v16 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_time REAL NOT NULL,

    -- coordinator node identity
    node_ieee ieee NOT NULL,
    node_nwk INTEGER NOT NULL,
    node_logical_type INTEGER NOT NULL,
    node_model TEXT,
    node_manufacturer TEXT,
    node_version TEXT,

    -- network identity
    extended_pan_id ieee NOT NULL,
    pan_id INTEGER NOT NULL,
    nwk_update_id INTEGER NOT NULL,
    nwk_manager_id INTEGER NOT NULL,
    channel INTEGER NOT NULL,
    channel_mask INTEGER NOT NULL,
    security_level INTEGER NOT NULL,
    tx_power INTEGER,

    -- network key + its outgoing (tx) frame counter
    network_key BLOB NOT NULL,
    network_key_seq INTEGER NOT NULL,
    network_key_tx_counter INTEGER NOT NULL,
    network_key_rx_counter INTEGER NOT NULL,

    -- trust center link key
    tc_link_key BLOB NOT NULL,
    tc_link_key_partner_ieee ieee NOT NULL,
    tc_link_key_seq INTEGER NOT NULL,
    tc_link_key_tx_counter INTEGER NOT NULL,
    tc_link_key_rx_counter INTEGER NOT NULL,

    -- opaque, small, mostly-immutable per-stack data
    stack_specific TEXT,
    metadata TEXT,
    source TEXT
);


-- per-device APS link keys
DROP TABLE IF EXISTS network_link_keys_v16;
CREATE TABLE network_link_keys_v16 (
    backup_id INTEGER NOT NULL,
    partner_ieee ieee NOT NULL,
    key BLOB NOT NULL,
    tx_counter INTEGER NOT NULL,
    rx_counter INTEGER NOT NULL,
    seq INTEGER NOT NULL,

    FOREIGN KEY(backup_id)
        REFERENCES network_info_v16(id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX network_link_keys_idx_v16
    ON network_link_keys_v16(backup_id, partner_ieee);


-- coordinator children
DROP TABLE IF EXISTS network_children_v16;
CREATE TABLE network_children_v16 (
    backup_id INTEGER NOT NULL,
    ieee ieee NOT NULL,

    FOREIGN KEY(backup_id)
        REFERENCES network_info_v16(id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX network_children_idx_v16
    ON network_children_v16(backup_id, ieee);


-- NWK to EUI64 address cache
DROP TABLE IF EXISTS network_addresses_v16;
CREATE TABLE network_addresses_v16 (
    backup_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,

    FOREIGN KEY(backup_id)
        REFERENCES network_info_v16(id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX network_addresses_idx_v16
    ON network_addresses_v16(backup_id, ieee);


-- next-hop route cache
DROP TABLE IF EXISTS network_routes_v16;
CREATE TABLE network_routes_v16 (
    backup_id INTEGER NOT NULL,
    destination INTEGER NOT NULL,
    next_hop INTEGER NOT NULL,

    FOREIGN KEY(backup_id)
        REFERENCES network_info_v16(id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX network_routes_idx_v16
    ON network_routes_v16(backup_id, destination);
