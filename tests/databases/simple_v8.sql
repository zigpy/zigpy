PRAGMA user_version=8;
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE devices_v8 (
    ieee ieee NOT NULL,
    nwk INTEGER NOT NULL,
    status INTEGER NOT NULL,
    last_seen unix_timestamp NOT NULL
);
INSERT INTO devices_v8 VALUES('00:12:4b:00:1c:a1:b8:46',0,2,1651119833288);
INSERT INTO devices_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',44170,2,1651119836445);
INSERT INTO devices_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',50064,2,1651119839551);
INSERT INTO devices_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',57374,2,1651119830048);
CREATE TABLE endpoints_v8 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    device_type INTEGER NOT NULL,
    status INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v8(ieee)
        ON DELETE CASCADE
);
INSERT INTO endpoints_v8 VALUES('00:12:4b:00:1c:a1:b8:46',1,260,48879,1);
INSERT INTO endpoints_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,260,268,1);
INSERT INTO endpoints_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',242,41440,97,1);
INSERT INTO endpoints_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,260,268,1);
INSERT INTO endpoints_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',242,41440,97,1);
INSERT INTO endpoints_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,260,2080,1);
CREATE TABLE in_clusters_v8 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v8(ieee, endpoint_id)
        ON DELETE CASCADE
);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,0);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,3);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,4);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,5);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,6);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,8);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,2821);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,4096);
INSERT INTO in_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,64642);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,0);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,3);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,4);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,5);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,6);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,8);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,2821);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,4096);
INSERT INTO in_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,64642);
INSERT INTO in_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,0);
INSERT INTO in_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,1);
INSERT INTO in_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,3);
INSERT INTO in_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,32);
INSERT INTO in_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,4096);
CREATE TABLE neighbors_v8 (
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
        REFERENCES devices_v8(ieee)
        ON DELETE CASCADE
);
INSERT INTO neighbors_v8 VALUES('00:12:4b:00:1c:a1:b8:46','bd:27:0b:38:37:95:dc:87','ec:1b:bd:ff:fe:2f:41:a4',44170,1,1,2,0,2,0,15,255);
INSERT INTO neighbors_v8 VALUES('00:12:4b:00:1c:a1:b8:46','bd:27:0b:38:37:95:dc:87','cc:cc:cc:ff:fe:e6:8e:ca',50064,1,1,2,0,2,0,15,255);
INSERT INTO neighbors_v8 VALUES('00:12:4b:00:1c:a1:b8:46','bd:27:0b:38:37:95:dc:87','00:0b:57:ff:fe:2b:d4:57',57374,2,0,1,0,0,0,1,255);
INSERT INTO neighbors_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4','bd:27:0b:38:37:95:dc:87','00:12:4b:00:1c:a1:b8:46',0,0,1,2,0,2,0,0,253);
INSERT INTO neighbors_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4','bd:27:0b:38:37:95:dc:87','cc:cc:cc:ff:fe:e6:8e:ca',50064,1,1,0,0,2,0,15,255);
INSERT INTO neighbors_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca','bd:27:0b:38:37:95:dc:87','00:12:4b:00:1c:a1:b8:46',0,0,1,0,0,2,0,0,255);
INSERT INTO neighbors_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca','bd:27:0b:38:37:95:dc:87','ec:1b:bd:ff:fe:2f:41:a4',44170,1,1,2,0,2,0,15,255);
CREATE TABLE node_descriptors_v8 (
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
        REFERENCES devices_v8(ieee)
        ON DELETE CASCADE
);
INSERT INTO node_descriptors_v8 VALUES('00:12:4b:00:1c:a1:b8:46',0,0,0,0,0,8,143,43981,82,128,11329,128,0);
INSERT INTO node_descriptors_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,0,0,0,0,8,142,4688,82,82,11264,82,0);
INSERT INTO node_descriptors_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,0,0,0,0,8,142,4688,82,82,11264,82,0);
INSERT INTO node_descriptors_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',2,0,0,0,0,8,128,4476,82,82,11264,82,0);
CREATE TABLE out_clusters_v8 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,

    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v8(ieee, endpoint_id)
        ON DELETE CASCADE
);
INSERT INTO out_clusters_v8 VALUES('00:12:4b:00:1c:a1:b8:46',1,1280);
INSERT INTO out_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,10);
INSERT INTO out_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,25);
INSERT INTO out_clusters_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',242,33);
INSERT INTO out_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,10);
INSERT INTO out_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,25);
INSERT INTO out_clusters_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',242,33);
INSERT INTO out_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,3);
INSERT INTO out_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,4);
INSERT INTO out_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,6);
INSERT INTO out_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,8);
INSERT INTO out_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,25);
INSERT INTO out_clusters_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,4096);
CREATE TABLE attributes_cache_v8 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,
    attrid INTEGER NOT NULL,
    value BLOB NOT NULL,

    -- Quirks can create "virtual" clusters and endpoints that won't be present in the
    -- DB but whose values still need to be cached
    FOREIGN KEY(ieee)
        REFERENCES devices_v8(ieee)
        ON DELETE CASCADE
);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,0,4,'The Home Depot');
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,0,5,'Ecosmart-ZBT-A19-CCT-Bulb');
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,6,0,1);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,6,16387,1);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,8,0,254);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,16395,153);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,16396,370);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,16394,16);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,0,4,'The Home Depot');
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,0,5,'Ecosmart-ZBT-A19-CCT-Bulb');
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,3,30002);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,4,26876);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,7,370);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,6,0,1);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,8,0,254);
INSERT INTO attributes_cache_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,8,2);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,8,2);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,7,370);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,3,30002);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,4,26876);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,6,16387,1);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,16395,153);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,16396,370);
INSERT INTO attributes_cache_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,16394,16);
INSERT INTO attributes_cache_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,0,4,'IKEA of Sweden');
INSERT INTO attributes_cache_v8 VALUES('00:0b:57:ff:fe:2b:d4:57',1,0,5,'TRADFRI wireless dimmer');
CREATE TABLE groups_v8 (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL
);
INSERT INTO groups_v8 VALUES(0,'Default Lightlink Group');
CREATE TABLE group_members_v8 (
    group_id INTEGER NOT NULL,
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,

    FOREIGN KEY(group_id)
        REFERENCES groups_v8(group_id)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id)
        REFERENCES endpoints_v8(ieee, endpoint_id)
        ON DELETE CASCADE
);
INSERT INTO group_members_v8 VALUES(0,'00:12:4b:00:1c:a1:b8:46',1);
CREATE TABLE relays_v8 (
    ieee ieee NOT NULL,
    relays BLOB NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v8(ieee)
        ON DELETE CASCADE
);
INSERT INTO relays_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',X'00');
INSERT INTO relays_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',X'00');
CREATE TABLE unsupported_attributes_v8 (
    ieee ieee NOT NULL,
    endpoint_id INTEGER NOT NULL,
    cluster INTEGER NOT NULL,
    attrid INTEGER NOT NULL,

    FOREIGN KEY(ieee)
        REFERENCES devices_v8(ieee)
        ON DELETE CASCADE,
    FOREIGN KEY(ieee, endpoint_id, cluster)
        REFERENCES in_clusters_v8(ieee, endpoint_id, cluster)
        ON DELETE CASCADE
);
INSERT INTO unsupported_attributes_v8 VALUES('ec:1b:bd:ff:fe:2f:41:a4',1,768,16386);
INSERT INTO unsupported_attributes_v8 VALUES('cc:cc:cc:ff:fe:e6:8e:ca',1,768,16386);
CREATE UNIQUE INDEX devices_idx_v8
    ON devices_v8(ieee);
CREATE UNIQUE INDEX endpoint_idx_v8
    ON endpoints_v8(ieee, endpoint_id);
CREATE UNIQUE INDEX in_clusters_idx_v8
    ON in_clusters_v8(ieee, endpoint_id, cluster);
CREATE INDEX neighbors_idx_v8
    ON neighbors_v8(device_ieee);
CREATE UNIQUE INDEX node_descriptors_idx_v8
    ON node_descriptors_v8(ieee);
CREATE UNIQUE INDEX out_clusters_idx_v8
    ON out_clusters_v8(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX attributes_idx_v8
    ON attributes_cache_v8(ieee, endpoint_id, cluster, attrid);
CREATE UNIQUE INDEX groups_idx_v8
    ON groups_v8(group_id);
CREATE UNIQUE INDEX group_members_idx_v8
    ON group_members_v8(group_id, ieee, endpoint_id);
CREATE UNIQUE INDEX relays_idx_v8
    ON relays_v8(ieee);
CREATE UNIQUE INDEX unsupported_attributes_idx_v8
    ON unsupported_attributes_v8(ieee, endpoint_id, cluster, attrid);
COMMIT;