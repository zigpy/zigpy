"""Constants Related to General Clusters"""

from __future__ import annotations

import zigpy.types as t


class AnalogInputType(t.enum8):
    Temp_Degrees_C = 0x00
    Relative_Humidity_Percent = 0x01
    Pressure_Pascal = 0x02
    Flow_Liters_Per_Sec = 0x03
    Percentage = 0x04
    Parts_Per_Million = 0x05
    Rotational_Speed_RPM = 0x06
    Current_Amps = 0x07
    Frequency_Hz = 0x08
    Power_Watts = 0x09
    Power_Kilo_Watts = 0x0A
    Energy_Kilo_Watt_Hours = 0x0B
    Count = 0x0C
    Enthalpy_KJoules_Per_Kg = 0x0D
    Time_Seconds = 0x0E


class TempDegreesC(t.enum16):
    Two_Pipe_Entering_Water_Temperature = 0x0000
    Two_Pipe_Leaving_Water_Temperature = 0x0001
    Boiler_Entering_Temperature = 0x0002
    Boiler_Leaving_Temperature = 0x0003
    Chiller_Chilled_Water_Entering_Temp = 0x0004
    Chiller_Chilled_Water_Leaving_Temp = 0x0005
    Chiller_Condenser_Water_Entering_Temp = 0x0006
    Chiller_Condenser_Water_Leaving_Temp = 0x0007
    Cold_Deck_Temperature = 0x0008
    Cooling_Coil_Discharge_Temperature = 0x0009
    Cooling_Entering_Water_Temperature = 0x000A
    Cooling_Leaving_Water_Temperature = 0x000B
    Condenser_Water_Return_Temperature = 0x000C
    Condenser_Water_Supply_Temperature = 0x000D
    Decouple_Loop_Temperature = 0x000E
    Building_Load = 0x000F
    Decouple_Loop_Temperature_2 = 0x0010
    Dew_Point_Temperature = 0x0011
    Discharge_Air_Temperature = 0x0012
    Discharge_Temperature = 0x0013
    Exhaust_Air_Temperature_After_Heat_Recovery = 0x0014
    Exhaust_Air_Temperature = 0x0015
    Glycol_Temperature = 0x0016
    Heat_Recovery_Air_Temperature = 0x0017
    Hot_Deck_Temperature = 0x0018
    Heat_Exchanger_Bypass_Temp = 0x0019
    Heat_Exchanger_Entering_Temp = 0x001A
    Heat_Exchanger_Leaving_Temp = 0x001B
    Mechanical_Room_Temperature = 0x001C
    Mixed_Air_Temperature = 0x001D
    Mixed_Air_Temperature_2 = 0x001E
    Outdoor_Air_Dewpoint_Temp = 0x001F
    Outdoor_Air_Temperature = 0x0020
    Preheat_Air_Temperature = 0x0021
    Preheat_Entering_Water_Temperature = 0x0022
    Preheat_Leaving_Water_Temperature = 0x0023
    Primary_Chilled_Water_Return_Temp = 0x0024
    Primary_Chilled_Water_Supply_Temp = 0x0025
    Primary_Hot_Water_Return_Temp = 0x0026
    Primary_Hot_Water_Supply_Temp = 0x0027
    Reheat_Coil_Discharge_Temperature = 0x0028
    Reheat_Entering_Water_Temperature = 0x0029
    Reheat_Leaving_Water_Temperature = 0x002A
    Return_Air_Temperature = 0x002B
    Secondary_Chilled_Water_Return_Temp = 0x002C
    Secondary_Chilled_Water_Supply_Temp = 0x002D
    Secondary_HW_Return_Temp = 0x002E
    Secondary_HW_Supply_Temp = 0x002F
    Sideloop_Reset_Temperature = 0x0030
    Sideloop_Temperature_Setpoint = 0x0031
    Sideloop_Temperature = 0x0032
    Source_Temperature = 0x0033
    Supply_Air_Temperature = 0x0034
    Supply_Low_Limit_Temperature = 0x0035
    Tower_Basin_Temp = 0x0036
    Two_Pipe_Leaving_Water_Temp = 0x0037
    Reserved = 0x0038
    Zone_Dewpoint_Temperature = 0x0039
    Zone_Sensor_Setpoint = 0x003A
    Zone_Sensor_Setpoint_Offset = 0x003B
    Zone_Temperature = 0x003C
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class RelativeHumidityPercent(t.enum16):
    Discharge_Humidity = 0x0000
    Exhaust_Humidity = 0x0001
    Hot_Deck_Humidity = 0x0002
    Mixed_Air_Humidity = 0x0003
    Outdoor_Air_Humidity = 0x0004
    Return_Humidity = 0x0005
    Sideloop_Humidity = 0x0006
    Space_Humidity = 0x0007
    Zone_Humidity = 0x0008
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class PressurePascal(t.enum16):
    Boiler_Pump_Differential_Pressure = 0x0000
    Building_Static_Pressure = 0x0001
    Cold_Deck_Differential_Pressure_Sensor = 0x0002
    Chilled_Water_Building_Differential_Pressure = 0x0003
    Cold_Deck_Differential_Pressure = 0x0004
    Cold_Deck_Static_Pressure = 0x0005
    Condenser_Water_Pump_Differential_Pressure = 0x0006
    Discharge_Differential_Pressure = 0x0007
    Discharge_Static_Pressure_1 = 0x0008
    Discharge_Static_Pressure_2 = 0x0009
    Exhaust_Air_Differential_Pressure = 0x000A
    Exhaust_Air_Static_Pressure = 0x000B
    Exhaust_Differential_Pressure = 0x000C
    Exhaust_Differential_Pressure_2 = 0x000D
    Hot_Deck_Differential_Pressure = 0x000E
    Hot_Deck_Differential_Pressure_2 = 0x000F
    Hot_Deck_Static_Pressure = 0x0010
    Hot_Water_Bldg_Diff_Pressure = 0x0011
    Heat_Exchanger_Steam_Pressure = 0x0012
    Minimum_Outdoor_Air_Differential_Pressure = 0x0013
    Outdoor_Air_Differential_Pressure = 0x0014
    Primary_Chilled_Water_Pump_Differential_Pressure = 0x0015
    Primary_Hot_Water_Pump_Differential_Pressure = 0x0016
    Relief_Differential_Pressure = 0x0017
    Return_Air_Static_Pressure = 0x0018
    Return_Differential_Pressure = 0x0019
    Secondary_Chilled_Water_Pump_Differential_Pressure = 0x001A
    Secondary_Hot_Water_Pump_Differential_Pressure = 0x001B
    Sideloop_Pressure = 0x001C
    Steam_Pressure = 0x001D
    Supply_Differential_Pressure_Sensor = 0x001E
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class FlowLitersPerSec(t.enum16):
    Chilled_Water_Flow = 0x0000
    Chiller_Chilled_Water_Flow = 0x0001
    Chiller_Condenser_Water_Flow = 0x0002
    Cold_Deck_Flow = 0x0003
    Decouple_Loop_Flow = 0x0004
    Discharge_Flow = 0x0005
    Exhaust_Fan_Flow = 0x0006
    Exhaust_Flow = 0x0007
    Fan_Flow = 0x0008
    Hot_Deck_Flow = 0x0009
    Hot_Water_Flow = 0x000A
    Minimum_Outdoor_Air_Fan_Flow = 0x000B
    Minimum_Outdoor_Air_Flow = 0x000C
    Outdoor_Air_Flow = 0x000D
    Primary_Chilled_Water_Flow = 0x000E
    Relief_Fan_Flow = 0x000F
    Relief_Flow = 0x0010
    Return_Fan_Flow = 0x0011
    Return_Flow = 0x0012
    Secondary_Chilled_Water_Flow = 0x0013
    Supply_Fan_Flow = 0x0014
    Tower_Fan_Flow = 0x0015
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class Percentage(t.enum16):
    Chiller_Percent_Full_Load_Amperage = 0x000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class PartsPerMillion(t.enum16):
    Return_Carbon_Dioxide = 0x0000
    Zone_Carbon_Dioxide = 0x0001
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class RotationalSpeedRPM(t.enum16):
    Exhaust_Fan_Remote_Speed = 0x0000
    Heat_Recovery_Wheel_Remote_Speed = 0x0001
    Min_Outdoor_Air_Fan_Remote_Speed = 0x0002
    Relief_Fan_Remote_Speed = 0x0003
    Return_Fan_Remote_Speed = 0x0004
    Supply_Fan_Remote_Speed = 0x0005
    Variable_Speed_Drive_Motor_Speed = 0x0006
    Variable_Speed_Drive_Speed_Setpoint = 0x0007
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class CurrentAmps(t.enum16):
    Chiller_Amps = 0x0000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class FrequencyHz(t.enum16):
    Variable_Speed_Drive_Output_Frequency = 0x0000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class PowerWatts(t.enum16):
    Power_Consumption = 0x0000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class PowerKiloWatts(t.enum16):
    Absolute_Power = 0x0000
    Power_Consumption = 0x0001
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class EnergyKiloWattHours(t.enum16):
    Variable_Speed_Drive_Kilowatt_Hours = 0x0000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class Count(t.enum16):
    Count = 0x0000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class EnthalpyKJoulesPerKg(t.enum16):
    Outdoor_Air_Enthalpy = 0x0000
    Return_Air_Enthalpy = 0x0001
    Space_Enthalpy = 0x0002
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


