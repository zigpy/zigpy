from zigpy.zcl import Cluster
import zigpy.types as t


class LightLink(Cluster):
    cluster_id = 0x1000
    ep_attribute = 'lightlink'
    attributes = {}
    server_commands = {
        0x0041: ('get_group_identifier_request', (t.uint8_t, ), False),
        0x0042: ('get_endpoint_list_request', (t.uint8_t, ), False),
        }
    client_commands = {
        0x0040: ('endpoint_information', (t.EUI64, t.uint16_t, t.uint8_t, t.uint16_t, t.uint16_t, t.uint8_t), True),
        0x0041: ('get_group_identifier_response', (t.uint8_t, t.uint8_t,  t.LVList(t.GroupInformationRecord)), True),
        0x0042: ('get_endpoint_list_response', (t.uint8_t, t.uint8_t, t.uint8_t,  t.LVList(t.EndpointInformationRecord)), True),
    }
