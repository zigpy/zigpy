import zigpy.types as t
from zigpy.zcl import Cluster


class Price(Cluster):
    cluster_id = 0x0700
    ep_attribute = "smartenergy_price"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Drlc(Cluster):
    cluster_id = 0x0701
    ep_attribute = "smartenergy_drlc"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Metering(Cluster):
    cluster_id = 0x0702
    ep_attribute = "smartenergy_metering"
    attributes = {
        0x0000: ("current_summ_delivered", t.uint48_t),
        0x0001: ("current_summ_received", t.uint48_t),
        0x0002: ("current_max_demand_delivered", t.uint48_t),
        0x0003: ("current_max_demand_received", t.uint48_t),
        0x0004: ("dft_summ", t.uint48_t),
        0x0005: ("daily_freeze_time", t.uint16_t),
        0x0006: ("power_factor", t.int8s),
        0x0007: ("reading_snapshot_time", t.uint32_t),
        0x0008: ("current_max_demand_deliverd_time", t.uint32_t),
        0x0009: ("current_max_demand_received_time", t.uint32_t),
        0x000A: ("default_update_period", t.uint8_t),
        0x000B: ("fast_poll_update_period", t.uint8_t),
        0x000C: ("current_block_period_consump_delivered", t.uint48_t),
        0x000D: ("daily_consump_target", t.uint24_t),
        0x000E: ("current_block", t.enum8),
        0x000F: ("profile_interval_period", t.enum8),
        # 0x0010: ('interval_read_reporting_period', UNKNOWN),
        0x0011: ("preset_reading_time", t.uint16_t),
        0x0012: ("volume_per_report", t.uint16_t),
        0x0013: ("flow_restriction", t.uint8_t),
        0x0014: ("supply_status", t.enum8),
        0x0015: ("current_in_energy_carrier_summ", t.uint48_t),
        0x0016: ("current_out_energy_carrier_summ", t.uint48_t),
        0x0017: ("inlet_tempreature", t.int24s),
        0x0018: ("outlet_tempreature", t.int24s),
        0x0019: ("control_tempreature", t.int24s),
        0x001A: ("current_in_energy_carrier_demand", t.int24s),
        0x001B: ("current_out_energy_carrier_demand", t.int24s),
        0x001D: ("current_block_period_consump_received", t.uint48_t),
        0x001E: ("current_block_received", t.uint48_t),
        # 0x0100: ('change_reporting_profile', UNKNOWN),
        0x0100: ("current_tier1_summ_delivered", t.uint48_t),
        0x0101: ("current_tier1_summ_received", t.uint48_t),
        0x0102: ("current_tier2_summ_delivered", t.uint48_t),
        0x0103: ("current_tier2_summ_received", t.uint48_t),
        0x0104: ("current_tier3_summ_delivered", t.uint48_t),
        0x0105: ("current_tier3_summ_received", t.uint48_t),
        0x0106: ("current_tier4_summ_delivered", t.uint48_t),
        0x0107: ("current_tier4_summ_received", t.uint48_t),
        0x0108: ("current_tier5_summ_delivered", t.uint48_t),
        0x0109: ("current_tier5_summ_received", t.uint48_t),
        0x010A: ("current_tier6_summ_delivered", t.uint48_t),
        0x010B: ("current_tier6_summ_received", t.uint48_t),
        0x010C: ("current_tier7_summ_delivered", t.uint48_t),
        0x010D: ("current_tier7_summ_received", t.uint48_t),
        0x010E: ("current_tier8_summ_delivered", t.uint48_t),
        0x010F: ("current_tier8_summ_received", t.uint48_t),
        0x0110: ("current_tier9_summ_delivered", t.uint48_t),
        0x0111: ("current_tier9_summ_received", t.uint48_t),
        0x0112: ("current_tier10_summ_delivered", t.uint48_t),
        0x0113: ("current_tier10_summ_received", t.uint48_t),
        0x0114: ("current_tier11_summ_delivered", t.uint48_t),
        0x0115: ("current_tier11_summ_received", t.uint48_t),
        0x0116: ("current_tier12_summ_delivered", t.uint48_t),
        0x0117: ("current_tier12_summ_received", t.uint48_t),
        0x0118: ("current_tier13_summ_delivered", t.uint48_t),
        0x0119: ("current_tier13_summ_received", t.uint48_t),
        0x011A: ("current_tier14_summ_delivered", t.uint48_t),
        0x011B: ("current_tier14_summ_received", t.uint48_t),
        0x011C: ("current_tier15_summ_delivered", t.uint48_t),
        0x011D: ("current_tier15_summ_received", t.uint48_t),
        0x0200: ("status", t.bitmap8),
        0x0201: ("remaining_batt_life", t.uint8_t),
        0x0202: ("hours_in_operation", t.uint24_t),
        0x0203: ("hours_in_fault", t.uint24_t),
        0x0204: ("extended_status", t.bitmap64),
        0x0300: ("unit_of_measure", t.enum8),
        0x0301: ("multiplier", t.uint24_t),
        0x0302: ("divisor", t.uint24_t),
        0x0303: ("summa_formatting", t.bitmap8),
        0x0304: ("demand_formatting", t.bitmap8),
        0x0305: ("historical_consump_formatting", t.bitmap8),
        0x0306: ("metering_device_type", t.bitmap8),
        0x0307: ("site_id", t.LimitedCharString(32)),
        0x0308: ("meter_serial_number", t.LimitedCharString(24)),
        0x0309: ("energy_carrier_unit_of_meas", t.enum8),
        0x030A: ("energy_carrier_summ_formatting", t.bitmap8),
        0x030B: ("energy_carrier_demand_formatting", t.bitmap8),
        0x030C: ("temperature_unit_of_meas", t.enum8),
        0x030D: ("temperature_formatting", t.bitmap8),
        0x030E: ("module_serial_number", t.LVBytes),
        0x030F: ("operating_tariff_level", t.LVBytes),
        0x0400: ("instantaneous_demand", t.int24s),
        0x0401: ("currentday_consump_delivered", t.uint24_t),
        0x0402: ("currentday_consump_received", t.uint24_t),
        0x0403: ("previousday_consump_delivered", t.uint24_t),
        0x0404: ("previousday_consump_received", t.uint24_t),
        0x0405: ("cur_part_profile_int_start_time_delivered", t.uint32_t),
        0x0406: ("cur_part_profile_int_start_time_received", t.uint32_t),
        0x0407: ("cur_part_profile_int_value_delivered", t.uint24_t),
        0x0408: ("cur_part_profile_int_value_received", t.uint24_t),
        0x0409: ("current_day_max_pressure", t.uint48_t),
        0x040A: ("current_day_min_pressure", t.uint48_t),
        0x040B: ("previous_day_max_pressure", t.uint48_t),
        0x040C: ("previous_day_min_pressure", t.uint48_t),
        0x040D: ("current_day_max_demand", t.int24s),
        0x040E: ("previous_day_max_demand", t.int24s),
        0x040F: ("current_month_max_demand", t.int24s),
        0x0410: ("current_year_max_demand", t.int24s),
        0x0411: ("currentday_max_energy_carr_demand", t.int24s),
        0x0412: ("previousday_max_energy_carr_demand", t.int24s),
        0x0413: ("cur_month_max_energy_carr_demand", t.int24s),
        0x0414: ("cur_month_min_energy_carr_demand", t.int24s),
        0x0415: ("cur_year_max_energy_carr_demand", t.int24s),
        0x0416: ("cur_year_min_energy_carr_demand", t.int24s),
        0x0500: ("max_number_of_periods_delivered", t.uint8_t),
        0x0600: ("current_demand_delivered", t.uint24_t),
        0x0601: ("demand_limit", t.uint24_t),
        0x0602: ("demand_integration_period", t.uint8_t),
        0x0603: ("number_of_demand_subintervals", t.uint8_t),
        0x0604: ("demand_limit_arm_duration", t.uint16_t),
        0x0800: ("generic_alarm_mask", t.bitmap16),
        0x0801: ("electricity_alarm_mask", t.bitmap32),
        0x0802: ("gen_flow_pressure_alarm_mask", t.bitmap16),
        0x0803: ("water_specific_alarm_mask", t.bitmap16),
        0x0804: ("heat_cool_specific_alarm_mask", t.bitmap16),
        0x0805: ("gas_specific_alarm_mask", t.bitmap16),
        0x0806: ("extended_generic_alarm_mask", t.bitmap48),
        0x0807: ("manufacture_alarm_mask", t.bitmap16),
        0x0A00: ("bill_to_date", t.uint32_t),
        0x0A01: ("bill_to_date_time_stamp", t.uint32_t),
        0x0A02: ("projected_bill", t.uint32_t),
        0x0A03: ("projected_bill_time_stamp", t.uint32_t),
    }
    server_commands = {
        0x0000: ("get_profile", (), False),
        0x0001: ("req_mirror", (), False),
        0x0002: ("mirror_rem", (), False),
        0x0003: ("req_fast_poll_mode", (), False),
        0x0004: ("get_snapshot", (), False),
        0x0005: ("take_snapshot", (), False),
        0x0006: ("mirror_report_attr_response", (), True),
    }
    client_commands = {
        0x0000: ("get_profile_response", (), True),
        0x0001: ("req_mirror_response", (), True),
        0x0002: ("mirror_rem_response", (), True),
        0x0003: ("req_fast_poll_mode_response", (), True),
        0x0004: ("get_snapshot_response", (), True),
    }


