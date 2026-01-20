from __future__ import annotations

import zigpy.types as t
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

ZDO_COMMANDS: dict[ZDOCmd, type[t.Struct]] = {}


def command(cmd_id: ZDOCmd):
    def decorator(cls: type[t.Struct]) -> type[t.Struct]:
        ZDO_COMMANDS[cmd_id] = cls
        return cls

    return decorator


# Device and Service Discovery Server Requests
@command(ZDOCmd.NWK_addr_req)
class NwkAddrReq(t.Struct):
    ieee_addr: t.EUI64
    request_type: AddrRequestType
    start_index: t.uint8_t


@command(ZDOCmd.IEEE_addr_req)
class IeeeAddrReq(t.Struct):
    nwk_addr_of_interest: t.NWK
    request_type: AddrRequestType
    start_index: t.uint8_t


@command(ZDOCmd.Node_Desc_req)
class NodeDescReq(t.Struct):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Power_Desc_req)
class PowerDescReq(t.Struct):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Simple_Desc_req)
class SimpleDescReq(t.Struct):
    nwk_addr_of_interest: t.NWK
    endpoint: t.uint8_t


@command(ZDOCmd.Active_EP_req)
class ActiveEpReq(t.Struct):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Match_Desc_req)
class MatchDescReq(t.Struct):
    nwk_addr_of_interest: t.NWK
    profile_id: t.uint16_t
    in_cluster_list: t.LVList[t.uint16_t, t.uint8_t]
    out_cluster_list: t.LVList[t.uint16_t, t.uint8_t]


@command(ZDOCmd.User_Desc_req)
class UserDescReq(t.Struct):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Discovery_Cache_req)
class DiscoveryCacheReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Device_annce)
class DeviceAnnce(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    capability: t.uint8_t


@command(ZDOCmd.User_Desc_set)
class UserDescSet(t.Struct):
    nwk_addr_of_interest: t.NWK
    user_descriptor: t.CharacterString


@command(ZDOCmd.System_Server_Discovery_req)
class SystemServerDiscoveryReq(t.Struct):
    server_mask: t.uint16_t


@command(ZDOCmd.Discovery_store_req)
class DiscoveryStoreReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    node_desc_size: t.uint8_t
    power_desc_size: t.uint8_t
    active_ep_size: t.uint8_t
    simple_desc_size_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Node_Desc_store_req)
class NodeDescStoreReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    node_descriptor: NodeDescriptor


@command(ZDOCmd.Active_EP_store_req)
class ActiveEpStoreReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    active_ep_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Simple_Desc_store_req)
class SimpleDescStoreReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    simple_descriptor: SizePrefixedSimpleDescriptor


@command(ZDOCmd.Remove_node_cache_req)
class RemoveNodeCacheReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Find_node_cache_req)
class FindNodeCacheReq(t.Struct):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_req)
class ExtendedSimpleDescReq(t.Struct):
    nwk_addr_of_interest: t.NWK
    endpoint: t.uint8_t
    start_index: t.uint8_t


@command(ZDOCmd.Extended_Active_EP_req)
class ExtendedActiveEpReq(t.Struct):
    nwk_addr_of_interest: t.NWK
    start_index: t.uint8_t


@command(ZDOCmd.Parent_annce)
class ParentAnnce(t.Struct):
    children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Requests
@command(ZDOCmd.End_Device_Bind_req)
class EndDeviceBindReq(t.Struct):
    binding_target: t.uint16_t
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    profile_id: t.uint8_t
    in_cluster_list: t.LVList[t.uint8_t, t.uint8_t]
    out_cluster_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Bind_req)
class BindReq(t.Struct):
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    cluster_id: t.uint16_t
    dst_address: MultiAddress


@command(ZDOCmd.Unbind_req)
class UnbindReq(t.Struct):
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    cluster_id: t.uint16_t
    dst_address: MultiAddress


# Network Management Server Services Requests
@command(ZDOCmd.Mgmt_Lqi_req)
class MgmtLqiReq(t.Struct):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Rtg_req)
class MgmtRtgReq(t.Struct):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Bind_req)
class MgmtBindReq(t.Struct):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Leave_req)
class MgmtLeaveReq(t.Struct):
    device_address: t.EUI64
    options: t.bitmap8