class TimeSeconds(t.enum16):
    Relative_Time = 0x0000
    # 0x0200 through 0xFFFE are vendor defined
    Other = 0xFFFF


ANALOG_INPUT_TYPES = {
    AnalogInputType.Temp_Degrees_C: TempDegreesC,
    AnalogInputType.Relative_Humidity_Percent: RelativeHumidityPercent,
    AnalogInputType.Pressure_Pascal: PressurePascal,
    AnalogInputType.Flow_Liters_Per_Sec: FlowLitersPerSec,
    AnalogInputType.Percentage: Percentage,
    AnalogInputType.Parts_Per_Million: PartsPerMillion,
    AnalogInputType.Rotational_Speed_RPM: RotationalSpeedRPM,
    AnalogInputType.Current_Amps: CurrentAmps,
    AnalogInputType.Frequency_Hz: FrequencyHz,
    AnalogInputType.Power_Watts: PowerWatts,
    AnalogInputType.Power_Kilo_Watts: PowerKiloWatts,
    AnalogInputType.Energy_Kilo_Watt_Hours: EnergyKiloWattHours,
    AnalogInputType.Count: Count,
    AnalogInputType.Enthalpy_KJoules_Per_Kg: EnthalpyKJoulesPerKg,
    AnalogInputType.Time_Seconds: TimeSeconds,
}


class ApplicationType(t.IntStruct, t.uint32_t):
    # Index = Bits 0 to 15
    index: t.uint16_t
    # Type = Bits 16 to 23
    type: AnalogInputType
    # Group = Bits 24 to 31
    group: t.uint8_t
