PRAGMA user_version = 3;
CREATE TABLE devices (ieee ieee, nwk, status);
CREATE TABLE endpoints (ieee ieee, endpoint_id, profile_id, device_type device_type, status);
CREATE TABLE clusters (ieee ieee, endpoint_id, cluster);
CREATE TABLE node_descriptors (ieee ieee, value, FOREIGN KEY(ieee) REFERENCES devices(ieee));
CREATE TABLE output_clusters (ieee ieee, endpoint_id, cluster);
CREATE TABLE attributes (ieee ieee, endpoint_id, cluster, attrid, value);
CREATE TABLE groups (group_id, name);
CREATE TABLE group_members (group_id, ieee ieee, endpoint_id,
                FOREIGN KEY(group_id) REFERENCES groups(group_id),
                FOREIGN KEY(ieee, endpoint_id)
                REFERENCES endpoints(ieee, endpoint_id));
CREATE TABLE relays (ieee ieee, relays,
                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
CREATE TABLE neighbors (device_ieee ieee NOT NULL, extended_pan_id ieee NOT NULL,ieee ieee NOT NULL, nwk INTEGER NOT NULL, struct INTEGER NOT NULL, permit_joining INTEGER NOT NULL, depth INTEGER NOT NULL, lqi INTEGER NOT NULL, FOREIGN KEY(device_ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
CREATE UNIQUE INDEX ieee_idx ON devices(ieee);
CREATE UNIQUE INDEX endpoint_idx ON endpoints(ieee, endpoint_id);
CREATE UNIQUE INDEX cluster_idx ON clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX node_descriptors_idx ON node_descriptors(ieee);
CREATE UNIQUE INDEX output_cluster_idx ON output_clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX attribute_idx ON attributes(ieee, endpoint_id, cluster, attrid);
CREATE UNIQUE INDEX group_idx ON groups(group_id);
CREATE UNIQUE INDEX group_members_idx ON group_members(group_id, ieee, endpoint_id);
CREATE UNIQUE INDEX relays_idx ON relays(ieee);
CREATE INDEX neighbors_idx ON neighbors(device_ieee);
