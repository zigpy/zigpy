"""Closures Functional Domain"""

from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    Direction,
    ZCLAttributeDef,
    ZCLCommandDef,
)


class ShadeStatus(t.bitmap8):
    Operational = 0b00000001
    Adjusting = 0b00000010
    Opening = 0b00000100
    Motor_forward_is_opening = 0b00001000


class ShadeMode(t.enum8):
    Normal = 0x00
    Configure = 0x00
    Unknown = 0xFF


class Shade(Cluster):
    """Attributes and commands for configuring a shade"""

    ShadeStatus: Final = ShadeStatus
    ShadeMode: Final = ShadeMode

    cluster_id: Final[t.uint16_t] = 0x0100
    name: Final = "Shade Configuration"
    ep_attribute: Final = "shade"

    class AttributeDefs(BaseAttributeDefs):
        # Shade Information
        physical_closed_limit: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="r"
        )
        motor_step_size: Final = ZCLAttributeDef(id=0x0001, type=t.uint8_t, access="r")
        status: Final = ZCLAttributeDef(
            id=0x0002, type=ShadeStatus, access="rw", mandatory=True
        )
        # Shade Settings
        closed_limit: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint16_t, access="rw", mandatory=True
        )
        mode: Final = ZCLAttributeDef(
            id=0x0012, type=ShadeMode, access="rw", mandatory=True
        )


class LockState(t.enum8):
    Not_fully_locked = 0x00
    Locked = 0x01
    Unlocked = 0x02
    Undefined = 0xFF


class LockType(t.enum8):
    Dead_bolt = 0x00
    Magnetic = 0x01
    Other = 0x02
    Mortise = 0x03
    Rim = 0x04
    Latch_bolt = 0x05
    Cylindrical_lock = 0x06
    Tubular_lock = 0x07
    Interconnected_lock = 0x08
    Dead_latch = 0x09
    Door_furniture = 0x0A


class DoorState(t.enum8):
    Open = 0x00
    Closed = 0x01
    Error_jammed = 0x02
    Error_forced_open = 0x03
    Error_unspecified = 0x04
    Undefined = 0xFF


class OperatingMode(t.enum8):
    Normal = 0x00
    Vacation = 0x01
    Privacy = 0x02
    No_RF_Lock_Unlock = 0x03
    Passage = 0x04


class SupportedOperatingModes(t.bitmap16):
    Normal = 0x0001
    Vacation = 0x0002
    Privacy = 0x0004
    No_RF = 0x0008
    Passage = 0x0010


class DefaultConfigurationRegister(t.bitmap16):
    Enable_Local_Programming = 0x0001
    Keypad_Interface_default_access = 0x0002
    RF_Interface_default_access = 0x0004
    Sound_Volume_non_zero = 0x0020
    Auto_Relock_time_non_zero = 0x0040
    Led_settings_non_zero = 0x0080


class ZigbeeSecurityLevel(t.enum8):
    Network_Security = 0x00
    APS_Security = 0x01


class AlarmMask(t.bitmap16):
    Deadbolt_Jammed = 0x0001
    Lock_Reset_to_Factory_Defaults = 0x0002
    Reserved = 0x0004
    RF_Module_Power_Cycled = 0x0008
    Tamper_Alarm_wrong_code_entry_limit = 0x0010
    Tamper_Alarm_front_escutcheon_removed = 0x0020
    Forced_Door_Open_under_Door_Lockec_Condition = 0x0040


class KeypadOperationEventMask(t.bitmap16):
    Manufacturer_specific = 0x0001
    Lock_source_keypad = 0x0002
    Unlock_source_keypad = 0x0004
    Lock_source_keypad_error_invalid_code = 0x0008
    Lock_source_keypad_error_invalid_schedule = 0x0010
    Unlock_source_keypad_error_invalid_code = 0x0020
    Unlock_source_keypad_error_invalid_schedule = 0x0040
    Non_Access_User_Operation = 0x0080


class RFOperationEventMask(t.bitmap16):
    Manufacturer_specific = 0x0001
    Lock_source_RF = 0x0002
    Unlock_source_RF = 0x0004
    Lock_source_RF_error_invalid_code = 0x0008
    Lock_source_RF_error_invalid_schedule = 0x0010
    Unlock_source_RF_error_invalid_code = 0x0020
    Unlock_source_RF_error_invalid_schedule = 0x0040


