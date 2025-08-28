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


# Figure 27
class CommissioningNotificationSchema(foundation.CommandSchema):
    options: t.bitmap16
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

    @property
    def application_id(self) -> zgptypes.ApplicationID:
        return zgptypes.ApplicationID(self.options & 0b111)

    @property
    def rx_after_tx(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 3) & 0x01)

    @property
    def security_level(self) -> zgptypes.SecurityLevel:
        return zgptypes.SecurityLevel((self.options >> 4) & 0b11)

    @property
    def security_key_type(self) -> zgptypes.SecurityKeyType:
        return zgptypes.SecurityKeyType((self.options >> 6) & 0b111)

    @property
    def security_failed(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 9) & 0x01)

    @property
    def bidirectional_cap(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 10) & 0x01)

    @property
    def proxy_info_present(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 11) & 0x01)


# ZGP spec Figure 45
class ResponseSchema(foundation.CommandSchema):
    options: t.bitmap8
    temp_master_short_addr: t.uint16_t
    temp_master_tx_channel: t.uint8_t
    gpd_id: zgptypes.DeviceID
    gpd_command_id: t.uint8_t
    gpd_command_payload: t.LVBytes

    @property
    def application_id(self) -> zgptypes.ApplicationID:
        return zgptypes.ApplicationID(self.options & 0b111)

    @application_id.setter
    def application_id(self, value: zgptypes.ApplicationID):
        self.options = (self.options & ~(0b111)) | value


# ZGP spec Figure 26
class PairingSearchSchema(foundation.CommandSchema):
    options: t.bitmap16
    gpd_id: zgptypes.DeviceID

    @property
    def application_id(self) -> zgptypes.ApplicationID:
        return zgptypes.ApplicationID(self.options & 0b111)

    @property
    def request_unicast_sink(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 3) & 0x01)

    @property
    def request_derived_groupcast_sink(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 4) & 0x01)

    @property
    def request_commissioned_groupcast_sink(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 5) & 0x01)

    @property
    def request_frame_counter(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 6) & 0x01)

    @property
    def request_security_key(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 7) & 0x01)


class NotificationSchema(foundation.CommandSchema):
    options: t.bitmap16
    gpd_id: zgptypes.DeviceID
    frame_counter: t.uint32_t
    command_id: t.uint8_t
    payload: t.LVBytes
    short_addr: t.uint16_t = StructField(
        requires=lambda s: s.proxy_info_present, optional=True
    )
    distance: t.uint8_t = StructField(
        requires=lambda s: s.proxy_info_present, optional=True
    )

    @property
    def application_id(self) -> zgptypes.ApplicationID:
        return zgptypes.ApplicationID(self.options & 0b111)

    @property
    def also_unicast(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 3) & 0x01)

    @property
    def also_derived_group(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 4) & 0x01)

    @property
    def also_commissioned_group(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 5) & 0x01)

    @property
    def security_level(self) -> zgptypes.SecurityLevel:
        return zgptypes.SecurityLevel((self.options >> 6) & 0b11)

    @property
    def security_key_type(self) -> zgptypes.SecurityKeyType:
        return zgptypes.SecurityKeyType((self.options >> 8) & 0b111)

    # XXX: these come from Wireshark, not the spec!
    @property
    def rx_after_tx(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 11) & 0x01)

    @property
    def gpp_tx_queue_full(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 12) & 0x01)

    @property
    def bidirectional_cap(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 13) & 0x01)

    @property
    def proxy_info_present(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 14) & 0x01)


class PairingSchema(foundation.CommandSchema):
    options: t.bitmap24
    gpd_id: zgptypes.DeviceID
    sink_ieee: t.EUI64 = StructField(optional=True)
    sink_nwk_addr: t.NWK = StructField(optional=True)
    sink_group: t.Group = StructField(optional=True)
    device_id: t.uint8_t = StructField(optional=True)
    frame_counter: t.uint32_t = StructField(optional=True)
    key: t.KeyData = StructField(optional=True)
    alias: t.uint16_t = StructField(optional=True)
    forwarding_radius: t.uint8_t = StructField(optional=True)

    @property
    def application_id(self) -> zgptypes.ApplicationID:
        return zgptypes.ApplicationID(self.options & 0b111)

    @application_id.setter
    def application_id(self, value: zgptypes.ApplicationID):
        self.options = (self.options & ~(0b111)) | value

    @property
    def add_sink(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 3) & 0x01)

    @add_sink.setter
    def add_sink(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 3)) | (value << 3)

    @property
    def remove_gpd(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 4) & 0x01)

    @remove_gpd.setter
    def remove_gpd(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 4)) | (value << 4)

    @property
    def communication_mode(self) -> zgptypes.CommunicationMode:
        return zgptypes.CommunicationMode((self.options >> 5) & 0b11)

    @communication_mode.setter
    def communication_mode(self, value: zgptypes.CommunicationMode):
        self.options = (self.options & ~(0b11 << 5)) | (value << 5)

    @property
    def gpd_fixed(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 7) & 0x01)

    @gpd_fixed.setter
    def gpd_fixed(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 7)) | (value << 7)

    @property
    def gpd_mac_seq_num_cap(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 8) & 0x01)

    @gpd_mac_seq_num_cap.setter
    def gpd_mac_seq_num_cap(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 8)) | (value << 8)

    @property
    def security_level(self) -> zgptypes.SecurityLevel:
        return zgptypes.SecurityLevel((self.options >> 9) & 0b11)

    @security_level.setter
    def security_level(self, value: zgptypes.SecurityLevel):
        self.options = (self.options & ~(0b11 << 9)) | (value << 9)

    @property
    def security_key_type(self) -> zgptypes.SecurityKeyType:
        return zgptypes.SecurityKeyType((self.options >> 11) & 0b111)

    @security_key_type.setter
    def security_key_type(self, value: zgptypes.SecurityKeyType):
        self.options = (self.options & ~(0b111 << 11)) | (value << 11)

    @property
    def security_frame_counter_present(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 14) & 0x01)

    @security_frame_counter_present.setter
    def security_frame_counter_present(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 14)) | (value << 14)

    @property
    def security_key_present(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 15) & 0x01)

    @security_key_present.setter
    def security_key_present(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 15)) | (value << 15)

    @property
    def assigned_alias_present(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 16) & 0x01)

    @assigned_alias_present.setter
    def assigned_alias_present(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 16)) | (value << 16)

    @property
    def forwarding_radius_present(self) -> t.uint1_t:
        return t.uint1_t((self.options >> 17) & 0x01)

    @forwarding_radius_present.setter
    def forwarding_radius_present(self, value: t.uint1_t):
        self.options = (self.options & ~(1 << 17)) | (value << 17)


