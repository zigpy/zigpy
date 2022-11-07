PRAGMA foreign_keys=OFF;
PRAGMA user_version=4;

BEGIN TRANSACTION;
CREATE TABLE devices (ieee ieee, nwk, status);
INSERT INTO devices VALUES('00:0d:6f:ff:fe:a6:11:7a',48461,2);
INSERT INTO devices VALUES('ec:1b:bd:ff:fe:54:4f:40',27932,2);
CREATE TABLE endpoints (ieee ieee, endpoint_id, profile_id, device_type device_type, status, FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
INSERT INTO endpoints VALUES('00:0d:6f:ff:fe:a6:11:7a',1,260,266,1);
INSERT INTO endpoints VALUES('00:0d:6f:ff:fe:a6:11:7a',242,41440,97,1);
INSERT INTO endpoints VALUES('ec:1b:bd:ff:fe:54:4f:40',1,260,268,1);
INSERT INTO endpoints VALUES('ec:1b:bd:ff:fe:54:4f:40',242,41440,97,1);
CREATE TABLE clusters (ieee ieee, endpoint_id, cluster, FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints(ieee, endpoint_id) ON DELETE CASCADE);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,3);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,4);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,4096);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,5);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,6);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,64636);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,8);
INSERT INTO clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',242,33);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,2821);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,3);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,4);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,4096);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,5);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,6);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,64642);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,768);
INSERT INTO clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,8);
CREATE TABLE neighbors (device_ieee ieee NOT NULL, extended_pan_id ieee NOT NULL,ieee ieee NOT NULL, nwk INTEGER NOT NULL, struct INTEGER NOT NULL, permit_joining INTEGER NOT NULL, depth INTEGER NOT NULL, lqi INTEGER NOT NULL, FOREIGN KEY(device_ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
INSERT INTO neighbors VALUES('00:0d:6f:ff:fe:a6:11:7a','81:b1:12:dc:9f:bd:f4:b6','ec:1b:bd:ff:fe:54:4f:40',27932,37,2,15,130);
INSERT INTO neighbors VALUES('ec:1b:bd:ff:fe:54:4f:40','81:b1:12:dc:9f:bd:f4:b6','00:0d:6f:ff:fe:a6:11:7a',48461,37,2,15,132);
CREATE TABLE node_descriptors (ieee ieee, value, FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
INSERT INTO node_descriptors VALUES('00:0d:6f:ff:fe:a6:11:7a',X'01408e7c11525200002c520000');
INSERT INTO node_descriptors VALUES('ec:1b:bd:ff:fe:54:4f:40',X'01408e6811525200002c520000');
CREATE TABLE output_clusters (ieee ieee, endpoint_id, cluster, FOREIGN KEY(ieee, endpoint_id) REFERENCES endpoints(ieee, endpoint_id) ON DELETE CASCADE);
INSERT INTO output_clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,25);
INSERT INTO output_clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,32);
INSERT INTO output_clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,4096);
INSERT INTO output_clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',1,5);
INSERT INTO output_clusters VALUES('00:0d:6f:ff:fe:a6:11:7a',242,33);
INSERT INTO output_clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,10);
INSERT INTO output_clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',1,25);
INSERT INTO output_clusters VALUES('ec:1b:bd:ff:fe:54:4f:40',242,33);
CREATE TABLE attributes (ieee ieee, endpoint_id, cluster, attrid, value, FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
INSERT INTO attributes VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0,4,'IKEA of Sweden');
INSERT INTO attributes VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0,5,'TRADFRI control outlet');
INSERT INTO attributes VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0,4,'con');
INSERT INTO attributes VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0,5,'ZBT-CCTLight-GLS0109');
CREATE TABLE groups (group_id, name);
CREATE TABLE group_members (group_id, ieee ieee, endpoint_id,
                FOREIGN KEY(group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY(ieee, endpoint_id)
                REFERENCES endpoints(ieee, endpoint_id) ON DELETE CASCADE);
CREATE TABLE relays (ieee ieee, relays,
                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
INSERT INTO relays VALUES('00:0d:6f:ff:fe:a6:11:7a',X'00');
INSERT INTO relays VALUES('ec:1b:bd:ff:fe:54:4f:40',X'00');
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

                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE
            );
INSERT INTO node_descriptors_v4 VALUES('00:0d:6f:ff:fe:a6:11:7a',1,0,0,0,0,8,142,4476,82,82,11264,82,0);
INSERT INTO node_descriptors_v4 VALUES('ec:1b:bd:ff:fe:54:4f:40',1,0,0,0,0,8,142,4456,82,82,11264,82,0);
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
INSERT INTO neighbors_v4 VALUES('00:0d:6f:ff:fe:a6:11:7a','81:b1:12:dc:9f:bd:f4:b6','ec:1b:bd:ff:fe:54:4f:40',27932,1,1,2,0,2,0,15,130);
INSERT INTO neighbors_v4 VALUES('ec:1b:bd:ff:fe:54:4f:40','81:b1:12:dc:9f:bd:f4:b6','00:0d:6f:ff:fe:a6:11:7a',48461,1,1,2,0,2,0,15,132);
CREATE UNIQUE INDEX ieee_idx ON devices(ieee);
CREATE UNIQUE INDEX endpoint_idx ON endpoints(ieee, endpoint_id);
CREATE UNIQUE INDEX cluster_idx ON clusters(ieee, endpoint_id, cluster);
CREATE INDEX neighbors_idx ON neighbors(device_ieee);
CREATE UNIQUE INDEX node_descriptors_idx ON node_descriptors(ieee);
CREATE UNIQUE INDEX output_cluster_idx ON output_clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX attribute_idx ON attributes(ieee, endpoint_id, cluster, attrid);
CREATE UNIQUE INDEX group_idx ON groups(group_id);
CREATE UNIQUE INDEX group_members_idx ON group_members(group_id, ieee, endpoint_id);
CREATE UNIQUE INDEX relays_idx ON relays(ieee);
CREATE UNIQUE INDEX node_descriptors_idx_v4 ON node_descriptors_v4(ieee);
CREATE INDEX neighbors_idx_v4 ON neighbors_v4(device_ieee);
COMMIT;