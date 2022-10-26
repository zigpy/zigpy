"""HVAC Functional Domain"""

from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class Pump(Cluster):
    """An interface for configuring and controlling pumps."""

    class AlarmMask(t.bitmap16):
        Supply_voltage_too_low = 0x0001
        Supply_voltage_too_high = 0x0002
        Power_missing_phase = 0x0004
        System_pressure_too_low = 0x0008
        System_pressure_too_high = 0x0010
        Dry_running = 0x0020
        Motor_temperature_too_high = 0x0040
        Pump_motor_has_fatal_failure = 0x0080
        Electronic_temperature_too_high = 0x0100
        Pump_blocked = 0x0200
        Sensor_failure = 0x0400
        Electronic_non_fatal_failure = 0x0800
        Electronic_fatal_failure = 0x1000
        General_fault = 0x2000

    class ControlMode(t.enum8):
        Constant_speed = 0x00
        Constant_pressure = 0x01
        Proportional_pressure = 0x02
        Constant_flow = 0x03
        Constant_temperature = 0x05
        Automatic = 0x07

    class OperationMode(t.enum8):
        Normal = 0x00
        Minimum = 0x01
        Maximum = 0x02
        Local = 0x03

    class PumpStatus(t.bitmap16):
        Device_fault = 0x0001
        Supply_fault = 0x0002
        Speed_low = 0x0004
        Speed_high = 0x0008
        Local_override = 0x0010
        Running = 0x0020
        Remote_Pressure = 0x0040
        Remote_Flow = 0x0080
        Remote_Temperature = 0x0100

    cluster_id = 0x0200
    name = "Pump Configuration and Control"
    ep_attribute = "pump"
    attributes: dict[int, ZCLAttributeDef] = {
        # Pump Information
        0x0000: ZCLAttributeDef(
            "max_pressure", type=t.int16s, access="r", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "max_speed", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_flow", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("min_const_pressure", type=t.int16s, access="r"),
        0x0004: ZCLAttributeDef("max_const_pressure", type=t.int16s, access="r"),
        0x0005: ZCLAttributeDef("min_comp_pressure", type=t.int16s, access="r"),
        0x0006: ZCLAttributeDef("max_comp_pressure", type=t.int16s, access="r"),
        0x0007: ZCLAttributeDef("min_const_speed", type=t.uint16_t, access="r"),
        0x0008: ZCLAttributeDef("max_const_speed", type=t.uint16_t, access="r"),
        0x0009: ZCLAttributeDef("min_const_flow", type=t.uint16_t, access="r"),
        0x000A: ZCLAttributeDef("max_const_flow", type=t.uint16_t, access="r"),
        0x000B: ZCLAttributeDef("min_const_temp", type=t.int16s, access="r"),
        0x000C: ZCLAttributeDef("max_const_temp", type=t.int16s, access="r"),
        # Pump Dynamic Information
        0x0010: ZCLAttributeDef("pump_status", type=PumpStatus, access="rp"),
        0x0011: ZCLAttributeDef(
            "effective_operation_mode", type=OperationMode, access="r", mandatory=True
        ),
        0x0012: ZCLAttributeDef(
            "effective_control_mode", type=ControlMode, access="r", mandatory=True
        ),
        0x0013: ZCLAttributeDef("capacity", type=t.int16s, access="rp", mandatory=True),
        0x0014: ZCLAttributeDef("speed", type=t.uint16_t, access="r"),
        0x0015: ZCLAttributeDef("lifetime_running_hours", type=t.uint24_t, access="rw"),
        0x0016: ZCLAttributeDef("power", type=t.uint24_t, access="rw"),
        0x0017: ZCLAttributeDef(
            "lifetime_energy_consumed", type=t.uint32_t, access="r"
        ),
        # Pump Settings
        0x0020: ZCLAttributeDef(
            "operation_mode", type=OperationMode, access="rw", mandatory=True
        ),
        0x0021: ZCLAttributeDef("control_mode", type=ControlMode, access="rw"),
        0x0022: ZCLAttributeDef("alarm_mask", type=AlarmMask, access="r"),
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class CoolingSystemStage(t.enum8):
    Cool_Stage_1 = 0x00
    Cool_Stage_2 = 0x01
    Cool_Stage_3 = 0x02
    Reserved = 0x03


class HeatingSystemStage(t.enum8):
    Heat_Stage_1 = 0x00
    Heat_Stage_2 = 0x01
    Heat_Stage_3 = 0x02
    Reserved = 0x03


class HeatingSystemType(t.enum8):
    Conventional = 0x00
    Heat_Pump = 0x01


class HeatingFuelSource(t.enum8):
    Electric = 0x00
    Gas = 0x01


class Thermostat(Cluster):
    """An interface for configuring and controlling the
    functionality of a thermostat."""

    class ACCapacityFormat(t.enum8):
        BTUh = 0x00

    class ACCompressorType(t.enum8):
        Reserved = 0x00
        T1_max_working_43C = 0x01
        T2_max_working_35C = 0x02
        T3_max_working_52C = 0x03

    class ACType(t.enum8):
        Reserved = 0x00
        Cooling_fixed_speed = 0x01
        Heat_Pump_fixed_speed = 0x02
        Cooling_Inverter = 0x03
        Heat_Pump_Inverter = 0x04

    class ACRefrigerantType(t.enum8):
        Reserved = 0x00
        R22 = 0x01
        R410a = 0x02
        R407c = 0x03

    class ACErrorCode(t.bitmap32):
        No_Errors = 0x00000000
        Commpressor_Failure = 0x00000001
        Room_Temperature_Sensor_Failure = 0x00000002
        Outdoor_Temperature_Sensor_Failure = 0x00000004
        Indoor_Coil_Temperature_Sensor_Failure = 0x00000008
        Fan_Failure = 0x00000010

    class ACLouverPosition(t.enum8):
        Closed = 0x01
        Open = 0x02
        Qurter_Open = 0x03
        Half_Open = 0x04
        Three_Quarters_Open = 0x05

    class AlarmMask(t.bitmap8):
        No_Alarms = 0x00
        Initialization_failure = 0x01
        Hardware_failure = 0x02
        Self_calibration_failure = 0x04

    class ControlSequenceOfOperation(t.enum8):
        Cooling_Only = 0x00
        Cooling_With_Reheat = 0x01
        Heating_Only = 0x02
        Heating_With_Reheat = 0x03
        Cooling_and_Heating = 0x04
        Cooling_and_Heating_with_Reheat = 0x05

    class SeqDayOfWeek(t.bitmap8):
        Sunday = 0x01
        Monday = 0x02
        Tuesday = 0x04
        Wednesday = 0x08
        Thursday = 0x10
        Friday = 0x20
        Saturday = 0x40
        Away = 0x80

    class SeqMode(t.bitmap8):
        Heat = 0x01
        Cool = 0x02

    class Occupancy(t.bitmap8):
        Unoccupied = 0x00
        Occupied = 0x01

    class ProgrammingOperationMode(t.bitmap8):
        Simple = 0x00
        Schedule_programming_mode = 0x01
        Auto_recovery_mode = 0x02
        Economy_mode = 0x04

    class RemoteSensing(t.bitmap8):
        all_local = 0x00
        local_temperature_sensed_remotely = 0x01
        outdoor_temperature_sensed_remotely = 0x02
        occupancy_sensed_remotely = 0x04

    class SetpointChangeSource(t.enum8):
        Manual = 0x00
        Schedule = 0x01
        External = 0x02

    class SetpointMode(t.enum8):
        Heat = 0x00
        Cool = 0x01
        Both = 0x02

    class StartOfWeek(t.enum8):
        Sunday = 0x00
        Monday = 0x01
        Tuesday = 0x02
        Wednesday = 0x03
        Thursday = 0x04
        Friday = 0x05
        Saturday = 0x06

    class SystemMode(t.enum8):
        Off = 0x00
        Auto = 0x01
        Cool = 0x03
        Heat = 0x04
        Emergency_Heating = 0x05
        Pre_cooling = 0x06
        Fan_only = 0x07
        Dry = 0x08
        Sleep = 0x09

    class SystemType(t.bitmap8):
        Heat_and_or_Cool_Stage_1 = 0x00
        Cool_Stage_1 = 0x01
        Cool_Stage_2 = 0x02
        Heat_Stage_1 = 0x04
        Heat_Stage_2 = 0x08
        Heat_Pump = 0x10
        Gas = 0x20

        @property
        def cooling_system_stage(self) -> CoolingSystemStage:
            return CoolingSystemStage(self & 0x03)

        @property
        def heating_system_stage(self) -> HeatingSystemStage:
            return HeatingSystemStage((self >> 2) & 0x03)

        @property
        def heating_system_type(self) -> HeatingSystemType:
            return HeatingSystemType((self >> 4) & 0x01)

        @property
        def heating_fuel_source(self) -> HeatingFuelSource:
            return HeatingFuelSource((self >> 5) & 0x01)

    class TemperatureSetpointHold(t.enum8):
        Setpoint_Hold_Off = 0x00
        Setpoint_Hold_On = 0x01

    class RunningMode(t.enum8):
        Off = 0x00
        Cool = 0x03
        Heat = 0x04

    class RunningState(t.bitmap16):
        Idle = 0x0000
        Heat_State_On = 0x0001
        Cool_State_On = 0x0002
        Fan_State_On = 0x0004
        Heat_2nd_Stage_On = 0x0008
        Cool_2nd_Stage_On = 0x0010
        Fan_2nd_Stage_On = 0x0020
        Fan_3rd_Stage_On = 0x0040

    cluster_id = 0x0201
    ep_attribute = "thermostat"
    attributes: dict[int, ZCLAttributeDef] = {
        # Thermostat Information
        0x0000: ZCLAttributeDef(
            "local_temperature", type=t.int16s, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef("outdoor_temperature", type=t.int16s, access="r"),
        0x0002: ZCLAttributeDef("occupancy", type=Occupancy, access="r"),
        0x0003: ZCLAttributeDef(
            "abs_min_heat_setpoint_limit", type=t.int16s, access="r"
        ),
        0x0004: ZCLAttributeDef(
            "abs_max_heat_setpoint_limit", type=t.int16s, access="r"
        ),
        0x0005: ZCLAttributeDef(
            "abs_min_cool_setpoint_limit", type=t.int16s, access="r"
        ),
        0x0006: ZCLAttributeDef(
            "abs_max_cool_setpoint_limit", type=t.int16s, access="r"
        ),
        0x0007: ZCLAttributeDef("pi_cooling_demand", type=t.uint8_t, access="rp"),
        0x0008: ZCLAttributeDef("pi_heating_demand", type=t.uint8_t, access="rp"),
        0x0009: ZCLAttributeDef("system_type_config", type=SystemType, access="r*w"),
        # Thermostat Settings
        0x0010: ZCLAttributeDef(
            "local_temperature_calibration", type=t.int8s, access="rw"
        ),
        # At least one of these two attribute sets will be available
        0x0011: ZCLAttributeDef(
            "occupied_cooling_setpoint", type=t.int16s, access="rws"
        ),
        0x0012: ZCLAttributeDef(
            "occupied_heating_setpoint", type=t.int16s, access="rws"
        ),
        0x0013: ZCLAttributeDef(
            "unoccupied_cooling_setpoint", type=t.int16s, access="rw"
        ),
        0x0014: ZCLAttributeDef(
            "unoccupied_heating_setpoint", type=t.int16s, access="rw"
        ),
        0x0015: ZCLAttributeDef("min_heat_setpoint_limit", type=t.int16s, access="rw"),
        0x0016: ZCLAttributeDef("max_heat_setpoint_limit", type=t.int16s, access="rw"),
        0x0017: ZCLAttributeDef("min_cool_setpoint_limit", type=t.int16s, access="rw"),
        0x0018: ZCLAttributeDef("max_cool_setpoint_limit", type=t.int16s, access="rw"),
        0x0019: ZCLAttributeDef("min_setpoint_dead_band", type=t.int8s, access="r*w"),
        0x001A: ZCLAttributeDef("remote_sensing", type=RemoteSensing, access="rw"),
        0x001B: ZCLAttributeDef(
            "ctrl_sequence_of_oper",
            type=ControlSequenceOfOperation,
            access="rw",
            mandatory=True,
        ),
        0x001C: ZCLAttributeDef(
            "system_mode", type=SystemMode, access="rws", mandatory=True
        ),
        0x001D: ZCLAttributeDef("alarm_mask", type=AlarmMask, access="r"),
        0x001E: ZCLAttributeDef("running_mode", type=RunningMode, access="r"),
        # Schedule
        0x0020: ZCLAttributeDef("start_of_week", type=StartOfWeek, access="r"),
        0x0021: ZCLAttributeDef(
            "number_of_weekly_transitions", type=t.uint8_t, access="r"
        ),
        0x0022: ZCLAttributeDef(
            "number_of_daily_transitions", type=t.uint8_t, access="r"
        ),
        0x0023: ZCLAttributeDef(
            "temp_setpoint_hold", type=TemperatureSetpointHold, access="rw"
        ),
        0x0024: ZCLAttributeDef(
            "temp_setpoint_hold_duration", type=t.uint16_t, access="rw"
        ),
        0x0025: ZCLAttributeDef(
            "programing_oper_mode", type=ProgrammingOperationMode, access="rwp"
        ),
        # HVAC Relay
        0x0029: ZCLAttributeDef("running_state", type=RunningState, access="r"),
        # Thermostat Setpoint Change Tracking
        0x0030: ZCLAttributeDef(
            "setpoint_change_source", type=SetpointChangeSource, access="r"
        ),
        0x0031: ZCLAttributeDef("setpoint_change_amount", type=t.int16s, access="r"),
        0x0032: ZCLAttributeDef(
            "setpoint_change_source_timestamp", type=t.UTCTime, access="r"
        ),
        0x0034: ZCLAttributeDef("occupied_setback", type=t.uint8_t, access="rw"),
        0x0035: ZCLAttributeDef("occupied_setback_min", type=t.uint8_t, access="r"),
        0x0036: ZCLAttributeDef("occupied_setback_max", type=t.uint8_t, access="r"),
        0x0037: ZCLAttributeDef("unoccupied_setback", type=t.uint8_t, access="rw"),
        0x0038: ZCLAttributeDef("unoccupied_setback_min", type=t.uint8_t, access="r"),
        0x0039: ZCLAttributeDef("unoccupied_setback_max", type=t.uint8_t, access="r"),
        0x003A: ZCLAttributeDef("emergency_heat_delta", type=t.uint8_t, access="rw"),
        # AC Information
        0x0040: ZCLAttributeDef("ac_type", type=ACType, access="rw"),
        0x0041: ZCLAttributeDef("ac_capacity", type=t.uint16_t, access="rw"),
        0x0042: ZCLAttributeDef(
            "ac_refrigerant_type", type=ACRefrigerantType, access="rw"
        ),
        0x0043: ZCLAttributeDef(
            "ac_compressor_type", type=ACCompressorType, access="rw"
        ),
        0x0044: ZCLAttributeDef("ac_error_code", type=ACErrorCode, access="rw"),
        0x0045: ZCLAttributeDef(
            "ac_louver_position", type=ACLouverPosition, access="rw"
        ),
        0x0046: ZCLAttributeDef("ac_coil_temperature", type=t.int16s, access="r"),
        0x0047: ZCLAttributeDef(
            "ac_capacity_format", type=ACCapacityFormat, access="rw"
        ),
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef(
            "setpoint_raise_lower", {"mode": SetpointMode, "amount": t.int8s}, False
        ),
        0x01: ZCLCommandDef(
            "set_weekly_schedule",
            {
                "num_transitions_for_sequence": t.enum8,
                "day_of_week_for_sequence": SeqDayOfWeek,
                "mode_for_sequence": SeqMode,
                "values": t.List[t.int16s],
            },  # TODO: properly parse values
            False,
        ),
        0x02: ZCLCommandDef(
            "get_weekly_schedule",
            {"days_to_return": SeqDayOfWeek, "mode_to_return": SeqMode},
            False,
        ),
        0x03: ZCLCommandDef("clear_weekly_schedule", {}, False),
        0x04: ZCLCommandDef("get_relay_status_log", {}, False),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef(
            "get_weekly_schedule_response",
            {
                "num_transitions_for_sequence": t.enum8,
                "day_of_week_for_sequence": SeqDayOfWeek,
                "mode_for_sequence": SeqMode,
                "values": t.List[t.int16s],
            },  # TODO: properly parse values
            True,
        ),
        0x01: ZCLCommandDef(
            "get_relay_status_log_response",
            {
                "time_of_day": t.uint16_t,
                "relay_status": t.bitmap8,
                "local_temperature": t.int16s,
                "humidity_in_percentage": t.uint8_t,
                "set_point": t.int16s,
                "unread_entries": t.uint16_t,
            },
            True,
        ),
    }


class Fan(Cluster):
    """An interface for controlling a fan in a heating /
    cooling system."""

    class FanMode(t.enum8):
        Off = 0x00
        Low = 0x01
        Medium = 0x02
        High = 0x03
        On = 0x04
        Auto = 0x05
        Smart = 0x06

    class FanModeSequence(t.enum8):
        Low_Med_High = 0x00
        Low_High = 0x01
        Low_Med_High_Auto = 0x02
        Low_High_Auto = 0x03
        On_Auto = 0x04

    cluster_id = 0x0202
    name = "Fan Control"
    ep_attribute = "fan"
    attributes: dict[int, ZCLAttributeDef] = {
        # Fan Control Status
        0x0000: ZCLAttributeDef("fan_mode", type=FanMode, access=""),
        0x0001: ZCLAttributeDef("fan_mode_sequence", type=FanModeSequence, access=""),
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Dehumidification(Cluster):
    """An interface for controlling dehumidification."""

    class RelativeHumidityMode(t.enum8):
        RH_measured_locally = 0x00
        RH_measured_remotely = 0x01

    class DehumidificationLockout(t.enum8):
        Dehumidification_not_allowed = 0x00
        Dehumidification_is_allowed = 0x01

    class RelativeHumidityDisplay(t.enum8):
        RH_not_displayed = 0x00
        RH_is_displayed = 0x01

    cluster_id = 0x0203
    ep_attribute = "dehumidification"
    attributes: dict[int, ZCLAttributeDef] = {
        # Dehumidification Information
        0x0000: ZCLAttributeDef("relative_humidity", type=t.uint8_t, access="r"),
        0x0001: ZCLAttributeDef(
            "dehumidification_cooling", type=t.uint8_t, access="rp", mandatory=True
        ),
        # Dehumidification Settings
        0x0010: ZCLAttributeDef(
            "rh_dehumidification_setpoint", type=t.uint8_t, access="rw", mandatory=True
        ),
        0x0011: ZCLAttributeDef(
            "relative_humidity_mode", type=RelativeHumidityMode, access="rw"
        ),
        0x0012: ZCLAttributeDef(
            "dehumidification_lockout", type=DehumidificationLockout, access="rw"
        ),
        0x0013: ZCLAttributeDef(
            "dehumidification_hysteresis", type=t.uint8_t, access="rw", mandatory=True
        ),
        0x0014: ZCLAttributeDef(
            "dehumidification_max_cool", type=t.uint8_t, access="rw", mandatory=True
        ),
        0x0015: ZCLAttributeDef(
            "relative_humidity_display", type=RelativeHumidityDisplay, access="rw"
        ),
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class UserInterface(Cluster):
    """An interface for configuring the user interface of a
    thermostat (which may be remote from the
    thermostat)."""

    class TemperatureDisplayMode(t.enum8):
        Metric = 0x00
        Imperial = 0x01

    class KeypadLockout(t.enum8):
        No_lockout = 0x00
        Level_1_lockout = 0x01
        Level_2_lockout = 0x02
        Level_3_lockout = 0x03
        Level_4_lockout = 0x04
        Level_5_lockout = 0x05

    class ScheduleProgrammingVisibility(t.enum8):
        Enabled = 0x00
        Disabled = 0x02

    cluster_id = 0x0204
    name = "Thermostat User Interface Configuration"
    ep_attribute = "thermostat_ui"
    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef(
            "temperature_display_mode",
            type=TemperatureDisplayMode,
            access="rw",
            mandatory=True,
        ),
        0x0001: ZCLAttributeDef(
            "keypad_lockout", type=KeypadLockout, access="rw", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "schedule_programming_visibility",
            type=ScheduleProgrammingVisibility,
            access="rw",
        ),
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