class ManualOperatitonEventMask(t.bitmap16):
    Manufacturer_specific = 0x0001
    Thumbturn_Lock = 0x0002
    Thumbturn_Unlock = 0x0004
    One_touch_lock = 0x0008
    Key_Lock = 0x0010
    Key_Unlock = 0x0020
    Auto_lock = 0x0040
    Schedule_Lock = 0x0080
    Schedule_Unlock = 0x0100
    Manual_Lock_key_or_thumbturn = 0x0200
    Manual_Unlock_key_or_thumbturn = 0x0400


class RFIDOperationEventMask(t.bitmap16):
    Manufacturer_specific = 0x0001
    Lock_source_RFID = 0x0002
    Unlock_source_RFID = 0x0004
    Lock_source_RFID_error_invalid_RFID_ID = 0x0008
    Lock_source_RFID_error_invalid_schedule = 0x0010
    Unlock_source_RFID_error_invalid_RFID_ID = 0x0020
    Unlock_source_RFID_error_invalid_schedule = 0x0040


class KeypadProgrammingEventMask(t.bitmap16):
    Manufacturer_Specific = 0x0001
    Master_code_changed = 0x0002
    PIN_added = 0x0004
    PIN_deleted = 0x0008
    PIN_changed = 0x0010


class RFProgrammingEventMask(t.bitmap16):
    Manufacturer_Specific = 0x0001
    PIN_added = 0x0004
    PIN_deleted = 0x0008
    PIN_changed = 0x0010
    RFID_code_added = 0x0020
    RFID_code_deleted = 0x0040


class RFIDProgrammingEventMask(t.bitmap16):
    Manufacturer_Specific = 0x0001
    RFID_code_added = 0x0020
    RFID_code_deleted = 0x0040


class OperationEventSource(t.enum8):
    Keypad = 0x00
    RF = 0x01
    Manual = 0x02
    RFID = 0x03
    Indeterminate = 0xFF


class OperationEvent(t.enum8):
    UnknownOrMfgSpecific = 0x00
    Lock = 0x01
    Unlock = 0x02
    LockFailureInvalidPINorID = 0x03
    LockFailureInvalidSchedule = 0x04
    UnlockFailureInvalidPINorID = 0x05
    UnlockFailureInvalidSchedule = 0x06
    OnTouchLock = 0x07
    KeyLock = 0x08
    KeyUnlock = 0x09
    AutoLock = 0x0A
    ScheduleLock = 0x0B
    ScheduleUnlock = 0x0C
    Manual_Lock = 0x0D
    Manual_Unlock = 0x0E
    Non_Access_User_Operational_Event = 0x0F


class ProgrammingEvent(t.enum8):
    UnknownOrMfgSpecific = 0x00
    MasterCodeChanged = 0x01
    PINCodeAdded = 0x02
    PINCodeDeleted = 0x03
    PINCodeChanges = 0x04
    RFIDCodeAdded = 0x05
    RFIDCodeDeleted = 0x06


class UserStatus(t.enum8):
    Available = 0x00
    Enabled = 0x01
    Disabled = 0x03
    Not_Supported = 0xFF


class UserType(t.enum8):
    Unrestricted = 0x00
    Year_Day_Schedule_User = 0x01
    Week_Day_Schedule_User = 0x02
    Master_User = 0x03
    Non_Access_User = 0x04
    Not_Supported = 0xFF


class DayMask(t.bitmap8):
    Sun = 0x01
    Mon = 0x02
    Tue = 0x04
    Wed = 0x08
    Thu = 0x10
    Fri = 0x20
    Sat = 0x40


class EventType(t.enum8):
    Operation = 0x00
    Programming = 0x01
    Alarm = 0x02


