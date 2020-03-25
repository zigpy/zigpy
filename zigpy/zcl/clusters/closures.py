"""Closures Functional Domain"""

import zigpy.types as t
from zigpy.zcl import Cluster, foundation


class Shade(Cluster):
    """Attributes and commands for configuring a shade"""

    cluster_id = 0x0100
    name = "Shade Configuration"
    ep_attribute = "shade"
    attributes = {
        # Shade Information
        0x0000: ("physical_closed_limit", t.uint16_t),
        0x0001: ("motor_step_size", t.uint8_t),
        0x0002: ("status", t.bitmap8),
        # Shade Settings
        0x0010: ("closed_limit", t.uint16_t),
        0x0012: ("mode", t.enum8),
    }
    server_commands = {}
    client_commands = {}


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
    attributes = {
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
    server_commands = {
        0x0000: ("lock_door", (t.Optional(t.CharacterString),), False),
        0x0001: ("unlock_door", (t.Optional(t.CharacterString),), False),
        0x0002: ("toggle_door", (t.Optional(t.CharacterString),), False),
        0x0003: (
            "unlock_with_timeout",
            (t.uint16_t, t.Optional(t.CharacterString)),
            False,
        ),
        0x0004: ("get_log_record", (t.uint16_t,), False),
        0x0005: (
            "set_pin_code",
            (t.uint16_t, UserStatus, UserType, t.CharacterString),
            False,
        ),
        0x0006: ("get_pin_code", (t.uint16_t,), False),
        0x0007: ("clear_pin_code", (t.uint16_t,), False),
        0x0008: ("clear_all_pin_codes", (), False),
        0x0009: ("set_user_status", (t.uint16_t, UserStatus), False),
        0x000A: ("get_user_status", (t.uint16_t,), False),
        0x000B: (
            "set_week_day_schedule",
            (
                t.uint8_t,
                t.uint16_t,
                DayMask,
                t.uint8_t,
                t.uint8_t,
                t.uint8_t,
                t.uint8_t,
            ),
            False,
        ),
        0x000C: ("get_week_day_schedule", (t.uint8_t, t.uint16_t), False),
        0x000D: ("clear_week_day_schedule", (t.uint8_t, t.uint16_t), False),
        0x000E: (
            "set_year_day_schedule",
            (t.uint8_t, t.uint16_t, t.LocalTime, t.LocalTime),
            False,
        ),
        0x000F: ("get_year_day_schedule", (t.uint8_t, t.uint16_t), False),
        0x0010: ("clear_year_day_schedule", (t.uint8_t, t.uint16_t), False),
        0x0011: (
            "set_holiday_schedule",
            (t.uint8_t, t.LocalTime, t.LocalTime, OperatingMode),
            False,
        ),
        0x0012: ("get_holiday_schedule", (t.uint8_t,), False),
        0x0013: ("clear_holiday_schedule", (t.uint8_t,), False),
        0x0014: ("set_user_type", (t.uint16_t, UserType), False),
        0x0015: ("get_user_type", (t.uint16_t,), False),
        0x0016: (
            "set_rfid_code",
            (t.uint16_t, UserStatus, UserType, t.CharacterString),
            False,
        ),
        0x0017: ("get_rfid_code", (t.uint16_t,), False),
        0x0018: ("clear_rfid_code", (t.uint16_t,), False),
        0x0019: ("clear_all_rfid_codes", (), False),
    }
    client_commands = {
        0x0000: ("lock_door_response", (foundation.Status,), True),
        0x0001: ("unlock_door_response", (foundation.Status,), True),
        0x0002: ("toggle_door_response", (foundation.Status,), True),
        0x0003: ("unlock_with_timeout_response", (foundation.Status,), True),
        0x0004: (
            "get_log_record_response",
            (
                t.uint16_t,
                t.uint32_t,
                EventType,
                OperationEventSource,
                t.uint8_t,
                t.uint16_t,
                t.Optional(t.CharacterString),
            ),
            True,
        ),
        0x0005: ("set_pin_code_response", (foundation.Status,), True),
        0x0006: (
            "get_pin_code_response",
            (t.uint16_t, UserStatus, UserType, t.CharacterString),
            True,
        ),
        0x0007: ("clear_pin_code_response", (foundation.Status,), True),
        0x0008: ("clear_all_pin_codes_response", (foundation.Status,), True),
        0x0009: ("set_user_status_response", (foundation.Status,), True),
        0x000A: ("get_user_status_response", (t.uint16_t, UserStatus), True),
        0x000B: ("set_week_day_schedule_response", (foundation.Status,), True),
        0x000C: (
            "get_week_day_schedule_response",
            (
                t.uint8_t,
                t.uint16_t,
                foundation.Status,
                t.Optional(t.uint8_t),
                t.Optional(t.uint8_t),
                t.Optional(t.uint8_t),
                t.Optional(t.uint8_t),
            ),
            True,
        ),
        0x000D: ("clear_week_day_schedule_response", (foundation.Status,), True),
        0x000E: ("set_year_day_schedule_response", (foundation.Status,), True),
        0x000F: (
            "get_year_day_schedule_response",
            (
                t.uint8_t,
                t.uint16_t,
                foundation.Status,
                t.Optional(t.LocalTime),
                t.Optional(t.LocalTime),
            ),
            True,
        ),
        0x0010: ("clear_year_day_schedule_response", (foundation.Status,), True),
        0x0011: ("set_holiday_schedule_response", (foundation.Status,), True),
        0x0012: (
            "get_holiday_schedule_response",
            (
                t.uint8_t,
                foundation.Status,
                t.Optional(t.LocalTime),
                t.Optional(t.LocalTime),
                t.Optional(t.uint8_t),
            ),
            True,
        ),
        0x0013: ("clear_holiday_schedule_response", (foundation.Status,), True),
        0x0014: ("set_user_type_response", (foundation.Status,), True),
        0x0015: ("get_user_type_response", (t.uint16_t, UserType), True),
        0x0016: ("set_rfid_code_response", (t.uint8_t,), True),
        0x0017: (
            "get_rfid_code_response",
            (t.uint16_t, UserStatus, UserType, t.CharacterString),
            True,
        ),
        0x0018: ("clear_rfid_code_response", (foundation.Status,), True),
        0x0019: ("clear_all_rfid_codes_response", (foundation.Status,), True),
        0x0020: (
            "operation_event_notification",
            (
                OperationEventSource,
                OperationEvent,
                t.uint16_t,
                t.uint8_t,
                t.LocalTime,
                t.CharacterString,
            ),
            False,
        ),
        0x0021: (
            "programming_event_notification",
            (
                OperationEventSource,
                ProgrammingEvent,
                t.uint16_t,
                t.uint8_t,
                UserType,
                UserStatus,
                t.LocalTime,
                t.CharacterString,
            ),
            False,
        ),
    }


class WindowCovering(Cluster):
    cluster_id = 0x0102
    name = "Window Covering"
    ep_attribute = "window_covering"
    attributes = {
        # Window Covering Information
        0x0000: ("window_covering_type", t.enum8),
        0x0001: ("physical_close_limit_lift_cm", t.uint16_t),
        0x0002: ("physical_close_limit_tilt_ddegree", t.uint16_t),
        0x0003: ("current_position_lift_cm", t.uint16_t),
        0x0004: ("current_position_tilt_ddegree", t.uint16_t),
        0x0005: ("num_of_actuation_lift", t.uint16_t),
        0x0007: ("config_status", t.bitmap8),
        0x0008: ("current_position_lift_percentage", t.uint8_t),
        0x0009: ("current_position_tilt_percentage", t.uint8_t),
        # Window Covering Settings
        0x0010: ("installed_open_limit_lift_cm", t.uint16_t),
        0x0011: ("installed_closed_limit_lift_cm", t.uint16_t),
        0x0012: ("installed_open_limit_tilt_ddegree", t.uint16_t),
        0x0013: ("installed_closed_limit_tilt_ddegree", t.uint16_t),
        0x0014: ("velocity_lift", t.uint16_t),
        0x0015: ("acceleration_time_lift", t.uint16_t),
        0x0016: ("num_of_actuation_tilt", t.uint16_t),
        0x0017: ("window_covering_mode", t.uint8_t),
        0x0018: ("intermediate_setpoints_lift", t.CharacterString),
        0x0019: ("intermediate_setpoints_tilt", t.CharacterString),
    }
    server_commands = {
        0x0000: ("up_open", (), False),
        0x0001: ("down_close", (), False),
        0x0002: ("stop", (), False),
        0x0004: ("go_to_lift_value", (t.uint16_t,), False),
        0x0005: ("go_to_lift_percentage", (t.uint8_t,), False),
        0x0007: ("go_to_tilt_value", (t.uint16_t,), False),
        0x0008: ("go_to_tilt_percentage", (t.uint8_t,), False),
    }
    client_commands = {}
