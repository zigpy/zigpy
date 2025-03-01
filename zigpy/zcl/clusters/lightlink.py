from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import BaseCommandDefs, Direction, ZCLCommandDef


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
    # (Profile Interop / Zigbee 3.0), this bit shall be set to 1
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
    cluster_id: Final[t.uint16_t] = 0x1000
    ep_attribute: Final = "lightlink"

    class ServerCommandDefs(BaseCommandDefs):
        scan: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "zigbee_information": ZigbeeInformation,
                "touchlink_information": ScanRequestInformation,
            },
            direction=Direction.Client_to_Server,
        )
        device_info: Final = ZCLCommandDef(
            id=0x02,
            schema={"inter_pan_transaction_id": t.uint32_t, "start_index": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        identify: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "identify_duration": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        reset_to_factory_new: Final = ZCLCommandDef(
            id=0x07,
            schema={"inter_pan_transaction_id": t.uint32_t},
            direction=Direction.Client_to_Server,
        )
        network_start: Final = ZCLCommandDef(
            id=0x10,
            schema={
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
            direction=Direction.Client_to_Server,
        )
        network_join_router: Final = ZCLCommandDef(
            id=0x12,
            schema={
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
            direction=Direction.Client_to_Server,
        )
        network_join_end_device: Final = ZCLCommandDef(
            id=0x14,
            schema={
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
            direction=Direction.Client_to_Server,
        )
        network_update: Final = ZCLCommandDef(
            id=0x16,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "epid": t.EUI64,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
                "nwk_addr": t.NWK,
            },
            direction=Direction.Client_to_Server,
        )
        # Utility
        get_group_identifiers: Final = ZCLCommandDef(
            id=0x41,
            schema={
                "start_index": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )
        get_endpoint_list: Final = ZCLCommandDef(
            id=0x42,
            schema={
                "start_index": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        scan_rsp: Final = ZCLCommandDef(
            id=0x01,
            schema={
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
            direction=Direction.Server_to_Client,
        )
        device_info_rsp: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "num_sub_devices": t.uint8_t,
                "start_index": t.uint8_t,
                "device_info_records": t.LVList[DeviceInfoRecord],
            },
            direction=Direction.Server_to_Client,
        )
        network_start_rsp: Final = ZCLCommandDef(
            id=0x11,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "status": Status,
                "epid": t.EUI64,
                "nwk_update_id": t.uint8_t,
                "logical_channel": t.uint8_t,
                "pan_id": t.PanId,
            },
            direction=Direction.Server_to_Client,
        )
        network_join_router_rsp: Final = ZCLCommandDef(
            id=0x13,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "status": Status,
            },
            direction=Direction.Server_to_Client,
        )
        network_join_end_device_rsp: Final = ZCLCommandDef(
            id=0x15,
            schema={
                "inter_pan_transaction_id": t.uint32_t,
                "status": Status,
            },
            direction=Direction.Server_to_Client,
        )
        # Utility
        endpoint_info: Final = ZCLCommandDef(
            id=0x40,
            schema={
                "ieee_addr": t.EUI64,
                "nwk_addr": t.NWK,
                "endpoint_id": t.uint8_t,
                "profile_id": t.uint16_t,
                "device_id": t.uint16_t,
                "version": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        get_group_identifiers_rsp: Final = ZCLCommandDef(
            id=0x41,
            schema={
                "total": t.uint8_t,
                "start_index": t.uint8_t,
                "group_info_records": t.LVList[GroupInfoRecord],
            },
            direction=Direction.Server_to_Client,
        )
        get_endpoint_list_rsp: Final = ZCLCommandDef(
            id=0x42,
            schema={
                "total": t.uint8_t,
                "start_index": t.uint8_t,
                "endpoint_info_records": t.LVList[EndpointInfoRecord],
            },
            direction=Direction.Server_to_Client,
        )
