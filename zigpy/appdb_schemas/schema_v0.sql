PRAGMA user_version = 0;

CREATE TABLE IF NOT EXISTS devices (ieee ieee, nwk, status);
CREATE TABLE IF NOT EXISTS endpoints (ieee ieee, endpoint_id, profile_id, device_type device_type, status);
CREATE TABLE IF NOT EXISTS clusters (ieee ieee, endpoint_id, cluster);
CREATE TABLE IF NOT EXISTS output_clusters (ieee ieee, endpoint_id, cluster);
CREATE TABLE IF NOT EXISTS attributes (ieee ieee, endpoint_id, cluster, attrid, value);
CREATE UNIQUE INDEX IF NOT EXISTS ieee_idx ON devices(ieee);
CREATE UNIQUE INDEX IF NOT EXISTS endpoint_idx ON endpoints(ieee, endpoint_id);
CREATE UNIQUE INDEX IF NOT EXISTS cluster_idx ON clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX IF NOT EXISTS output_cluster_idx ON output_clusters(ieee, endpoint_id, cluster);
CREATE UNIQUE INDEX IF NOT EXISTS attribute_idx ON attributes(ieee, endpoint_id, cluster, attrid);
