"""Zigbee Green Power Domain"""

from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.types.struct import StructField
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    ZCLAttributeDef,
    ZCLCommandDef,
)
import zigpy.zgp.types as zgptypes


class CommissioningNotificationOptions(t.Struct):
    application_id: zgptypes.ApplicationID
    rx_after_tx: t.uint1_t
    security_level: zgptypes.SecurityLevel
    security_key_type: zgptypes.SecurityKeyType
    security_failed: t.uint1_t
    bidirectional_cap: t.uint1_t
    proxy_info_present: t.uint1_t
    _reserved: t.uint6_t


# Figure 27
class CommissioningNotificationSchema(foundation.CommandSchema):
    options: CommissioningNotificationOptions
    gpd_id: zgptypes.DeviceID
    frame_counter: t.uint32_t
    command_id: t.uint8_t
    payload: t.LVBytes
    gpp_short_addr: t.uint16_t = StructField(
        requires=lambda s: s.proxy_info_present, optional=True
    )
    distance: t.uint8_t = StructField(
        requires=lambda s: s.proxy_info_present, optional=True
    )
    mic: t.uint32_t = StructField(requires=lambda s: s.security_failed, optional=True)


class ResponseOptions(t.Struct):
    application_id: zgptypes.ApplicationID
    _reserved: t.uint5_t


# Figure 45
class ResponseSchema(foundation.CommandSchema):
    options: ResponseOptions
    temp_master_short_addr: t.uint16_t
    temp_master_tx_channel: t.uint8_t
    gpd_id: zgptypes.DeviceID
    gpd_command_id: t.uint8_t
    gpd_command_payload: t.LVBytes


# Figure 26
class PairingSearchOptions(t.Struct):
    application_id: zgptypes.ApplicationID
    request_unicast_sink: t.uint1_t
    request_derived_groupcast_sink: t.uint1_t
    request_commissioned_groupcast_sink: t.uint1_t
    request_frame_counter: t.uint1_t
    request_security_key: t.uint1_t
    _reserved: t.uint8_t


# Figure 25
class PairingSearchSchema(foundation.CommandSchema):
    options: PairingSearchOptions
    gpd_id: zgptypes.DeviceID


# Figure 24
class NotificationOptions(t.Struct):
    application_id: zgptypes.ApplicationID
    also_unicast: t.uint1_t
    also_derived_group: t.uint1_t
    also_commissioned_group: t.uint1_t
    security_level: zgptypes.SecurityLevel
    security_key_type: zgptypes.SecurityKeyType
    appoint_temp_master: t.uint1_t
    tx_queue_full: t.uint1_t
    _reserved: t.uint3_t


# Figure 23
class NotificationSchema(foundation.CommandSchema):
    options: NotificationOptions
    gpd_id: zgptypes.DeviceID
    frame_counter: t.uint32_t
    command_id: t.uint8_t
    payload: t.LVBytes
    short_addr: t.uint16_t = StructField(
        requires=lambda s: s.options.appoint_temp_master
    )
    distance: t.uint8_t = StructField(requires=lambda s: s.options.appoint_temp_master)


# Figure 40, 41
class PairingOptions(t.Struct):
    application_id: zgptypes.ApplicationID
    add_sink: t.uint1_t
    remove_gpd: t.uint1_t
    communication_mode: zgptypes.CommunicationMode
    gpd_fixed: t.uint1_t
    gpd_mac_seq_num_cap: t.uint1_t
    security_level: zgptypes.SecurityLevel
    security_key_type: zgptypes.SecurityKeyType
    security_frame_counter_present: t.uint1_t
    security_key_present: t.uint1_t
    assigned_alias_present: t.uint1_t
    forwarding_radius_present: t.uint1_t
    _reserved: t.uint6_t


# Figure 38, 39
class PairingSchema(foundation.CommandSchema):
    options: PairingOptions
    gpd_id: zgptypes.DeviceID
    # Table 37
    sink_ieee: t.EUI64 = StructField(
        requires=lambda s: not s.options.remove_gpd
        and s.options.communication_mode
        in (
            zgptypes.CommunicationMode.Unicast,
            zgptypes.CommunicationMode.UnicastLightweight,
        )
    )
    sink_nwk_addr: t.NWK = StructField(
        requires=lambda s: not s.options.remove_gpd
        and s.options.communication_mode
        in (
            zgptypes.CommunicationMode.Unicast,
            zgptypes.CommunicationMode.UnicastLightweight,
        )
    )
    sink_group: t.Group = StructField(
        requires=lambda s: not s.options.remove_gpd
        and s.options.communication_mode
        in (
            zgptypes.CommunicationMode.GroupcastForwardToDGroup,
            zgptypes.CommunicationMode.GroupcastForwardToCommGroup,
        )
    )

    device_id: t.uint8_t = StructField(requires=lambda s: s.options.add_sink)
    frame_counter: t.uint32_t = StructField(
        requires=lambda s: s.options.add_sink
        and s.options.security_frame_counter_present
    )
    key: t.KeyData = StructField(
        requires=lambda s: s.options.add_sink and s.options.security_key_present
    )
    alias: t.uint16_t = StructField(
        requires=lambda s: s.options.add_sink and s.options.assigned_alias_present
    )
    forwarding_radius: t.uint8_t = StructField(
        requires=lambda s: s.options.add_sink and s.options.forwarding_radius_present
    )


