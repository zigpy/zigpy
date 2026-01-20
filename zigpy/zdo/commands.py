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
    IEEEAddr: t.EUI64
    RequestType: AddrRequestType
    StartIndex: t.uint8_t


@command(ZDOCmd.IEEE_addr_req)
class IeeeAddrReq(t.Struct):
    NWKAddrOfInterest: t.NWK
    RequestType: AddrRequestType
    StartIndex: t.uint8_t


@command(ZDOCmd.Node_Desc_req)
class NodeDescReq(t.Struct):
    NWKAddrOfInterest: t.NWK


@command(ZDOCmd.Power_Desc_req)
class PowerDescReq(t.Struct):
    NWKAddrOfInterest: t.NWK


@command(ZDOCmd.Simple_Desc_req)
class SimpleDescReq(t.Struct):
    NWKAddrOfInterest: t.NWK
    EndPoint: t.uint8_t


@command(ZDOCmd.Active_EP_req)
class ActiveEpReq(t.Struct):
    NWKAddrOfInterest: t.NWK


@command(ZDOCmd.Match_Desc_req)
class MatchDescReq(t.Struct):
    NWKAddrOfInterest: t.NWK
    ProfileID: t.uint16_t
    InClusterList: t.LVList[t.uint16_t, t.uint8_t]
    OutClusterList: t.LVList[t.uint16_t, t.uint8_t]


@command(ZDOCmd.User_Desc_req)
class UserDescReq(t.Struct):
    NWKAddrOfInterest: t.NWK


@command(ZDOCmd.Discovery_Cache_req)
class DiscoveryCacheReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64


@command(ZDOCmd.Device_annce)
class DeviceAnnce(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64
    Capability: t.uint8_t


@command(ZDOCmd.User_Desc_set)
class UserDescSet(t.Struct):
    NWKAddrOfInterest: t.NWK
    UserDescriptor: t.CharacterString


@command(ZDOCmd.System_Server_Discovery_req)
class SystemServerDiscoveryReq(t.Struct):
    ServerMask: t.uint16_t


@command(ZDOCmd.Discovery_store_req)
class DiscoveryStoreReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64
    NodeDescSize: t.uint8_t
    PowerDescSize: t.uint8_t
    ActiveEPSize: t.uint8_t
    SimpleDescSizeList: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Node_Desc_store_req)
class NodeDescStoreReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64
    NodeDescriptor: NodeDescriptor


@command(ZDOCmd.Active_EP_store_req)
class ActiveEpStoreReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64
    ActiveEPList: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Simple_Desc_store_req)
class SimpleDescStoreReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64
    SimpleDescriptor: SizePrefixedSimpleDescriptor


@command(ZDOCmd.Remove_node_cache_req)
class RemoveNodeCacheReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64


@command(ZDOCmd.Find_node_cache_req)
class FindNodeCacheReq(t.Struct):
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_req)
class ExtendedSimpleDescReq(t.Struct):
    NWKAddrOfInterest: t.NWK
    EndPoint: t.uint8_t
    StartIndex: t.uint8_t


@command(ZDOCmd.Extended_Active_EP_req)
class ExtendedActiveEpReq(t.Struct):
    NWKAddrOfInterest: t.NWK
    StartIndex: t.uint8_t


@command(ZDOCmd.Parent_annce)
class ParentAnnce(t.Struct):
    Children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Requests
@command(ZDOCmd.End_Device_Bind_req)
class EndDeviceBindReq(t.Struct):
    BindingTarget: t.uint16_t
    SrcAddress: t.EUI64
    SrcEndpoint: t.uint8_t
    ProfileID: t.uint8_t
    InClusterList: t.LVList[t.uint8_t, t.uint8_t]
    OutClusterList: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Bind_req)
class BindReq(t.Struct):
    SrcAddress: t.EUI64
    SrcEndpoint: t.uint8_t
    ClusterID: t.uint16_t
    DstAddress: MultiAddress


@command(ZDOCmd.Unbind_req)
class UnbindReq(t.Struct):
    SrcAddress: t.EUI64
    SrcEndpoint: t.uint8_t
    ClusterID: t.uint16_t
    DstAddress: MultiAddress


# Network Management Server Services Requests
@command(ZDOCmd.Mgmt_Lqi_req)
class MgmtLqiReq(t.Struct):
    StartIndex: t.uint8_t


@command(ZDOCmd.Mgmt_Rtg_req)
class MgmtRtgReq(t.Struct):
    StartIndex: t.uint8_t


@command(ZDOCmd.Mgmt_Bind_req)
class MgmtBindReq(t.Struct):
    StartIndex: t.uint8_t


@command(ZDOCmd.Mgmt_Leave_req)
class MgmtLeaveReq(t.Struct):
    DeviceAddress: t.EUI64
    Options: t.bitmap8


@command(ZDOCmd.Mgmt_Permit_Joining_req)
class MgmtPermitJoiningReq(t.Struct):
    PermitDuration: t.uint8_t
    TC_Significant: t.Bool


