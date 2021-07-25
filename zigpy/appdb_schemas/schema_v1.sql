PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS devices (ieee ieee, nwk, status);
CREATE TABLE IF NOT EXISTS endpoints (ieee ieee, endpoint_id, profile_id, device_type device_type, status);
CREATE TABLE IF NOT EXISTS clusters (ieee ieee, endpoint_id, cluster);
CREATE TABLE IF NOT EXISTS node_descriptors (ieee ieee, value, FOREIGN KEY(ieee) REFERENCES devices(ieee));
CREATE TABLE IF NOT EXISTS output_clusters (ieee ieee, endpoint_id, cluster);
CREATE TABLE IF NOT EXISTS attributes (ieee ieee, endpoint_id, cluster, attrid, value);
CREATE TABLE IF NOT EXISTS groups (group_id, name);
CREATE TABLE IF NOT EXISTS group_members (group_id, ieee ieee, endpoint_id,
                FOREIGN KEY(group_id) REFERENCES groups(group_id),
                FOREIGN KEY(ieee, endpoint_id)
                REFERENCES endpoints(ieee, endpoint_id));
CREATE TABLE IF NOT EXISTS relays (ieee ieee, relays,
                FOREIGN KEY(ieee) REFERENCES devices(ieee) ON DELETE CASCADE);
CREATE UNIQUE INDEX IF NOT EXISTS ieee_idx ON devices(ieee);
CREATE UNIQUE INDEX IF NOT EXISTS endpoint_idx ON endpoints(ieee, endpoint_id);
CREATE UNIQUE INDEX IF NOT EXISTS cluster_idx ON clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX IF NOT EXISTS node_descriptors_idx ON node_descriptors(ieee);
CREATE UNIQUE INDEX IF NOT EXISTS output_cluster_idx ON output_clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX IF NOT EXISTS attribute_idx ON attributes(ieee, endpoint_id, cluster, attrid);
CREATE UNIQUE INDEX IF NOT EXISTS group_idx ON groups(group_id);
CREATE UNIQUE INDEX IF NOT EXISTS group_members_idx ON group_members(group_id, ieee, endpoint_id);
CREATE UNIQUE INDEX IF NOT EXISTS relays_idx ON relays(ieee);
