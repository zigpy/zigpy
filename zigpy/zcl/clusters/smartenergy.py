from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    DataTypeId,
    ZCLAttributeDef,
    ZCLCommandDef,
)


class Price(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0700
    ep_attribute: Final = "smartenergy_price"


class Drlc(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0701
    ep_attribute: Final = "smartenergy_drlc"


class RegisteredTier(t.enum8):
    No_Tier = 0x00
    Tier_1 = 0x01
    Tier_2 = 0x02
    Tier_3 = 0x03
    Tier_4 = 0x04
    Tier_5 = 0x05
    Tier_6 = 0x06
    Tier_7 = 0x07
    Tier_8 = 0x08
    Tier_9 = 0x09
    Tier_10 = 0x0A
    Tier_11 = 0x0B
    Tier_12 = 0x0C
    Tier_13 = 0x0D
    Tier_14 = 0x0E
    Extended_Tier = 0x0F


class MeteringDeviceType(t.enum8):
    """Metering device type."""

    Electric_Metering = 0
    Gas_Metering = 1
    Water_Metering = 2
    Thermal_Metering = 3  # Deprecated
    Pressure_Metering = 4
    Heat_Metering = 5
    Cooling_Metering = 6
    EUMD_for_metering_electric_vehicle_charging = 7
    PV_Generation_Metering = 8
    Wind_Turbine_Generation_Metering = 9
    Water_Turbine_Generation_Metering = 10
    Micro_Generation_Metering = 11
    Solar_Hot_Water_Generation_Metering = 12
    Electric_Metering_Element_Phase_1 = 13
    Electric_Metering_Element_Phase_2 = 14
    Electric_Metering_Element_Phase_3 = 15

    # 127 + above enum values
    Mirrored_Electric_Metering = 127
    Mirrored_Gas_Metering = 128
    Mirrored_Water_Metering = 129
    Mirrored_Thermal_Metering = 130  # Deprecated
    Mirrored_Pressure_Metering = 131
    Mirrored_Heat_Metering = 132
    Mirrored_Cooling_Metering = 133
    Mirrored_EUMD_for_metering_electric_vehicle_charging = 134
    Mirrored_PV_Generation_Metering = 135
    Mirrored_Wind_Turbine_Generation_Metering = 136
    Mirrored_Water_Turbine_Generation_Metering = 137
    Mirrored_Micro_Generation_Metering = 138
    Mirrored_Solar_Hot_Water_Generation_Metering = 139
    Mirrored_Electric_Metering_Element_Phase_1 = 140
    Mirrored_Electric_Metering_Element_Phase_2 = 141
    Mirrored_Electric_Metering_Element_Phase_3 = 142


class MeteringUnitofMeasure(t.enum8):
    """Metering unit of measure."""

    Kwh_and_Kwh_binary = 0x00
    Cubic_Meter_and_Cubic_Meter_per_Hour_binary = 0x01
    Cubic_Feet_and_Cubic_Feet_per_Hour_binary = 0x02
    Ccf_and_Ccf_per_Hour_binary = 0x03
    US_Gallons_and_US_Gallons_per_Hour_binary = 0x04
    Imperial_Gallons_and_Imperial_Gallons_per_Hour_binary = 0x05
    BTU_and_BTU_per_Hour_binary = 0x06
    Liters_and_Liters_per_Hour_binary = 0x07
    KPA_gauge_binary = 0x08
    KPA_absolute_binary = 0x09
    MCF_and_MCF_per_Hour_binary = 0x0A
    Unitless_binary = 0x0B
    Mega_Joule_and_Mega_Joule_per_second_binary = 0x0C
    Kvar_and_Kvarh_binary = 0x0D
    Kwh_and_Kwh_bcd = 0x80
    Cubic_Meter_and_Cubic_Meter_per_Hour_bcd = 0x81
    Cubic_Feet_and_Cubic_Feet_per_Hour_bcd = 0x82
    Ccf_and_Ccf_per_Hour_bcd = 0x83
    US_Gallons_and_US_Gallons_per_Hour_bcd = 0x84
    Imperial_Gallons_and_Imperial_Gallons_per_Hour_bcd = 0x85
    BTU_and_BTU_per_Hour_bcd = 0x86
    Liters_and_Liters_per_Hour_bcd = 0x87
    KPA_gauge_bcd = 0x88
    KPA_absolute_bcd = 0x89
    MCF_and_MCF_per_Hour_bcd = 0x8A
    Unitless_bcd = 0x8B
    Mega_Joule_and_Mega_Joule_per_second_bcd = 0x8C
    Kvar_and_Kvarh_bcd = 0x8D


class NumberFormatting(t.IntStruct, t.uint8_t):
    """Number formatting."""

    num_digits_right_of_decimal: t.uint3_t
    num_digits_left_of_decimal: t.uint4_t
    suppress_leading_zeros: t.uint1_t


class MeteringStatus(t.bitmap8):
    """Metering status."""

    Check_Meter = 0b00000001
    Low_Battery = 0b00000010
    Tamper_Detect = 0b00000100
    Power_Failure = 0b00001000
    Power_Quality = 0b00010000
    Leak_Detect = 0b00100000
    Service_Disconnect_Open = 0b01000000
    Reserved = 0b10000000


class CurrentBlock(t.enum8):
    """Block enumeration for CurrentBlock attribute."""

    No_Blocks_In_Use = 0x00
    Block1 = 0x01
    Block2 = 0x02
    Block3 = 0x03
    Block4 = 0x04
    Block5 = 0x05
    Block6 = 0x06
    Block7 = 0x07
    Block8 = 0x08
    Block9 = 0x09
    Block10 = 0x0A
    Block11 = 0x0B
    Block12 = 0x0C
    Block13 = 0x0D
    Block14 = 0x0E
    Block15 = 0x0F
    Block16 = 0x10


class ProfileIntervalPeriod(t.enum8):
    """Profile interval period timeframes."""

    Daily = 0x00
    Minutes_60 = 0x01
    Minutes_30 = 0x02
    Minutes_15 = 0x03
    Minutes_10 = 0x04
    Minutes_7_5 = 0x05
    Minutes_5 = 0x06
    Minutes_2_5 = 0x07
    Minutes_1 = 0x08


class SupplyStatus(t.enum8):
    """Supply status at customer premises."""

    Supply_Off = 0x00
    Supply_Off_Armed = 0x01
    Supply_On = 0x02


class AmbientConsumptionIndicator(t.enum8):
    """Ambient consumption indicator - low/medium/high."""

    Low_Energy_Usage = 0x00
    Medium_Energy_Usage = 0x01
    High_Energy_Usage = 0x02


class GenericAlarmMask(t.bitmap16):
    """Generic alarm mask - bits correspond to alarm codes 0x00-0x0F."""

    Check_Meter = 0x0001
    Low_Battery = 0x0002
    Tamper_Detect = 0x0004
    Power_Failure = 0x0008
    Power_Quality = 0x0010
    Leak_Detect = 0x0020
    Service_Disconnect = 0x0040
    Reserved_0x07 = 0x0080
    Meter_Cover_Removed = 0x0100
    Meter_Cover_Closed = 0x0200
    Strong_Magnetic_Field = 0x0400
    No_Strong_Magnetic_Field = 0x0800
    Battery_Failure = 0x1000
    Program_Memory_Error = 0x2000
    RAM_Error = 0x4000
    NV_Memory_Error = 0x8000


class ElectricityAlarmMask(t.bitmap32):
    """Electricity alarm mask - bits correspond to alarm codes 0x10-0x2F."""

    Low_Voltage_L1 = 0x00000001
    High_Voltage_L1 = 0x00000002
    Low_Voltage_L2 = 0x00000004
    High_Voltage_L2 = 0x00000008
    Low_Voltage_L3 = 0x00000010
    High_Voltage_L3 = 0x00000020
    Over_Current_L1 = 0x00000040
    Over_Current_L2 = 0x00000080
    Over_Current_L3 = 0x00000100
    Frequency_Too_Low_L1 = 0x00000200
    Frequency_Too_High_L1 = 0x00000400
    Frequency_Too_Low_L2 = 0x00000800
    Frequency_Too_High_L2 = 0x00001000
    Frequency_Too_Low_L3 = 0x00002000
    Frequency_Too_High_L3 = 0x00004000
    Ground_Fault = 0x00008000
    Electric_Tamper_Detect = 0x00010000
    Incorrect_Polarity = 0x00020000
    Current_No_Voltage = 0x00040000
    Under_Voltage = 0x00080000
    Over_Voltage = 0x00100000
    Normal_Voltage = 0x00200000
    PF_Below_Threshold = 0x00400000
    PF_Above_Threshold = 0x00800000
    Terminal_Cover_Removed = 0x01000000
    Terminal_Cover_Closed = 0x02000000


class GenericFlowPressureAlarmMask(t.bitmap16):
    """Generic flow/pressure alarm mask - bits correspond to alarm codes 0x30-0x3F."""

    Burst_Detect = 0x0001
    Pressure_Too_Low = 0x0002
    Pressure_Too_High = 0x0004
    Flow_Sensor_Communication_Error = 0x0008
    Flow_Sensor_Measurement_Fault = 0x0010
    Flow_Sensor_Reverse_Flow = 0x0020
    Flow_Sensor_Air_Detect = 0x0040
    Pipe_Empty = 0x0080


class WaterSpecificAlarmMask(t.bitmap16):
    """Water specific alarm mask - bits correspond to alarm codes 0x40-0x4F."""

    Water_Pipe_Empty = 0x0001
    Water_Valve_Fraud = 0x0002
    Water_Valve_Moving = 0x0004


class HeatCoolingSpecificAlarmMask(t.bitmap16):
    """Heat and cooling specific alarm mask - bits correspond to alarm codes 0x50-0x5F."""

    Inlet_Temperature_Sensor_Fault = 0x0001
    Outlet_Temperature_Sensor_Fault = 0x0002


class GasSpecificAlarmMask(t.bitmap16):
    """Gas specific alarm mask - bits correspond to alarm codes 0x60-0x6F."""

    Tilt_Tamper = 0x0001
    Battery_Cover_Removed = 0x0002
    Battery_Cover_Closed = 0x0004
    Excess_Flow = 0x0008
    Tilt_Tamper_Ended = 0x0010


class ExtendedStatus(t.bitmap64):
    """Extended status bitmap for Metering cluster."""

    # General flags (bits 0-13)
    Meter_Cover_Removed = 0x0000000000000001
    Strong_Magnetic_Field_Detected = 0x0000000000000002
    Battery_Failure = 0x0000000000000004
    Program_Memory_Error = 0x0000000000000008
    RAM_Error = 0x0000000000000010
    NV_Memory_Error = 0x0000000000000020
    Measurement_System_Error = 0x0000000000000040
    Watchdog_Error = 0x0000000000000080
    Supply_Disconnect_Failure = 0x0000000000000100
    Supply_Connect_Failure = 0x0000000000000200
    Measurement_SW_Changed_Tampered = 0x0000000000000400
    Clock_Invalid = 0x0000000000000800
    Temperature_Exceeded = 0x0000000000001000
    Moisture_Detected = 0x0000000000002000
    # bits 14-23 Reserved
    # Electricity-meter specific flags (bits 24-29)
    Terminal_Cover_Removed = 0x0000000001000000
    Incorrect_Polarity = 0x0000000002000000
    Current_With_No_Voltage = 0x0000000004000000
    Limit_Threshold_Exceeded = 0x0000000008000000
    Under_Voltage = 0x0000000010000000
    Over_Voltage = 0x0000000020000000
    # Gas-meter specific flags (bits 24-26) - shared bit positions with electricity
    # Battery_Cover_Removed_Gas = 0x0000000001000000  # Same as Terminal_Cover_Removed
    # Tilt_Tamper_Gas = 0x0000000002000000  # Same as Incorrect_Polarity
    # Excess_Flow_Gas = 0x0000000004000000  # Same as Current_With_No_Voltage


class ExtendedGenericAlarmMask(t.bitmap48):
    """Extended generic alarm mask - bits for alarm codes 0x70-0x9F.

    Note: Table D-34 defines the Extended Generic Alarm Group range as 0x70-0xAF
    (64 codes), but the attribute type in Table D-33 is a 48-bit bitmap which can
    only represent codes 0x70-0x9F. Codes 0xA0-0xAF cannot be represented.
    """

    Measurement_System_Error = 0x000000000001  # 0x70
    Watchdog_Error = 0x000000000002  # 0x71
    Supply_Disconnect_Failure = 0x000000000004  # 0x72
    Supply_Connect_Failure = 0x000000000008  # 0x73
    Measurement_Software_Changed = 0x000000000010  # 0x74
    DST_Enabled = 0x000000000020  # 0x75
    DST_Disabled = 0x000000000040  # 0x76
    Clock_Adj_Backward = 0x000000000080  # 0x77
    Clock_Adj_Forward = 0x000000000100  # 0x78
    Clock_Invalid = 0x000000000200  # 0x79
    Communication_Error_HAN = 0x000000000400  # 0x7A
    Communication_OK_HAN = 0x000000000800  # 0x7B
    Meter_Fraud_Attempt = 0x000000001000  # 0x7C
    Power_Loss = 0x000000002000  # 0x7D
    Unusual_HAN_Traffic = 0x000000004000  # 0x7E
    Unexpected_Clock_Change = 0x000000008000  # 0x7F
    Comms_Using_Unauthenticated_Component = 0x000000010000  # 0x80
    Error_Reg_Clear = 0x000000020000  # 0x81
    Alarm_Reg_Clear = 0x000000040000  # 0x82
    Unexpected_HW_Reset = 0x000000080000  # 0x83
    Unexpected_Program_Execution = 0x000000100000  # 0x84
    EventLog_Cleared = 0x000000200000  # 0x85
    Limit_Threshold_Exceeded = 0x000000400000  # 0x86
    Limit_Threshold_OK = 0x000000800000  # 0x87
    Limit_Threshold_Changed = 0x000001000000  # 0x88
    Maximum_Demand_Exceeded = 0x000002000000  # 0x89
    Profile_Cleared = 0x000004000000  # 0x8A
    Sampling_Buffer_Cleared = 0x000008000000  # 0x8B
    Battery_Warning = 0x000010000000  # 0x8C
    Wrong_Signature = 0x000020000000  # 0x8D
    No_Signature = 0x000040000000  # 0x8E
    Unauthorized_Action_From_HAN = 0x000080000000  # 0x8F
    Fast_Polling_Start = 0x000100000000  # 0x90
    Fast_Polling_End = 0x000200000000  # 0x91
    Meter_Reporting_Interval_Changed = 0x000400000000  # 0x92
    Disconnect_Due_To_Load_Limit = 0x000800000000  # 0x93
    Meter_Supply_Status_Register_Changed = 0x001000000000  # 0x94
    Meter_Alarm_Status_Register_Changed = 0x002000000000  # 0x95
    Extended_Meter_Alarm_Status_Register_Changed = 0x004000000000  # 0x96
    # 0x97-0x9F Reserved (bits 39-47)


class ManufacturerAlarmMask(t.bitmap16):
    """Manufacturer specific alarm mask - bits for alarm codes 0xB0-0xBF."""

    Manufacturer_Specific_A = 0x0001  # 0xB0
    Manufacturer_Specific_B = 0x0002  # 0xB1
    Manufacturer_Specific_C = 0x0004  # 0xB2
    Manufacturer_Specific_D = 0x0008  # 0xB3
    Manufacturer_Specific_E = 0x0010  # 0xB4
    Manufacturer_Specific_F = 0x0020  # 0xB5
    Manufacturer_Specific_G = 0x0040  # 0xB6
    Manufacturer_Specific_H = 0x0080  # 0xB7
    Manufacturer_Specific_I = 0x0100  # 0xB8
    # 0xB9-0xBF Reserved (bits 9-15)


class SnapshotCause(t.bitmap32):
    """Snapshot cause bitmap per SE 1.4a Table D-52."""

    General = 0x00000001
    End_Of_Billing_Period = 0x00000002
    End_Of_Block_Period = 0x00000004
    Change_Of_Tariff_Information = 0x00000008
    Change_Of_Price_Matrix = 0x00000010
    Change_Of_Block_Thresholds = 0x00000020
    Change_Of_CV = 0x00000040
    Change_Of_CF = 0x00000080
    Change_Of_Calendar = 0x00000100
    Critical_Peak_Pricing = 0x00000200
    Manually_Triggered_From_Client = 0x00000400
    End_Of_Resolve_Period = 0x00000800
    Change_Of_Tenancy = 0x00001000
    Change_Of_Supplier = 0x00002000
    Change_Of_Meter_Mode = 0x00004000
    Debt_Payment = 0x00008000
    Scheduled_Snapshot = 0x00010000
    OTA_Firmware_Download = 0x00020000
    # Bits 18-19: Reserved for Prepayment cluster
    # Bits 20-31: Reserved


class Metering(Cluster):
    RegisteredTier: Final = RegisteredTier
    MeteringDeviceType: Final = MeteringDeviceType
    MeteringUnitofMeasure: Final = MeteringUnitofMeasure
    NumberFormatting: Final = NumberFormatting
    MeteringStatus: Final = MeteringStatus
    CurrentBlock: Final = CurrentBlock
    ProfileIntervalPeriod: Final = ProfileIntervalPeriod
    SupplyStatus: Final = SupplyStatus
    AmbientConsumptionIndicator: Final = AmbientConsumptionIndicator
    GenericAlarmMask: Final = GenericAlarmMask
    ElectricityAlarmMask: Final = ElectricityAlarmMask
    GenericFlowPressureAlarmMask: Final = GenericFlowPressureAlarmMask
    WaterSpecificAlarmMask: Final = WaterSpecificAlarmMask
    HeatCoolingSpecificAlarmMask: Final = HeatCoolingSpecificAlarmMask
    GasSpecificAlarmMask: Final = GasSpecificAlarmMask
    ExtendedStatus: Final = ExtendedStatus
    ExtendedGenericAlarmMask: Final = ExtendedGenericAlarmMask
    ManufacturerAlarmMask: Final = ManufacturerAlarmMask

    cluster_id: Final[t.uint16_t] = 0x0702
    ep_attribute: Final = "smartenergy_metering"

    class AttributeDefs(BaseAttributeDefs):
        current_summ_delivered: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint48_t, access="r", mandatory=True
        )
        current_summ_received: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint48_t, access="r"
        )
        current_max_demand_delivered: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint48_t, access="r"
        )
        current_max_demand_received: Final = ZCLAttributeDef(
            id=0x0003, type=t.uint48_t, access="r"
        )
        dft_summ: Final = ZCLAttributeDef(id=0x0004, type=t.uint48_t, access="r")
        daily_freeze_time: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint16_t, access="r"
        )
        power_factor: Final = ZCLAttributeDef(id=0x0006, type=t.int8s, access="r")
        reading_snapshot_time: Final = ZCLAttributeDef(
            id=0x0007, type=t.UTCTime, access="r"
        )
        current_max_demand_delivered_time: Final = ZCLAttributeDef(
            id=0x0008, type=t.UTCTime, access="r"
        )
        current_max_demand_received_time: Final = ZCLAttributeDef(
            id=0x0009, type=t.UTCTime, access="r"
        )
        default_update_period: Final = ZCLAttributeDef(
            id=0x000A, type=t.uint8_t, access="r"
        )
        fast_poll_update_period: Final = ZCLAttributeDef(
            id=0x000B, type=t.uint8_t, access="r"
        )
        current_block_period_consumption_delivered: Final = ZCLAttributeDef(
            id=0x000C, type=t.uint48_t, access="r"
        )
        daily_consumption_target: Final = ZCLAttributeDef(
            id=0x000D, type=t.uint24_t, access="r"
        )
        current_block: Final = ZCLAttributeDef(id=0x000E, type=CurrentBlock, access="r")
        profile_interval_period: Final = ZCLAttributeDef(
            id=0x000F, type=ProfileIntervalPeriod, access="r"
        )
        # 0x0010: ('interval_read_reporting_period', UNKNOWN), # Deprecated
        preset_reading_time: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint16_t, access="r"
        )
        summation_delivered_per_report: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint16_t, access="r"
        )
        flow_restriction: Final = ZCLAttributeDef(id=0x0013, type=t.uint8_t, access="r")
        supply_status: Final = ZCLAttributeDef(id=0x0014, type=SupplyStatus, access="r")
        current_in_energy_carrier_summ: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint48_t, access="r"
        )
        current_out_energy_carrier_summ: Final = ZCLAttributeDef(
            id=0x0016, type=t.uint48_t, access="r"
        )
        inlet_temperature: Final = ZCLAttributeDef(id=0x0017, type=t.int24s, access="r")
        outlet_temperature: Final = ZCLAttributeDef(
            id=0x0018, type=t.int24s, access="r"
        )
        control_temperature: Final = ZCLAttributeDef(
            id=0x0019, type=t.int24s, access="r"
        )
        current_in_energy_carrier_demand: Final = ZCLAttributeDef(
            id=0x001A, type=t.int24s, access="r"
        )
        current_out_energy_carrier_demand: Final = ZCLAttributeDef(
            id=0x001B, type=t.int24s, access="r"
        )
        previous_block_period_consumption_delivered: Final = ZCLAttributeDef(
            id=0x001C, type=t.uint48_t, access="r"
        )
        current_block_period_consumption_received: Final = ZCLAttributeDef(
            id=0x001D, type=t.uint48_t, access="r"
        )
        current_block_received: Final = ZCLAttributeDef(
            id=0x001E, type=CurrentBlock, access="r"
        )
        dft_summation_received: Final = ZCLAttributeDef(
            id=0x001F, type=t.uint48_t, access="r"
        )
        active_register_tier_delivered: Final = ZCLAttributeDef(
            id=0x0020, type=RegisteredTier, access="r"
        )
        active_register_tier_received: Final = ZCLAttributeDef(
            id=0x0021, type=RegisteredTier, access="r"
        )
        last_block_switch_time: Final = ZCLAttributeDef(
            id=0x0022, type=t.UTCTime, access="r"
        )
        # 0x0100: ('change_reporting_profile', UNKNOWN),
        current_tier1_summ_delivered: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint48_t, access="r"
        )
        current_tier1_summ_received: Final = ZCLAttributeDef(
            id=0x0101, type=t.uint48_t, access="r"
        )
        current_tier2_summ_delivered: Final = ZCLAttributeDef(
            id=0x0102, type=t.uint48_t, access="r"
        )
        current_tier2_summ_received: Final = ZCLAttributeDef(
            id=0x0103, type=t.uint48_t, access="r"
        )
        current_tier3_summ_delivered: Final = ZCLAttributeDef(
            id=0x0104, type=t.uint48_t, access="r"
        )
        current_tier3_summ_received: Final = ZCLAttributeDef(
            id=0x0105, type=t.uint48_t, access="r"
        )
        current_tier4_summ_delivered: Final = ZCLAttributeDef(
            id=0x0106, type=t.uint48_t, access="r"
        )
        current_tier4_summ_received: Final = ZCLAttributeDef(
            id=0x0107, type=t.uint48_t, access="r"
        )
        current_tier5_summ_delivered: Final = ZCLAttributeDef(
            id=0x0108, type=t.uint48_t, access="r"
        )
        current_tier5_summ_received: Final = ZCLAttributeDef(
            id=0x0109, type=t.uint48_t, access="r"
        )
        current_tier6_summ_delivered: Final = ZCLAttributeDef(
            id=0x010A, type=t.uint48_t, access="r"
        )
        current_tier6_summ_received: Final = ZCLAttributeDef(
            id=0x010B, type=t.uint48_t, access="r"
        )
        current_tier7_summ_delivered: Final = ZCLAttributeDef(
            id=0x010C, type=t.uint48_t, access="r"
        )
        current_tier7_summ_received: Final = ZCLAttributeDef(
            id=0x010D, type=t.uint48_t, access="r"
        )
        current_tier8_summ_delivered: Final = ZCLAttributeDef(
            id=0x010E, type=t.uint48_t, access="r"
        )
        current_tier8_summ_received: Final = ZCLAttributeDef(
            id=0x010F, type=t.uint48_t, access="r"
        )
        current_tier9_summ_delivered: Final = ZCLAttributeDef(
            id=0x0110, type=t.uint48_t, access="r"
        )
        current_tier9_summ_received: Final = ZCLAttributeDef(
            id=0x0111, type=t.uint48_t, access="r"
        )
        current_tier10_summ_delivered: Final = ZCLAttributeDef(
            id=0x0112, type=t.uint48_t, access="r"
        )
        current_tier10_summ_received: Final = ZCLAttributeDef(
            id=0x0113, type=t.uint48_t, access="r"
        )
        current_tier11_summ_delivered: Final = ZCLAttributeDef(
            id=0x0114, type=t.uint48_t, access="r"
        )
        current_tier11_summ_received: Final = ZCLAttributeDef(
            id=0x0115, type=t.uint48_t, access="r"
        )
        current_tier12_summ_delivered: Final = ZCLAttributeDef(
            id=0x0116, type=t.uint48_t, access="r"
        )
        current_tier12_summ_received: Final = ZCLAttributeDef(
            id=0x0117, type=t.uint48_t, access="r"
        )
        current_tier13_summ_delivered: Final = ZCLAttributeDef(
            id=0x0118, type=t.uint48_t, access="r"
        )
        current_tier13_summ_received: Final = ZCLAttributeDef(
            id=0x0119, type=t.uint48_t, access="r"
        )
        current_tier14_summ_delivered: Final = ZCLAttributeDef(
            id=0x011A, type=t.uint48_t, access="r"
        )
        current_tier14_summ_received: Final = ZCLAttributeDef(
            id=0x011B, type=t.uint48_t, access="r"
        )
        current_tier15_summ_delivered: Final = ZCLAttributeDef(
            id=0x011C, type=t.uint48_t, access="r"
        )
        current_tier15_summ_received: Final = ZCLAttributeDef(
            id=0x011D, type=t.uint48_t, access="r"
        )
        status: Final = ZCLAttributeDef(
            id=0x0200, type=MeteringStatus, access="r", mandatory=True
        )
        remaining_battery_life: Final = ZCLAttributeDef(
            id=0x0201, type=t.uint8_t, access="r"
        )
        hours_in_operation: Final = ZCLAttributeDef(
            id=0x0202, type=t.uint24_t, access="r"
        )
        hours_in_fault: Final = ZCLAttributeDef(id=0x0203, type=t.uint24_t, access="r")
        extended_status: Final = ZCLAttributeDef(
            id=0x0204, type=ExtendedStatus, access="r"
        )
        remaining_battery_life_days: Final = ZCLAttributeDef(
            id=0x0205, type=t.uint16_t, access="r"
        )
        current_meter_id: Final = ZCLAttributeDef(id=0x0206, type=t.LVBytes, access="r")
        iambient_consumption_indicator: Final = ZCLAttributeDef(
            id=0x0207, type=AmbientConsumptionIndicator, access="r"
        )
        unit_of_measure: Final = ZCLAttributeDef(
            id=0x0300, type=MeteringUnitofMeasure, access="r", mandatory=True
        )
        multiplier: Final = ZCLAttributeDef(id=0x0301, type=t.uint24_t, access="r")
        divisor: Final = ZCLAttributeDef(id=0x0302, type=t.uint24_t, access="r")

        # This attribute shall be used against the following attributes:
        # • CurrentSummationDelivered
        # • CurrentSummationReceived
        # • SummationDeliveredPerReport
        # • TOU Information attributes
        # • DFTSummation
        # • Block Information attributes
        summation_formatting: Final = ZCLAttributeDef(
            id=0x0303,
            zcl_type=DataTypeId.map8,
            type=NumberFormatting,
            access="r",
            mandatory=True,
        )

        # This attribute shall be used against the following attributes:
        # • CurrentMaxDemandDelivered
        # • CurrentMaxDemandReceived
        # • InstantaneousDemand
        demand_formatting: Final = ZCLAttributeDef(
            id=0x0304, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )

        # This attribute shall be used against the following attributes:
        # • CurrentDayConsumptionDelivered
        # • CurrentDayConsumptionReceived
        # • PreviousDayConsumptionDelivered
        # • PreviousDayConsumptionReceived
        # • CurrentPartialProfileIntervalValue
        # • Intervals
        # • DailyConsumptionTarget
        # • CurrentDayConsumptionDelivered
        # • CurrentDayConsumptionReceived
        # • PreviousDayNConsumptionDelivered
        # • PreviousDayNConsumptionReceived
        # • CurrentWeekConsumptionDelivered
        # • CurrentWeekConsumptionReceived
        # • PreviousWeekNConsumptionDelivered
        # • PreviousWeekNConsumptionReceived
        # • CurrentMonthConsumptionDelivered
        # • CurrentMonthConsumptionReceived
        # • PreviousMonthNConsumptionDelivered
        # • PreviousMonthNConsumptionReceived
        historical_consumption_formatting: Final = ZCLAttributeDef(
            id=0x0305, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )
        metering_device_type: Final = ZCLAttributeDef(
            id=0x0306,
            type=MeteringDeviceType,
            # Note that these values represent an Enumeration, and not an 8-bit bitmap
            # as indicated in the attribute description. For backwards compatibility
            # reasons, the data type has not been changed, though the data itself should
            # be treated like an enum
            zcl_type=DataTypeId.map8,
            access="r",
            mandatory=True,
        )
        site_id: Final = ZCLAttributeDef(
            id=0x0307, type=t.LimitedLVBytes(32), access="r"
        )
        meter_serial_number: Final = ZCLAttributeDef(
            id=0x0308, type=t.LimitedLVBytes(24), access="r"
        )
        energy_carrier_unit_of_measure: Final = ZCLAttributeDef(
            id=0x0309, type=MeteringUnitofMeasure, access="r"
        )
        energy_carrier_summation_formatting: Final = ZCLAttributeDef(
            id=0x030A, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )
        energy_carrier_demand_formatting: Final = ZCLAttributeDef(
            id=0x030B, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )
        temperature_unit_of_measure: Final = ZCLAttributeDef(
            id=0x030C, type=MeteringUnitofMeasure, access="r"
        )

        # This attribute shall be used in relation with the following attributes:
        # • InletTemperature
        # • OutletTemperature
        # • ControlTemperature
        temperature_formatting: Final = ZCLAttributeDef(
            id=0x030D, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )
        module_serial_number: Final = ZCLAttributeDef(
            id=0x030E, type=t.LimitedLVBytes(24), access="r"
        )
        operating_tariff_label_delivered: Final = ZCLAttributeDef(
            id=0x030F, type=t.LimitedLVBytes(24), access="r"
        )
        operating_tariff_label_received: Final = ZCLAttributeDef(
            id=0x0310, type=t.LimitedLVBytes(24), access="r"
        )
        customer_id_number: Final = ZCLAttributeDef(
            id=0x0311, type=t.LimitedLVBytes(24), access="r"
        )
        alternative_unit_of_measure: Final = ZCLAttributeDef(
            id=0x0312, type=MeteringUnitofMeasure, access="r"
        )

        # This attribute shall be used against the following attribute:
        # • AlternativeInstantaneousDemand
        alternative_demand_formatting: Final = ZCLAttributeDef(
            id=0x0313, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )
        # This attribute shall be used against the following attributes:
        # • CurrentDayAlternativeConsumptionDelivered
        # • CurrentDayAlternativeConsumptionReceived
        # • PreviousDayAlternativeConsumptionDelivered
        # • PreviousDayAlternativeConsumptionReceived
        # • CurrentAlternativePartialProfileIntervalValue
        # • PreviousDayNAlternativeConsumptionDelivered
        # • PreviousDayNAlternativeConsumptionReceived
        # • CurrentWeekAlternativeConsumptionDelivered
        # • CurrentWeekAlternativeConsumptionReceived
        # • PreviousWeekNAlternativeConsumptionDelivered
        # • PreviousWeekNAlternativeConsumptionReceived
        # • CurrentMonthAlternativeConsumptionDelivered
        # • CurrentMonthAlternativeConsumptionReceived
        # • PreviousMonthNAlternativeConsumptionDelivered
        # • PreviousMonthNAlternativeConsumptionReceived
        alternative_consumption_formatting: Final = ZCLAttributeDef(
            id=0x0314, zcl_type=DataTypeId.map8, type=NumberFormatting, access="r"
        )
        instantaneous_demand: Final = ZCLAttributeDef(
            id=0x0400, type=t.int24s, access="r"
        )
        currentday_consumption_delivered: Final = ZCLAttributeDef(
            id=0x0401, type=t.uint24_t, access="r"
        )
        currentday_consumption_received: Final = ZCLAttributeDef(
            id=0x0402, type=t.uint24_t, access="r"
        )
        previousday_consumption_delivered: Final = ZCLAttributeDef(
            id=0x0403, type=t.uint24_t, access="r"
        )
        previousday_consumption_received: Final = ZCLAttributeDef(
            id=0x0404, type=t.uint24_t, access="r"
        )
        cur_part_profile_int_start_time_delivered: Final = ZCLAttributeDef(
            id=0x0405, type=t.UTCTime, access="r"
        )
        cur_part_profile_int_start_time_received: Final = ZCLAttributeDef(
            id=0x0406, type=t.UTCTime, access="r"
        )
        cur_part_profile_int_value_delivered: Final = ZCLAttributeDef(
            id=0x0407, type=t.uint24_t, access="r"
        )
        cur_part_profile_int_value_received: Final = ZCLAttributeDef(
            id=0x0408, type=t.uint24_t, access="r"
        )
        current_day_max_pressure: Final = ZCLAttributeDef(
            id=0x0409, type=t.uint48_t, access="r"
        )
        current_day_min_pressure: Final = ZCLAttributeDef(
            id=0x040A, type=t.uint48_t, access="r"
        )
        previous_day_max_pressure: Final = ZCLAttributeDef(
            id=0x040B, type=t.uint48_t, access="r"
        )
        previous_day_min_pressure: Final = ZCLAttributeDef(
            id=0x040C, type=t.uint48_t, access="r"
        )
        current_day_max_demand: Final = ZCLAttributeDef(
            id=0x040D, type=t.int24s, access="r"
        )
        previous_day_max_demand: Final = ZCLAttributeDef(
            id=0x040E, type=t.int24s, access="r"
        )
        current_month_max_demand: Final = ZCLAttributeDef(
            id=0x040F, type=t.int24s, access="r"
        )
        current_year_max_demand: Final = ZCLAttributeDef(
            id=0x0410, type=t.int24s, access="r"
        )
        currentday_max_energy_carr_demand: Final = ZCLAttributeDef(
            id=0x0411, type=t.int24s, access="r"
        )
        previousday_max_energy_carr_demand: Final = ZCLAttributeDef(
            id=0x0412, type=t.int24s, access="r"
        )
        cur_month_max_energy_carr_demand: Final = ZCLAttributeDef(
            id=0x0413, type=t.int24s, access="r"
        )
        cur_month_min_energy_carr_demand: Final = ZCLAttributeDef(
            id=0x0414, type=t.int24s, access="r"
        )
        cur_year_max_energy_carr_demand: Final = ZCLAttributeDef(
            id=0x0415, type=t.int24s, access="r"
        )
        cur_year_min_energy_carr_demand: Final = ZCLAttributeDef(
            id=0x0416, type=t.int24s, access="r"
        )
        max_number_of_periods_delivered: Final = ZCLAttributeDef(
            id=0x0500, type=t.uint8_t, access="r"
        )
        current_demand_delivered: Final = ZCLAttributeDef(
            id=0x0600, type=t.uint24_t, access="r"
        )
        demand_limit: Final = ZCLAttributeDef(id=0x0601, type=t.uint24_t, access="r")
        demand_integration_period: Final = ZCLAttributeDef(
            id=0x0602, type=t.uint8_t, access="r"
        )
        number_of_demand_subintervals: Final = ZCLAttributeDef(
            id=0x0603, type=t.uint8_t, access="r"
        )
        demand_limit_arm_duration: Final = ZCLAttributeDef(
            id=0x0604, type=t.uint16_t, access="r"
        )
        generic_alarm_mask: Final = ZCLAttributeDef(
            id=0x0800, type=GenericAlarmMask, access="rw"
        )
        electricity_alarm_mask: Final = ZCLAttributeDef(
            id=0x0801, type=ElectricityAlarmMask, access="rw"
        )
        gen_flow_pressure_alarm_mask: Final = ZCLAttributeDef(
            id=0x0802, type=GenericFlowPressureAlarmMask, access="rw"
        )
        water_specific_alarm_mask: Final = ZCLAttributeDef(
            id=0x0803, type=WaterSpecificAlarmMask, access="rw"
        )
        heat_cool_specific_alarm_mask: Final = ZCLAttributeDef(
            id=0x0804, type=HeatCoolingSpecificAlarmMask, access="rw"
        )
        gas_specific_alarm_mask: Final = ZCLAttributeDef(
            id=0x0805, type=GasSpecificAlarmMask, access="rw"
        )
        extended_generic_alarm_mask: Final = ZCLAttributeDef(
            id=0x0806, type=ExtendedGenericAlarmMask, access="rw"
        )
        manufacture_alarm_mask: Final = ZCLAttributeDef(
            id=0x0807, type=ManufacturerAlarmMask, access="rw"
        )
        bill_to_date: Final = ZCLAttributeDef(id=0x0A00, type=t.uint32_t, access="r")
        bill_to_date_time_stamp: Final = ZCLAttributeDef(
            id=0x0A01, type=t.UTCTime, access="r"
        )
        projected_bill: Final = ZCLAttributeDef(id=0x0A02, type=t.uint32_t, access="r")
        projected_bill_time_stamp: Final = ZCLAttributeDef(
            id=0x0A03, type=t.UTCTime, access="r"
        )

    class ServerCommandDefs(BaseCommandDefs):
        get_profile: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "interval_channel": t.uint8_t,
                "end_time": t.UTCTime,
                "number_of_periods": t.uint8_t,
            },
        )
        request_mirror_response: Final = ZCLCommandDef(
            id=0x01,
            schema={"endpoint_id": t.uint16_t},
        )
        mirror_removed: Final = ZCLCommandDef(
            id=0x02,
            schema={"removed_endpoint_id": t.uint16_t},
        )
        request_fast_poll_mode: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "fast_poll_update_period": t.uint8_t,
                "duration": t.uint8_t,
            },
        )
        schedule_snapshot: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "issuer_event_id": t.uint32_t,
                "command_index": t.uint8_t,
                "total_number_of_commands": t.uint8_t,
                "snapshot_schedule_payload": t.LVBytes,
            },
        )
        take_snapshot: Final = ZCLCommandDef(
            id=0x05,
            schema={"snapshot_cause": SnapshotCause},
        )
        get_snapshot: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "earliest_start_time": t.UTCTime,
                "latest_end_time": t.UTCTime,
                "snapshot_offset": t.uint8_t,
                "snapshot_cause": SnapshotCause,
            },
        )
        start_sampling: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "issuer_event_id": t.uint32_t,
                "start_sampling_time": t.UTCTime,
                "sample_type": t.uint8_t,
                "sample_request_interval": t.uint16_t,
                "max_number_of_samples": t.uint16_t,
            },
        )
        get_sampled_data: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "sample_id": t.uint16_t,
                "earliest_sample_time": t.UTCTime,
                "sample_type": t.uint8_t,
                "number_of_samples": t.uint16_t,
            },
        )
        mirror_report_attribute_response: Final = ZCLCommandDef(
            id=0x09,
            schema={
                "notification_scheme": t.uint8_t,
                "notification_flags": t.LVBytes,
            },
        )
        reset_load_limit_counter: Final = ZCLCommandDef(
            id=0x0A,
            schema={
                "provider_id": t.uint32_t,
                "issuer_event_id": t.uint32_t,
            },
        )
        change_supply: Final = ZCLCommandDef(
            id=0x0B,
            schema={
                "provider_id": t.uint32_t,
                "issuer_event_id": t.uint32_t,
                "request_date_time": t.UTCTime,
                "implementation_date_time": t.UTCTime,
                "proposed_supply_status": t.uint8_t,
                "supply_control_bits": t.bitmap8,
            },
        )
        local_change_supply: Final = ZCLCommandDef(
            id=0x0C,
            schema={"proposed_supply_status": t.uint8_t},
        )
        set_supply_status: Final = ZCLCommandDef(
            id=0x0D,
            schema={
                "issuer_event_id": t.uint32_t,
                "supply_tamper_state": t.uint8_t,
                "supply_depletion_state": t.uint8_t,
                "supply_uncontrolled_flow_state": t.uint8_t,
                "load_limit_supply_state": t.uint8_t,
            },
        )
        set_uncontrolled_flow_threshold: Final = ZCLCommandDef(
            id=0x0E,
            schema={
                "provider_id": t.uint32_t,
                "issuer_event_id": t.uint32_t,
                "uncontrolled_flow_threshold": t.uint16_t,
                "unit_of_measure": t.uint8_t,
                "multiplier": t.uint16_t,
                "divisor": t.uint16_t,
                "stabilisation_period": t.uint8_t,
                "measurement_period": t.uint16_t,
            },
        )

    class ClientCommandDefs(BaseCommandDefs):
        get_profile_response: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "end_time": t.UTCTime,
                "status": t.uint8_t,
                "profile_interval_period": t.uint8_t,
                "number_of_periods_delivered": t.uint8_t,
                "intervals": t.LVBytes,
            },
        )
        request_mirror: Final = ZCLCommandDef(id=0x01, schema={})
        remove_mirror: Final = ZCLCommandDef(id=0x02, schema={})
        request_fast_poll_mode_response: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "applied_update_period": t.uint8_t,
                "fast_poll_mode_end_time": t.UTCTime,
            },
        )
        schedule_snapshot_response: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "issuer_event_id": t.uint32_t,
                "snapshot_response_payload": t.LVBytes,
            },
        )
        take_snapshot_response: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "snapshot_id": t.uint32_t,
                "snapshot_confirmation": t.uint8_t,
            },
        )
        publish_snapshot: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "snapshot_id": t.uint32_t,
                "snapshot_time": t.UTCTime,
                "total_snapshots_found": t.uint8_t,
                "command_index": t.uint8_t,
                "total_number_of_commands": t.uint8_t,
                "snapshot_cause": SnapshotCause,
                "snapshot_payload_type": t.uint8_t,
                "snapshot_payload": t.LVBytes,
            },
        )
        get_sampled_data_response: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "sample_id": t.uint16_t,
                "sample_start_time": t.UTCTime,
                "sample_type": t.uint8_t,
                "sample_request_interval": t.uint16_t,
                "number_of_samples": t.uint16_t,
                "samples": t.LVBytes,
            },
        )
        configure_mirror: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "issuer_event_id": t.uint32_t,
                "reporting_interval": t.uint24_t,
                "mirror_notification_reporting": t.Bool,
                "notification_scheme": t.uint8_t,
            },
        )
        configure_notification_scheme: Final = ZCLCommandDef(
            id=0x09,
            schema={
                "issuer_event_id": t.uint32_t,
                "notification_scheme": t.uint8_t,
                "notification_flag_order": t.bitmap32,
            },
        )
        configure_notification_flag: Final = ZCLCommandDef(
            id=0x0A,
            schema={
                "issuer_event_id": t.uint32_t,
                "notification_scheme": t.uint8_t,
                "notification_flag_attribute_id": t.uint16_t,
                "cluster_id": t.uint16_t,
                "manufacturer_code": t.uint16_t,
                "number_of_commands": t.uint8_t,
                "command_ids": t.LVBytes,
            },
        )
        get_notified_message: Final = ZCLCommandDef(
            id=0x0B,
            schema={
                "notification_scheme": t.uint8_t,
                "notification_flag_attribute_id": t.uint16_t,
                "notification_flags": t.bitmap32,
            },
        )
        supply_status_response: Final = ZCLCommandDef(
            id=0x0C,
            schema={
                "provider_id": t.uint32_t,
                "issuer_event_id": t.uint32_t,
                "implementation_date_time": t.UTCTime,
                "supply_status": t.uint8_t,
            },
        )
        start_sampling_response: Final = ZCLCommandDef(
            id=0x0D,
            schema={"sample_id": t.uint16_t},
        )


class Messaging(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0703
    ep_attribute: Final = "smartenergy_messaging"


class Tunneling(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0704
    ep_attribute: Final = "smartenergy_tunneling"


class Prepayment(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0705
    ep_attribute: Final = "smartenergy_prepayment"


class EnergyManagement(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0706
    ep_attribute: Final = "smartenergy_energy_management"


class Calendar(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0707
    ep_attribute: Final = "smartenergy_calendar"


class DeviceManagement(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0708
    ep_attribute: Final = "smartenergy_device_management"


class Events(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0709
    ep_attribute: Final = "smartenergy_events"


class MduPairing(Cluster):
    cluster_id: Final[t.uint16_t] = 0x070A
    ep_attribute: Final = "smartenergy_mdu_pairing"


class KeyEstablishment(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0800
    ep_attribute: Final = "smartenergy_key_establishment"
