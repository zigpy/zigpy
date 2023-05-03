from __future__ import annotations
from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class Price(Cluster):
    cluster_id: Final[int] = 0x0700
    ep_attribute: Final[str] = "smartenergy_price"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Drlc(Cluster):
    cluster_id: Final[int] = 0x0701
    ep_attribute: Final[str] = "smartenergy_drlc"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Metering(Cluster):
    CURRENT_SUMM_DELIVERED: Final[str] = "current_summ_delivered"
    CURRENT_SUMM_RECEIVED: Final[str] = "current_summ_received"
    CURRENT_MAX_DEMAND_DELIVERED: Final[str] = "current_max_demand_delivered"
    CURRENT_MAX_DEMAND_RECEIVED: Final[str] = "current_max_demand_received"
    DFT_SUMM: Final[str] = "dft_summ"
    DAILY_FREEZE_TIME: Final[str] = "daily_freeze_time"
    POWER_FACTOR: Final[str] = "power_factor"
    READING_SNAPSHOT_TIME: Final[str] = "reading_snapshot_time"
    CURRENT_MAX_DEMAND_DELIVERED_TIME: Final[str] = "current_max_demand_delivered_time"
    CURRENT_MAX_DEMAND_RECEIVED_TIME: Final[str] = "current_max_demand_received_time"
    DEFAULT_UPDATE_PERIOD: Final[str] = "default_update_period"
    FAST_POLL_UPDATE_PERIOD: Final[str] = "fast_poll_update_period"
    CURRENT_BLOCK_PERIOD_CONSUMP_DELIVERED: Final[
        str
    ] = "current_block_period_consump_delivered"
    DAILY_CONSUMP_TARGET: Final[str] = "daily_consump_target"
    CURRENT_BLOCK: Final[str] = "current_block"
    PROFILE_INTERVAL_PERIOD: Final[str] = "profile_interval_period"
    PRESET_READING_TIME: Final[str] = "preset_reading_time"
    VOLUME_PER_REPORT: Final[str] = "volume_per_report"
    FLOW_RESTRICTION: Final[str] = "flow_restriction"
    SUPPLY_STATUS: Final[str] = "supply_status"
    CURRENT_IN_ENERGY_CARRIER_SUMM: Final[str] = "current_in_energy_carrier_summ"
    CURRENT_OUT_ENERGY_CARRIER_SUMM: Final[str] = "current_out_energy_carrier_summ"
    INLET_TEMPERATURE: Final[str] = "inlet_temperature"
    OUTLET_TEMPERATURE: Final[str] = "outlet_temperature"
    CONTROL_TEMPERATURE: Final[str] = "control_temperature"
    CURRENT_IN_ENERGY_CARRIER_DEMAND: Final[str] = "current_in_energy_carrier_demand"
    CURRENT_OUT_ENERGY_CARRIER_DEMAND: Final[str] = "current_out_energy_carrier_demand"
    CURRENT_BLOCK_PERIOD_CONSUMP_RECEIVED: Final[
        str
    ] = "current_block_period_consump_received"
    CURRENT_BLOCK_RECEIVED: Final[str] = "current_block_received"
    DFT_SUMMATION_RECEIVED: Final[str] = "dft_summation_received"
    ACTIVE_REGISTER_TIER_DELIVERED: Final[str] = "active_register_tier_delivered"
    ACTIVE_REGISTER_TIER_RECEIVED: Final[str] = "active_register_tier_received"
    LAST_BLOCK_SWITCH_TIME: Final[str] = "last_block_switch_time"
    CURRENT_TIER1_SUMM_DELIVERED: Final[str] = "current_tier1_summ_delivered"
    CURRENT_TIER1_SUMM_RECEIVED: Final[str] = "current_tier1_summ_received"
    CURRENT_TIER2_SUMM_DELIVERED: Final[str] = "current_tier2_summ_delivered"
    CURRENT_TIER2_SUMM_RECEIVED: Final[str] = "current_tier2_summ_received"
    CURRENT_TIER3_SUMM_DELIVERED: Final[str] = "current_tier3_summ_delivered"
    CURRENT_TIER3_SUMM_RECEIVED: Final[str] = "current_tier3_summ_received"
    CURRENT_TIER4_SUMM_DELIVERED: Final[str] = "current_tier4_summ_delivered"
    CURRENT_TIER4_SUMM_RECEIVED: Final[str] = "current_tier4_summ_received"
    CURRENT_TIER5_SUMM_DELIVERED: Final[str] = "current_tier5_summ_delivered"
    CURRENT_TIER5_SUMM_RECEIVED: Final[str] = "current_tier5_summ_received"
    CURRENT_TIER6_SUMM_DELIVERED: Final[str] = "current_tier6_summ_delivered"
    CURRENT_TIER6_SUMM_RECEIVED: Final[str] = "current_tier6_summ_received"
    CURRENT_TIER7_SUMM_DELIVERED: Final[str] = "current_tier7_summ_delivered"
    CURRENT_TIER7_SUMM_RECEIVED: Final[str] = "current_tier7_summ_received"
    CURRENT_TIER8_SUMM_DELIVERED: Final[str] = "current_tier8_summ_delivered"
    CURRENT_TIER8_SUMM_RECEIVED: Final[str] = "current_tier8_summ_received"
    CURRENT_TIER9_SUMM_DELIVERED: Final[str] = "current_tier9_summ_delivered"
    CURRENT_TIER9_SUMM_RECEIVED: Final[str] = "current_tier9_summ_received"
    CURRENT_TIER10_SUMM_DELIVERED: Final[str] = "current_tier10_summ_delivered"
    CURRENT_TIER10_SUMM_RECEIVED: Final[str] = "current_tier10_summ_received"
    CURRENT_TIER11_SUMM_DELIVERED: Final[str] = "current_tier11_summ_delivered"
    CURRENT_TIER11_SUMM_RECEIVED: Final[str] = "current_tier11_summ_received"
    CURRENT_TIER12_SUMM_DELIVERED: Final[str] = "current_tier12_summ_delivered"
    CURRENT_TIER12_SUMM_RECEIVED: Final[str] = "current_tier12_summ_received"
    CURRENT_TIER13_SUMM_DELIVERED: Final[str] = "current_tier13_summ_delivered"
    CURRENT_TIER13_SUMM_RECEIVED: Final[str] = "current_tier13_summ_received"
    CURRENT_TIER14_SUMM_DELIVERED: Final[str] = "current_tier14_summ_delivered"
    CURRENT_TIER14_SUMM_RECEIVED: Final[str] = "current_tier14_summ_received"
    CURRENT_TIER15_SUMM_DELIVERED: Final[str] = "current_tier15_summ_delivered"
    CURRENT_TIER15_SUMM_RECEIVED: Final[str] = "current_tier15_summ_received"
    STATUS: Final[str] = "status"
    REMAINING_BATTERY_LIFE: Final[str] = "remaining_battery_life"
    HOURS_IN_OPERATION: Final[str] = "hours_in_operation"
    HOURS_IN_FAULT: Final[str] = "hours_in_fault"
    EXTENDED_STATUS: Final[str] = "extended_status"
    REMAINING_BATTERY_LIFE_DAYS: Final[str] = "remaining_battery_life_days"
    CURRENT_METER_ID: Final[str] = "current_meter_id"
    IAMBIENT_CONSUMPTION_INDICATOR: Final[str] = "iambient_consumption_indicator"
    UNIT_OF_MEASURE: Final[str] = "unit_of_measure"
    MULTIPLIER: Final[str] = "multiplier"
    DIVISOR: Final[str] = "divisor"
    SUMMATION_FORMATTING: Final[str] = "summation_formatting"
    DEMAND_FORMATTING: Final[str] = "demand_formatting"
    HISTORICAL_CONSUMP_FORMATTING: Final[str] = "historical_consump_formatting"
    METERING_DEVICE_TYPE: Final[str] = "metering_device_type"
    SITE_ID: Final[str] = "site_id"
    METER_SERIAL_NUMBER: Final[str] = "meter_serial_number"
    ENERGY_CARRIER_UNIT_OF_MEAS: Final[str] = "energy_carrier_unit_of_meas"
    ENERGY_CARRIER_SUMM_FORMATTING: Final[str] = "energy_carrier_summ_formatting"
    ENERGY_CARRIER_DEMAND_FORMATTING: Final[str] = "energy_carrier_demand_formatting"
    TEMPERATURE_UNIT_OF_MEASURE: Final[str] = "temperature_unit_of_measure"
    TEMPERATURE_FORMATTING: Final[str] = "temperature_formatting"
    MODULE_SERIAL_NUMBER: Final[str] = "module_serial_number"
    OPERATING_TARIFF_LABEL_DELIVERED: Final[str] = "operating_tariff_label_delivered"
    OPERATING_TARIFF_LABEL_RECEIVED: Final[str] = "operating_tariff_label_received"
    CUSTOMER_ID_NUMBER: Final[str] = "customer_id_number"
    ALTERNATIVE_UNIT_OF_MEASURE: Final[str] = "alternative_unit_of_measure"
    ALTERNATIVE_DEMAND_FORMATTING: Final[str] = "alternative_demand_formatting"
    ALTERNATIVE_CONSUMPTION_FORMATTING: Final[
        str
    ] = "alternative_consumption_formatting"
    INSTANTANEOUS_DEMAND: Final[str] = "instantaneous_demand"
    CURRENTDAY_CONSUMP_DELIVERED: Final[str] = "currentday_consump_delivered"
    CURRENTDAY_CONSUMP_RECEIVED: Final[str] = "currentday_consump_received"
    PREVIOUSDAY_CONSUMP_DELIVERED: Final[str] = "previousday_consump_delivered"
    PREVIOUSDAY_CONSUMP_RECEIVED: Final[str] = "previousday_consump_received"
    CUR_PART_PROFILE_INT_START_TIME_DELIVERED: Final[
        str
    ] = "cur_part_profile_int_start_time_delivered"
    CUR_PART_PROFILE_INT_START_TIME_RECEIVED: Final[
        str
    ] = "cur_part_profile_int_start_time_received"
    CUR_PART_PROFILE_INT_VALUE_DELIVERED: Final[
        str
    ] = "cur_part_profile_int_value_delivered"
    CUR_PART_PROFILE_INT_VALUE_RECEIVED: Final[
        str
    ] = "cur_part_profile_int_value_received"
    CURRENT_DAY_MAX_PRESSURE: Final[str] = "current_day_max_pressure"
    CURRENT_DAY_MIN_PRESSURE: Final[str] = "current_day_min_pressure"
    PREVIOUS_DAY_MAX_PRESSURE: Final[str] = "previous_day_max_pressure"
    PREVIOUS_DAY_MIN_PRESSURE: Final[str] = "previous_day_min_pressure"
    CURRENT_DAY_MAX_DEMAND: Final[str] = "current_day_max_demand"
    PREVIOUS_DAY_MAX_DEMAND: Final[str] = "previous_day_max_demand"
    CURRENT_MONTH_MAX_DEMAND: Final[str] = "current_month_max_demand"
    CURRENT_YEAR_MAX_DEMAND: Final[str] = "current_year_max_demand"
    CURRENTDAY_MAX_ENERGY_CARR_DEMAND: Final[str] = "currentday_max_energy_carr_demand"
    PREVIOUSDAY_MAX_ENERGY_CARR_DEMAND: Final[
        str
    ] = "previousday_max_energy_carr_demand"
    CUR_MONTH_MAX_ENERGY_CARR_DEMAND: Final[str] = "cur_month_max_energy_carr_demand"
    CUR_MONTH_MIN_ENERGY_CARR_DEMAND: Final[str] = "cur_month_min_energy_carr_demand"
    CUR_YEAR_MAX_ENERGY_CARR_DEMAND: Final[str] = "cur_year_max_energy_carr_demand"
    CUR_YEAR_MIN_ENERGY_CARR_DEMAND: Final[str] = "cur_year_min_energy_carr_demand"
    MAX_NUMBER_OF_PERIODS_DELIVERED: Final[str] = "max_number_of_periods_delivered"
    CURRENT_DEMAND_DELIVERED: Final[str] = "current_demand_delivered"
    DEMAND_LIMIT: Final[str] = "demand_limit"
    DEMAND_INTEGRATION_PERIOD: Final[str] = "demand_integration_period"
    NUMBER_OF_DEMAND_SUBINTERVALS: Final[str] = "number_of_demand_subintervals"
    DEMAND_LIMIT_ARM_DURATION: Final[str] = "demand_limit_arm_duration"
    GENERIC_ALARM_MASK: Final[str] = "generic_alarm_mask"
    ELECTRICITY_ALARM_MASK: Final[str] = "electricity_alarm_mask"
    GEN_FLOW_PRESSURE_ALARM_MASK: Final[str] = "gen_flow_pressure_alarm_mask"
    WATER_SPECIFIC_ALARM_MASK: Final[str] = "water_specific_alarm_mask"
    HEAT_COOL_SPECIFIC_ALARM_MASK: Final[str] = "heat_cool_specific_alarm_mask"
    GAS_SPECIFIC_ALARM_MASK: Final[str] = "gas_specific_alarm_mask"
    EXTENDED_GENERIC_ALARM_MASK: Final[str] = "extended_generic_alarm_mask"
    MANUFACTURE_ALARM_MASK: Final[str] = "manufacture_alarm_mask"
    BILL_TO_DATE: Final[str] = "bill_to_date"
    BILL_TO_DATE_TIME_STAMP: Final[str] = "bill_to_date_time_stamp"
    PROJECTED_BILL: Final[str] = "projected_bill"
    PROJECTED_BILL_TIME_STAMP: Final[str] = "projected_bill_time_stamp"

    GET_PROFILE: Final[str] = "get_profile"
    REQ_MIRROR: Final[str] = "req_mirror"
    MIRROR_REM: Final[str] = "mirror_rem"
    REQ_FAST_POLL_MODE: Final[str] = "req_fast_poll_mode"
    GET_SNAPSHOT: Final[str] = "get_snapshot"
    TAKE_SNAPSHOT: Final[str] = "take_snapshot"
    MIRROR_REPORT_ATTR_RESPONSE: Final[str] = "mirror_report_attr_response"

    GET_PROFILE_RESPONSE: Final[str] = "get_profile_response"
    REQ_MIRROR_RESPONSE: Final[str] = "req_mirror_response"
    MIRROR_REM_RESPONSE: Final[str] = "mirror_rem_response"
    REQ_FAST_POLL_MODE_RESPONSE: Final[str] = "req_fast_poll_mode_response"
    GET_SNAPSHOT_RESPONSE: Final[str] = "get_snapshot_response"

    cluster_id: Final[int] = 0x0702
    ep_attribute: Final[str] = "smartenergy_metering"

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

    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef(CURRENT_SUMM_DELIVERED, type=t.uint48_t, access="r"),
        0x0001: ZCLAttributeDef(CURRENT_SUMM_RECEIVED, type=t.uint48_t, access="r"),
        0x0002: ZCLAttributeDef(
            CURRENT_MAX_DEMAND_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0003: ZCLAttributeDef(
            CURRENT_MAX_DEMAND_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0004: ZCLAttributeDef(DFT_SUMM, type=t.uint48_t, access="r"),
        0x0005: ZCLAttributeDef(DAILY_FREEZE_TIME, type=t.uint16_t, access="r"),
        0x0006: ZCLAttributeDef(POWER_FACTOR, type=t.int8s, access="r"),
        0x0007: ZCLAttributeDef(READING_SNAPSHOT_TIME, type=t.UTCTime, access="r"),
        0x0008: ZCLAttributeDef(
            CURRENT_MAX_DEMAND_DELIVERED_TIME, type=t.UTCTime, access="r"
        ),
        0x0009: ZCLAttributeDef(
            CURRENT_MAX_DEMAND_RECEIVED_TIME, type=t.UTCTime, access="r"
        ),
        0x000A: ZCLAttributeDef(DEFAULT_UPDATE_PERIOD, type=t.uint8_t, access="r"),
        0x000B: ZCLAttributeDef(FAST_POLL_UPDATE_PERIOD, type=t.uint8_t, access="r"),
        0x000C: ZCLAttributeDef(
            CURRENT_BLOCK_PERIOD_CONSUMP_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x000D: ZCLAttributeDef(DAILY_CONSUMP_TARGET, type=t.uint24_t, access="r"),
        0x000E: ZCLAttributeDef(CURRENT_BLOCK, type=t.enum8, access="r"),
        0x000F: ZCLAttributeDef(PROFILE_INTERVAL_PERIOD, type=t.enum8, access="r"),
        # 0x0010: ('interval_read_reporting_period', UNKNOWN), # Deprecated
        0x0011: ZCLAttributeDef(PRESET_READING_TIME, type=t.uint16_t, access="r"),
        0x0012: ZCLAttributeDef(VOLUME_PER_REPORT, type=t.uint16_t, access="r"),
        0x0013: ZCLAttributeDef(FLOW_RESTRICTION, type=t.uint8_t, access="r"),
        0x0014: ZCLAttributeDef(SUPPLY_STATUS, type=t.enum8, access="r"),
        0x0015: ZCLAttributeDef(
            CURRENT_IN_ENERGY_CARRIER_SUMM, type=t.uint48_t, access="r"
        ),
        0x0016: ZCLAttributeDef(
            CURRENT_OUT_ENERGY_CARRIER_SUMM, type=t.uint48_t, access="r"
        ),
        0x0017: ZCLAttributeDef(INLET_TEMPERATURE, type=t.int24s, access="r"),
        0x0018: ZCLAttributeDef(OUTLET_TEMPERATURE, type=t.int24s, access="r"),
        0x0019: ZCLAttributeDef(CONTROL_TEMPERATURE, type=t.int24s, access="r"),
        0x001A: ZCLAttributeDef(
            CURRENT_IN_ENERGY_CARRIER_DEMAND, type=t.int24s, access="r"
        ),
        0x001B: ZCLAttributeDef(
            CURRENT_OUT_ENERGY_CARRIER_DEMAND, type=t.int24s, access="r"
        ),
        0x001D: ZCLAttributeDef(
            CURRENT_BLOCK_PERIOD_CONSUMP_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x001E: ZCLAttributeDef(CURRENT_BLOCK_RECEIVED, type=t.uint48_t, access="r"),
        0x001F: ZCLAttributeDef(DFT_SUMMATION_RECEIVED, type=t.uint48_t, access="r"),
        0x0020: ZCLAttributeDef(
            ACTIVE_REGISTER_TIER_DELIVERED, type=RegisteredTier, access="r"
        ),
        0x0021: ZCLAttributeDef(
            ACTIVE_REGISTER_TIER_RECEIVED, type=RegisteredTier, access="r"
        ),
        0x0022: ZCLAttributeDef(LAST_BLOCK_SWITCH_TIME, type=t.UTCTime, access="r"),
        # 0x0100: ('change_reporting_profile', UNKNOWN),
        0x0100: ZCLAttributeDef(
            CURRENT_TIER1_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0101: ZCLAttributeDef(
            CURRENT_TIER1_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0102: ZCLAttributeDef(
            CURRENT_TIER2_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0103: ZCLAttributeDef(
            CURRENT_TIER2_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0104: ZCLAttributeDef(
            CURRENT_TIER3_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0105: ZCLAttributeDef(
            CURRENT_TIER3_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0106: ZCLAttributeDef(
            CURRENT_TIER4_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0107: ZCLAttributeDef(
            CURRENT_TIER4_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0108: ZCLAttributeDef(
            CURRENT_TIER5_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0109: ZCLAttributeDef(
            CURRENT_TIER5_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x010A: ZCLAttributeDef(
            CURRENT_TIER6_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x010B: ZCLAttributeDef(
            CURRENT_TIER6_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x010C: ZCLAttributeDef(
            CURRENT_TIER7_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x010D: ZCLAttributeDef(
            CURRENT_TIER7_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x010E: ZCLAttributeDef(
            CURRENT_TIER8_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x010F: ZCLAttributeDef(
            CURRENT_TIER8_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0110: ZCLAttributeDef(
            CURRENT_TIER9_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0111: ZCLAttributeDef(
            CURRENT_TIER9_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0112: ZCLAttributeDef(
            CURRENT_TIER10_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0113: ZCLAttributeDef(
            CURRENT_TIER10_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0114: ZCLAttributeDef(
            CURRENT_TIER11_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0115: ZCLAttributeDef(
            CURRENT_TIER11_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0116: ZCLAttributeDef(
            CURRENT_TIER12_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0117: ZCLAttributeDef(
            CURRENT_TIER12_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0118: ZCLAttributeDef(
            CURRENT_TIER13_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x0119: ZCLAttributeDef(
            CURRENT_TIER13_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x011A: ZCLAttributeDef(
            CURRENT_TIER14_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x011B: ZCLAttributeDef(
            CURRENT_TIER14_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x011C: ZCLAttributeDef(
            CURRENT_TIER15_SUMM_DELIVERED, type=t.uint48_t, access="r"
        ),
        0x011D: ZCLAttributeDef(
            CURRENT_TIER15_SUMM_RECEIVED, type=t.uint48_t, access="r"
        ),
        0x0200: ZCLAttributeDef(STATUS, type=t.bitmap8, access="r"),
        0x0201: ZCLAttributeDef(REMAINING_BATTERY_LIFE, type=t.uint8_t, access="r"),
        0x0202: ZCLAttributeDef(HOURS_IN_OPERATION, type=t.uint24_t, access="r"),
        0x0203: ZCLAttributeDef(HOURS_IN_FAULT, type=t.uint24_t, access="r"),
        0x0204: ZCLAttributeDef(EXTENDED_STATUS, type=t.bitmap64, access="r"),
        0x0205: ZCLAttributeDef(
            REMAINING_BATTERY_LIFE_DAYS, type=t.uint16_t, access="r"
        ),
        0x0206: ZCLAttributeDef(CURRENT_METER_ID, type=t.LVBytes, access="r"),
        0x0207: ZCLAttributeDef(
            IAMBIENT_CONSUMPTION_INDICATOR, type=t.enum8, access="r"
        ),
        0x0300: ZCLAttributeDef(UNIT_OF_MEASURE, type=t.enum8, access="r"),
        0x0301: ZCLAttributeDef(MULTIPLIER, type=t.uint24_t, access="r"),
        0x0302: ZCLAttributeDef(DIVISOR, type=t.uint24_t, access="r"),
        0x0303: ZCLAttributeDef(SUMMATION_FORMATTING, type=t.bitmap8, access="r"),
        0x0304: ZCLAttributeDef(DEMAND_FORMATTING, type=t.bitmap8, access="r"),
        0x0305: ZCLAttributeDef(
            HISTORICAL_CONSUMP_FORMATTING, type=t.bitmap8, access="r"
        ),
        0x0306: ZCLAttributeDef(METERING_DEVICE_TYPE, type=t.bitmap8, access="r"),
        0x0307: ZCLAttributeDef(SITE_ID, type=t.LimitedLVBytes(32), access="r"),
        0x0308: ZCLAttributeDef(
            METER_SERIAL_NUMBER, type=t.LimitedLVBytes(24), access="r"
        ),
        0x0309: ZCLAttributeDef(ENERGY_CARRIER_UNIT_OF_MEAS, type=t.enum8, access="r"),
        0x030A: ZCLAttributeDef(
            ENERGY_CARRIER_SUMM_FORMATTING, type=t.bitmap8, access="r"
        ),
        0x030B: ZCLAttributeDef(
            ENERGY_CARRIER_DEMAND_FORMATTING, type=t.bitmap8, access="r"
        ),
        0x030C: ZCLAttributeDef(TEMPERATURE_UNIT_OF_MEASURE, type=t.enum8, access="r"),
        0x030D: ZCLAttributeDef(TEMPERATURE_FORMATTING, type=t.bitmap8, access="r"),
        0x030E: ZCLAttributeDef(
            MODULE_SERIAL_NUMBER, type=t.LimitedLVBytes(24), access="r"
        ),
        0x030F: ZCLAttributeDef(
            OPERATING_TARIFF_LABEL_DELIVERED, type=t.LimitedLVBytes(24), access="r"
        ),
        0x0310: ZCLAttributeDef(
            OPERATING_TARIFF_LABEL_RECEIVED, type=t.LimitedLVBytes(24), access="r"
        ),
        0x0311: ZCLAttributeDef(
            CUSTOMER_ID_NUMBER, type=t.LimitedLVBytes(24), access="r"
        ),
        0x0312: ZCLAttributeDef(ALTERNATIVE_UNIT_OF_MEASURE, type=t.enum8, access="r"),
        0x0313: ZCLAttributeDef(
            ALTERNATIVE_DEMAND_FORMATTING, type=t.bitmap8, access="r"
        ),
        0x0314: ZCLAttributeDef(
            ALTERNATIVE_CONSUMPTION_FORMATTING, type=t.bitmap8, access="r"
        ),
        0x0400: ZCLAttributeDef(INSTANTANEOUS_DEMAND, type=t.int24s, access="r"),
        0x0401: ZCLAttributeDef(
            CURRENTDAY_CONSUMP_DELIVERED, type=t.uint24_t, access="r"
        ),
        0x0402: ZCLAttributeDef(
            CURRENTDAY_CONSUMP_RECEIVED, type=t.uint24_t, access="r"
        ),
        0x0403: ZCLAttributeDef(
            PREVIOUSDAY_CONSUMP_DELIVERED, type=t.uint24_t, access="r"
        ),
        0x0404: ZCLAttributeDef(
            PREVIOUSDAY_CONSUMP_RECEIVED, type=t.uint24_t, access="r"
        ),
        0x0405: ZCLAttributeDef(
            CUR_PART_PROFILE_INT_START_TIME_DELIVERED, type=t.uint32_t, access="r"
        ),
        0x0406: ZCLAttributeDef(
            CUR_PART_PROFILE_INT_START_TIME_RECEIVED, type=t.uint32_t, access="r"
        ),
        0x0407: ZCLAttributeDef(
            CUR_PART_PROFILE_INT_VALUE_DELIVERED, type=t.uint24_t, access="r"
        ),
        0x0408: ZCLAttributeDef(
            CUR_PART_PROFILE_INT_VALUE_RECEIVED, type=t.uint24_t, access="r"
        ),
        0x0409: ZCLAttributeDef(CURRENT_DAY_MAX_PRESSURE, type=t.uint48_t, access="r"),
        0x040A: ZCLAttributeDef(CURRENT_DAY_MIN_PRESSURE, type=t.uint48_t, access="r"),
        0x040B: ZCLAttributeDef(PREVIOUS_DAY_MAX_PRESSURE, type=t.uint48_t, access="r"),
        0x040C: ZCLAttributeDef(PREVIOUS_DAY_MIN_PRESSURE, type=t.uint48_t, access="r"),
        0x040D: ZCLAttributeDef(CURRENT_DAY_MAX_DEMAND, type=t.int24s, access="r"),
        0x040E: ZCLAttributeDef(PREVIOUS_DAY_MAX_DEMAND, type=t.int24s, access="r"),
        0x040F: ZCLAttributeDef(CURRENT_MONTH_MAX_DEMAND, type=t.int24s, access="r"),
        0x0410: ZCLAttributeDef(CURRENT_YEAR_MAX_DEMAND, type=t.int24s, access="r"),
        0x0411: ZCLAttributeDef(
            CURRENTDAY_MAX_ENERGY_CARR_DEMAND, type=t.int24s, access="r"
        ),
        0x0412: ZCLAttributeDef(
            PREVIOUSDAY_MAX_ENERGY_CARR_DEMAND, type=t.int24s, access="r"
        ),
        0x0413: ZCLAttributeDef(
            CUR_MONTH_MAX_ENERGY_CARR_DEMAND, type=t.int24s, access="r"
        ),
        0x0414: ZCLAttributeDef(
            CUR_MONTH_MIN_ENERGY_CARR_DEMAND, type=t.int24s, access="r"
        ),
        0x0415: ZCLAttributeDef(
            CUR_YEAR_MAX_ENERGY_CARR_DEMAND, type=t.int24s, access="r"
        ),
        0x0416: ZCLAttributeDef(
            CUR_YEAR_MIN_ENERGY_CARR_DEMAND, type=t.int24s, access="r"
        ),
        0x0500: ZCLAttributeDef(
            MAX_NUMBER_OF_PERIODS_DELIVERED, type=t.uint8_t, access="r"
        ),
        0x0600: ZCLAttributeDef(CURRENT_DEMAND_DELIVERED, type=t.uint24_t, access="r"),
        0x0601: ZCLAttributeDef(DEMAND_LIMIT, type=t.uint24_t, access="r"),
        0x0602: ZCLAttributeDef(DEMAND_INTEGRATION_PERIOD, type=t.uint8_t, access="r"),
        0x0603: ZCLAttributeDef(
            NUMBER_OF_DEMAND_SUBINTERVALS, type=t.uint8_t, access="r"
        ),
        0x0604: ZCLAttributeDef(DEMAND_LIMIT_ARM_DURATION, type=t.uint16_t, access="r"),
        0x0800: ZCLAttributeDef(GENERIC_ALARM_MASK, type=t.bitmap16, access="r"),
        0x0801: ZCLAttributeDef(ELECTRICITY_ALARM_MASK, type=t.bitmap32, access="r"),
        0x0802: ZCLAttributeDef(
            GEN_FLOW_PRESSURE_ALARM_MASK, type=t.bitmap16, access="r"
        ),
        0x0803: ZCLAttributeDef(WATER_SPECIFIC_ALARM_MASK, type=t.bitmap16, access="r"),
        0x0804: ZCLAttributeDef(
            HEAT_COOL_SPECIFIC_ALARM_MASK, type=t.bitmap16, access="r"
        ),
        0x0805: ZCLAttributeDef(GAS_SPECIFIC_ALARM_MASK, type=t.bitmap16, access="r"),
        0x0806: ZCLAttributeDef(
            EXTENDED_GENERIC_ALARM_MASK, type=t.bitmap48, access="r"
        ),
        0x0807: ZCLAttributeDef(MANUFACTURE_ALARM_MASK, type=t.bitmap16, access="r"),
        0x0A00: ZCLAttributeDef(BILL_TO_DATE, type=t.uint32_t, access="r"),
        0x0A01: ZCLAttributeDef(BILL_TO_DATE_TIME_STAMP, type=t.uint32_t, access="r"),
        0x0A02: ZCLAttributeDef(PROJECTED_BILL, type=t.uint32_t, access="r"),
        0x0A03: ZCLAttributeDef(PROJECTED_BILL_TIME_STAMP, type=t.uint32_t, access="r"),
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef(GET_PROFILE, {}, False),
        0x01: ZCLCommandDef(REQ_MIRROR, {}, False),
        0x02: ZCLCommandDef(MIRROR_REM, {}, False),
        0x03: ZCLCommandDef(REQ_FAST_POLL_MODE, {}, False),
        0x04: ZCLCommandDef(GET_SNAPSHOT, {}, False),
        0x05: ZCLCommandDef(TAKE_SNAPSHOT, {}, False),
        0x06: ZCLCommandDef(MIRROR_REPORT_ATTR_RESPONSE, {}, True),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef(GET_PROFILE_RESPONSE, {}, True),
        0x01: ZCLCommandDef(REQ_MIRROR_RESPONSE, {}, True),
        0x02: ZCLCommandDef(MIRROR_REM_RESPONSE, {}, True),
        0x03: ZCLCommandDef(REQ_FAST_POLL_MODE_RESPONSE, {}, True),
        0x04: ZCLCommandDef(GET_SNAPSHOT_RESPONSE, {}, True),
    }


class Messaging(Cluster):
    cluster_id: Final[int] = 0x0703
    ep_attribute: Final[str] = "smartenergy_messaging"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Tunneling(Cluster):
    cluster_id: Final[int] = 0x0704
    ep_attribute: Final[str] = "smartenergy_tunneling"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Prepayment(Cluster):
    cluster_id: Final[int] = 0x0705
    ep_attribute: Final[str] = "smartenergy_prepayment"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class EnergyManagement(Cluster):
    cluster_id: Final[int] = 0x0706
    ep_attribute: Final[str] = "smartenergy_energy_management"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Calendar(Cluster):
    cluster_id: Final[int] = 0x0707
    ep_attribute: Final[str] = "smartenergy_calendar"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class DeviceManagement(Cluster):
    cluster_id: Final[int] = 0x0708
    ep_attribute: Final[str] = "smartenergy_device_management"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Events(Cluster):
    cluster_id: Final[int] = 0x0709
    ep_attribute: Final[str] = "smartenergy_events"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class MduPairing(Cluster):
    cluster_id: Final[int] = 0x070A
    ep_attribute: Final[str] = "smartenergy_mdu_pairing"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class KeyEstablishment(Cluster):
    cluster_id: Final[int] = 0x0800
    ep_attribute: Final[str] = "smartenergy_key_establishment"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
