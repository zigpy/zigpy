from __future__ import annotations

import dataclasses
import logging
from typing import ClassVar, TypeVar

import zigpy.types as t
from zigpy.zdo.types import (
    CHANNEL_CHANGE_REQ,
    CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ,
    AddrRequestType,
    Binding,
    MACCapabilityFlags,
    MultiAddress,
    Neighbor,
    NodeDescriptor,
    PowerDescriptor,
    Route,
    SimpleDescriptor,
    SizePrefixedSimpleDescriptor,
    Status,
    ZDOCmd,
)

LOGGER = logging.getLogger(__name__)


class ZDOPayload(t.Struct):
    command_id: ClassVar[ZDOCmd]


ZDOPayloadT = TypeVar("ZDOPayloadT", bound=ZDOPayload)


ZDO_COMMANDS: dict[ZDOCmd, type[ZDOPayload]] = {}


def command(cmd_id: ZDOCmd):
    def decorator(cls: type[ZDOPayloadT]) -> type[ZDOPayloadT]:
        cls.command_id = cmd_id
        ZDO_COMMANDS[cmd_id] = cls
        return cls

    return decorator


class UnknownCommand(t.Struct):
    """Payload of a ZDO command without a schema."""

    data: t.Bytes


@dataclasses.dataclass(frozen=True)
class ZDOCommand:
    """A ZDO frame. Its command ID is carried by the APS cluster ID, not the payload."""

    command_id: ZDOCmd
    tsn: t.uint8_t
    command: ZDOPayload | UnknownCommand

    def __post_init__(self) -> None:
        assert isinstance(self.command, UnknownCommand) or (
            self.command_id == self.command.command_id
        )

    @classmethod
    def deserialize(cls, cluster_id: t.uint16_t, data: bytes) -> ZDOCommand:
        command_id = ZDOCmd(cluster_id)
        tsn, data = t.uint8_t.deserialize(data)

        command: ZDOPayload | UnknownCommand

        if command_id in ZDO_COMMANDS:
            command, data = ZDO_COMMANDS[command_id].deserialize(data)
        else:
            command, data = UnknownCommand.deserialize(data)

        if data:
            LOGGER.warning("Data remains after deserializing ZDO frame: %r", data)

        return cls(command_id=command_id, tsn=tsn, command=command)

    def serialize(self) -> bytes:
        return self.tsn.serialize() + self.command.serialize()


# Device and Service Discovery Server Requests
@command(ZDOCmd.NWK_addr_req)
class NwkAddrReq(ZDOPayload):
    ieee_addr: t.EUI64
    request_type: AddrRequestType
    start_index: t.uint8_t


@command(ZDOCmd.IEEE_addr_req)
class IeeeAddrReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK
    request_type: AddrRequestType
    start_index: t.uint8_t


@command(ZDOCmd.Node_Desc_req)
class NodeDescReq(ZDOPayload):
    # TODO: R23 appends a list of TLVs
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Power_Desc_req)
class PowerDescReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Simple_Desc_req)
class SimpleDescReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK
    endpoint: t.uint8_t


@command(ZDOCmd.Active_EP_req)
class ActiveEpReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Match_Desc_req)
class MatchDescReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK
    profile_id: t.uint16_t
    in_cluster_list: t.LVList[t.uint16_t, t.uint8_t]
    out_cluster_list: t.LVList[t.uint16_t, t.uint8_t]


@command(ZDOCmd.User_Desc_req)
class UserDescReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.Discovery_Cache_req)
class DiscoveryCacheReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Device_annce)
class DeviceAnnce(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    capability: MACCapabilityFlags


@command(ZDOCmd.User_Desc_set)
class UserDescSet(ZDOPayload):
    nwk_addr_of_interest: t.NWK
    user_descriptor: t.CharacterString


@command(ZDOCmd.System_Server_Discovery_req)
class SystemServerDiscoveryReq(ZDOPayload):
    server_mask: t.uint16_t


@command(ZDOCmd.Discovery_store_req)
class DiscoveryStoreReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    node_desc_size: t.uint8_t
    power_desc_size: t.uint8_t
    active_ep_size: t.uint8_t
    simple_desc_size_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Node_Desc_store_req)
class NodeDescStoreReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    node_descriptor: NodeDescriptor


