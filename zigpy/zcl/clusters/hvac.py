"""HVAC Functional Domain"""

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


class PumpAlarmMask(t.bitmap16):
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


class Pump(Cluster):
    """An interface for configuring and controlling pumps."""

    AlarmMask: Final = PumpAlarmMask
    ControlMode: Final = ControlMode
    OperationMode: Final = OperationMode
    PumpStatus: Final = PumpStatus

    cluster_id: Final[t.uint16_t] = 0x0200
    name: Final = "Pump Configuration and Control"
    ep_attribute: Final = "pump"

    class AttributeDefs(BaseAttributeDefs):
        # Pump Information
        max_pressure: Final = ZCLAttributeDef(
            id=0x0000, type=t.int16s, access="r", mandatory=True
        )
        max_speed: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_flow: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        min_const_pressure: Final = ZCLAttributeDef(
            id=0x0003, type=t.int16s, access="r"
        )
        max_const_pressure: Final = ZCLAttributeDef(
            id=0x0004, type=t.int16s, access="r"
        )
        min_comp_pressure: Final = ZCLAttributeDef(id=0x0005, type=t.int16s, access="r")
        max_comp_pressure: Final = ZCLAttributeDef(id=0x0006, type=t.int16s, access="r")
        min_const_speed: Final = ZCLAttributeDef(id=0x0007, type=t.uint16_t, access="r")
        max_const_speed: Final = ZCLAttributeDef(id=0x0008, type=t.uint16_t, access="r")
        min_const_flow: Final = ZCLAttributeDef(id=0x0009, type=t.uint16_t, access="r")
        max_const_flow: Final = ZCLAttributeDef(id=0x000A, type=t.uint16_t, access="r")
        min_const_temp: Final = ZCLAttributeDef(id=0x000B, type=t.int16s, access="r")
        max_const_temp: Final = ZCLAttributeDef(id=0x000C, type=t.int16s, access="r")
        # Pump Dynamic Information
        pump_status: Final = ZCLAttributeDef(id=0x0010, type=PumpStatus, access="rp")
        effective_operation_mode: Final = ZCLAttributeDef(
            id=0x0011, type=OperationMode, access="r", mandatory=True
        )
        effective_control_mode: Final = ZCLAttributeDef(
            id=0x0012, type=ControlMode, access="r", mandatory=True
        )
        capacity: Final = ZCLAttributeDef(
            id=0x0013, type=t.int16s, access="rp", mandatory=True
        )
        speed: Final = ZCLAttributeDef(id=0x0014, type=t.uint16_t, access="r")
        lifetime_running_hours: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint24_t, access="rw"
        )
        power: Final = ZCLAttributeDef(id=0x0016, type=t.uint24_t, access="rw")
        lifetime_energy_consumed: Final = ZCLAttributeDef(
            id=0x0017, type=t.uint32_t, access="r"
        )
        # Pump Settings
        operation_mode: Final = ZCLAttributeDef(
            id=0x0020, type=OperationMode, access="rw", mandatory=True
        )
        control_mode: Final = ZCLAttributeDef(id=0x0021, type=ControlMode, access="rw")
        alarm_mask: Final = ZCLAttributeDef(id=0x0022, type=PumpAlarmMask, access="r")


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