@command(ZDOCmd.Mgmt_Permit_Joining_req)
class MgmtPermitJoiningReq(t.Struct):
    permit_duration: t.uint8_t
    tc_significant: t.Bool


@command(ZDOCmd.Mgmt_NWK_Update_req)
class MgmtNwkUpdateReq(t.Struct):
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
class NwkAddrRsp(t.Struct):
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
class IeeeAddrRsp(t.Struct):
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
class NodeDescRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    node_descriptor: NodeDescriptor | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Power_Desc_rsp)
class PowerDescRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    power_descriptor: PowerDescriptor | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Simple_Desc_rsp)
class SimpleDescRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    simple_descriptor: SizePrefixedSimpleDescriptor | None = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Active_EP_rsp)
class ActiveEpRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    active_ep_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Match_Desc_rsp)
class MatchDescRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    match_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.User_Desc_rsp)
class UserDescRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    user_descriptor: t.CharacterString


@command(ZDOCmd.Discovery_Cache_rsp)
class DiscoveryCacheRsp(t.Struct):
    status: Status


@command(ZDOCmd.User_Desc_conf)
class UserDescConf(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.System_Server_Discovery_rsp)
class SystemServerDiscoveryRsp(t.Struct):
    status: Status
    server_mask: t.uint16_t


@command(ZDOCmd.Discovery_Store_rsp)
class DiscoveryStoreRsp(t.Struct):
    status: Status


@command(ZDOCmd.Node_Desc_store_rsp)
class NodeDescStoreRsp(t.Struct):
    status: Status


@command(ZDOCmd.Power_Desc_store_rsp)
class PowerDescStoreRsp(t.Struct):
    status: Status
    ieee_addr: t.EUI64
    power_descriptor: PowerDescriptor


@command(ZDOCmd.Active_EP_store_rsp)
class ActiveEpStoreRsp(t.Struct):
    status: Status


@command(ZDOCmd.Simple_Desc_store_rsp)
class SimpleDescStoreRsp(t.Struct):
    status: Status


@command(ZDOCmd.Remove_node_cache_rsp)
class RemoveNodeCacheRsp(t.Struct):
    status: Status


@command(ZDOCmd.Find_node_cache_rsp)
class FindNodeCacheRsp(t.Struct):
    cache_nwk_addr: t.EUI64
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_rsp)
class ExtendedSimpleDescRsp(t.Struct):
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
class ExtendedActiveEpRsp(t.Struct):
    status: Status
    nwk_addr_of_interest: t.NWK
    active_ep_count: t.uint8_t
    start_index: t.uint8_t
    active_ep_list: t.List[t.uint8_t]


@command(ZDOCmd.Parent_annce_rsp)
class ParentAnnceRsp(t.Struct):
    status: Status
    children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Responses
@command(ZDOCmd.End_Device_Bind_rsp)
class EndDeviceBindRsp(t.Struct):
    status: Status


@command(ZDOCmd.Bind_rsp)
class BindRsp(t.Struct):
    status: Status


@command(ZDOCmd.Unbind_rsp)
class UnbindRsp(t.Struct):
    status: Status


# Network Management Server Services Responses
@command(ZDOCmd.Mgmt_Lqi_rsp)
class MgmtLqiRsp(t.Struct):
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
class MgmtRtgRsp(t.Struct):
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
class MgmtBindRsp(t.Struct):
    status: Status
    binding_table_entries: t.uint8_t
    start_index: t.uint8_t
    binding_table_list: t.LVList[Binding, t.uint8_t]


@command(ZDOCmd.Mgmt_Leave_rsp)
class MgmtLeaveRsp(t.Struct):
    status: Status


@command(ZDOCmd.Mgmt_Permit_Joining_rsp)
class MgmtPermitJoiningRsp(t.Struct):
    status: Status


@command(ZDOCmd.Mgmt_NWK_Update_rsp)
class MgmtNwkUpdateRsp(t.Struct):
    status: Status
    scanned_channels: t.Channels
    total_transmissions: t.uint16_t
    transmission_failures: t.uint16_t
    energy_values: t.LVList[t.uint8_t, t.uint8_t]
