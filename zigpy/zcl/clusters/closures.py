"""Closures Functional Domain"""

import zigpy.types as t
from zigpy.zcl import Cluster


class Shade(Cluster):
    """Attributes and commands for configuring a shade"""
    cluster_id = 0x0100
    name = 'Shade Configuration'
    ep_attribute = 'shade'
    attributes = {
        # Shade Information
        0x0000: ('physical_closed_limit', t.uint16_t),
        0x0001: ('motor_step_size', t.uint8_t),
        0x0002: ('status', t.bitmap8),
        # Shade Settings
        0x0010: ('closed_limit', t.uint16_t),
        0x0012: ('mode', t.enum8),
    }
    server_commands = {}
    client_commands = {}


class DoorLock(Cluster):
    cluster_id = 0x0101
    name = 'Door Lock'
    ep_attribute = 'door_lock'
    attributes = {
        0x0000: ('lock_state', t.enum8),
        0x0002: ('actuator_enabled', t.Bool),
        0x0003: ('door_state', t.enum8),
        0x0004: ('door_open_events', t.uint32_t),
        0x0005: ('door_closed_events', t.uint32_t),
        0x0006: ('open_period', t.uint16_t),
        0x0010: ('num_of_lock_records_supported', t.uint16_t),
        0x0011: ('num_of_total_users_supported', t.uint16_t),
        0x0012: ('num_of_pin_users_supported', t.uint16_t),
        0x0013: ('num_of_rfid_users_supported', t.uint16_t),
        0x0014: ('num_of_week_day_schedules_supported_per_user', t.uint8_t),
        0x0015: ('num_of_year_day_schedules_supported_per_user', t.uint8_t),
        0x0016: ('num_of_holiday_scheduleds_supported', t.uint8_t),
        0x0017: ('max_pin_len', t.uint8_t),
        0x0018: ('min_pin_len', t.uint8_t),
        0x0019: ('max_rfid_len', t.uint8_t),
        0x001a: ('min_rfid_len', t.uint8_t),
        0x0020: ('enable__logging', t.Bool),
        0x0021: ('language', t.LimitedCharString(3)),
        0x0022: ('led_settings', t.uint8_t),
        0x0023: ('auto_relock_time', t.uint32_t),
        0x0024: ('sound_volume', t.uint8_t),
        0x0025: ('operating_mode', t.uint32_t),
        0x0026: ('lock_type', t.bitmap16),
        0x0027: ('default_configuration_register', t.bitmap16),
        0x0028: ('enable_local_programming', t.Bool),
        0x0029: ('enable_one_touch_locking', t.Bool),
        0x002a: ('enable_inside_status_led', t.Bool),
        0x002b: ('enable_privacy_mode_button', t.Bool),
        0x0030: ('wrong_code_entry_limit', t.uint8_t),
        0x0031: ('user_code_temporary_disable_time', t.uint8_t),
        0x0032: ('send_pin_ota', t.Bool),
        0x0033: ('require_pin_for_rf_operation', t.Bool),
        0x0034: ('zigbee_security_level', t.uint8_t),
        0x0040: ('alarm_mask', t.bitmap16),
        0x0041: ('keypad_operation_event_mask', t.bitmap16),
        0x0042: ('rf_operation_event_mask', t.bitmap16),
        0x0043: ('manual_operation_event_mask', t.bitmap16),
        0x0044: ('rfid_operation_event_mask', t.bitmap16),
        0x0045: ('keypad_programming_event_mask', t.bitmap16),
        0x0046: ('rf_programming_event_mask', t.bitmap16),
        0x0047: ('rfid_programming_event_mask', t.bitmap16),
    }
    server_commands = {
        0x0000: ('lock_door', (), False),
        0x0001: ('unlock_door', (), False),
        0x0002: ('toggle_door', (), False),
        0x0003: ('unlock_with_timeout', (), False),
        0x0004: ('get_log_record', (), False),
        0x0005: ('set_pin_code', (), False),
        0x0006: ('get_pin_code', (), False),
        0x0007: ('clear_pin_code', (), False),
        0x0008: ('clear_all_pin_codes', (), False),
        0x0009: ('set_user_status', (), False),
        0x000a: ('get_user_status', (), False),
        0x000b: ('set_week_day_schedule', (), False),
        0x000c: ('get_week_day_schedule', (), False),
        0x000d: ('clear_week_day_schedule', (), False),
        0x000e: ('set_year_day_schedule', (), False),
        0x000f: ('get_year_day_schedule', (), False),
        0x0010: ('clear_year_day_schedule', (), False),
        0x0011: ('set_holiday_schedule', (), False),
        0x0012: ('get_holiday_schedule', (), False),
        0x0013: ('clear_holiday_schedule', (), False),
        0x0014: ('set_user_type', (), False),
        0x0015: ('get_user_type', (), False),
        0x0016: ('set_rfid_code', (), False),
        0x0017: ('get_rfid_code', (), False),
        0x0018: ('clear_rfid_code', (), False),
        0x0019: ('clear_all_rfid_codes', (), False),
    }
    client_commands = {
        0x0000: ('lock_door_response', (), True),
        0x0001: ('unlock_door_response', (), True),
        0x0002: ('toggle_door_response', (), True),
        0x0003: ('unlock_with_timeout_response', (), True),
        0x0004: ('get_log_record_response', (), True),
        0x0005: ('set_pin_ode_response', (), True),
        0x0006: ('get_pin_code_response', (), True),
        0x0007: ('clear_pin_code_response', (), True),
        0x0008: ('clear_all_pin_codes_response', (), True),
        0x0009: ('set_user_status_response', (), True),
        0x000a: ('get_user_status_response', (), True),
        0x000b: ('set_week_day_schedule_response', (), True),
        0x000c: ('get_week_day_schedule_response', (), True),
        0x000d: ('clear_week_day_schedule_response', (), True),
        0x000e: ('set_year_day_schedule_response', (), True),
        0x000f: ('get_year_day_schedule_response', (), True),
        0x0010: ('clear_year_day_schedule_response', (), True),
        0x0011: ('set_holiday_schedule_response', (), True),
        0x0012: ('get_holiday_schedule_response', (), True),
        0x0013: ('clear_holiday_schedule_response', (), True),
        0x0014: ('set_user_type_response', (), True),
        0x0015: ('get_user_type_response', (), True),
        0x0016: ('set_rfid_code_response', (), True),
        0x0017: ('get_rfid_code_response', (), True),
        0x0018: ('clear_rfid_code_response', (), True),
        0x0019: ('clear_all_rfid_codes_response', (), True),
        0x0020: ('operation_event_notification', (), False),
        0x0021: ('programming_event_notification', (), False),
    }


