PRAGMA user_version = 5;

-- devices
CREATE TABLE IF NOT EXISTS devices_v5 (
    ieee ieee,
    nwk,
    status
);

CREATE UNIQUE INDEX IF NOT EXISTS devices_idx_v5
    ON devices_v5(ieee);


-- endpoints
CREATE TABLE IF NOT EXISTS endpoints_v5 (
    ieee ieee,
    endpoint_id,
    profile_id,
    device_type device_type,
    status,
    FOREIGN KEY(ieee)
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS endpoint_idx_v5
    ON endpoints_v5(ieee, endpoint_id);


-- clusters
CREATE TABLE IF NOT EXISTS clusters_v5 (
    ieee ieee,
    endpoint_id,
    cluster,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS cluster_idx_v5
    ON clusters_v5(ieee, endpoint_id, cluster);


-- neighbors
CREATE TABLE IF NOT EXISTS neighbors_v5 (
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
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS neighbors_idx_v5
    ON neighbors_v5(device_ieee);


-- node descriptors
CREATE TABLE IF NOT EXISTS node_descriptors_v5 (
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

    FOREIGN KEY(ieee)
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS node_descriptors_idx_v5
    ON node_descriptors_v5(ieee);


-- output clusters
CREATE TABLE IF NOT EXISTS output_clusters_v5 (
    ieee ieee,
    endpoint_id,
    cluster,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS output_clusters_idx_v5
    ON output_clusters_v5(ieee, endpoint_id, cluster);


-- attributes
CREATE TABLE IF NOT EXISTS attributes_v5 (
    ieee ieee,
    endpoint_id,
    cluster,
    attrid,
    value,

    FOREIGN KEY(ieee)
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS attributes_idx_v5
    ON attributes_v5(ieee, endpoint_id, cluster, attrid);


-- groups
CREATE TABLE IF NOT EXISTS groups_v5 (
    group_id,
    name
);

CREATE UNIQUE INDEX IF NOT EXISTS groups_idx_v5
    ON groups_v5(group_id);


-- group members
CREATE TABLE IF NOT EXISTS group_members_v5 (
    group_id,
    ieee ieee,
    endpoint_id,

    FOREIGN KEY(group_id)
        REFERENCES groups_v5(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS group_members_idx_v5
    ON group_members_v5(group_id, ieee, endpoint_id);


-- relays
CREATE TABLE IF NOT EXISTS relays_v5 (
    ieee ieee,
    relays,

    FOREIGN KEY(ieee)
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS relays_idx_v5
    ON relays_v5(ieee);
