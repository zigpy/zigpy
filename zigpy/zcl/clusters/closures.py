"""Closures Functional Domain"""

from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class Shade(Cluster):
    """Attributes and commands for configuring a shade"""

    cluster_id = 0x0100
    name = "Shade Configuration"
    ep_attribute = "shade"

    class ShadeStatus(t.bitmap8):
        Operational = 0b00000001
        Adjusting = 0b00000010
        Opening = 0b00000100
        Motor_forward_is_opening = 0b00001000

    class ShadeMode(t.enum8):
        Normal = 0x00
        Configure = 0x00
        Unknown = 0xFF

    attributes: dict[int, ZCLAttributeDef] = {
        # Shade Information
        0x0000: ("physical_closed_limit", t.uint16_t),
        0x0001: ("motor_step_size", t.uint8_t),
        0x0002: ("status", ShadeStatus),
        # Shade Settings
        0x0010: ("closed_limit", t.uint16_t),
        0x0012: ("mode", ShadeMode),
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class DoorLock(Cluster):
    """The door lock cluster provides an interface to a generic way to secure a door."""

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

    cluster_id = 0x0101
    name = "Door Lock"
    ep_attribute = "door_lock"
    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ("lock_state", LockState),
        0x0001: ("lock_type", LockType),
        0x0002: ("actuator_enabled", t.Bool),
        0x0003: ("door_state", DoorState),
        0x0004: ("door_open_events", t.uint32_t),
        0x0005: ("door_closed_events", t.uint32_t),
        0x0006: ("open_period", t.uint16_t),
        0x0010: ("num_of_lock_records_supported", t.uint16_t),
        0x0011: ("num_of_total_users_supported", t.uint16_t),
        0x0012: ("num_of_pin_users_supported", t.uint16_t),
        0x0013: ("num_of_rfid_users_supported", t.uint16_t),
        0x0014: ("num_of_week_day_schedules_supported_per_user", t.uint8_t),
        0x0015: ("num_of_year_day_schedules_supported_per_user", t.uint8_t),
        0x0016: ("num_of_holiday_scheduleds_supported", t.uint8_t),
        0x0017: ("max_pin_len", t.uint8_t),
        0x0018: ("min_pin_len", t.uint8_t),
        0x0019: ("max_rfid_len", t.uint8_t),
        0x001A: ("min_rfid_len", t.uint8_t),
        0x0020: ("enable_logging", t.Bool),
        0x0021: ("language", t.LimitedCharString(3)),
        0x0022: ("led_settings", t.uint8_t),
        0x0023: ("auto_relock_time", t.uint32_t),
        0x0024: ("sound_volume", t.uint8_t),
        0x0025: ("operating_mode", OperatingMode),
        0x0026: ("supported_operating_modes", SupportedOperatingModes),
        0x0027: ("default_configuration_register", DefaultConfigurationRegister),
        0x0028: ("enable_local_programming", t.Bool),
        0x0029: ("enable_one_touch_locking", t.Bool),
        0x002A: ("enable_inside_status_led", t.Bool),
        0x002B: ("enable_privacy_mode_button", t.Bool),
        0x0030: ("wrong_code_entry_limit", t.uint8_t),
        0x0031: ("user_code_temporary_disable_time", t.uint8_t),
        0x0032: ("send_pin_ota", t.Bool),
        0x0033: ("require_pin_for_rf_operation", t.Bool),
        0x0034: ("zigbee_security_level", ZigbeeSecurityLevel),
        0x0040: ("alarm_mask", AlarmMask),
        0x0041: ("keypad_operation_event_mask", KeypadOperationEventMask),
        0x0042: ("rf_operation_event_mask", RFOperationEventMask),
        0x0043: ("manual_operation_event_mask", ManualOperatitonEventMask),
        0x0044: ("rfid_operation_event_mask", RFIDOperationEventMask),
        0x0045: ("keypad_programming_event_mask", KeypadProgrammingEventMask),
        0x0046: ("rf_programming_event_mask", RFProgrammingEventMask),
        0x0047: ("rfid_programming_event_mask", RFIDProgrammingEventMask),
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("lock_door", {"pin_code?": t.CharacterString}, False),
        0x01: ZCLCommandDef("unlock_door", {"pin_code?": t.CharacterString}, False),
        0x02: ZCLCommandDef("toggle_door", {"pin_code?": t.CharacterString}, False),
        0x03: ZCLCommandDef(
            "unlock_with_timeout",
            {"timeout": t.uint16_t, "pin_code?": t.CharacterString},
            False,
        ),
        0x04: ZCLCommandDef("get_log_record", {"log_index": t.uint16_t}, False),
        0x05: ZCLCommandDef(
            "set_pin_code",
            {
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "pin_code": t.CharacterString,
            },
            False,
        ),
        0x06: ZCLCommandDef("get_pin_code", {"user_id": t.uint16_t}, False),
        0x07: ZCLCommandDef("clear_pin_code", {"user_id": t.uint16_t}, False),
        0x08: ZCLCommandDef("clear_all_pin_codes", {}, False),
        0x09: ZCLCommandDef(
            "set_user_status", {"user_id": t.uint16_t, "user_status": UserStatus}, False
        ),
        0x0A: ZCLCommandDef("get_user_status", {"user_id": t.uint16_t}, False),
        0x0B: ZCLCommandDef(
            "set_week_day_schedule",
            {
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "days_mask": DayMask,
                "start_hour": t.uint8_t,
                "start_minute": t.uint8_t,
                "end_hour": t.uint8_t,
                "end_minute": t.uint8_t,
            },
            False,
        ),
        0x0C: ZCLCommandDef(
            "get_week_day_schedule",
            {"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            False,
        ),
        0x0D: ZCLCommandDef(
            "clear_week_day_schedule",
            {"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            False,
        ),
        0x0E: ZCLCommandDef(
            "set_year_day_schedule",
            {
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "local_start_time": t.LocalTime,
                "local_end_time": t.LocalTime,
            },
            False,
        ),
        0x0F: ZCLCommandDef(
            "get_year_day_schedule",
            {"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            False,
        ),
        0x10: ZCLCommandDef(
            "clear_year_day_schedule",
            {"schedule_id": t.uint8_t, "user_id": t.uint16_t},
            False,
        ),
        0x11: ZCLCommandDef(
            "set_holiday_schedule",
            {
                "holiday_schedule_id": t.uint8_t,
                "local_start_time": t.LocalTime,
                "local_end_time": t.LocalTime,
                "operating_mode_during_holiday": OperatingMode,
            },
            False,
        ),
        0x12: ZCLCommandDef(
            "get_holiday_schedule", {"holiday_schedule_id": t.uint8_t}, False
        ),
        0x13: ZCLCommandDef(
            "clear_holiday_schedule", {"holiday_schedule_id": t.uint8_t}, False
        ),
        0x14: ZCLCommandDef(
            "set_user_type", {"user_id": t.uint16_t, "user_type": UserType}, False
        ),
        0x15: ZCLCommandDef("get_user_type", {"user_id": t.uint16_t}, False),
        0x16: ZCLCommandDef(
            "set_rfid_code",
            {
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "rfid_code": t.CharacterString,
            },
            False,
        ),
        0x17: ZCLCommandDef("get_rfid_code", {"user_id": t.uint16_t}, False),
        0x18: ZCLCommandDef("clear_rfid_code", {"user_id": t.uint16_t}, False),
        0x19: ZCLCommandDef("clear_all_rfid_codes", {}, False),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("lock_door_response", {"status": foundation.Status}, True),
        0x01: ZCLCommandDef(
            "unlock_door_response", {"status": foundation.Status}, True
        ),
        0x02: ZCLCommandDef(
            "toggle_door_response", {"status": foundation.Status}, True
        ),
        0x03: ZCLCommandDef(
            "unlock_with_timeout_response", {"status": foundation.Status}, True
        ),
        0x04: ZCLCommandDef(
            "get_log_record_response",
            {
                "log_entry_id": t.uint16_t,
                "timestamp": t.uint32_t,
                "event_type": EventType,
                "source": OperationEventSource,
                "event_id_or_alarm_code": t.uint8_t,
                "user_id": t.uint16_t,
                "pin?": t.CharacterString,
            },
            True,
        ),
        0x05: ZCLCommandDef(
            "set_pin_code_response", {"status": foundation.Status}, True
        ),
        0x06: ZCLCommandDef(
            "get_pin_code_response",
            {
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "code": t.CharacterString,
            },
            True,
        ),
        0x07: ZCLCommandDef(
            "clear_pin_code_response", {"status": foundation.Status}, True
        ),
        0x08: ZCLCommandDef(
            "clear_all_pin_codes_response", {"status": foundation.Status}, True
        ),
        0x09: ZCLCommandDef(
            "set_user_status_response", {"status": foundation.Status}, True
        ),
        0x0A: ZCLCommandDef(
            "get_user_status_response",
            {"user_id": t.uint16_t, "user_status": UserStatus},
            True,
        ),
        0x0B: ZCLCommandDef(
            "set_week_day_schedule_response", {"status": foundation.Status}, True
        ),
        0x0C: ZCLCommandDef(
            "get_week_day_schedule_response",
            {
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "status": foundation.Status,
                "days_mask?": t.uint8_t,
                "start_hour?": t.uint8_t,
                "start_minute?": t.uint8_t,
                "end_hour?": t.uint8_t,
                "end_minute?": t.uint8_t,
            },
            True,
        ),
        0x0D: ZCLCommandDef(
            "clear_week_day_schedule_response", {"status": foundation.Status}, True
        ),
        0x0E: ZCLCommandDef(
            "set_year_day_schedule_response", {"status": foundation.Status}, True
        ),
        0x0F: ZCLCommandDef(
            "get_year_day_schedule_response",
            {
                "schedule_id": t.uint8_t,
                "user_id": t.uint16_t,
                "status": foundation.Status,
                "local_start_time?": t.LocalTime,
                "local_end_time?": t.LocalTime,
            },
            True,
        ),
        0x10: ZCLCommandDef(
            "clear_year_day_schedule_response", {"status": foundation.Status}, True
        ),
        0x11: ZCLCommandDef(
            "set_holiday_schedule_response", {"status": foundation.Status}, True
        ),
        0x12: ZCLCommandDef(
            "get_holiday_schedule_response",
            {
                "holiday_schedule_id": t.uint8_t,
                "status": foundation.Status,
                "local_start_time?": t.LocalTime,
                "local_end_time?": t.LocalTime,
                "operating_mode_during_holiday?": t.uint8_t,
            },
            True,
        ),
        0x13: ZCLCommandDef(
            "clear_holiday_schedule_response", {"status": foundation.Status}, True
        ),
        0x14: ZCLCommandDef(
            "set_user_type_response", {"status": foundation.Status}, True
        ),
        0x15: ZCLCommandDef(
            "get_user_type_response",
            {"user_id": t.uint16_t, "user_type": UserType},
            True,
        ),
        0x16: ZCLCommandDef(
            "set_rfid_code_response", {"status": foundation.Status}, True
        ),
        0x17: ZCLCommandDef(
            "get_rfid_code_response",
            {
                "user_id": t.uint16_t,
                "user_status": UserStatus,
                "user_type": UserType,
                "rfid_code": t.CharacterString,
            },
            True,
        ),
        0x18: ZCLCommandDef(
            "clear_rfid_code_response", {"status": foundation.Status}, True
        ),
        0x19: ZCLCommandDef(
            "clear_all_rfid_codes_response", {"status": foundation.Status}, True
        ),
        0x20: ZCLCommandDef(
            "operation_event_notification",
            {
                "operation_event_source": OperationEventSource,
                "operation_event_code": OperationEvent,
                "user_id": t.uint16_t,
                "pin": t.CharacterString,
                "local_time": t.LocalTime,
                "data?": t.CharacterString,
            },
            False,
        ),
        0x21: ZCLCommandDef(
            "programming_event_notification",
            {
                "program_event_source": OperationEventSource,
                "program_event_code": ProgrammingEvent,
                "user_id": t.uint16_t,
                "pin": t.CharacterString,
                "user_type": UserType,
                "user_status": UserStatus,
                "local_time": t.LocalTime,
                "data?": t.CharacterString,
            },
            False,
        ),
    }


class WindowCovering(Cluster):
    cluster_id = 0x0102
    name = "Window Covering"
    ep_attribute = "window_covering"

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

    attributes: dict[int, ZCLAttributeDef] = {
        # Window Covering Information
        0x0000: ("window_covering_type", WindowCoveringType),
        0x0001: ("physical_closed_limit_lift", t.uint16_t),
        0x0002: ("physical_closed_limit_tilt", t.uint16_t),
        0x0003: ("current_position_lift", t.uint16_t),
        0x0004: ("current_position_tilt", t.uint16_t),
        0x0005: ("number_of_actuations_lift", t.uint16_t),
        0x0006: ("number_of_actuations_tilt", t.uint16_t),
        0x0007: ("config_status", ConfigStatus),
        0x0008: ("current_position_lift_percentage", t.uint8_t),
        0x0009: ("current_position_tilt_percentage", t.uint8_t),
        # Window Covering Settings
        0x0010: ("installed_open_limit_lift", t.uint16_t),
        0x0011: ("installed_closed_limit_lift", t.uint16_t),
        0x0012: ("installed_open_limit_tilt", t.uint16_t),
        0x0013: ("installed_closed_limit_tilt", t.uint16_t),
        0x0014: ("velocity_lift", t.uint16_t),
        0x0015: ("acceleration_time_lift", t.uint16_t),
        0x0016: ("deceleration_time_lift", t.uint16_t),
        0x0017: ("window_covering_mode", WindowCoveringMode),
        0x0018: ("intermediate_setpoints_lift", t.LVBytes),
        0x0019: ("intermediate_setpoints_tilt", t.LVBytes),
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("up_open", {}, False),
        0x01: ZCLCommandDef("down_close", {}, False),
        0x02: ZCLCommandDef("stop", {}, False),
        0x04: ZCLCommandDef("go_to_lift_value", {"lift_value": t.uint16_t}, False),
        0x05: ZCLCommandDef(
            "go_to_lift_percentage", {"percentage_lift_value": t.uint8_t}, False
        ),
        0x07: ZCLCommandDef("go_to_tilt_value", {"tilt_value": t.uint16_t}, False),
        0x08: ZCLCommandDef(
            "go_to_tilt_percentage", {"percentage_tilt_value": t.uint8_t}, False
        ),
    }
    client_commands: dict[int, ZCLCommandDef] = {}