@command(ZDOCmd.Active_EP_store_req)
class ActiveEpStoreReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    active_ep_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Simple_Desc_store_req)
class SimpleDescStoreReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64
    simple_descriptor: SizePrefixedSimpleDescriptor


@command(ZDOCmd.Remove_node_cache_req)
class RemoveNodeCacheReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Find_node_cache_req)
class FindNodeCacheReq(ZDOPayload):
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_req)
class ExtendedSimpleDescReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK
    endpoint: t.uint8_t
    start_index: t.uint8_t


@command(ZDOCmd.Extended_Active_EP_req)
class ExtendedActiveEpReq(ZDOPayload):
    nwk_addr_of_interest: t.NWK
    start_index: t.uint8_t


@command(ZDOCmd.Parent_annce)
class ParentAnnce(ZDOPayload):
    children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Requests
@command(ZDOCmd.End_Device_Bind_req)
class EndDeviceBindReq(ZDOPayload):
    binding_target: t.uint16_t
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    profile_id: t.uint8_t
    in_cluster_list: t.LVList[t.uint8_t, t.uint8_t]
    out_cluster_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Bind_req)
class BindReq(ZDOPayload):
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    cluster_id: t.uint16_t
    dst_address: MultiAddress


@command(ZDOCmd.Unbind_req)
class UnbindReq(ZDOPayload):
    src_address: t.EUI64
    src_endpoint: t.uint8_t
    cluster_id: t.uint16_t
    dst_address: MultiAddress


# Network Management Server Services Requests
@command(ZDOCmd.Mgmt_Lqi_req)
class MgmtLqiReq(ZDOPayload):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Rtg_req)
class MgmtRtgReq(ZDOPayload):
    start_index: t.uint8_t


@command(ZDOCmd.Mgmt_Bind_req)
class MgmtBindReq(ZDOPayload):
    start_index: t.uint8_t


class LeaveOptions(t.bitmap8):
    """ZDO Mgmt_Leave_req Options."""

    NONE = 0
    RemoveChildren = 1 << 6
    Rejoin = 1 << 7


@command(ZDOCmd.Mgmt_Leave_req)
class MgmtLeaveReq(ZDOPayload):
    device_address: t.EUI64
    options: LeaveOptions


@command(ZDOCmd.Mgmt_Permit_Joining_req)
class MgmtPermitJoiningReq(ZDOPayload):
    # TODO: R23 appends a list of TLVs
    permit_duration: t.uint8_t
    tc_significant: t.Bool


@command(ZDOCmd.Mgmt_NWK_Update_req)
class MgmtNwkUpdateReq(ZDOPayload):
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
class NwkAddrRsp(ZDOPayload):
    status: Status
    ieee_addr: t.EUI64
    nwk_addr: t.NWK
    # Only present for an extended request, which the response does not indicate
    num_assoc_dev: t.uint8_t = t.StructField(optional=True)
    start_index: t.uint8_t = t.StructField(
        requires=lambda s: s.num_assoc_dev is not None and s.num_assoc_dev > 0
    )
    nwk_address_assoc_dev_list: t.List[t.NWK] = t.StructField(
        requires=lambda s: s.num_assoc_dev is not None and s.num_assoc_dev > 0,
        length=lambda s: s.num_assoc_dev,
    )


@command(ZDOCmd.IEEE_addr_rsp)
class IeeeAddrRsp(ZDOPayload):
    status: Status
    ieee_addr: t.EUI64
    nwk_addr: t.NWK
    # Only present for an extended request, which the response does not indicate
    num_assoc_dev: t.uint8_t = t.StructField(optional=True)
    start_index: t.uint8_t = t.StructField(
        requires=lambda s: s.num_assoc_dev is not None and s.num_assoc_dev > 0
    )
    nwk_addr_assoc_dev_list: t.List[t.NWK] = t.StructField(
        requires=lambda s: s.num_assoc_dev is not None and s.num_assoc_dev > 0,
        length=lambda s: s.num_assoc_dev,
    )


@command(ZDOCmd.Node_Desc_rsp)
class NodeDescRsp(ZDOPayload):
    # TODO: R23 appends a list of TLVs
    status: Status
    nwk_addr_of_interest: t.NWK
    node_descriptor: NodeDescriptor = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Power_Desc_rsp)