@command(ZDOCmd.Mgmt_NWK_Update_req)
class MgmtNwkUpdateReq(t.Struct):
    ScanChannels: t.Channels
    ScanDuration: t.uint8_t
    ScanCount: t.uint8_t = t.StructField(requires=lambda s: s.ScanDuration <= 0x05)
    nwkUpdateId: t.uint8_t = t.StructField(
        requires=lambda s: s.ScanDuration
        in (CHANNEL_CHANGE_REQ, CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ)
    )
    nwkManagerAddr: t.NWK = t.StructField(
        requires=lambda s: s.ScanDuration == CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ
    )


# Device and Service Discovery Server Responses
@command(ZDOCmd.NWK_addr_rsp)
class NwkAddrRsp(t.Struct):
    Status: Status
    IEEEAddr: t.EUI64
    NWKAddr: t.NWK
    NumAssocDev: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    StartIndex: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    NWKAddressAssocDevList: t.List[t.NWK] | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.IEEE_addr_rsp)
class IeeeAddrRsp(t.Struct):
    Status: Status
    IEEEAddr: t.EUI64
    NWKAddr: t.NWK
    NumAssocDev: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    StartIndex: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    NWKAddrAssocDevList: t.List[t.NWK] | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Node_Desc_rsp)
class NodeDescRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    NodeDescriptor: NodeDescriptor | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Power_Desc_rsp)
class PowerDescRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    PowerDescriptor: PowerDescriptor | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Simple_Desc_rsp)
class SimpleDescRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    SimpleDescriptor: SizePrefixedSimpleDescriptor | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Active_EP_rsp)
class ActiveEpRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    ActiveEPList: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Match_Desc_rsp)
class MatchDescRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    MatchList: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.User_Desc_rsp)
class UserDescRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    UserDescriptor: t.CharacterString


@command(ZDOCmd.Discovery_Cache_rsp)
class DiscoveryCacheRsp(t.Struct):
    Status: Status


@command(ZDOCmd.User_Desc_conf)
class UserDescConf(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK


@command(ZDOCmd.System_Server_Discovery_rsp)
class SystemServerDiscoveryRsp(t.Struct):
    Status: Status
    ServerMask: t.uint16_t


@command(ZDOCmd.Discovery_Store_rsp)
class DiscoveryStoreRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Node_Desc_store_rsp)
class NodeDescStoreRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Power_Desc_store_rsp)
class PowerDescStoreRsp(t.Struct):
    Status: Status
    IEEEAddr: t.EUI64
    PowerDescriptor: PowerDescriptor


@command(ZDOCmd.Active_EP_store_rsp)
class ActiveEpStoreRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Simple_Desc_store_rsp)
class SimpleDescStoreRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Remove_node_cache_rsp)
class RemoveNodeCacheRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Find_node_cache_rsp)
class FindNodeCacheRsp(t.Struct):
    CacheNWKAddr: t.EUI64
    NWKAddr: t.NWK
    IEEEAddr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_rsp)
class ExtendedSimpleDescRsp(t.Struct):
    Status: Status
    NWKAddr: t.NWK
    Endpoint: t.uint8_t
    AppInputClusterCount: t.uint8_t
    AppOutputClusterCount: t.uint8_t
    StartIndex: t.uint8_t
    AppClusterList: t.List[t.uint16_t] | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Extended_Active_EP_rsp)
class ExtendedActiveEpRsp(t.Struct):
    Status: Status
    NWKAddrOfInterest: t.NWK
    ActiveEPCount: t.uint8_t
    StartIndex: t.uint8_t
    ActiveEPList: t.List[t.uint8_t]


@command(ZDOCmd.Parent_annce_rsp)
class ParentAnnceRsp(t.Struct):
    Status: Status
    Children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Responses
@command(ZDOCmd.End_Device_Bind_rsp)
class EndDeviceBindRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Bind_rsp)
class BindRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Unbind_rsp)
class UnbindRsp(t.Struct):
    Status: Status


# Network Management Server Services Responses
@command(ZDOCmd.Mgmt_Lqi_rsp)
class MgmtLqiRsp(t.Struct):
    Status: Status
    Entries: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    StartIndex: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    NeighborTableList: t.LVList[Neighbor, t.uint8_t] | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Rtg_rsp)
class MgmtRtgRsp(t.Struct):
    Status: Status
    Entries: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    StartIndex: t.uint8_t | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )
    RoutingTableList: t.LVList[Route, t.uint8_t] | None = t.StructField(
        requires=lambda s: s.Status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Bind_rsp)
class MgmtBindRsp(t.Struct):
    Status: Status
    BindingTableEntries: t.uint8_t
    StartIndex: t.uint8_t
    BindingTableList: t.LVList[Binding, t.uint8_t]


@command(ZDOCmd.Mgmt_Leave_rsp)
class MgmtLeaveRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Mgmt_Permit_Joining_rsp)
class MgmtPermitJoiningRsp(t.Struct):
    Status: Status


@command(ZDOCmd.Mgmt_NWK_Update_rsp)
class MgmtNwkUpdateRsp(t.Struct):
    Status: Status
    ScannedChannels: t.Channels
    TotalTransmissions: t.uint16_t
    TransmissionFailures: t.uint16_t
    EnergyValues: t.LVList[t.uint8_t, t.uint8_t]
