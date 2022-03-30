from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class LogicalType(t.enum2):
    Coordinator = 0b00
    Router = 0b01
    EndDevice = 0b10


class ZigbeeInformation(t.Struct):
    logical_type: LogicalType
    rx_on_when_idle: t.uint1_t
    reserved: t.uint5_t


class ScanRequestInformation(t.Struct):
    # whether the device is factory new
    factory_new: t.uint1_t

    # whether the device is capable of assigning addresses
    address_assignment: t.uint1_t
    reserved1: t.uint2_t

    # indicate the device is capable of initiating a link (i.e., it supports the
    # touchlink commissioning cluster at the client side) or 0 otherwise (i.e., it does
    # not support the touchlink commissioning cluster at the client side).
    touchlink_initiator: t.uint1_t
    undefined: t.uint1_t
    reserved2: t.uint1_t

    # If the ZLL profile is implemented, this bit shall be set to 0. In all other case
    # (Profile Interop / ZigBee 3.0), this bit shall be set to 1
    profile_interop: t.uint1_t


class ScanResponseInformation(t.Struct):
    factory_new: t.uint1_t
    address_assignment: t.uint1_t
    reserved1: t.uint2_t
    touchlink_initiator: t.uint1_t
    touchlink_priority_request: t.uint1_t
    reserved2: t.uint1_t
    profile_interop: t.uint1_t


class DeviceInfoRecord(t.Struct):
    ieee: t.EUI64
    endpoint_id: t.uint8_t
    profile_id: t.uint8_t
    device_id: t.uint16_t
    version: t.uint8_t
    group_id_count: t.uint8_t
    sort: t.uint8_t


class Status(t.enum8):
    Success = 0x00
    Failure = 0x01


class GroupInfoRecord(t.Struct):
    group_id: t.Group
    group_type: t.uint8_t


class EndpointInfoRecord(t.Struct):
    nwk_addr: t.NWK
    endpoint_id: t.uint8_t
    profile_id: t.uint16_t
    device_id: t.uint16_t
    version: t.uint8_t


class LightLink(Cluster):
    cluster_id = 0x1000
    ep_attribute = "lightlink"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {
        # Touchlink
        0x00: ZCLCommandDef(
            "scan",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "zigbee_information": ZigbeeInformation,
                "touchlink_information": ScanRequestInformation,
            },
            False,
        ),
        0x02: ZCLCommandDef(
            "device_info",
            {"inter_pan_transaction_id": t.uint32_t, "start_index": t.uint8_t},
            False,
        ),
        0x06: ZCLCommandDef(
            "identify",
            {"inter_pan_transaction_id": t.uint32_t, "identify_duration": t.uint16_t},
            False,
        ),
        0x07: ZCLCommandDef(
            "reset_to_factory_new",
            {"inter_pan_transaction_id": t.uint32_t},
            False,
        ),
        0x10: ZCLCommandDef(
            "network_start",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "epid": t.EUI64,
                "key_index": t.uint8_t,
                "encrypted_network_key": t.KeyData,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
                "nwk_addr": t.NWK,
                "group_identifiers_begin": t.Group,
                "group_identifiers_end": t.Group,
                "free_network_addr_range_begin": t.NWK,
                "free_network_addr_range_end": t.NWK,
                "free_group_id_range_begin": t.Group,
                "free_group_id_range_end": t.Group,
                "initiator_ieee": t.EUI64,
                "initiator_nwk": t.NWK,
            },
            False,
        ),
        0x12: ZCLCommandDef(
            "network_join_router",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "epid": t.EUI64,
                "key_index": t.uint8_t,
                "encrypted_network_key": t.KeyData,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
                "nwk_addr": t.NWK,
                "group_identifiers_begin": t.Group,
                "group_identifiers_end": t.Group,
                "free_network_addr_range_begin": t.NWK,
                "free_network_addr_range_end": t.NWK,
                "free_group_id_range_begin": t.Group,
                "free_group_id_range_end": t.Group,
            },
            False,
        ),
        0x14: ZCLCommandDef(
            "network_join_end_device",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "epid": t.EUI64,
                "key_index": t.uint8_t,
                "encrypted_network_key": t.KeyData,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
                "nwk_addr": t.NWK,
                "group_identifiers_begin": t.Group,
                "group_identifiers_end": t.Group,
                "free_network_addr_range_begin": t.NWK,
                "free_network_addr_range_end": t.NWK,
                "free_group_id_range_begin": t.Group,
                "free_group_id_range_end": t.Group,
            },
            False,
        ),
        0x16: ZCLCommandDef(
            "network_update",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "epid": t.EUI64,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
                "nwk_addr": t.NWK,
            },
            False,
        ),
        # Utility
        0x41: ZCLCommandDef(
            "get_group_identifiers",
            {
                "start_index": t.uint8_t,
            },
            False,
        ),
        0x42: ZCLCommandDef(
            "get_endpoint_list",
            {
                "start_index": t.uint8_t,
            },
            False,
        ),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        # Touchlink
        0x01: ZCLCommandDef(
            "scan_rsp",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "rssi_correction": t.uint8_t,
                "zigbee_info": ZigbeeInformation,
                "touchlink_info": ScanResponseInformation,
                "key_bitmask": t.uint16_t,
                "response_id": t.uint32_t,
                "epid": t.EUI64,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
                "nwk_addr": t.NWK,
                "num_sub_devices": t.uint8_t,
                "total_group_ids": t.uint8_t,
                "endpoint_id?": t.uint8_t,
                "profile_id?": t.uint16_t,
                "device_id?": t.uint16_t,
                "version?": t.uint8_t,
                "group_id_count?": t.uint8_t,
            },
            True,
        ),
        0x03: ZCLCommandDef(
            "device_info_rsp",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "num_sub_devices": t.uint8_t,
                "start_index": t.uint8_t,
                "device_info_records": t.LVList[DeviceInfoRecord],
            },
            True,
        ),
        0x11: ZCLCommandDef(
            "network_start_rsp",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "status": Status,
                "epid": t.EUI64,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
            },
            True,
        ),
        0x13: ZCLCommandDef(
            "network_join_router_rsp",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "status": Status,
            },
            True,
        ),
        0x15: ZCLCommandDef(
            "network_join_end_device_rsp",
            {
                "inter_pan_transaction_id": t.uint32_t,
                "status": Status,
            },
            True,
        ),
        # Utility
        0x40: ZCLCommandDef(
            "endpoint_info",
            {
                "ieee_addr": t.EUI64,
                "nwk_addr": t.NWK,
                "endpoint_id": t.uint8_t,
                "profile_id": t.uint16_t,
                "device_id": t.uint16_t,
                "version": t.uint8_t,
            },
            True,
        ),
        0x41: ZCLCommandDef(
            "get_group_identifiers_rsp",
            {
                "total": t.uint8_t,
                "start_index": t.uint8_t,
                "group_info_records": t.LVList[GroupInfoRecord],
            },
            True,
        ),
        0x42: ZCLCommandDef(
            "get_endpoint_list_rsp",
            {
                "total": t.uint8_t,
                "start_index": t.uint8_t,
                "endpoint_info_records": t.LVList[EndpointInfoRecord],
            },
            True,
        ),
    }
