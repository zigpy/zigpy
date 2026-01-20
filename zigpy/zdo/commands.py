from __future__ import annotations

import zigpy.types as t
from typing import ClassVar
from zigpy.zdo.types import (
    CHANNEL_CHANGE_REQ,
    CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ,
    AddrRequestType,
    Binding,
    MultiAddress,
    Neighbor,
    NodeDescriptor,
    PowerDescriptor,
    Route,
    SizePrefixedSimpleDescriptor,
    Status,
    ZDOCmd,
)



class ZDOCommand(t.Struct):
    command_id: ClassVar[ZDOCmd]


ZDO_COMMANDS: dict[ZDOCmd, type[ZDOCommand]] = {}


def command(cmd_id: ZDOCmd):
    def decorator[T](cls: T) -> T:
        cls.command_id = cmd_id
        ZDO_COMMANDS[cmd_id] = cls
        return cls

    return decorator


# Device and Service Discovery Server Requests
@command(ZDOCmd.NWK_addr_req)
class NwkAddrReq(ZDOCommand):
    ieee_addr: t.EUI64
    request_type: AddrRequestType
    start_index: t.uint8_t


@command(ZDOCmd.IEEE_addr_req)
class IeeeAddrReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK
    request_type: AddrRequestType
    start_index: t.uint8_t


@command(ZDOCmd.Node_Desc_req)
class NodeDescReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Power_Desc_req)
class PowerDescReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Simple_Desc_req)
class SimpleDescReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK
    endpoint: t.uint8_t


@command(ZDOCmd.Active_EP_req)
class ActiveEpReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Match_Desc_req)
class MatchDescReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK
    profile_id: t.uint16_t
    in_cluster_list: t.LVList[t.uint16_t, t.uint8_t]
    out_cluster_list: t.LVList[t.uint16_t, t.uint8_t]


@command(ZDOCmd.User_Desc_req)
class UserDescReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Discovery_Cache_req)
class DiscoveryCacheReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Device_annce)
class DeviceAnnce(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    capability: t.uint8_t


@command(ZDOCmd.User_Desc_set)
class UserDescSet(ZDOCommand):
    nwk_addr_of_interest: t.NWK
    user_descriptor: t.CharacterString


@command(ZDOCmd.System_Server_Discovery_req)
class SystemServerDiscoveryReq(ZDOCommand):
    server_mask: t.uint16_t


@command(ZDOCmd.Discovery_store_req)
class DiscoveryStoreReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    node_desc_size: t.uint8_t
    power_desc_size: t.uint8_t
    active_ep_size: t.uint8_t
    simple_desc_size_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Node_Desc_store_req)
class NodeDescStoreReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    node_descriptor: NodeDescriptor


@command(ZDOCmd.Active_EP_store_req)
class ActiveEpStoreReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    active_ep_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Simple_Desc_store_req)
class SimpleDescStoreReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    simple_descriptor: SizePrefixedSimpleDescriptor


@command(ZDOCmd.Remove_node_cache_req)
class RemoveNodeCacheReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Find_node_cache_req)
class FindNodeCacheReq(ZDOCommand):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_req)
class ExtendedSimpleDescReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK
    endpoint: t.uint8_t
    start_index: t.uint8_t


@command(ZDOCmd.Extended_Active_EP_req)
class ExtendedActiveEpReq(ZDOCommand):
    nwk_addr_of_interest: t.NWK
    start_index: t.uint8_t


@command(ZDOCmd.Parent_annce)
class ParentAnnce(ZDOCommand):
    children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Requests
@command(ZDOCmd.End_Device_Bind_req)
class EndDeviceBindReq(ZDOCommand):
    binding_target: t.uint16_t
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    profile_id: t.uint8_t
    in_cluster_list: t.LVList[t.uint8_t, t.uint8_t]
    out_cluster_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Bind_req)
class BindReq(ZDOCommand):
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    cluster_id: t.uint16_t
    dst_address: MultiAddress


@command(ZDOCmd.Unbind_req)
class UnbindReq(ZDOCommand):
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    cluster_id: t.uint16_t
    dst_address: MultiAddress


# Network Management Server Services Requests
@command(ZDOCmd.Mgmt_Lqi_req)
class MgmtLqiReq(ZDOCommand):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Rtg_req)
class MgmtRtgReq(ZDOCommand):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Bind_req)
class MgmtBindReq(ZDOCommand):
    start_index: t.uint8_t


class LeaveOptions(t.bitmap8):
    """ZDO Mgmt_Leave_req Options."""

    NONE = 0
    RemoveChildren = 1 << 6
    Rejoin = 1 << 7

@command(ZDOCmd.Mgmt_Leave_req)
class MgmtLeaveReq(ZDOCommand):
    device_address: t.EUI64
    options: LeaveOptions


@command(ZDOCmd.Mgmt_Permit_Joining_req)
class MgmtPermitJoiningReq(ZDOCommand):
    permit_duration: t.uint8_t
    tc_significant: t.Bool