class WindowCovering(Cluster):
    cluster_id = 0x0102
    name = 'Window Covering'
    ep_attribute = 'window_covering'
    attributes = {
        # Window Covering Information
        0x0000: ('window_covering_type', t.enum8),
        0x0001: ('physical_close_limit_lift_cm', t.uint16_t),
        0x0002: ('physical_close_limit_tilt_ddegree', t.uint16_t),
        0x0003: ('current_position_lift_cm', t.uint16_t),
        0x0004: ('current_position_tilt_ddegree', t.uint16_t),
        0x0005: ('num_of_actuation_lift', t.uint16_t),
        0x0007: ('config_status', t.bitmap8),
        0x0008: ('current_position_lift_percentage', t.uint8_t),
        0x0009: ('current_position_tilt_percentage', t.uint8_t),
        # Window Covering Settings
        0x0010: ('installed_open_limit_lift_cm', t.uint16_t),
        0x0011: ('installed_closed_limit_lift_cm', t.uint16_t),
        0x0012: ('installed_open_limit_tilt_ddegree', t.uint16_t),
        0x0013: ('installed_closed_limit_tilt_ddegree', t.uint16_t),
        0x0014: ('velocity_lift', t.uint16_t),
        0x0015: ('acceleration_time_lift', t.uint16_t),
        0x0016: ('num_of_actuation_tilt', t.uint16_t),
        0x0017: ('window_covering_mode', t.uint8_t),
        0x0018: ('intermediate_setpoints_lift', t.CharacterString),
        0x0019: ('intermediate_setpoints_tilt', t.CharacterString),
    }
    server_commands = {
        0x0000: ('up_open', (), False),
        0x0001: ('down_close', (), False),
        0x0002: ('stop', (), False),
        0x0004: ('go_to_lift_value', (t.uint16_t, ), False),
        0x0005: ('go_to_lift_percentage', (t.uint8_t, ), False),
        0x0007: ('go_to_tilt_value', (t.uint16_t, ), False),
        0x0008: ('go_to_tilt_percentage', (t.uint8_t, ), False),
    }
    client_commands = {}