class PowerDescRsp(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK
    power_descriptor: PowerDescriptor = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Simple_Desc_rsp)
class SimpleDescRsp(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK
    length: t.uint8_t
    simple_descriptor: SimpleDescriptor = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Active_EP_rsp)
class ActiveEpRsp(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK
    active_ep_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.Match_Desc_rsp)
class MatchDescRsp(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK
    match_list: t.LVList[t.uint8_t, t.uint8_t]


@command(ZDOCmd.User_Desc_rsp)
class UserDescRsp(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK
    user_descriptor: t.CharacterString


@command(ZDOCmd.Discovery_Cache_rsp)
class DiscoveryCacheRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.User_Desc_conf)
class UserDescConf(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK


@command(ZDOCmd.System_Server_Discovery_rsp)
class SystemServerDiscoveryRsp(ZDOPayload):
    status: Status
    server_mask: t.uint16_t


@command(ZDOCmd.Discovery_Store_rsp)
class DiscoveryStoreRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Node_Desc_store_rsp)
class NodeDescStoreRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Power_Desc_store_rsp)
class PowerDescStoreRsp(ZDOPayload):
    status: Status
    ieee_addr: t.EUI64
    power_descriptor: PowerDescriptor


@command(ZDOCmd.Active_EP_store_rsp)
class ActiveEpStoreRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Simple_Desc_store_rsp)
class SimpleDescStoreRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Remove_node_cache_rsp)
class RemoveNodeCacheRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Find_node_cache_rsp)
class FindNodeCacheRsp(ZDOPayload):
    cache_nwk_addr: t.EUI64
    nwk_addr: t.NWK
    ieee_addr: t.EUI64


@command(ZDOCmd.Extended_Simple_Desc_rsp)
class ExtendedSimpleDescRsp(ZDOPayload):
    status: Status
    nwk_addr: t.NWK
    endpoint: t.uint8_t
    app_input_cluster_count: t.uint8_t
    app_output_cluster_count: t.uint8_t
    start_index: t.uint8_t
    app_cluster_list: t.List[t.uint16_t] = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Extended_Active_EP_rsp)
class ExtendedActiveEpRsp(ZDOPayload):
    status: Status
    nwk_addr_of_interest: t.NWK
    active_ep_count: t.uint8_t
    start_index: t.uint8_t
    active_ep_list: t.List[t.uint8_t]


@command(ZDOCmd.Parent_annce_rsp)
class ParentAnnceRsp(ZDOPayload):
    status: Status
    children: t.LVList[t.EUI64, t.uint8_t]


# Bind Management Server Services Responses
@command(ZDOCmd.End_Device_Bind_rsp)
class EndDeviceBindRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Bind_rsp)
class BindRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Unbind_rsp)
class UnbindRsp(ZDOPayload):
    status: Status


# Network Management Server Services Responses
@command(ZDOCmd.Mgmt_Lqi_rsp)
class MgmtLqiRsp(ZDOPayload):
    status: Status
    neighbor_table_entries: t.uint8_t = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    neighbor_table_list: t.LVList[Neighbor, t.uint8_t] = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Rtg_rsp)
class MgmtRtgRsp(ZDOPayload):
    status: Status
    routing_table_entries: t.uint8_t = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    routing_table_list: t.LVList[Route, t.uint8_t] = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Bind_rsp)
class MgmtBindRsp(ZDOPayload):
    status: Status
    binding_table_entries: t.uint8_t = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    start_index: t.uint8_t = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )
    binding_table_list: t.LVList[Binding, t.uint8_t] = t.StructField(
        requires=lambda s: s.status == Status.SUCCESS
    )


@command(ZDOCmd.Mgmt_Leave_rsp)
class MgmtLeaveRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Mgmt_Permit_Joining_rsp)
class MgmtPermitJoiningRsp(ZDOPayload):
    status: Status


@command(ZDOCmd.Mgmt_NWK_Update_rsp)
class MgmtNwkUpdateRsp(ZDOPayload):
    status: Status
    scanned_channels: t.Channels
    total_transmissions: t.uint16_t
    transmission_failures: t.uint16_t
    energy_values: t.LVList[t.uint8_t, t.uint8_t]