class Messaging(Cluster):
    cluster_id = 0x0703
    ep_attribute = "smartenergy_messaging"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Tunneling(Cluster):
    cluster_id = 0x0704
    ep_attribute = "smartenergy_tunneling"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Prepayment(Cluster):
    cluster_id = 0x0705
    ep_attribute = "smartenergy_prepayment"
    attributes = {}
    server_commands = {}
    client_commands = {}


class EnergyManagement(Cluster):
    cluster_id = 0x0706
    ep_attribute = "smartenergy_energy_management"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Calendar(Cluster):
    cluster_id = 0x0707
    ep_attribute = "smartenergy_calendar"
    attributes = {}
    server_commands = {}
    client_commands = {}


class DeviceManagement(Cluster):
    cluster_id = 0x0708
    ep_attribute = "smartenergy_device_management"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Events(Cluster):
    cluster_id = 0x0709
    ep_attribute = "smartenergy_events"
    attributes = {}
    server_commands = {}
    client_commands = {}


class MduPairing(Cluster):
    cluster_id = 0x070A
    ep_attribute = "smartenergy_mdu_pairing"
    attributes = {}
    server_commands = {}
    client_commands = {}


class KeyEstablishment(Cluster):
    cluster_id = 0x0800
    ep_attribute = "smartenergy_key_establishment"
    attributes = {}
    server_commands = {}
    client_commands = {}
