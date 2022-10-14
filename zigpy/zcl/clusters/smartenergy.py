from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class Price(Cluster):
    cluster_id = 0x0700
    ep_attribute = "smartenergy_price"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Drlc(Cluster):
    cluster_id = 0x0701
    ep_attribute = "smartenergy_drlc"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Metering(Cluster):
    cluster_id = 0x0702
    ep_attribute = "smartenergy_metering"
    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef("current_summ_delivered", type=t.uint48_t, access="r"),
        0x0001: ZCLAttributeDef("current_summ_received", type=t.uint48_t, access="r"),
        0x0002: ZCLAttributeDef(
            "current_max_demand_delivered", type=t.uint48_t, access="r"
        ),
        0x0003: ZCLAttributeDef(
            "current_max_demand_received", type=t.uint48_t, access="r"
        ),
        0x0004: ZCLAttributeDef("dft_summ", type=t.uint48_t, access="r"),
        0x0005: ZCLAttributeDef("daily_freeze_time", type=t.uint16_t, access="r"),
        0x0006: ZCLAttributeDef("power_factor", type=t.int8s, access="r"),
        0x0007: ZCLAttributeDef("reading_snapshot_time", type=t.UTCTime, access="r"),
        0x0008: ZCLAttributeDef(
            "current_max_demand_delivered_time", type=t.UTCTime, access="r"
        ),
        0x0009: ZCLAttributeDef(
            "current_max_demand_received_time", type=t.UTCTime, access="r"
        ),
        0x000A: ZCLAttributeDef("default_update_period", type=t.uint8_t, access="r"),
        0x000B: ZCLAttributeDef("fast_poll_update_period", type=t.uint8_t, access="r"),
        0x000C: ZCLAttributeDef(
            "current_block_period_consump_delivered", type=t.uint48_t, access="r"
        ),
        0x000D: ZCLAttributeDef("daily_consump_target", type=t.uint24_t, access="r"),
        0x000E: ZCLAttributeDef("current_block", type=t.enum8, access="r"),
        0x000F: ZCLAttributeDef("profile_interval_period", type=t.enum8, access="r"),
        # 0x0010: ('interval_read_reporting_period', UNKNOWN),  # Deprecated
        0x0011: ZCLAttributeDef("preset_reading_time", type=t.uint16_t, access="r"),
        0x0012: ZCLAttributeDef("volume_per_report", type=t.uint16_t, access="r"),
        0x0013: ZCLAttributeDef("flow_restriction", type=t.uint8_t, access="r"),
        0x0014: ZCLAttributeDef("supply_status", type=t.enum8, access="r"),
        0x0015: ZCLAttributeDef(
            "current_in_energy_carrier_summ", type=t.uint48_t, access="r"
        ),
        0x0016: ZCLAttributeDef(
            "current_out_energy_carrier_summ", type=t.uint48_t, access="r"
        ),
        0x0017: ZCLAttributeDef("inlet_temperature", type=t.int24s, access="r"),
        0x0018: ZCLAttributeDef("outlet_temperature", type=t.int24s, access="r"),
        0x0019: ZCLAttributeDef("control_temperature", type=t.int24s, access="r"),
        0x001A: ZCLAttributeDef(
            "current_in_energy_carrier_demand", type=t.int24s, access="r"
        ),
        0x001B: ZCLAttributeDef(
            "current_out_energy_carrier_demand", type=t.int24s, access="r"
        ),
        0x001D: ZCLAttributeDef(
            "current_block_period_consump_received", type=t.uint48_t, access="r"
        ),
        0x001E: ZCLAttributeDef("current_block_received", type=t.uint48_t, access="r"),
        0x001F: ZCLAttributeDef("dft_summation_received", type=t.uint48_t, access="r"),
        0x0020: ZCLAttributeDef(
            "active_register_tier_delivered", type=t.enum8, access="r"
        ),
        0x0021: ZCLAttributeDef(
            "active_register_tier_received", type=t.enum8, access="r"
        ),
        0x0022: ZCLAttributeDef("last_block_switch_time", type=t.UTCTime, access="r"),
        # 0x0100: ('change_reporting_profile', UNKNOWN),
        0x0100: ZCLAttributeDef(
            "current_tier1_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0101: ZCLAttributeDef(
            "current_tier1_summ_received", type=t.uint48_t, access="r"
        ),
        0x0102: ZCLAttributeDef(
            "current_tier2_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0103: ZCLAttributeDef(
            "current_tier2_summ_received", type=t.uint48_t, access="r"
        ),
        0x0104: ZCLAttributeDef(
            "current_tier3_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0105: ZCLAttributeDef(
            "current_tier3_summ_received", type=t.uint48_t, access="r"
        ),
        0x0106: ZCLAttributeDef(
            "current_tier4_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0107: ZCLAttributeDef(
            "current_tier4_summ_received", type=t.uint48_t, access="r"
        ),
        0x0108: ZCLAttributeDef(
            "current_tier5_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0109: ZCLAttributeDef(
            "current_tier5_summ_received", type=t.uint48_t, access="r"
        ),
        0x010A: ZCLAttributeDef(
            "current_tier6_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x010B: ZCLAttributeDef(
            "current_tier6_summ_received", type=t.uint48_t, access="r"
        ),
        0x010C: ZCLAttributeDef(
            "current_tier7_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x010D: ZCLAttributeDef(
            "current_tier7_summ_received", type=t.uint48_t, access="r"
        ),
        0x010E: ZCLAttributeDef(
            "current_tier8_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x010F: ZCLAttributeDef(
            "current_tier8_summ_received", type=t.uint48_t, access="r"
        ),
        0x0110: ZCLAttributeDef(
            "current_tier9_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0111: ZCLAttributeDef(
            "current_tier9_summ_received", type=t.uint48_t, access="r"
        ),
        0x0112: ZCLAttributeDef(
            "current_tier10_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0113: ZCLAttributeDef(
            "current_tier10_summ_received", type=t.uint48_t, access="r"
        ),
        0x0114: ZCLAttributeDef(
            "current_tier11_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0115: ZCLAttributeDef(
            "current_tier11_summ_received", type=t.uint48_t, access="r"
        ),
        0x0116: ZCLAttributeDef(
            "current_tier12_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0117: ZCLAttributeDef(
            "current_tier12_summ_received", type=t.uint48_t, access="r"
        ),
        0x0118: ZCLAttributeDef(
            "current_tier13_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x0119: ZCLAttributeDef(
            "current_tier13_summ_received", type=t.uint48_t, access="r"
        ),
        0x011A: ZCLAttributeDef(
            "current_tier14_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x011B: ZCLAttributeDef(
            "current_tier14_summ_received", type=t.uint48_t, access="r"
        ),
        0x011C: ZCLAttributeDef(
            "current_tier15_summ_delivered", type=t.uint48_t, access="r"
        ),
        0x011D: ZCLAttributeDef(
            "current_tier15_summ_received", type=t.uint48_t, access="r"
        ),
        0x0200: ZCLAttributeDef("status", type=t.bitmap8, access="r"),
        0x0201: ZCLAttributeDef("remaining_battery_life", type=t.uint8_t, access="r"),
        0x0202: ZCLAttributeDef("hours_in_operation", type=t.uint24_t, access="r"),
        0x0203: ZCLAttributeDef("hours_in_fault", type=t.uint24_t, access="r"),
        0x0204: ZCLAttributeDef("extended_status", type=t.bitmap64, access="r"),
        0x0205: ZCLAttributeDef(
            "remaining_battery_life_days", type=t.uint16_t, access="r"
        ),
        0x0206: ZCLAttributeDef("current_meter_id", type=t.LVBytes, access="r"),
        0x0207: ZCLAttributeDef(
            "iambient_consumption_indicator", type=t.enum8, access="r"
        ),
        0x0300: ZCLAttributeDef("unit_of_measure", type=t.enum8, access="r"),
        0x0301: ZCLAttributeDef("multiplier", type=t.uint24_t, access="r"),
        0x0302: ZCLAttributeDef("divisor", type=t.uint24_t, access="r"),
        0x0303: ZCLAttributeDef("summation_formatting", type=t.bitmap8, access="r"),
        0x0304: ZCLAttributeDef("demand_formatting", type=t.bitmap8, access="r"),
        0x0305: ZCLAttributeDef(
            "historical_consump_formatting", type=t.bitmap8, access="r"
        ),
        0x0306: ZCLAttributeDef("metering_device_type", type=t.bitmap8, access="r"),
        0x0307: ZCLAttributeDef("site_id", type=t.LimitedLVBytes(32), access="r"),
        0x0308: ZCLAttributeDef(
            "meter_serial_number", type=t.LimitedLVBytes(24), access="r"
        ),
        0x0309: ZCLAttributeDef(
            "energy_carrier_unit_of_meas", type=t.enum8, access="r"
        ),
        0x030A: ZCLAttributeDef(
            "energy_carrier_summ_formatting", type=t.bitmap8, access="r"
        ),
        0x030B: ZCLAttributeDef(
            "energy_carrier_demand_formatting", type=t.bitmap8, access="r"
        ),
        0x030C: ZCLAttributeDef(
            "temperature_unit_of_measure", type=t.enum8, access="r"
        ),
        0x030D: ZCLAttributeDef("temperature_formatting", type=t.bitmap8, access="r"),
        0x030E: ZCLAttributeDef(
            "module_serial_number", type=t.LimitedLVBytes(24), access="r"
        ),
        0x030F: ZCLAttributeDef(
            "operating_tariff_label_delivered", type=t.LimitedLVBytes(24), access="r"
        ),
        0x0310: ZCLAttributeDef(
            "operating_tariff_label_received", type=t.LimitedLVBytes(24), access="r"
        ),
        0x0311: ZCLAttributeDef(
            "customer_id_number", type=t.LimitedLVBytes(24), access="r"
        ),
        0x0312: ZCLAttributeDef(
            "alternative_unit_of_measure", type=t.enum8, access="r"
        ),
        0x0313: ZCLAttributeDef(
            "alternative_demand_formatting", type=t.bitmap8, access="r"
        ),
        0x0314: ZCLAttributeDef(
            "alternative_consumption_formatting", type=t.bitmap8, access="r"
        ),
        0x0400: ZCLAttributeDef("instantaneous_demand", type=t.int24s, access="r"),
        0x0401: ZCLAttributeDef(
            "currentday_consump_delivered", type=t.uint24_t, access="r"
        ),
        0x0402: ZCLAttributeDef(
            "currentday_consump_received", type=t.uint24_t, access="r"
        ),
        0x0403: ZCLAttributeDef(
            "previousday_consump_delivered", type=t.uint24_t, access="r"
        ),
        0x0404: ZCLAttributeDef(
            "previousday_consump_received", type=t.uint24_t, access="r"
        ),
        0x0405: ZCLAttributeDef(
            "cur_part_profile_int_start_time_delivered", type=t.uint32_t, access="r"
        ),
        0x0406: ZCLAttributeDef(
            "cur_part_profile_int_start_time_received", type=t.uint32_t, access="r"
        ),
        0x0407: ZCLAttributeDef(
            "cur_part_profile_int_value_delivered", type=t.uint24_t, access="r"
        ),
        0x0408: ZCLAttributeDef(
            "cur_part_profile_int_value_received", type=t.uint24_t, access="r"
        ),
        0x0409: ZCLAttributeDef(
            "current_day_max_pressure", type=t.uint48_t, access="r"
        ),
        0x040A: ZCLAttributeDef(
            "current_day_min_pressure", type=t.uint48_t, access="r"
        ),
        0x040B: ZCLAttributeDef(
            "previous_day_max_pressure", type=t.uint48_t, access="r"
        ),
        0x040C: ZCLAttributeDef(
            "previous_day_min_pressure", type=t.uint48_t, access="r"
        ),
        0x040D: ZCLAttributeDef("current_day_max_demand", type=t.int24s, access="r"),
        0x040E: ZCLAttributeDef("previous_day_max_demand", type=t.int24s, access="r"),
        0x040F: ZCLAttributeDef("current_month_max_demand", type=t.int24s, access="r"),
        0x0410: ZCLAttributeDef("current_year_max_demand", type=t.int24s, access="r"),
        0x0411: ZCLAttributeDef(
            "currentday_max_energy_carr_demand", type=t.int24s, access="r"
        ),
        0x0412: ZCLAttributeDef(
            "previousday_max_energy_carr_demand", type=t.int24s, access="r"
        ),
        0x0413: ZCLAttributeDef(
            "cur_month_max_energy_carr_demand", type=t.int24s, access="r"
        ),
        0x0414: ZCLAttributeDef(
            "cur_month_min_energy_carr_demand", type=t.int24s, access="r"
        ),
        0x0415: ZCLAttributeDef(
            "cur_year_max_energy_carr_demand", type=t.int24s, access="r"
        ),
        0x0416: ZCLAttributeDef(
            "cur_year_min_energy_carr_demand", type=t.int24s, access="r"
        ),
        0x0500: ZCLAttributeDef(
            "max_number_of_periods_delivered", type=t.uint8_t, access="r"
        ),
        0x0600: ZCLAttributeDef(
            "current_demand_delivered", type=t.uint24_t, access="r"
        ),
        0x0601: ZCLAttributeDef("demand_limit", type=t.uint24_t, access="r"),
        0x0602: ZCLAttributeDef(
            "demand_integration_period", type=t.uint8_t, access="r"
        ),
        0x0603: ZCLAttributeDef(
            "number_of_demand_subintervals", type=t.uint8_t, access="r"
        ),
        0x0604: ZCLAttributeDef(
            "demand_limit_arm_duration", type=t.uint16_t, access="r"
        ),
        0x0800: ZCLAttributeDef("generic_alarm_mask", type=t.bitmap16, access="r"),
        0x0801: ZCLAttributeDef("electricity_alarm_mask", type=t.bitmap32, access="r"),
        0x0802: ZCLAttributeDef(
            "gen_flow_pressure_alarm_mask", type=t.bitmap16, access="r"
        ),
        0x0803: ZCLAttributeDef(
            "water_specific_alarm_mask", type=t.bitmap16, access="r"
        ),
        0x0804: ZCLAttributeDef(
            "heat_cool_specific_alarm_mask", type=t.bitmap16, access="r"
        ),
        0x0805: ZCLAttributeDef("gas_specific_alarm_mask", type=t.bitmap16, access="r"),
        0x0806: ZCLAttributeDef(
            "extended_generic_alarm_mask", type=t.bitmap48, access="r"
        ),
        0x0807: ZCLAttributeDef("manufacture_alarm_mask", type=t.bitmap16, access="r"),
        0x0A00: ZCLAttributeDef("bill_to_date", type=t.uint32_t, access="r"),
        0x0A01: ZCLAttributeDef("bill_to_date_time_stamp", type=t.uint32_t, access="r"),
        0x0A02: ZCLAttributeDef("projected_bill", type=t.uint32_t, access="r"),
        0x0A03: ZCLAttributeDef(
            "projected_bill_time_stamp", type=t.uint32_t, access="r"
        ),
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("get_profile", {}, False),
        0x01: ZCLCommandDef("req_mirror", {}, False),
        0x02: ZCLCommandDef("mirror_rem", {}, False),
        0x03: ZCLCommandDef("req_fast_poll_mode", {}, False),
        0x04: ZCLCommandDef("get_snapshot", {}, False),
        0x05: ZCLCommandDef("take_snapshot", {}, False),
        0x06: ZCLCommandDef("mirror_report_attr_response", {}, True),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("get_profile_response", {}, True),
        0x01: ZCLCommandDef("req_mirror_response", {}, True),
        0x02: ZCLCommandDef("mirror_rem_response", {}, True),
        0x03: ZCLCommandDef("req_fast_poll_mode_response", {}, True),
        0x04: ZCLCommandDef("get_snapshot_response", {}, True),
    }


class Messaging(Cluster):
    cluster_id = 0x0703
    ep_attribute = "smartenergy_messaging"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Tunneling(Cluster):
    cluster_id = 0x0704
    ep_attribute = "smartenergy_tunneling"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Prepayment(Cluster):
    cluster_id = 0x0705
    ep_attribute = "smartenergy_prepayment"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class EnergyManagement(Cluster):
    cluster_id = 0x0706
    ep_attribute = "smartenergy_energy_management"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Calendar(Cluster):
    cluster_id = 0x0707
    ep_attribute = "smartenergy_calendar"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class DeviceManagement(Cluster):
    cluster_id = 0x0708
    ep_attribute = "smartenergy_device_management"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class Events(Cluster):
    cluster_id = 0x0709
    ep_attribute = "smartenergy_events"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class MduPairing(Cluster):
    cluster_id = 0x070A
    ep_attribute = "smartenergy_mdu_pairing"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class KeyEstablishment(Cluster):
    cluster_id = 0x0800
    ep_attribute = "smartenergy_key_establishment"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
