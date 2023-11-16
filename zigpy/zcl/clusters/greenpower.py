
from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Optional

import zigpy.types as t
from zigpy.types.named import GPSecurityLevel
from zigpy.typing import AddressingMode
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    ZCLAttributeDef,
    ZCLCommandDef,
)

# ZGP spec Figure 24
class GPNotificationOptions(t.bitmap16):
    @property
    def application_id(self) -> t.GPApplicationID:
        return t.GPApplicationID(self & 0b111)
    @property
    def also_unicast(self) -> bool:
        return bool((self >> 3) & 0x01)
    @property
    def also_derived_group(self) -> bool:
        return bool((self >> 4) & 0x01)
    @property
    def also_commissioned_group(self) -> bool:
        return bool((self >> 5) & 0x01)
    @property
    def security_level(self) -> t.GPSecurityLevel:
        return t.GPSecurityLevel((self >> 6) & 0b11)
    @property
    def security_key_type(self) -> t.GPSecurityKeyType:
        return t.GPSecurityKeyType((self >> 8) & 0b111)
    @property
    def temp_master(self) -> bool:
        return bool((self >> 11) & 0x01)
    @property
    def gpp_tx_queue_full(self) -> bool:
        return bool((self >> 12) & 0x01)

# ZGP spec Figure 26
class GPPairingSearchOptions(t.bitmap16):
    @property
    def application_id(self) -> t.GPApplicationID:
        return t.GPApplicationID(self & 0b111)
    @property
    def request_unicast_sink(self) -> bool:
        return bool((self >> 3) & 0x01)
    @property
    def request_derived_groupcast_sink(self) -> bool:
        return bool((self >> 4) & 0x01)
    @property
    def request_commissioned_groupcast_sink(self) -> bool:
        return bool((self >> 5) & 0x01)
    @property
    def request_frame_counter(self) -> bool:
        return bool((self >> 6) & 0x01)
    @property
    def request_security_key(self) -> bool:
        return bool((self >> 7) & 0x01)

# ZGP spec Figure 28
class GPCommissioningNotificationOptions(t.bitmap16):
    @property
    def application_id(self) -> t.GPApplicationID:
        return t.GPApplicationID(self & 0b111)
    @property
    def temp_master(self) -> bool:
        return bool((self >> 3) & 0x01)
    @property
    def security_level(self) -> t.GPSecurityLevel:
        return t.GPSecurityLevel((self >> 4) & 0b11)
    @property
    def security_key_type(self) -> t.GPSecurityKeyType:
        return t.GPSecurityKeyType((self >> 6) & 0b111)
    @property
    def security_failed(self) -> bool:
        return bool((self >> 9) & 0x01)
    
# ZGP spec Figure 37
class GPNotificationResponseOptions(t.Struct):
    application_id: t.GPApplicationID
    first_to_forward: t.uint1_t
    no_pairing: t.uint1_t
    reserved: t.uint3_t
    def __new__(cls: GPNotificationResponseOptions, *args, **kwargs) -> GPNotificationResponseOptions:
        kwargs.setdefault("application_id", t.GPApplicationID.GPZero)
        kwargs.setdefault("first_to_forward", 0)
        kwargs.setdefault("no_pairing", 0)
        kwargs.setdefault("reserved", 0)
        return super().__new__(cls, *args, **kwargs)

# ZGP spec Figure 41
class GPPairingOptions(t.Struct):
    application_id: t.GPApplicationID
    add_sink: t.uint1_t
    remove_gpd: t.uint1_t
    communication_mode: t.GPCommunicationMode
    gpd_fixed: t.uint1_t
    gpd_mac_seq_num_cap: t.uint1_t
    security_level: t.GPSecurityLevel
    security_key_type: t.GPSecurityKeyType
    security_frame_counter_present: t.uint1_t
    assigned_alias_present: t.uint1_t
    forwarding_radius_present: t.uint1_t
    reserved: t.uint6_t
    def __new__(cls: GPPairingOptions, *args, **kwargs) -> GPPairingOptions:
        kwargs.setdefault("application_id", t.GPApplicationID.GPZero)
        kwargs.setdefault("add_sink", 0)
        kwargs.setdefault("remove_gpd", 0)
        kwargs.setdefault("communication_mode", t.GPCommunicationMode.Unicast)
        kwargs.setdefault("gpd_fixed", 0)
        kwargs.setdefault("gpd_mac_seq_num_cap", 0)
        kwargs.setdefault("security_level", t.GPSecurityLevel.NoSecurity)
        kwargs.setdefault("security_key_type", t.GPSecurityKeyType.NoKey)
        kwargs.setdefault("security_frame_counter_present", 0)
        kwargs.setdefault("assigned_alias_present", 0)
        kwargs.setdefault("forwarding_radius_present", 0)
        kwargs.setdefault("reserved", 0)
        return super().__new__(cls, *args, **kwargs)

# ZGP spec Figure 43
class GPProxyCommissioningModeOptions(t.Struct):
    enter: t.uint1_t
    exit_mode: t.GPProxyCommissioningModeExitMode
    channel_present: t.uint1_t
    reserved: t.uint3_t
    def __new__(cls: GPProxyCommissioningModeOptions, *args, **kwargs) -> GPProxyCommissioningModeOptions:
        kwargs.setdefault("exit_mode", t.GPProxyCommissioningModeExitMode.NotDefined)
        kwargs.setdefault("channel_present", 0)
        kwargs.setdefault("reserved", 0)
        return super().__new__(cls, *args, **kwargs)

