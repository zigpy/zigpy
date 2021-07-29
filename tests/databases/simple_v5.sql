PRAGMA foreign_keys=OFF;
PRAGMA user_version=5;

BEGIN TRANSACTION;
CREATE TABLE devices_v5 (
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,
    status INTEGER NOT NULL
);
INSERT INTO devices_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',48461,2);
INSERT INTO devices_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',27932,2);
CREATE TABLE endpoints_v5 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    device_type INTEGER NOT NULL,
    status INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);
INSERT INTO endpoints_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,260,266,1);
INSERT INTO endpoints_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',242,41440,97,1);
INSERT INTO endpoints_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,260,268,1);
INSERT INTO endpoints_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',242,41440,97,1);
CREATE TABLE in_clusters_v5 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,3);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,4);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,4096);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,5);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,6);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,64636);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,8);
INSERT INTO in_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',242,33);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,2821);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,3);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,4);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,4096);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,5);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,6);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,64642);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,768);
INSERT INTO in_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,8);
CREATE TABLE neighbors_v5 (
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
INSERT INTO neighbors_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a','81:b1:12:dc:9f:bd:f4:b6','ec:1b:bd:ff:fe:54:4f:40',27932,1,1,2,0,2,0,15,130);
INSERT INTO neighbors_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40','81:b1:12:dc:9f:bd:f4:b6','00:0d:6f:ff:fe:a6:11:7a',48461,1,1,2,0,2,0,15,132);
CREATE TABLE node_descriptors_v5 (
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
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);
INSERT INTO node_descriptors_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0,0,0,0,8,142,4476,82,82,11264,82,0);
INSERT INTO node_descriptors_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0,0,0,0,8,142,4456,82,82,11264,82,0);
CREATE TABLE out_clusters_v5 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);
INSERT INTO out_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,25);
INSERT INTO out_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,32);
INSERT INTO out_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,4096);
INSERT INTO out_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,5);
INSERT INTO out_clusters_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',242,33);
INSERT INTO out_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,10);
INSERT INTO out_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,25);
INSERT INTO out_clusters_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',242,33);
CREATE TABLE attributes_cache_v5 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,
    attrid INTEGER NOT NULL,
    value BLOB NOT NULL,

    -- Quirks can create "virtual" clusters that won't be present in the DB but whose
    -- values still need to be cached
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);
INSERT INTO attributes_cache_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0,4,'IKEA of Sweden');
INSERT INTO attributes_cache_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0,5,'TRADFRI control outlet');
INSERT INTO attributes_cache_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0,4,'con');
INSERT INTO attributes_cache_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0,5,'ZBT-CCTLight-GLS0109');
CREATE TABLE groups_v5 (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE group_members_v5 (
    group_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,

    FOREIGN KEY(group_id)
        REFERENCES groups_v5(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v5(ieee, endpoint_id)
        ON DELETE CASCADE
);
CREATE TABLE relays_v5 (
    ieee ieee NOT NULL,
    relays BLOB NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v5(ieee)
        ON DELETE CASCADE
);
INSERT INTO relays_v5 VALUES('00:0d:6f:ff:fe:a6:11:7a',X'00');
INSERT INTO relays_v5 VALUES('ec:1b:bd:ff:fe:54:4f:40',X'00');
CREATE UNIQUE INDEX devices_idx_v5
    ON devices_v5(ieee);
CREATE UNIQUE INDEX endpoint_idx_v5
    ON endpoints_v5(ieee, endpoint_id);
CREATE UNIQUE INDEX in_clusters_idx_v5
    ON in_clusters_v5(ieee, endpoint_id, cluster);
CREATE INDEX neighbors_idx_v5
    ON neighbors_v5(device_ieee);
CREATE UNIQUE INDEX node_descriptors_idx_v5
    ON node_descriptors_v5(ieee);
CREATE UNIQUE INDEX out_clusters_idx_v5
    ON out_clusters_v5(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX attributes_idx_v5
    ON attributes_cache_v5(ieee, endpoint_id, cluster, attrid);
CREATE UNIQUE INDEX groups_idx_v5
    ON groups_v5(group_id);
CREATE UNIQUE INDEX group_members_idx_v5
    ON group_members_v5(group_id, ieee, endpoint_id);
CREATE UNIQUE INDEX relays_idx_v5
    ON relays_v5(ieee);
COMMIT;