# Figure 37
class NotificationResponseOptions(t.Struct):
    application_id: zgptypes.ApplicationID
    first_to_forward: t.uint1_t
    no_pairing: t.uint1_t
    _reserved: t.uint3_t


class NotificationResponseSchema(foundation.CommandSchema):
    options: NotificationResponseOptions
    gpd_id: zgptypes.DeviceID
    frame_counter: t.uint32_t


# Figure 43
class ProxyCommissioningModeOptions(t.Struct):
    enter: t.uint1_t
    exit_mode: zgptypes.ProxyCommissioningModeExitMode
    channel_present: t.uint1_t
    unicast: t.uint1_t
    _reserved: t.uint2_t


class ProxyCommissioningModeSchema(foundation.CommandSchema):
    options: ProxyCommissioningModeOptions
    window: t.uint16_t = StructField(optional=True)


class GreenPowerProxy(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0021
    name: Final = "Green Power"
    ep_attribute: Final = "green_power"

    NotificationSchema: Final = NotificationSchema
    PairingSearchSchema: Final = PairingSearchSchema
    PairingSchema: Final = PairingSchema
    ResponseSchema: Final = ResponseSchema
    CommissioningNotificationSchema: Final = CommissioningNotificationSchema
    NotificationResponseSchema: Final = NotificationResponseSchema
    ProxyCommissioningModeSchema: Final = ProxyCommissioningModeSchema

    class AttributeDefs(BaseAttributeDefs):
        max_sink_table_entries: Final = ZCLAttributeDef(
            id=0x0000,
            type=t.uint8_t,
            access="r",
            mandatory=True,
        )
        sink_table: Final = ZCLAttributeDef(
            id=0x0001,
            type=t.LongOctetString,
            access="r",
            mandatory=True,
        )
        communication_mode: Final = ZCLAttributeDef(
            id=0x0002,
            type=zgptypes.CommunicationMode,
            access="rw",
            mandatory=True,
        )
        commissioning_exit_mode: Final = ZCLAttributeDef(
            id=0x0003,
            type=zgptypes.ProxyCommissioningModeExitMode,
            access="rw",
            mandatory=True,
        )
        commissioning_window: Final = ZCLAttributeDef(
            id=0x0004,
            type=t.uint16_t,
            access="rw",
        )
        security_level: Final = ZCLAttributeDef(
            id=0x0005,
            type=zgptypes.SecurityLevel,
            access="rw",
            mandatory=True,
        )
        functionality: Final = ZCLAttributeDef(
            id=0x0006,
            type=t.bitmap24,
            access="rw",
            mandatory=True,
        )
        active_functionality: Final = ZCLAttributeDef(
            id=0x0007,
            type=t.bitmap24,
            access="r",
            mandatory=True,
        )
        gpp_max_table_entries: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint8_t, access="r"
        )
        gpp_proxy_table: Final = ZCLAttributeDef(
            id=0x0011, type=t.LongOctetString, access="r"
        )
        gpp_functionality: Final = ZCLAttributeDef(
            id=0x0016, type=t.bitmap24, access="r"
        )
        gpp_active_functionality: Final = ZCLAttributeDef(
            id=0x0017, type=t.bitmap24, access="r"
        )
        link_key: Final = ZCLAttributeDef(
            id=0x0022,
            type=t.KeyData,
            access="r",
            mandatory=True,
        )

    class ServerCommandDefs(BaseCommandDefs):
        notification: Final = ZCLCommandDef(
            id=0x00,
            schema=NotificationSchema,
        )

        pairing_search: Final = ZCLCommandDef(
            id=0x01,
            schema=PairingSearchSchema,
        )

        commissioning_notification: Final = ZCLCommandDef(
            id=0x04,
            schema=CommissioningNotificationSchema,
        )

    class ClientCommandDefs(BaseCommandDefs):
        notification_response: Final = ZCLCommandDef(
            id=0x00,
            schema=NotificationResponseSchema,
        )

        pairing: Final = ZCLCommandDef(
            id=0x01,
            schema=PairingSchema,
        )

        proxy_commissioning_mode: Final = ZCLCommandDef(
            id=0x02,
            schema=ProxyCommissioningModeSchema,
        )

        response: Final = ZCLCommandDef(
            id=0x06,
            schema=ResponseSchema,
        )