class DoorLock(Cluster):
    """The door lock cluster provides an interface to a generic way to secure a door."""

    LockState: Final = LockState
    LockType: Final = LockType
    DoorState: Final = DoorState
    OperatingMode: Final = OperatingMode
    SupportedOperatingModes: Final = SupportedOperatingModes
    DefaultConfigurationRegister: Final = DefaultConfigurationRegister
    ZigbeeSecurityLevel: Final = ZigbeeSecurityLevel
    AlarmMask: Final = AlarmMask
    KeypadOperationEventMask: Final = KeypadOperationEventMask
    RFOperationEventMask: Final = RFOperationEventMask
    ManualOperatitonEventMask: Final = ManualOperatitonEventMask
    RFIDOperationEventMask: Final = RFIDOperationEventMask
    KeypadProgrammingEventMask: Final = KeypadProgrammingEventMask
    RFProgrammingEventMask: Final = RFProgrammingEventMask
    RFIDProgrammingEventMask: Final = RFIDProgrammingEventMask
    OperationEventSource: Final = OperationEventSource
    OperationEvent: Final = OperationEvent
    ProgrammingEvent: Final = ProgrammingEvent
    UserStatus: Final = UserStatus
    UserType: Final = UserType
    DayMask: Final = DayMask
    EventType: Final = EventType

    cluster_id: Final[t.uint16_t] = 0x0101
    name: Final = "Door Lock"
    ep_attribute: Final = "door_lock"

    class AttributeDefs(BaseAttributeDefs):
        lock_state: Final = ZCLAttributeDef(
            id=0x0000, type=LockState, access="rp", mandatory=True
        )
        lock_type: Final = ZCLAttributeDef(
            id=0x0001, type=LockType, access="r", mandatory=True
        )
        actuator_enabled: Final = ZCLAttributeDef(
            id=0x0002, type=t.Bool, access="r", mandatory=True
        )
        door_state: Final = ZCLAttributeDef(id=0x0003, type=DoorState, access="rp")
        door_open_events: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint32_t, access="rw"
        )
        door_closed_events: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint32_t, access="rw"
        )
        open_period: Final = ZCLAttributeDef(id=0x0006, type=t.uint16_t, access="rw")
        num_of_lock_records_supported: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint16_t, access="r"
        )
        num_of_total_users_supported: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint16_t, access="r"
        )
        num_of_pin_users_supported: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint16_t, access="r"
        )
        num_of_rfid_users_supported: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint16_t, access="r"
        )
        num_of_week_day_schedules_supported_per_user: Final = ZCLAttributeDef(
            id=0x0014, type=t.uint8_t, access="r"
        )
        num_of_year_day_schedules_supported_per_user: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint8_t, access="r"
        )
        num_of_holiday_scheduleds_supported: Final = ZCLAttributeDef(
            id=0x0016, type=t.uint8_t, access="r"
        )
        max_pin_len: Final = ZCLAttributeDef(id=0x0017, type=t.uint8_t, access="r")
        min_pin_len: Final = ZCLAttributeDef(id=0x0018, type=t.uint8_t, access="r")
        max_rfid_len: Final = ZCLAttributeDef(id=0x0019, type=t.uint8_t, access="r")
        min_rfid_len: Final = ZCLAttributeDef(id=0x001A, type=t.uint8_t, access="r")
        enable_logging: Final = ZCLAttributeDef(id=0x0020, type=t.Bool, access="r*wp")
        language: Final = ZCLAttributeDef(
            id=0x0021, type=t.LimitedCharString(3), access="r*wp"
        )
        led_settings: Final = ZCLAttributeDef(id=0x0022, type=t.uint8_t, access="r*wp")
        auto_relock_time: Final = ZCLAttributeDef(
            id=0x0023, type=t.uint32_t, access="r*wp"
        )
        sound_volume: Final = ZCLAttributeDef(id=0x0024, type=t.uint8_t, access="r*wp")
        operating_mode: Final = ZCLAttributeDef(
            id=0x0025, type=OperatingMode, access="r*wp"
        )
        supported_operating_modes: Final = ZCLAttributeDef(
            id=0x0026, type=SupportedOperatingModes, access="r"
        )
        default_configuration_register: Final = ZCLAttributeDef(
            id=0x0027,
            type=DefaultConfigurationRegister,
            access="rp",
        )
        enable_local_programming: Final = ZCLAttributeDef(
            id=0x0028, type=t.Bool, access="r*wp"
        )
        enable_one_touch_locking: Final = ZCLAttributeDef(
            id=0x0029, type=t.Bool, access="rwp"
        )
        enable_inside_status_led: Final = ZCLAttributeDef(
            id=0x002A, type=t.Bool, access="rwp"
        )
        enable_privacy_mode_button: Final = ZCLAttributeDef(
            id=0x002B, type=t.Bool, access="rwp"
        )
        wrong_code_entry_limit: Final = ZCLAttributeDef(
            id=0x0030, type=t.uint8_t, access="r*wp"
        )
        user_code_temporary_disable_time: Final = ZCLAttributeDef(
            id=0x0031, type=t.uint8_t, access="r*wp"
        )
        send_pin_ota: Final = ZCLAttributeDef(id=0x0032, type=t.Bool, access="r*wp")
        require_pin_for_rf_operation: Final = ZCLAttributeDef(
            id=0x0033, type=t.Bool, access="r*wp"
        )
        zigbee_security_level: Final = ZCLAttributeDef(
            id=0x0034, type=ZigbeeSecurityLevel, access="rp"
        )
        alarm_mask: Final = ZCLAttributeDef(id=0x0040, type=AlarmMask, access="rwp")
        keypad_operation_event_mask: Final = ZCLAttributeDef(
            id=0x0041, type=KeypadOperationEventMask, access="rwp"
        )
        rf_operation_event_mask: Final = ZCLAttributeDef(
            id=0x0042, type=RFOperationEventMask, access="rwp"
        )
        manual_operation_event_mask: Final = ZCLAttributeDef(
            id=0x0043, type=ManualOperatitonEventMask, access="rwp"
        )
        rfid_operation_event_mask: Final = ZCLAttributeDef(
            id=0x0044, type=RFIDOperationEventMask, access="rwp"
        )
        keypad_programming_event_mask: Final = ZCLAttributeDef(
            id=0x0045,
            type=KeypadProgrammingEventMask,
            access="rwp",
        )
        rf_programming_event_mask: Final = ZCLAttributeDef(
            id=0x0046, type=RFProgrammingEventMask, access="rwp"
        )
        rfid_programming_event_mask: Final = ZCLAttributeDef(
            id=0x0047, type=RFIDProgrammingEventMask, access="rwp"
        )

    class ServerCommandDefs(BaseCommandDefs):
        lock_door: Final = ZCLCommandDef(
            id=0x00,
            schema={"pin_code?": t.CharacterString},
            direction=Direction.Client_to_Server,
        )
        unlock_door: Final = ZCLCommandDef(
            id=0x01,
            schema={"pin_code?": t.CharacterString},
            direction=Direction.Client_to_Server,
        )
        toggle_door: Final = ZCLCommandDef(
            id=0x02,
            schema={"pin_code?": t.CharacterString},
            direction=Direction.Client_to_Server,
        )
        unlock_with_timeout: Final = ZCLCommandDef(
            id=0x03,
            schema={"timeout": t.uint16_t, "pin_code?": t.CharacterString},
            direction=Direction.Client_to_Server,
        )
        get_log_record: Final = ZCLCommandDef(
            id=0x04,
            schema={"log_index": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        set_pin_code: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "pin_code": t.CharacterString,
            },
            direction=Direction.Client_to_Server,
        )
        get_pin_code: Final = ZCLCommandDef(
            id=0x06,
            schema={"user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        clear_pin_code: Final = ZCLCommandDef(
            id=0x07,
            schema={"user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        clear_all_pin_codes: Final = ZCLCommandDef(
            id=0x08, schema={}, direction=Direction.Client_to_Server
        )
        set_user_status: Final = ZCLCommandDef(
            id=0x09,
            schema={"user_id": t.uint16_t, "user_status": UserStatus},
            direction=Direction.Client_to_Server,
        )
        get_user_status: Final = ZCLCommandDef(
            id=0x0A,
            schema={"user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        set_week_day_schedule: Final = ZCLCommandDef(
            id=0x0B,
            schema={
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "days_mask": DayMask,
                "start_hour": t.uint8_t,
                "start_minute": t.uint8_t,
                "end_hour": t.uint8_t,
                "end_minute": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )
        get_week_day_schedule: Final = ZCLCommandDef(
            id=0x0C,
            schema={"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        clear_week_day_schedule: Final = ZCLCommandDef(
            id=0x0D,
            schema={"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        set_year_day_schedule: Final = ZCLCommandDef(
            id=0x0E,
            schema={
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "local_start_time": t.LocalTime,
                "local_end_time": t.LocalTime,
            },
            direction=Direction.Client_to_Server,
        )
        get_year_day_schedule: Final = ZCLCommandDef(
            id=0x0F,
            schema={"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        clear_year_day_schedule: Final = ZCLCommandDef(
            id=0x10,
            schema={"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        set_holiday_schedule: Final = ZCLCommandDef(
            id=0x11,
            schema={
                "holiday_schedule_id": t.uint8_t,
                "local_start_time": t.LocalTime,
                "local_end_time": t.LocalTime,
                "operating_mode_during_holiday": OperatingMode,
            },
            direction=Direction.Client_to_Server,
        )
        get_holiday_schedule: Final = ZCLCommandDef(
            id=0x12,
            schema={"holiday_schedule_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        clear_holiday_schedule: Final = ZCLCommandDef(
            id=0x13,
            schema={"holiday_schedule_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        set_user_type: Final = ZCLCommandDef(
            id=0x14,
            schema={"user_id": t.uint16_t, "user_type": UserType},
            direction=Direction.Client_to_Server,
        )
        get_user_type: Final = ZCLCommandDef(
            id=0x15,
            schema={"user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        set_rfid_code: Final = ZCLCommandDef(
            id=0x16,
            schema={
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "rfid_code": t.CharacterString,
            },
            direction=Direction.Client_to_Server,
        )
        get_rfid_code: Final = ZCLCommandDef(
            id=0x17,
            schema={"user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        clear_rfid_code: Final = ZCLCommandDef(
            id=0x18,
            schema={"user_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        clear_all_rfid_codes: Final = ZCLCommandDef(
            id=0x19, schema={}, direction=Direction.Client_to_Server
        )

    class ClientCommandDefs(BaseCommandDefs):
        lock_door_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        unlock_door_response: Final = ZCLCommandDef(
            id=0x01,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        toggle_door_response: Final = ZCLCommandDef(
            id=0x02,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        unlock_with_timeout_response: Final = ZCLCommandDef(
            id=0x03,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_log_record_response: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "log_entry_id": t.uint16_t,
                "timestamp": t.uint32_t,
                "event_type": EventType,
                "source": OperationEventSource,
                "event_id_or_alarm_code": t.uint8_t,
                "user_id": t.uint16_t,
                "pin?": t.CharacterString,
            },
            direction=Direction.Server_to_Client,
        )
        set_pin_code_response: Final = ZCLCommandDef(
            id=0x05,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_pin_code_response: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "code": t.CharacterString,
            },
            direction=Direction.Server_to_Client,
        )
        clear_pin_code_response: Final = ZCLCommandDef(
            id=0x07,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        clear_all_pin_codes_response: Final = ZCLCommandDef(
            id=0x08,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        set_user_status_response: Final = ZCLCommandDef(
            id=0x09,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_user_status_response: Final = ZCLCommandDef(
            id=0x0A,
            schema={"user_id": t.uint16_t, "user_status": UserStatus},
            direction=Direction.Server_to_Client,
        )
        set_week_day_schedule_response: Final = ZCLCommandDef(
            id=0x0B,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_week_day_schedule_response: Final = ZCLCommandDef(
            id=0x0C,
            schema={
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "status": foundation.Status,
                "days_mask?": t.uint8_t,
                "start_hour?": t.uint8_t,
                "start_minute?": t.uint8_t,
                "end_hour?": t.uint8_t,
                "end_minute?": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        clear_week_day_schedule_response: Final = ZCLCommandDef(
            id=0x0D,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        set_year_day_schedule_response: Final = ZCLCommandDef(
            id=0x0E,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_year_day_schedule_response: Final = ZCLCommandDef(
            id=0x0F,
            schema={
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "status": foundation.Status,
                "local_start_time?": t.LocalTime,
                "local_end_time?": t.LocalTime,
            },
            direction=Direction.Server_to_Client,
        )
        clear_year_day_schedule_response: Final = ZCLCommandDef(
            id=0x10,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        set_holiday_schedule_response: Final = ZCLCommandDef(
            id=0x11,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_holiday_schedule_response: Final = ZCLCommandDef(
            id=0x12,
            schema={
                "holiday_schedule_id": t.uint8_t,
                "status": foundation.Status,
                "local_start_time?": t.LocalTime,
                "local_end_time?": t.LocalTime,
                "operating_mode_during_holiday?": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        clear_holiday_schedule_response: Final = ZCLCommandDef(
            id=0x13,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        set_user_type_response: Final = ZCLCommandDef(
            id=0x14,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_user_type_response: Final = ZCLCommandDef(
            id=0x15,
            schema={"user_id": t.uint16_t, "user_type": UserType},
            direction=Direction.Server_to_Client,
        )
        set_rfid_code_response: Final = ZCLCommandDef(
            id=0x16,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        get_rfid_code_response: Final = ZCLCommandDef(
            id=0x17,
            schema={
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "rfid_code": t.CharacterString,
            },
            direction=Direction.Server_to_Client,
        )
        clear_rfid_code_response: Final = ZCLCommandDef(
            id=0x18,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        clear_all_rfid_codes_response: Final = ZCLCommandDef(
            id=0x19,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        operation_event_notification: Final = ZCLCommandDef(
            id=0x20,
            schema={
                "operation_event_source": OperationEventSource,
                "operation_event_code": OperationEvent,
                "user_id": t.uint16_t,
                "pin": t.CharacterString,
                "local_time": t.LocalTime,
                "data?": t.CharacterString,
            },
            direction=Direction.Server_to_Client,
        )
        programming_event_notification: Final = ZCLCommandDef(
            id=0x21,
            schema={
                "program_event_source": OperationEventSource,
                "program_event_code": ProgrammingEvent,
                "user_id": t.uint16_t,
                "pin": t.CharacterString,
                "user_type": UserType,
                "user_status": UserStatus,
                "local_time": t.LocalTime,
                "data?": t.CharacterString,
            },
            direction=Direction.Server_to_Client,
        )


class WindowCoveringType(t.enum8):
    Rollershade = 0x00
    Rollershade_two_motors = 0x01
    Rollershade_exterior = 0x02
    Rollershade_exterior_two_motors = 0x03
    Drapery = 0x04
    Awning = 0x05
    Shutter = 0x06
    Tilt_blind_tilt_only = 0x07
    Tilt_blind_tilt_and_lift = 0x08
    Projector_screen = 0x09


class ConfigStatus(t.bitmap8):
    Operational = 0b00000001
    Online = 0b00000010
    Open_up_commands_reversed = 0b00000100
    Closed_loop_lift_control = 0b00001000
    Closed_loop_tilt_control = 0b00010000
    Encoder_controlled_lift = 0b00100000
    Encoder_controlled_tilt = 0b01000000


class WindowCoveringMode(t.bitmap8):
    Motor_direction_reversed = 0b00000001
    Run_in_calibration_mode = 0b00000010
    Motor_in_maintenance_mode = 0b00000100
    LEDs_display_feedback = 0b00001000


class WindowCovering(Cluster):
    WindowCoveringType: Final = WindowCoveringType
    ConfigStatus: Final = ConfigStatus
    WindowCoveringMode: Final = WindowCoveringMode

    cluster_id: Final[t.uint16_t] = 0x0102
    name: Final = "Window Covering"
    ep_attribute: Final = "window_covering"

    class AttributeDefs(BaseAttributeDefs):
        # Window Covering Information
        window_covering_type: Final = ZCLAttributeDef(
            id=0x0000, type=WindowCoveringType, access="r", mandatory=True
        )
        physical_closed_limit_lift: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r"
        )
        physical_closed_limit_tilt: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r"
        )
        current_position_lift: Final = ZCLAttributeDef(
            id=0x0003, type=t.uint16_t, access="r"
        )
        current_position_tilt: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint16_t, access="r"
        )
        number_of_actuations_lift: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint16_t, access="r"
        )
        number_of_actuations_tilt: Final = ZCLAttributeDef(
            id=0x0006, type=t.uint16_t, access="r"
        )
        config_status: Final = ZCLAttributeDef(
            id=0x0007, type=ConfigStatus, access="r", mandatory=True
        )
        # All subsequent attributes are mandatory if their control types are enabled
        current_position_lift_percentage: Final = ZCLAttributeDef(
            id=0x0008, type=t.uint8_t, access="rps"
        )
        current_position_tilt_percentage: Final = ZCLAttributeDef(
            id=0x0009, type=t.uint8_t, access="rps"
        )
        # Window Covering Settings
        installed_open_limit_lift: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint16_t, access="r"
        )
        installed_closed_limit_lift: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint16_t, access="r"
        )
        installed_open_limit_tilt: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint16_t, access="r"
        )
        installed_closed_limit_tilt: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint16_t, access="r"
        )
        velocity_lift: Final = ZCLAttributeDef(id=0x0014, type=t.uint16_t, access="rw")
        acceleration_time_lift: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint16_t, access="rw"
        )
        deceleration_time_lift: Final = ZCLAttributeDef(
            id=0x0016, type=t.uint16_t, access="rw"
        )
        window_covering_mode: Final = ZCLAttributeDef(
            id=0x0017, type=WindowCoveringMode, access="rw", mandatory=True
        )
        intermediate_setpoints_lift: Final = ZCLAttributeDef(
            id=0x0018, type=t.LVBytes, access="rw"
        )
        intermediate_setpoints_tilt: Final = ZCLAttributeDef(
            id=0x0019, type=t.LVBytes, access="rw"
        )

    class ServerCommandDefs(BaseCommandDefs):
        up_open: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Client_to_Server
        )
        down_close: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        stop: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        go_to_lift_value: Final = ZCLCommandDef(
            id=0x04,
            schema={"lift_value": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        go_to_lift_percentage: Final = ZCLCommandDef(
            id=0x05,
            schema={"percentage_lift_value": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        go_to_tilt_value: Final = ZCLCommandDef(
            id=0x07,
            schema={"tilt_value": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        go_to_tilt_percentage: Final = ZCLCommandDef(
            id=0x08,
            schema={"percentage_tilt_value": t.uint8_t},
            direction=Direction.Client_to_Server,
        )


class MovingState(t.enum8):
    Stopped = 0x00
    Closing = 0x01
    Opening = 0x02


class SafetyStatus(t.bitmap16):
    Remote_Lockout = 0b00000000_00000001
    Tamper_Detected = 0b00000000_00000010
    Failed_Communication = 0b00000000_00000100
    Position_Failure = 0b00000000_00001000


class Capabilities(t.bitmap8):
    Partial_Barrier = 0b00000001


class BarrierControl(Cluster):
    cluster_id: Final = 0x0103
    name: Final = "Barrier Control"
    ep_attribute: Final = "barrier_control"

    class AttributeDefs(BaseAttributeDefs):
        moving_state: Final = ZCLAttributeDef(
            id=0x0001, type=MovingState, access="rp", mandatory=True
        )
        safety_status: Final = ZCLAttributeDef(
            id=0x0002, type=SafetyStatus, access="rp", mandatory=True
        )
        capabilities: Final = ZCLAttributeDef(
            id=0x0003, type=Capabilities, access="r", mandatory=True
        )
        open_events: Final = ZCLAttributeDef(id=0x0004, type=t.uint16_t, access="rw")
        close_events: Final = ZCLAttributeDef(id=0x0005, type=t.uint16_t, access="rw")
        command_open_events: Final = ZCLAttributeDef(
            id=0x0006, type=t.uint16_t, access="rw"
        )
        command_close_events: Final = ZCLAttributeDef(
            id=0x0007, type=t.uint16_t, access="rw"
        )
        open_period: Final = ZCLAttributeDef(id=0x0008, type=t.uint16_t, access="rw")
        close_period: Final = ZCLAttributeDef(id=0x0009, type=t.uint16_t, access="rw")
        barrier_position: Final = ZCLAttributeDef(
            id=0x000A, type=t.uint8_t, access="rps", mandatory=True
        )

    class ServerCommandDefs(BaseCommandDefs):
        go_to_percent: Final = ZCLCommandDef(
            id=0x00,
            schema={"percent_open": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        stop: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )

    class ClientCommandDefs(BaseCommandDefs):
        pass