@command(ZDOCmd.Mgmt_NWK_Update_req)
class MgmtNwkUpdateReq(ZDOCommand):
    scan_channels: t.Channels
    scan_duration: t.uint8_t
    scan_count: t.uint8_t = t.StructField(requires=lambda s: s.scan_duration <= 0x05)
    nwk_update_id: t.uint8_t = t.StructField(
        requires=lambda s: s.scan_duration
        in (CHANNEL_CHANGE_REQ, CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ)
    )
    nwk_manager_addr: t.NWK = t.StructField(
        requires=lambda s: s.scan_duration == CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ
    )


# Device and Service Discovery Server Responses
@command(ZDOCmd.NWK_addr_rsp)
class NwkAddrRsp(ZDOCommand):
    status: Status
    ieee_addr: t.EUI64
    nwk_addr: t.NWK
    num_assoc_dev: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    nwk_address_assoc_dev_list: t.List[t.NWK] | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.IEEE_addr_rsp)
class IeeeAddrRsp(ZDOCommand):
    status: Status
    ieee_addr: t.EUI64
    nwk_addr: t.NWK
    num_assoc_dev: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    nwk_addr_assoc_dev_list: t.List[t.NWK] | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Node_Desc_rsp)
class NodeDescRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    node_descriptor: NodeDescriptor | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Power_Desc_rsp)
class PowerDescRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    power_descriptor: PowerDescriptor | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Simple_Desc_rsp)
class SimpleDescRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    simple_descriptor: SizePrefixedSimpleDescriptor | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Active_EP_rsp)
class ActiveEpRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    active_ep_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Match_Desc_rsp)
class MatchDescRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    match_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.User_Desc_rsp)
class UserDescRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    user_descriptor: t.CharacterString


@command(ZDOCmd.Discovery_Cache_rsp)
class DiscoveryCacheRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.User_Desc_conf)
class UserDescConf(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.System_Server_Discovery_rsp)
class SystemServerDiscoveryRsp(ZDOCommand):
    status: Status
    server_mask: t.uint16_t


@command(ZDOCmd.Discovery_Store_rsp)
class DiscoveryStoreRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Node_Desc_store_rsp)
class NodeDescStoreRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Power_Desc_store_rsp)
class PowerDescStoreRsp(ZDOCommand):
    status: Status
    ieee_addr: t.EUI64
    power_descriptor: PowerDescriptor


@command(ZDOCmd.Active_EP_store_rsp)
class ActiveEpStoreRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Simple_Desc_store_rsp)
class SimpleDescStoreRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Remove_node_cache_rsp)
class RemoveNodeCacheRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Find_node_cache_rsp)
class FindNodeCacheRsp(ZDOCommand):
    cache_nwk_addr: t.EUI64
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_rsp)
class ExtendedSimpleDescRsp(ZDOCommand):
    status: Status
    nwk_addr: t.NWK
    endpoint: t.uint8_t
    app_input_cluster_count: t.uint8_t
    app_output_cluster_count: t.uint8_t
    start_index: t.uint8_t
    app_cluster_list: t.List[t.uint16_t] | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Extended_Active_EP_rsp)
class ExtendedActiveEpRsp(ZDOCommand):
    status: Status
    nwk_addr_of_interest: t.NWK
    active_ep_count: t.uint8_t
    start_index: t.uint8_t
    active_ep_list: t.List[t.uint8_t]


@command(ZDOCmd.Parent_annce_rsp)
class ParentAnnceRsp(ZDOCommand):
    status: Status
    children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Responses
@command(ZDOCmd.End_Device_Bind_rsp)
class EndDeviceBindRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Bind_rsp)
class BindRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Unbind_rsp)
class UnbindRsp(ZDOCommand):
    status: Status


# Network Management Server Services Responses
@command(ZDOCmd.Mgmt_Lqi_rsp)
class MgmtLqiRsp(ZDOCommand):
    status: Status
    entries: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    neighbor_table_list: t.LVList[Neighbor, t.uint8_t] | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Rtg_rsp)
class MgmtRtgRsp(ZDOCommand):
    status: Status
    entries: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    routing_table_list: t.LVList[Route, t.uint8_t] | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Bind_rsp)
class MgmtBindRsp(ZDOCommand):
    status: Status
    binding_table_entries: t.uint8_t
    start_index: t.uint8_t
    binding_table_list: t.LVList[Binding, t.uint8_t]


@command(ZDOCmd.Mgmt_Leave_rsp)
class MgmtLeaveRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Mgmt_Permit_Joining_rsp)
class MgmtPermitJoiningRsp(ZDOCommand):
    status: Status


@command(ZDOCmd.Mgmt_NWK_Update_rsp)
class MgmtNwkUpdateRsp(ZDOCommand):
    status: Status
    scanned_channels: t.Channels
    total_transmissions: t.uint16_t
    transmission_failures: t.uint16_t
    energy_values: t.LVList[t.uint8_t, t.uint8_t]