class GreenPowerProxy(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0021
    name: Final = "Green Power"
    ep_attribute: Final = "green_power"

    NotificationSchema: Final = NotificationSchema
    PairingSearchSchema: Final = PairingSearchSchema
    NotificationResponseOptions: Final = zgptypes.NotificationResponseOptions
    PairingSchema: Final = PairingSchema
    ProxyCommissioningModeOptions: Final = zgptypes.ProxyCommissioningModeOptions
    ResponseSchema: Final = ResponseSchema
    CommissioningNotificationSchema: Final = CommissioningNotificationSchema

    class AttributeDefs(BaseAttributeDefs):
        max_sink_table_entries: Final = ZCLAttributeDef(
            id=0x0000,
            type=t.uint8_t,
            access=foundation.ZCLAttributeAccess.Read,
            mandatory=True,
        )
        sink_table: Final = ZCLAttributeDef(
            id=0x0001,
            type=t.LongOctetString,
            access=foundation.ZCLAttributeAccess.Read,
            mandatory=True,
        )
        communication_mode: Final = ZCLAttributeDef(
            id=0x0002,
            type=zgptypes.CommunicationMode,
            access=(
                foundation.ZCLAttributeAccess.Read | foundation.ZCLAttributeAccess.Write
            ),
            mandatory=True,
        )
        commissioning_exit_mode: Final = ZCLAttributeDef(
            id=0x0003,
            type=zgptypes.ProxyCommissioningModeExitMode,
            access=(
                foundation.ZCLAttributeAccess.Read | foundation.ZCLAttributeAccess.Write
            ),
            mandatory=True,
        )
        commissioning_window: Final = ZCLAttributeDef(
            id=0x0004,
            type=t.uint16_t,
            access=(
                foundation.ZCLAttributeAccess.Read | foundation.ZCLAttributeAccess.Write
            ),
        )
        security_level: Final = ZCLAttributeDef(
            id=0x0005,
            type=zgptypes.SecurityLevel,
            access=(
                foundation.ZCLAttributeAccess.Read | foundation.ZCLAttributeAccess.Write
            ),
            mandatory=True,
        )
        functionality: Final = ZCLAttributeDef(
            id=0x0006,
            type=t.bitmap24,
            access=(
                foundation.ZCLAttributeAccess.Read | foundation.ZCLAttributeAccess.Write
            ),
            mandatory=True,
        )
        active_functionality: Final = ZCLAttributeDef(
            id=0x0007,
            type=t.bitmap24,
            access=foundation.ZCLAttributeAccess.Read,
            mandatory=True,
        )
        gpp_max_table_entries: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint8_t, access=foundation.ZCLAttributeAccess.Read
        )
        gpp_proxy_table: Final = ZCLAttributeDef(
            id=0x0011, type=t.LongOctetString, access=foundation.ZCLAttributeAccess.Read
        )
        gpp_functionality: Final = ZCLAttributeDef(
            id=0x0016, type=t.bitmap24, access=foundation.ZCLAttributeAccess.Read
        )
        gpp_active_functionality: Final = ZCLAttributeDef(
            id=0x0017, type=t.bitmap24, access=foundation.ZCLAttributeAccess.Read
        )
        link_key: Final = ZCLAttributeDef(
            id=0x0022,
            type=t.KeyData,
            access=foundation.ZCLAttributeAccess.Read,
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
            schema={
                "options": zgptypes.NotificationResponseOptions,
                "gpd_id": zgptypes.DeviceID,
                "frame_counter": t.uint32_t,
            },
        )

        pairing: Final = ZCLCommandDef(
            id=0x01,
            schema=PairingSchema,
        )

        proxy_commissioning_mode: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "options": zgptypes.ProxyCommissioningModeOptions,
                "window?": t.uint16_t,
            },
        )

        response: Final = ZCLCommandDef(
            id=0x06,
            schema=ResponseSchema,
        )