class Thermostat(Cluster):
    """An interface for configuring and controlling the
    functionality of a thermostat.
    """

    ACCapacityFormat: Final = ACCapacityFormat
    ACErrorCode: Final = ACErrorCode
    ACLouverPosition: Final = ACLouverPosition
    AlarmMask: Final = AlarmMask
    ControlSequenceOfOperation: Final = ControlSequenceOfOperation
    SeqDayOfWeek: Final = SeqDayOfWeek
    SeqMode: Final = SeqMode
    Occupancy: Final = Occupancy
    ProgrammingOperationMode: Final = ProgrammingOperationMode
    RemoteSensing: Final = RemoteSensing
    SetpointChangeSource: Final = SetpointChangeSource
    SetpointMode: Final = SetpointMode
    StartOfWeek: Final = StartOfWeek
    SystemMode: Final = SystemMode
    SystemType: Final = SystemType
    TemperatureSetpointHold: Final = TemperatureSetpointHold
    RunningMode: Final = RunningMode
    RunningState: Final = RunningState

    cluster_id: Final[t.uint16_t] = 0x0201
    ep_attribute: Final = "thermostat"

    class AttributeDefs(BaseAttributeDefs):
        # Thermostat Information
        local_temperature: Final = ZCLAttributeDef(
            id=0x0000, type=t.int16s, access="rp", mandatory=True
        )
        outdoor_temperature: Final = ZCLAttributeDef(
            id=0x0001, type=t.int16s, access="r"
        )
        occupancy: Final = ZCLAttributeDef(id=0x0002, type=Occupancy, access="r")
        abs_min_heat_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0003, type=t.int16s, access="r"
        )
        abs_max_heat_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0004, type=t.int16s, access="r"
        )
        abs_min_cool_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0005, type=t.int16s, access="r"
        )
        abs_max_cool_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0006, type=t.int16s, access="r"
        )
        pi_cooling_demand: Final = ZCLAttributeDef(
            id=0x0007, type=t.uint8_t, access="rp"
        )
        pi_heating_demand: Final = ZCLAttributeDef(
            id=0x0008, type=t.uint8_t, access="rp"
        )
        system_type_config: Final = ZCLAttributeDef(
            id=0x0009, type=SystemType, access="r*w"
        )
        # Thermostat Settings
        local_temperature_calibration: Final = ZCLAttributeDef(
            id=0x0010, type=t.int8s, access="rw"
        )
        # At least one of these two attribute sets will be available
        occupied_cooling_setpoint: Final = ZCLAttributeDef(
            id=0x0011, type=t.int16s, access="rws"
        )
        occupied_heating_setpoint: Final = ZCLAttributeDef(
            id=0x0012, type=t.int16s, access="rws"
        )
        unoccupied_cooling_setpoint: Final = ZCLAttributeDef(
            id=0x0013, type=t.int16s, access="rw"
        )
        unoccupied_heating_setpoint: Final = ZCLAttributeDef(
            id=0x0014, type=t.int16s, access="rw"
        )
        min_heat_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0015, type=t.int16s, access="rw"
        )
        max_heat_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0016, type=t.int16s, access="rw"
        )
        min_cool_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0017, type=t.int16s, access="rw"
        )
        max_cool_setpoint_limit: Final = ZCLAttributeDef(
            id=0x0018, type=t.int16s, access="rw"
        )
        min_setpoint_dead_band: Final = ZCLAttributeDef(
            id=0x0019, type=t.int8s, access="r*w"
        )
        remote_sensing: Final = ZCLAttributeDef(
            id=0x001A, type=RemoteSensing, access="rw"
        )
        ctrl_sequence_of_oper: Final = ZCLAttributeDef(
            id=0x001B,
            type=ControlSequenceOfOperation,
            access="rw",
            mandatory=True,
        )
        system_mode: Final = ZCLAttributeDef(
            id=0x001C, type=SystemMode, access="rws", mandatory=True
        )
        alarm_mask: Final = ZCLAttributeDef(id=0x001D, type=AlarmMask, access="r")
        running_mode: Final = ZCLAttributeDef(id=0x001E, type=RunningMode, access="r")
        # Schedule
        start_of_week: Final = ZCLAttributeDef(id=0x0020, type=StartOfWeek, access="r")
        number_of_weekly_transitions: Final = ZCLAttributeDef(
            id=0x0021, type=t.uint8_t, access="r"
        )
        number_of_daily_transitions: Final = ZCLAttributeDef(
            id=0x0022, type=t.uint8_t, access="r"
        )
        temp_setpoint_hold: Final = ZCLAttributeDef(
            id=0x0023, type=TemperatureSetpointHold, access="rw"
        )
        temp_setpoint_hold_duration: Final = ZCLAttributeDef(
            id=0x0024, type=t.uint16_t, access="rw"
        )
        programing_oper_mode: Final = ZCLAttributeDef(
            id=0x0025, type=ProgrammingOperationMode, access="rwp"
        )
        # HVAC Relay
        running_state: Final = ZCLAttributeDef(id=0x0029, type=RunningState, access="r")
        # Thermostat Setpoint Change Tracking
        setpoint_change_source: Final = ZCLAttributeDef(
            id=0x0030, type=SetpointChangeSource, access="r"
        )
        setpoint_change_amount: Final = ZCLAttributeDef(
            id=0x0031, type=t.int16s, access="r"
        )
        setpoint_change_source_timestamp: Final = ZCLAttributeDef(
            id=0x0032, type=t.UTCTime, access="r"
        )
        occupied_setback: Final = ZCLAttributeDef(
            id=0x0034, type=t.uint8_t, access="rw"
        )
        occupied_setback_min: Final = ZCLAttributeDef(
            id=0x0035, type=t.uint8_t, access="r"
        )
        occupied_setback_max: Final = ZCLAttributeDef(
            id=0x0036, type=t.uint8_t, access="r"
        )
        unoccupied_setback: Final = ZCLAttributeDef(
            id=0x0037, type=t.uint8_t, access="rw"
        )
        unoccupied_setback_min: Final = ZCLAttributeDef(
            id=0x0038, type=t.uint8_t, access="r"
        )
        unoccupied_setback_max: Final = ZCLAttributeDef(
            id=0x0039, type=t.uint8_t, access="r"
        )
        emergency_heat_delta: Final = ZCLAttributeDef(
            id=0x003A, type=t.uint8_t, access="rw"
        )
        # AC Information
        ac_type: Final = ZCLAttributeDef(id=0x0040, type=ACType, access="rw")
        ac_capacity: Final = ZCLAttributeDef(id=0x0041, type=t.uint16_t, access="rw")
        ac_refrigerant_type: Final = ZCLAttributeDef(
            id=0x0042, type=ACRefrigerantType, access="rw"
        )
        ac_compressor_type: Final = ZCLAttributeDef(
            id=0x0043, type=ACCompressorType, access="rw"
        )
        ac_error_code: Final = ZCLAttributeDef(id=0x0044, type=ACErrorCode, access="rw")
        ac_louver_position: Final = ZCLAttributeDef(
            id=0x0045, type=ACLouverPosition, access="rw"
        )
        ac_coil_temperature: Final = ZCLAttributeDef(
            id=0x0046, type=t.int16s, access="r"
        )
        ac_capacity_format: Final = ZCLAttributeDef(
            id=0x0047, type=ACCapacityFormat, access="rw"
        )

    class ServerCommandDefs(BaseCommandDefs):
        setpoint_raise_lower: Final = ZCLCommandDef(
            id=0x00,
            schema={"mode": SetpointMode, "amount": t.int8s},
            direction=Direction.Client_to_Server,
        )
        set_weekly_schedule: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "num_transitions_for_sequence": t.enum8,
                "day_of_week_for_sequence": SeqDayOfWeek,
                "mode_for_sequence": SeqMode,
                "values": t.List[t.int16s],
            },
            direction=Direction.Client_to_Server,
        )
        get_weekly_schedule: Final = ZCLCommandDef(
            id=0x02,
            schema={"days_to_return": SeqDayOfWeek, "mode_to_return": SeqMode},
            direction=Direction.Client_to_Server,
        )
        clear_weekly_schedule: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Client_to_Server
        )
        get_relay_status_log: Final = ZCLCommandDef(
            id=0x04, schema={}, direction=Direction.Client_to_Server
        )

    class ClientCommandDefs(BaseCommandDefs):
        get_weekly_schedule_response: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "num_transitions_for_sequence": t.enum8,
                "day_of_week_for_sequence": SeqDayOfWeek,
                "mode_for_sequence": SeqMode,
                "values": t.List[t.int16s],
            },
            direction=Direction.Server_to_Client,
        )
        get_relay_status_log_response: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "time_of_day": t.uint16_t,
                "relay_status": t.bitmap8,
                "local_temperature": t.int16s,
                "humidity_in_percentage": t.uint8_t,
                "set_point": t.int16s,
                "unread_entries": t.uint16_t,
            },
            direction=Direction.Server_to_Client,
        )


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


