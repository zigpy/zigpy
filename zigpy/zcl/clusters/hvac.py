"""HVAC Functional Domain"""

import zigpy.types as t
from zigpy.zcl import Cluster


class Pump(Cluster):
    """An interface for configuring and controlling pumps."""

    cluster_id = 0x0200
    name = "Pump Configuration and Control"
    ep_attribute = "pump"
    attributes = {
        # Pump Information
        0x0000: ("max_pressure", t.int16s),
        0x0001: ("max_speed", t.uint16_t),
        0x0002: ("max_flow", t.uint16_t),
        0x0003: ("min_const_pressure", t.int16s),
        0x0004: ("max_const_pressure", t.int16s),
        0x0005: ("min_comp_pressure", t.int16s),
        0x0006: ("max_comp_pressure", t.int16s),
        0x0007: ("min_const_speed", t.uint16_t),
        0x0008: ("max_const_speed", t.uint16_t),
        0x0009: ("min_const_flow", t.uint16_t),
        0x000A: ("max_const_flow", t.uint16_t),
        0x000B: ("min_const_temp", t.int16s),
        0x000C: ("max_const_temp", t.int16s),
        # Pump Dynamic Information
        0x0010: ("pump_status", t.bitmap16),
        0x0011: ("effective_operation_mode", t.enum8),
        0x0012: ("effective_control_mode", t.enum8),
        0x0013: ("capacity", t.int16s),
        0x0014: ("speed", t.uint16_t),
        0x0015: ("lifetime_running_hours", t.uint24_t),
        0x0016: ("power", t.uint24_t),
        0x0017: ("lifetime_energy_consumed", t.uint32_t),
        # Pump Settings
        0x0020: ("operation_mode", t.enum8),
        0x0021: ("control_mode", t.enum8),
        0x0022: ("alarm_mask", t.bitmap16),
    }
    server_commands = {}
    client_commands = {}


class Thermostat(Cluster):
    """An interface for configuring and controlling the
    functionality of a thermostat."""

    cluster_id = 0x0201
    ep_attribute = "thermostat"
    attributes = {
        # Thermostat Information
        0x0000: ("local_temp", t.int16s),
        0x0001: ("outdoor_temp", t.int16s),
        0x0002: ("occupancy", t.bitmap8),
        0x0003: ("abs_min_heat_setpoint_limit", t.int16s),
        0x0004: ("abs_max_heat_setpoint_limit", t.int16s),
        0x0005: ("abs_min_cool_setpoint_limit", t.int16s),
        0x0006: ("abs_max_cool_setpoint_limit", t.int16s),
        0x0007: ("pi_cooling_demand", t.uint8_t),
        0x0008: ("pi_heating_demand", t.uint8_t),
        0x0009: ("system_type_config", t.bitmap8),
        # Thermostat Settings
        0x0010: ("local_temperature_calibration", t.int8s),
        0x0011: ("occupied_cooling_setpoint", t.int16s),
        0x0012: ("occupied_heating_setpoint", t.int16s),
        0x0013: ("unoccupied_cooling_setpoint", t.int16s),
        0x0014: ("unoccupied_heating_setpoint", t.int16s),
        0x0015: ("min_heat_setpoint_limit", t.int16s),
        0x0016: ("max_heat_setpoint_limit", t.int16s),
        0x0017: ("min_cool_setpoint_limit", t.int16s),
        0x0018: ("max_cool_setpoint_limit", t.int16s),
        0x0019: ("min_setpoint_dead_band", t.int8s),
        0x001A: ("remote_sensing", t.bitmap8),
        0x001B: ("ctrl_seqe_of_oper", t.enum8),
        0x001C: ("system_mode", t.enum8),
        0x001D: ("alarm_mask", t.bitmap8),
        0x001E: ("running_mode", t.enum8),
        # ...
        0x0020: ("start_of_week", t.enum8),
        0x0021: ("number_of_weekly_trans", t.uint8_t),
        0x0022: ("number_of_daily_trans", t.uint8_t),
        0x0023: ("temp_setpoint_hold", t.enum8),
        0x0024: ("temp_setpoint_hold_duration", t.uint16_t),
        0x0025: ("programing_oper_mode", t.bitmap8),
        0x0029: ("running_state", t.bitmap16),
        0x0030: ("setpoint_change_source", t.enum8),
        0x0031: ("setpoint_change_amount", t.int16s),
        0x0032: ("setpoint_change_source_time_stamp", t.uint32_t),
        0x0040: ("ac_type", t.enum8),
        0x0041: ("ac_capacity", t.uint16_t),
        0x0042: ("ac_refrigerant_type", t.enum8),
        0x0043: ("ac_compressor_type", t.enum8),
        0x0044: ("ac_error_code", t.bitmap32),
        0x0045: ("ac_louver_position", t.enum8),
        0x0046: ("ac_coll_temp", t.int16s),
        0x0047: ("ac_capacity_format", t.enum8),
    }
    server_commands = {
        0x0000: ("setpoint_raise_lower", (t.enum8, t.int8s), False),
        0x0001: (
            "set_weekly_schedule",
            (t.enum8, t.bitmap8, t.bitmap8, t.List(t.int16s)),
            False,
        ),
        0x0002: ("get_weekly_schedule", (t.bitmap8, t.bitmap8), False),
        0x0003: ("clear_weekly_schedule", (), False),
        0x0004: ("get_relay_status_log", (), False),
    }
    client_commands = {
        0x0000: (
            "get_weekly_schedule_response",
            (t.enum8, t.bitmap8, t.bitmap8, t.List(t.int16s)),
            True,
        ),
        0x0001: (
            "get_relay_status_log_response",
            (t.uint16_t, t.bitmap8, t.int16s, t.uint8_t, t.int16s, t.uint16_t),
            True,
        ),
    }


class Fan(Cluster):
    """ An interface for controlling a fan in a heating /
    cooling system."""

    cluster_id = 0x0202
    name = "Fan Control"
    ep_attribute = "fan"
    attributes = {
        # Fan Control Status
        0x0000: ("fan_mode", t.enum8),
        0x0001: ("fan_mode_sequence", t.enum8),
    }
    server_commands = {}
    client_commands = {}


class Dehumidification(Cluster):
    """An interface for controlling dehumidification."""

    cluster_id = 0x0203
    ep_attribute = "dehumidification"
    attributes = {
        # Dehumidification Information
        0x0000: ("relative_humidity", t.uint8_t),
        0x0001: ("dehumid_cooling", t.uint8_t),
        # Dehumidification Settings
        0x0010: ("rh_dehumid_setpoint", t.uint8_t),
        0x0011: ("relative_humidity_mode", t.enum8),
        0x0012: ("dehumid_lockout", t.enum8),
        0x0013: ("dehumid_hysteresis", t.uint8_t),
        0x0014: ("dehumid_max_cool", t.uint8_t),
        0x0015: ("relative_humid_display", t.enum8),
    }
    server_commands = {}
    client_commands = {}


class UserInterface(Cluster):
    """An interface for configuring the user interface of a
    thermostat (which may be remote from the
    thermostat)."""

    cluster_id = 0x0204
    name = "Thermostat User Interface Configuration"
    ep_attribute = "thermostat_ui"
    attributes = {
        0x0000: ("temp_display_mode", t.enum8),
        0x0001: ("keypad_lockout", t.enum8),
        0x0002: ("programming_visibility", t.enum8),
    }
    server_commands = {}
    client_commands = {}
