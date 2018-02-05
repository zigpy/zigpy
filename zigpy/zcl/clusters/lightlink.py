from zigpy.zcl import Cluster


class LightLink(Cluster):
    cluster_id = 0x1000
    ep_attribute = 'lightlink'
    attributes = {}
    server_commands = {}
    client_commands = {}
