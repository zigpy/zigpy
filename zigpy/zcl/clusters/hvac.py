"""HVAC Functional Domain"""

import zigpy.types as t
from zigpy.zcl import Cluster


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
        0x0010: ("pump_status", PumpStatus),
        0x0011: ("effective_operation_mode", OperationMode),
        0x0012: ("effective_control_mode", ControlMode),
        0x0013: ("capacity", t.int16s),
        0x0014: ("speed", t.uint16_t),
        0x0015: ("lifetime_running_hours", t.uint24_t),
        0x0016: ("power", t.uint24_t),
        0x0017: ("lifetime_energy_consumed", t.uint32_t),
        # Pump Settings
        0x0020: ("operation_mode", OperationMode),
        0x0021: ("control_mode", ControlMode),
        0x0022: ("alarm_mask", AlarmMask),
    }
    server_commands = {}
    client_commands = {}


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
    attributes = {
        # Thermostat Information
        0x0000: ("local_temp", t.int16s),
        0x0001: ("outdoor_temp", t.int16s),
        0x0002: ("occupancy", Occupancy),
        0x0003: ("abs_min_heat_setpoint_limit", t.int16s),
        0x0004: ("abs_max_heat_setpoint_limit", t.int16s),
        0x0005: ("abs_min_cool_setpoint_limit", t.int16s),
        0x0006: ("abs_max_cool_setpoint_limit", t.int16s),
        0x0007: ("pi_cooling_demand", t.uint8_t),
        0x0008: ("pi_heating_demand", t.uint8_t),
        0x0009: ("system_type_config", SystemType),
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
        0x001A: ("remote_sensing", RemoteSensing),
        0x001B: ("ctrl_seqe_of_oper", ControlSequenceOfOperation),
        0x001C: ("system_mode", SystemMode),
        0x001D: ("alarm_mask", AlarmMask),
        0x001E: ("running_mode", RunningMode),
        # ...
        0x0020: ("start_of_week", StartOfWeek),
        0x0021: ("number_of_weekly_trans", t.uint8_t),
        0x0022: ("number_of_daily_trans", t.uint8_t),
        0x0023: ("temp_setpoint_hold", TemperatureSetpointHold),
        0x0024: ("temp_setpoint_hold_duration", t.uint16_t),
        0x0025: ("programing_oper_mode", ProgrammingOperationMode),
        0x0029: ("running_state", RunningState),
        0x0030: ("setpoint_change_source", SetpointChangeSource),
        0x0031: ("setpoint_change_amount", t.int16s),
        0x0032: ("setpoint_change_source_time_stamp", t.uint32_t),
        0x0040: ("ac_type", ACType),
        0x0041: ("ac_capacity", t.uint16_t),
        0x0042: ("ac_refrigerant_type", ACRefrigerantType),
        0x0043: ("ac_compressor_type", ACCompressorType),
        0x0044: ("ac_error_code", ACErrorCode),
        0x0045: ("ac_louver_position", ACLouverPosition),
        0x0046: ("ac_coll_temp", t.int16s),
        0x0047: ("ac_capacity_format", ACCapacityFormat),
    }
    server_commands = {
        0x0000: ("setpoint_raise_lower", (SetpointMode, t.int8s), False),
        0x0001: (
            "set_weekly_schedule",
            (t.enum8, SeqDayOfWeek, SeqMode, t.List[t.int16s]),
            False,
        ),
        0x0002: ("get_weekly_schedule", (SeqDayOfWeek, SeqMode), False),
        0x0003: ("clear_weekly_schedule", (), False),
        0x0004: ("get_relay_status_log", (), False),
    }
    client_commands = {
        0x0000: (
            "get_weekly_schedule_response",
            (t.enum8, SeqDayOfWeek, SeqMode, t.List[t.int16s]),
            True,
        ),
        0x0001: (
            "get_relay_status_log_response",
            (t.uint16_t, t.bitmap8, t.int16s, t.uint8_t, t.int16s, t.uint16_t),
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
    attributes = {
        # Fan Control Status
        0x0000: ("fan_mode", FanMode),
        0x0001: ("fan_mode_sequence", FanModeSequence),
    }
    server_commands = {}
    client_commands = {}


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
    attributes = {
        # Dehumidification Information
        0x0000: ("relative_humidity", t.uint8_t),
        0x0001: ("dehumid_cooling", t.uint8_t),
        # Dehumidification Settings
        0x0010: ("rh_dehumid_setpoint", t.uint8_t),
        0x0011: ("relative_humidity_mode", RelativeHumidityMode),
        0x0012: ("dehumid_lockout", DehumidificationLockout),
        0x0013: ("dehumid_hysteresis", t.uint8_t),
        0x0014: ("dehumid_max_cool", t.uint8_t),
        0x0015: ("relative_humid_display", RelativeHumidityDisplay),
    }
    server_commands = {}
    client_commands = {}


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
    attributes = {
        0x0000: ("temp_display_mode", TemperatureDisplayMode),
        0x0001: ("keypad_lockout", KeypadLockout),
        0x0002: ("programming_visibility", ScheduleProgrammingVisibility),
    }
    server_commands = {}
    client_commands = {}