# ZGP spec Figure 45
class GPResponseOptions(t.Struct):
    application_id: t.GPApplicationID
    reserved: t.uint5_t
    def __new__(cls: GPProxyCommissioningModeOptions, *args, **kwargs) -> GPProxyCommissioningModeOptions:
        kwargs.setdefault("application_id", t.GPApplicationID.GPZero)
        kwargs.setdefault("reserved", 0)
        return super().__new__(cls, *args, **kwargs)

class GreenPowerProxy(Cluster):
    cluster_id: Final = 0x0021
    name: Final = "Green Power"
    ep_attribute: Final = "green_power"

    GPNotificationOptions: Final = GPNotificationOptions
    GPPairingSearchOptions: Final = GPPairingSearchOptions
    GPCommissioningNotificationOptions: Final = GPCommissioningNotificationOptions
    GPNotificationResponseOptions: Final = GPNotificationResponseOptions
    GPPairingOptions: Final = GPPairingOptions
    GPProxyCommissioningModeOptions: Final = GPProxyCommissioningModeOptions
    GPResponseOptions: Final = GPResponseOptions

    def handle_message(self, data):
        self.log("Green Power Cluster direct message received")
    
    class AttributeDefs(BaseAttributeDefs):
        max_sink_table_entries: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        sink_table: Final = ZCLAttributeDef(
            id=0x0001, type=t.LongOctetString, access="r", mandatory=True
        )
        communication_mode: Final = ZCLAttributeDef(
            id=0x0002, type=t.bitmap8, access="rw", mandatory=True
        )
        commissioning_exit_mode: Final = ZCLAttributeDef(
            id=0x0003, type=t.bitmap8, access="rw", mandatory=True
        )
        commissioning_window: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint16_t, access="rw"
        )
        security_level: Final = ZCLAttributeDef(
            id=0x0005, type=t.bitmap8, access="rw", mandatory=True
        )
        functionality: Final = ZCLAttributeDef(
            id=0x0006, type=t.bitmap24, access="r", mandatory=True
        )
        active_functionality: Final = ZCLAttributeDef(
            id=0x0007, type=t.bitmap24, access="r", mandatory=True
        )
        gpp_functionality: Final = ZCLAttributeDef(
            id=0x0016, type=t.bitmap24, access="r", mandatory=True
        )
        gpp_active_functionality: Final = ZCLAttributeDef(
            id=0x0017, type=t.bitmap24, access="r", mandatory=True
        )
        joiningAllowUntil: Final = ZCLAttributeDef(
            id=0x9997, type=t.uint32_t, access="rw"
        )
        key: Final = ZCLAttributeDef(
            id=0x9998, type=t.uint32_t, access="rw"
        )
        counter: Final = ZCLAttributeDef(
            id=0x9999, type=t.uint64_t, access="rw"
        )
    
    class ServerCommandDefs(BaseCommandDefs):
        notification: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "options": GPNotificationOptions,
                "gpd_id": t.GreenPowerDeviceID,
                "frame_counter": t.uint32_t,
                "command_id": t.uint8_t,
                "payload": t.LVBytes,
                "short_addr?": t.uint16_t,
                "distance?": t.uint8_t,
            },
            direction=False,
        )
        
        pairing_search: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "options": GPPairingSearchOptions,
                "gpdId": t.GreenPowerDeviceID,
            },
            direction=False,
        )

        commissioning_notification: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "options": GPCommissioningNotificationOptions,
                "gpd_id": t.GreenPowerDeviceID,
                "frame_counter": t.uint32_t,
                "command_id": t.uint8_t,
                "payload": t.LVBytes,
                "short_addr?": t.uint16_t,
                "distance?": t.uint8_t,
                "mic?": t.uint32_t,
            },
            direction=False,
        )
        
    class ClientCommandDefs(BaseCommandDefs):
        notification_response: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "options": GPNotificationResponseOptions,
                "gpd_id": t.GreenPowerDeviceID,
                "frame_counter": t.uint32_t
            },
            direction=True,
        )

        pairing: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "options": GPPairingOptions,
                "gpd_id": t.GreenPowerDeviceID,
                "sink_IEEE?": t.EUI64,
                "sink_nwk_addr?": t.NWK,
                "sink_group?": t.Group,
                "device_id?": t.uint8_t,
                "frame_counter?": t.uint32_t,
                "key?": t.KeyData,
                "alias?": t.uint16_t,
                "forwarding_radius?": t.uint8_t
            },
            direction=True,
        )

        proxy_commissioning_mode: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "options": GPProxyCommissioningModeOptions,
                "window?": t.uint16_t
            },
            direction=True
        )

        response: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "options": GPResponseOptions,
                "temp_master_short_addr": t.uint16_t,
                "temp_master_tx_channel": t.uint8_t,
                "gpd_id": t.GreenPowerDeviceID,
                "gpd_command_id": t.uint8_t,
                "gpd_command_payload": t.LongOctetString,
            },
            direction=True
        )

