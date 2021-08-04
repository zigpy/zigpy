PRAGMA user_version = 4;

-- devices
CREATE TABLE IF NOT EXISTS devices (
    ieee ieee,
    nwk,
    status
);

CREATE UNIQUE INDEX IF NOT EXISTS ieee_idx
    ON devices(ieee);


-- endpoints
CREATE TABLE IF NOT EXISTS endpoints (
    ieee ieee,
    endpoint_id,
    profile_id,
    device_type device_type,
    status,
    FOREIGN KEY(ieee)
        REFERENCES devices(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS endpoint_idx
    ON endpoints(ieee, endpoint_id);


-- clusters
CREATE TABLE IF NOT EXISTS clusters (
    ieee ieee,
    endpoint_id,
    cluster,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS cluster_idx
    ON clusters(ieee, endpoint_id, cluster);


-- neighbors
DROP TABLE IF EXISTS neighbors_v4;
CREATE TABLE neighbors_v4 (
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
);

CREATE INDEX neighbors_idx_v4
    ON neighbors_v4(device_ieee);


-- node descriptors
DROP TABLE IF EXISTS node_descriptors_v4;
CREATE TABLE node_descriptors_v4 (
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
        REFERENCES devices(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX node_descriptors_idx_v4
    ON node_descriptors_v4(ieee);


-- output clusters
CREATE TABLE IF NOT EXISTS output_clusters (
    ieee ieee,
    endpoint_id,
    cluster,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS output_cluster_idx
    ON output_clusters(ieee, endpoint_id, cluster);


-- attributes
CREATE TABLE IF NOT EXISTS attributes (
    ieee ieee,
    endpoint_id,
    cluster,
    attrid,
    value,

    FOREIGN KEY(ieee)
        REFERENCES devices(ieee)
        ON DELETE CASCADE
);


CREATE UNIQUE INDEX IF NOT EXISTS attribute_idx
    ON attributes(ieee, endpoint_id, cluster, attrid);


-- groups
CREATE TABLE IF NOT EXISTS groups (
    group_id,
    name
);

CREATE UNIQUE INDEX IF NOT EXISTS group_idx
    ON groups(group_id);


-- group members
CREATE TABLE IF NOT EXISTS group_members (
    group_id,
    ieee ieee,
    endpoint_id,

    FOREIGN KEY(group_id)
        REFERENCES groups(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints(ieee, endpoint_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS group_members_idx
    ON group_members(group_id, ieee, endpoint_id);


-- relays
CREATE TABLE IF NOT EXISTS relays (
    ieee ieee,
    relays,

    FOREIGN KEY(ieee)
        REFERENCES devices(ieee)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS relays_idx
    ON relays(ieee);
