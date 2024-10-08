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


class Metering(Cluster):
    RegisteredTier: Final = RegisteredTier

    cluster_id: Final[t.uint16_t] = 0x0702
    ep_attribute: Final = "smartenergy_metering"

    class AttributeDefs(BaseAttributeDefs):
        current_summ_delivered: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint48_t, access="r"
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
        current_block_period_consump_delivered: Final = ZCLAttributeDef(
            id=0x000C, type=t.uint48_t, access="r"
        )
        daily_consump_target: Final = ZCLAttributeDef(
            id=0x000D, type=t.uint24_t, access="r"
        )
        current_block: Final = ZCLAttributeDef(id=0x000E, type=t.enum8, access="r")
        profile_interval_period: Final = ZCLAttributeDef(
            id=0x000F, type=t.enum8, access="r"
        )
        # 0x0010: ('interval_read_reporting_period', UNKNOWN), # Deprecated
        preset_reading_time: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint16_t, access="r"
        )
        volume_per_report: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint16_t, access="r"
        )
        flow_restriction: Final = ZCLAttributeDef(id=0x0013, type=t.uint8_t, access="r")
        supply_status: Final = ZCLAttributeDef(id=0x0014, type=t.enum8, access="r")
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
        current_block_period_consump_received: Final = ZCLAttributeDef(
            id=0x001D, type=t.uint48_t, access="r"
        )
        current_block_received: Final = ZCLAttributeDef(
            id=0x001E, type=t.uint48_t, access="r"
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
        status: Final = ZCLAttributeDef(id=0x0200, type=t.bitmap8, access="r")
        remaining_battery_life: Final = ZCLAttributeDef(
            id=0x0201, type=t.uint8_t, access="r"
        )
        hours_in_operation: Final = ZCLAttributeDef(
            id=0x0202, type=t.uint24_t, access="r"
        )
        hours_in_fault: Final = ZCLAttributeDef(id=0x0203, type=t.uint24_t, access="r")
        extended_status: Final = ZCLAttributeDef(id=0x0204, type=t.bitmap64, access="r")
        remaining_battery_life_days: Final = ZCLAttributeDef(
            id=0x0205, type=t.uint16_t, access="r"
        )
        current_meter_id: Final = ZCLAttributeDef(id=0x0206, type=t.LVBytes, access="r")
        iambient_consumption_indicator: Final = ZCLAttributeDef(
            id=0x0207, type=t.enum8, access="r"
        )
        unit_of_measure: Final = ZCLAttributeDef(id=0x0300, type=t.enum8, access="r")
        multiplier: Final = ZCLAttributeDef(id=0x0301, type=t.uint24_t, access="r")
        divisor: Final = ZCLAttributeDef(id=0x0302, type=t.uint24_t, access="r")
        summation_formatting: Final = ZCLAttributeDef(
            id=0x0303, type=t.bitmap8, access="r"
        )
        demand_formatting: Final = ZCLAttributeDef(
            id=0x0304, type=t.bitmap8, access="r"
        )
        historical_consump_formatting: Final = ZCLAttributeDef(
            id=0x0305, type=t.bitmap8, access="r"
        )
        metering_device_type: Final = ZCLAttributeDef(
            id=0x0306, type=t.bitmap8, access="r"
        )
        site_id: Final = ZCLAttributeDef(
            id=0x0307, type=t.LimitedLVBytes(32), access="r"
        )
        meter_serial_number: Final = ZCLAttributeDef(
            id=0x0308, type=t.LimitedLVBytes(24), access="r"
        )
        energy_carrier_unit_of_meas: Final = ZCLAttributeDef(
            id=0x0309, type=t.enum8, access="r"
        )
        energy_carrier_summ_formatting: Final = ZCLAttributeDef(
            id=0x030A, type=t.bitmap8, access="r"
        )
        energy_carrier_demand_formatting: Final = ZCLAttributeDef(
            id=0x030B, type=t.bitmap8, access="r"
        )
        temperature_unit_of_measure: Final = ZCLAttributeDef(
            id=0x030C, type=t.enum8, access="r"
        )
        temperature_formatting: Final = ZCLAttributeDef(
            id=0x030D, type=t.bitmap8, access="r"
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
            id=0x0312, type=t.enum8, access="r"
        )
        alternative_demand_formatting: Final = ZCLAttributeDef(
            id=0x0313, type=t.bitmap8, access="r"
        )
        alternative_consumption_formatting: Final = ZCLAttributeDef(
            id=0x0314, type=t.bitmap8, access="r"
        )
        instantaneous_demand: Final = ZCLAttributeDef(
            id=0x0400, type=t.int24s, access="r"
        )
        currentday_consump_delivered: Final = ZCLAttributeDef(
            id=0x0401, type=t.uint24_t, access="r"
        )
        currentday_consump_received: Final = ZCLAttributeDef(
            id=0x0402, type=t.uint24_t, access="r"
        )
        previousday_consump_delivered: Final = ZCLAttributeDef(
            id=0x0403, type=t.uint24_t, access="r"
        )
        previousday_consump_received: Final = ZCLAttributeDef(
            id=0x0404, type=t.uint24_t, access="r"
        )
        cur_part_profile_int_start_time_delivered: Final = ZCLAttributeDef(
            id=0x0405, type=t.uint32_t, access="r"
        )
        cur_part_profile_int_start_time_received: Final = ZCLAttributeDef(
            id=0x0406, type=t.uint32_t, access="r"
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
            id=0x0800, type=t.bitmap16, access="r"
        )
        electricity_alarm_mask: Final = ZCLAttributeDef(
            id=0x0801, type=t.bitmap32, access="r"
        )
        gen_flow_pressure_alarm_mask: Final = ZCLAttributeDef(
            id=0x0802, type=t.bitmap16, access="r"
        )
        water_specific_alarm_mask: Final = ZCLAttributeDef(
            id=0x0803, type=t.bitmap16, access="r"
        )
        heat_cool_specific_alarm_mask: Final = ZCLAttributeDef(
            id=0x0804, type=t.bitmap16, access="r"
        )
        gas_specific_alarm_mask: Final = ZCLAttributeDef(
            id=0x0805, type=t.bitmap16, access="r"
        )
        extended_generic_alarm_mask: Final = ZCLAttributeDef(
            id=0x0806, type=t.bitmap48, access="r"
        )
        manufacture_alarm_mask: Final = ZCLAttributeDef(
            id=0x0807, type=t.bitmap16, access="r"
        )
        bill_to_date: Final = ZCLAttributeDef(id=0x0A00, type=t.uint32_t, access="r")
        bill_to_date_time_stamp: Final = ZCLAttributeDef(
            id=0x0A01, type=t.uint32_t, access="r"
        )
        projected_bill: Final = ZCLAttributeDef(id=0x0A02, type=t.uint32_t, access="r")
        projected_bill_time_stamp: Final = ZCLAttributeDef(
            id=0x0A03, type=t.uint32_t, access="r"
        )

    class ServerCommandDefs(BaseCommandDefs):
        get_profile: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Client_to_Server
        )
        req_mirror: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        mirror_rem: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        req_fast_poll_mode: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Client_to_Server
        )
        get_snapshot: Final = ZCLCommandDef(
            id=0x04, schema={}, direction=Direction.Client_to_Server
        )
        take_snapshot: Final = ZCLCommandDef(
            id=0x05, schema={}, direction=Direction.Client_to_Server
        )
        mirror_report_attr_response: Final = ZCLCommandDef(
            id=0x06, schema={}, direction=Direction.Server_to_Client
        )

    class ClientCommandDefs(BaseCommandDefs):
        get_profile_response: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Server_to_Client
        )
        req_mirror_response: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Server_to_Client
        )
        mirror_rem_response: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Server_to_Client
        )
        req_fast_poll_mode_response: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Server_to_Client
        )
        get_snapshot_response: Final = ZCLCommandDef(
            id=0x04, schema={}, direction=Direction.Server_to_Client
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