class Fan(Cluster):
    """An interface for controlling a fan in a heating /
    cooling system.
    """

    FanMode: Final = FanMode
    FanModeSequence: Final = FanModeSequence

    cluster_id: Final[t.uint16_t] = 0x0202
    name: Final = "Fan Control"
    ep_attribute: Final = "fan"

    class AttributeDefs(BaseAttributeDefs):
        fan_mode: Final = ZCLAttributeDef(id=0x0000, type=FanMode, access="")
        fan_mode_sequence: Final = ZCLAttributeDef(
            id=0x0001, type=FanModeSequence, access=""
        )


class RelativeHumidityMode(t.enum8):
    RH_measured_locally = 0x00
    RH_measured_remotely = 0x01


class DehumidificationLockout(t.enum8):
    Dehumidification_not_allowed = 0x00
    Dehumidification_is_allowed = 0x01


class RelativeHumidityDisplay(t.enum8):
    RH_not_displayed = 0x00
    RH_is_displayed = 0x01


class Dehumidification(Cluster):
    """An interface for controlling dehumidification."""

    RelativeHumidityMode: Final = RelativeHumidityMode
    DehumidificationLockout: Final = DehumidificationLockout
    RelativeHumidityDisplay: Final = RelativeHumidityDisplay

    cluster_id: Final[t.uint16_t] = 0x0203
    ep_attribute: Final = "dehumidification"

    class AttributeDefs(BaseAttributeDefs):
        # Dehumidification Information
        relative_humidity: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r"
        )
        dehumidification_cooling: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint8_t, access="rp", mandatory=True
        )
        # Dehumidification Settings
        rh_dehumidification_setpoint: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint8_t, access="rw", mandatory=True
        )
        relative_humidity_mode: Final = ZCLAttributeDef(
            id=0x0011, type=RelativeHumidityMode, access="rw"
        )
        dehumidification_lockout: Final = ZCLAttributeDef(
            id=0x0012, type=DehumidificationLockout, access="rw"
        )
        dehumidification_hysteresis: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint8_t, access="rw", mandatory=True
        )
        dehumidification_max_cool: Final = ZCLAttributeDef(
            id=0x0014, type=t.uint8_t, access="rw", mandatory=True
        )
        relative_humidity_display: Final = ZCLAttributeDef(
            id=0x0015, type=RelativeHumidityDisplay, access="rw"
        )


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


class UserInterface(Cluster):
    """An interface for configuring the user interface of a
    thermostat (which may be remote from the
    thermostat).
    """

    TemperatureDisplayMode: Final = TemperatureDisplayMode
    KeypadLockout: Final = KeypadLockout
    ScheduleProgrammingVisibility: Final = ScheduleProgrammingVisibility

    cluster_id: Final[t.uint16_t] = 0x0204
    name: Final = "Thermostat User Interface Configuration"
    ep_attribute: Final = "thermostat_ui"

    class AttributeDefs(BaseAttributeDefs):
        temperature_display_mode: Final = ZCLAttributeDef(
            id=0x0000,
            type=TemperatureDisplayMode,
            access="rw",
            mandatory=True,
        )
        keypad_lockout: Final = ZCLAttributeDef(
            id=0x0001, type=KeypadLockout, access="rw", mandatory=True
        )
        schedule_programming_visibility: Final = ZCLAttributeDef(
            id=0x0002,
            type=ScheduleProgrammingVisibility,
            access="rw",
        )
