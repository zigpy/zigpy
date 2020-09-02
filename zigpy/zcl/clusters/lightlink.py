from zigpy import types as t
from zigpy.zcl import Cluster, foundation

NET_START = (
    t.uint32_t,
    t.EUI64,
    t.uint8_t,
    t.KeyData,
    t.uint8_t,
    t.NWK,
    t.NWK,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.EUI64,
    t.NWK,
)

NET_JOIN = (
    t.uint32_t,
    t.EUI64,
    t.uint8_t,
    t.KeyData,
    t.uint8_t,
    t.uint8_t,
    t.NWK,
    t.NWK,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
    t.uint16_t,
)


class DeviceInfoRecord(t.Struct):
    ieee: t.EUI64
    endpoint_id: t.uint8_t
    profile_id: t.uint16_t
    device_id: t.uint16_t
    version: t.uint8_t
    group_id_count: t.uint8_t
    sort: t.uint8_t


class EndpointInfoRecord(t.Struct):
    nwk: t.NWK
    endpoint_id: t.uint8_t
    profile_id: t.uint16_t
    device_id: t.uint16_t
    version: t.uint8_t


class GroupInfoRecord(t.Struct):
    group_id: t.Group
    group_type: t.uint8_t


class LightLink(Cluster):
    cluster_id = 0x1000
    ep_attribute = "lightlink"
    attributes = {}
    server_commands = {
        0x0000: ("scan", (t.uint32_t, t.bitmap8, t.bitmap8), False),
        0x0002: ("device_information", (t.uint32_t, t.uint8_t), False),
        0x0006: ("identify", (t.uint32_t, t.uint16_t), False),
        0x0007: ("reset_to_factory_new", (t.uint32_t,), False),
        0x0010: ("network_start", NET_START, False),
        0x0012: ("network_join_router", NET_JOIN, False),
        0x0014: ("network_join_end_device", NET_JOIN, False),
        0x0016: (
            "network_update",
            (t.uint32_t, t.EUI64, t.uint8_t, t.uint8_t, t.NWK, t.NWK),
            False,
        ),
        0x0041: ("get_group_identifiers", (t.uint8_t,), False),
        0x0042: ("get_endpoint_list", (t.uint8_t,), False),
    }
    client_commands = {
        0x0001: (
            "scan_rsp",
            (
                t.uint32_t,
                t.uint8_t,
                t.bitmap8,
                t.bitmap8,
                t.bitmap16,
                t.uint32_t,
                t.EUI64,
                t.uint8_t,
                t.uint8_t,
                t.NWK,
                t.NWK,
                t.uint8_t,
                t.uint8_t,
                t.Optional(t.uint8_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint8_t),
                t.Optional(t.uint8_t),
            ),
            True,
        ),
        0x0003: (
            "device_information_rsp",
            (t.uint32_t, t.uint8_t, t.uint8_t, t.LVList[DeviceInfoRecord]),
            True,
        ),
        0x0011: (
            "network_start_rsp",
            (t.uint32_t, foundation.Status, t.EUI64, t.uint8_t, t.uint8_t, t.uint16_t),
            True,
        ),
        0x0013: ("network_join_router_rsp", (t.uint32_t, foundation.Status), True),
        0x0015: ("network_join_end_device_rsp", (t.uint32_t, foundation.Status), True),
        0x0040: (
            "endpoint_information",
            (t.EUI64, t.NWK, t.uint8_t, t.uint16_t, t.uint16_t, t.uint8_t),
            True,
        ),
        0x0041: (
            "get_group_identifiers_rsp",
            (t.uint8_t, t.uint8_t, t.LVList[GroupInfoRecord]),
            True,
        ),
        0x0042: (
            "get_endpoint_list_rsp",
            (t.uint8_t, t.uint8_t, t.LVList[EndpointInfoRecord]),
            True,
        ),
    }
