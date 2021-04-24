from __future__ import annotations

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
        0x00: ("scan", (t.uint32_t, t.bitmap8, t.bitmap8), False),
        0x02: ("device_information", (t.uint32_t, t.uint8_t), False),
        0x06: ("identify", (t.uint32_t, t.uint16_t), False),
        0x07: ("reset_to_factory_new", (t.uint32_t,), False),
        0x10: ("network_start", NET_START, False),
        0x12: ("network_join_router", NET_JOIN, False),
        0x14: ("network_join_end_device", NET_JOIN, False),
        0x16: (
            "network_update",
            (t.uint32_t, t.EUI64, t.uint8_t, t.uint8_t, t.NWK, t.NWK),
            False,
        ),
        0x41: ("get_group_identifiers", (t.uint8_t,), False),
        0x42: ("get_endpoint_list", (t.uint8_t,), False),
    }
    client_commands = {
        0x01: (
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
        0x03: (
            "device_information_rsp",
            (t.uint32_t, t.uint8_t, t.uint8_t, t.LVList[DeviceInfoRecord]),
            True,
        ),
        0x11: (
            "network_start_rsp",
            (t.uint32_t, foundation.Status, t.EUI64, t.uint8_t, t.uint8_t, t.uint16_t),
            True,
        ),
        0x13: ("network_join_router_rsp", (t.uint32_t, foundation.Status), True),
        0x15: ("network_join_end_device_rsp", (t.uint32_t, foundation.Status), True),
        0x40: (
            "endpoint_information",
            (t.EUI64, t.NWK, t.uint8_t, t.uint16_t, t.uint16_t, t.uint8_t),
            True,
        ),
        0x41: (
            "get_group_identifiers_rsp",
            (t.uint8_t, t.uint8_t, t.LVList[GroupInfoRecord]),
            True,
        ),
        0x42: (
            "get_endpoint_list_rsp",
            (t.uint8_t, t.uint8_t, t.LVList[EndpointInfoRecord]),
            True,
        ),
    }
