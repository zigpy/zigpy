"""Protocol Interfaces Functional Domain"""

from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    Direction,
    ZCLAttributeDef,
    ZCLCommandDef,
)


class DateTime(t.Struct):
    date: t.uint32_t
    time: t.uint32_t


class GenericTunnel(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0600
    ep_attribute: Final = "generic_tunnel"

    class AttributeDefs(BaseAttributeDefs):
        max_income_trans_size: Final = ZCLAttributeDef(id=0x0001, type=t.uint16_t)
        max_outgo_trans_size: Final = ZCLAttributeDef(id=0x0002, type=t.uint16_t)
        protocol_addr: Final = ZCLAttributeDef(id=0x0003, type=t.LVBytes)

    class ServerCommandDefs(BaseCommandDefs):
        match_protocol_addr: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Client_to_Server
        )

    class ClientCommandDefs(BaseCommandDefs):
        match_protocol_addr_response: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Server_to_Client
        )
        advertise_protocol_address: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )


class BacnetProtocolTunnel(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0601
    ep_attribute: Final = "bacnet_tunnel"

    class ServerCommandDefs(BaseCommandDefs):
        transfer_npdu: Final = ZCLCommandDef(
            id=0x00, schema={"npdu": t.LVBytes}, direction=Direction.Client_to_Server
        )


class AnalogInputRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0602
    ep_attribute: Final = "bacnet_regular_analog_input"

    class AttributeDefs(BaseAttributeDefs):
        cov_increment: Final = ZCLAttributeDef(id=0x0016, type=t.Single)
        device_type: Final = ZCLAttributeDef(id=0x001F, type=t.CharacterString)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        update_interval: Final = ZCLAttributeDef(id=0x0076, type=t.uint8_t)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class AnalogInputExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0603
    ep_attribute: Final = "bacnet_extended_analog_input"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        deadband: Final = ZCLAttributeDef(id=0x0019, type=t.Single)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        high_limit: Final = ZCLAttributeDef(id=0x002D, type=t.Single)
        limit_enable: Final = ZCLAttributeDef(id=0x0034, type=t.bitmap8)
        low_limit: Final = ZCLAttributeDef(id=0x003B, type=t.Single)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # event_time_stamps: Final = ZCLAttributeDef(id=0x0082, type=t.Array[3, t.uint32_t])
        # integer, time of day, or structure of (date, time of day))

    class ServerCommandDefs(BaseCommandDefs):
        transfer_apdu: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Client_to_Server
        )
        connect_req: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        disconnect_req: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        connect_status_noti: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Client_to_Server
        )


class AnalogOutputRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0604
    ep_attribute: Final = "bacnet_regular_analog_output"

    class AttributeDefs(BaseAttributeDefs):
        cov_increment: Final = ZCLAttributeDef(id=0x0016, type=t.Single)
        device_type: Final = ZCLAttributeDef(id=0x001F, type=t.CharacterString)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        update_interval: Final = ZCLAttributeDef(id=0x0076, type=t.uint8_t)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class AnalogOutputExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0605
    ep_attribute: Final = "bacnet_extended_analog_output"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        deadband: Final = ZCLAttributeDef(id=0x0019, type=t.Single)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        high_limit: Final = ZCLAttributeDef(id=0x002D, type=t.Single)
        limit_enable: Final = ZCLAttributeDef(id=0x0034, type=t.bitmap8)
        low_limit: Final = ZCLAttributeDef(id=0x003B, type=t.Single)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # event_time_stamps: Final = ZCLAttributeDef(id=0x0082, type=t.Array[3, t.uint32_t])
        # integer, time of day, or structure of (date, time of day))


class AnalogValueRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0606
    ep_attribute: Final = "bacnet_regular_analog_value"

    class AttributeDefs(BaseAttributeDefs):
        cov_increment: Final = ZCLAttributeDef(id=0x0016, type=t.Single)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class AnalogValueExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0607
    ep_attribute: Final = "bacnet_extended_analog_value"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        deadband: Final = ZCLAttributeDef(id=0x0019, type=t.Single)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        high_limit: Final = ZCLAttributeDef(id=0x002D, type=t.Single)
        limit_enable: Final = ZCLAttributeDef(id=0x0034, type=t.bitmap8)
        low_limit: Final = ZCLAttributeDef(id=0x003B, type=t.Single)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)


class BinaryInputRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0608
    ep_attribute: Final = "bacnet_regular_binary_input"

    class AttributeDefs(BaseAttributeDefs):
        change_of_state_count: Final = ZCLAttributeDef(id=0x000F, type=t.uint32_t)
        change_of_state_time: Final = ZCLAttributeDef(id=0x0010, type=DateTime)
        device_type: Final = ZCLAttributeDef(id=0x001F, type=t.CharacterString)
        elapsed_active_time: Final = ZCLAttributeDef(id=0x0021, type=t.uint32_t)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        time_of_at_reset: Final = ZCLAttributeDef(id=0x0072, type=DateTime)
        time_of_sc_reset: Final = ZCLAttributeDef(id=0x0073, type=DateTime)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class BinaryInputExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0609
    ep_attribute: Final = "bacnet_extended_binary_input"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        alarm_value: Final = ZCLAttributeDef(id=0x0006, type=t.Bool)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # 0x0082: ZCLAttributeDef('event_time_stamps', type=TODO.array),  # Array[3] of (16-bit unsigned
        # integer, time of day, or structure of (date, time of day))


class BinaryOutputRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x060A
    ep_attribute: Final = "bacnet_regular_binary_output"

    class AttributeDefs(BaseAttributeDefs):
        change_of_state_count: Final = ZCLAttributeDef(id=0x000F, type=t.uint32_t)
        change_of_state_time: Final = ZCLAttributeDef(id=0x0010, type=DateTime)
        device_type: Final = ZCLAttributeDef(id=0x001F, type=t.CharacterString)
        elapsed_active_time: Final = ZCLAttributeDef(id=0x0021, type=t.uint32_t)
        feed_back_value: Final = ZCLAttributeDef(id=0x0028, type=t.enum8)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        time_of_at_reset: Final = ZCLAttributeDef(id=0x0072, type=DateTime)
        time_of_sc_reset: Final = ZCLAttributeDef(id=0x0073, type=DateTime)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class BinaryOutputExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x060B
    ep_attribute: Final = "bacnet_extended_binary_output"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # 0x0082: ZCLAttributeDef('event_time_stamps', type=TODO.array),  # Array[3] of (16-bit unsigned
        # integer, time of day, or structure of (date, time of day))


class BinaryValueRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x060C
    ep_attribute: Final = "bacnet_regular_binary_value"

    class AttributeDefs(BaseAttributeDefs):
        change_of_state_count: Final = ZCLAttributeDef(id=0x000F, type=t.uint32_t)
        change_of_state_time: Final = ZCLAttributeDef(id=0x0010, type=DateTime)
        elapsed_active_time: Final = ZCLAttributeDef(id=0x0021, type=t.uint32_t)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        time_of_at_reset: Final = ZCLAttributeDef(id=0x0072, type=DateTime)
        time_of_sc_reset: Final = ZCLAttributeDef(id=0x0073, type=DateTime)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class BinaryValueExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x060D
    ep_attribute: Final = "bacnet_extended_binary_value"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        alarm_value: Final = ZCLAttributeDef(id=0x0006, type=t.Bool)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # 0x0082: ZCLAttributeDef('event_time_stamps', type=TODO.array),  # Array[3] of (16-bit unsigned
        # integer, time of day, or structure of (date, time of day))


class MultistateInputRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x060E
    ep_attribute: Final = "bacnet_regular_multistate_input"

    class AttributeDefs(BaseAttributeDefs):
        device_type: Final = ZCLAttributeDef(id=0x001F, type=t.CharacterString)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class MultistateInputExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x060F
    ep_attribute: Final = "bacnet_extended_multistate_input"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        alarm_value: Final = ZCLAttributeDef(id=0x0006, type=t.uint16_t)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        fault_values: Final = ZCLAttributeDef(id=0x0025, type=t.uint16_t)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # 0x0082: ZCLAttributeDef('event_time_stamps', type=TODO.array),  # Array[3] of (16-bit unsigned
        # integer, time of day, or structure of (date, time of day))


class MultistateOutputRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0610
    ep_attribute: Final = "bacnet_regular_multistate_output"

    class AttributeDefs(BaseAttributeDefs):
        device_type: Final = ZCLAttributeDef(id=0x001F, type=t.CharacterString)
        feed_back_value: Final = ZCLAttributeDef(id=0x0028, type=t.enum8)
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class MultistateOutputExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0611
    ep_attribute: Final = "bacnet_extended_multistate_output"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # 0x0082: ZCLAttributeDef('event_time_stamps', type=TODO.array),  # Array[3] of (16-bit unsigned
        # integer, time of day, or structure of (date, time of day))


class MultistateValueRegular(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0612
    ep_attribute: Final = "bacnet_regular_multistate_value"

    class AttributeDefs(BaseAttributeDefs):
        object_id: Final = ZCLAttributeDef(id=0x004B, type=t.FixedList[4, t.uint8_t])
        object_name: Final = ZCLAttributeDef(id=0x004D, type=t.CharacterString)
        object_type: Final = ZCLAttributeDef(id=0x004F, type=t.enum16)
        profile_name: Final = ZCLAttributeDef(id=0x00A8, type=t.CharacterString)


class MultistateValueExtended(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0613
    ep_attribute: Final = "bacnet_extended_multistate_value"

    class AttributeDefs(BaseAttributeDefs):
        acked_transitions: Final = ZCLAttributeDef(id=0x0000, type=t.bitmap8)
        alarm_value: Final = ZCLAttributeDef(id=0x0006, type=t.uint16_t)
        notification_class: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t)
        event_enable: Final = ZCLAttributeDef(id=0x0023, type=t.bitmap8)
        event_state: Final = ZCLAttributeDef(id=0x0024, type=t.enum8)
        fault_values: Final = ZCLAttributeDef(id=0x0025, type=t.uint16_t)
        notify_type: Final = ZCLAttributeDef(id=0x0048, type=t.enum8)
        time_delay: Final = ZCLAttributeDef(id=0x0071, type=t.uint8_t)
        # 0x0082: ZCLAttributeDef('event_time_stamps', type=TODO.array),  # Array[3] of (16-bit unsigned
        # integer, time of day, or structure of (date, time of day))
