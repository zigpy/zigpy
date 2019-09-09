import zigpy.types as t
from zigpy.zcl import Cluster


class ApplianceIdentification(Cluster):
    cluster_id = 0x0B00
    name = "Appliance Identification"
    ep_attribute = "appliance_id"
    attributes = {
        0x0000: ("basic_identification", t.uint56_t),
        0x0010: ("company_name", t.CharacterString),
        0x0011: ("company_id", t.uint16_t),
        0x0012: ("brand_name", t.CharacterString),
        0x0013: ("brand_id", t.uint16_t),
        0x0014: ("model", t.CharacterString),
        0x0015: ("part_number", t.CharacterString),
        0x0016: ("product_revision", t.CharacterString),
        0x0017: ("software_revision", t.CharacterString),
        0x0018: ("product_type_name", t.CharacterString),
        0x0019: ("product_type_id", t.uint16_t),
        0x001A: ("ceced_specification_version", t.uint8_t),
    }
    server_commands = {}
    client_commands = {}


class MeterIdentification(Cluster):
    cluster_id = 0x0B01
    name = "Meter Identification"
    ep_attribute = "meter_id"
    attributes = {
        0x0000: ("company_name", t.LimitedCharString(16)),
        0x0001: ("meter_type_id", t.uint16_t),
        0x0004: ("data_quality_id", t.uint16_t),
        0x0005: ("customer_name", t.LimitedCharString(16)),
        0x0006: ("model", t.LimitedCharString(16)),
        0x0007: ("part_number", t.LimitedCharString(16)),
        0x0008: ("product_revision", t.LimitedCharString(6)),
        0x000A: ("software_revision", t.LimitedCharString(6)),
        0x000B: ("utility_name", t.LimitedCharString(16)),
        0x000C: ("pod", t.LimitedCharString(16)),
        0x000D: ("available_power", t.int24s),
        0x000E: ("power_threshold", t.int24s),
    }
    server_commands = {}
    client_commands = {}


class ApplianceEventAlerts(Cluster):
    cluster_id = 0x0B02
    name = "Appliance Event Alerts"
    ep_attribute = "appliance_event"
    attributes = {}
    server_commands = {0x0000: ("get_alerts", (), False)}
    client_commands = {
        0x0000: ("get_alarts_response", (), True),
        0x0001: ("alerts_notification", (), False),
        0x0002: ("event_notification", (), False),
    }


class ApplianceStatistics(Cluster):
    cluster_id = 0x0B03
    name = "Appliance Statistics"
    ep_attribute = "appliance_stats"
    attributes = {
        0x0000: ("log_max_size", t.uint32_t),
        0x0001: ("log_queue_max_size", t.uint8_t),
    }
    server_commands = {0x0000: ("log", (), False), 0x0001: ("log_queue", (), False)}
    client_commands = {
        0x0000: ("log_notification", (), False),
        0x0001: ("log_response", (), True),
        0x0002: ("log_queue_response", (), True),
        0x0003: ("statistics_available", (), False),
    }


class ElectricalMeasurement(Cluster):
    cluster_id = 0x0B04
    name = "Electrical Measurement"
    ep_attribute = "electrical_measurement"
    attributes = {
        # Basic Information
        0x0000: ("measurement_type", t.bitmap32),
        # DC Measurement
        0x0100: ("dc_voltage", t.int16s),
        0x0101: ("dc_voltage_min", t.int16s),
        0x0102: ("dcvoltagemax", t.int16s),
        0x0103: ("dc_current", t.int16s),
        0x0104: ("dc_current_min", t.int16s),
        0x0105: ("dc_current_max", t.int16s),
        0x0106: ("dc_power", t.int16s),
        0x0107: ("dc_power_min", t.int16s),
        0x0108: ("dc_power_max", t.int16s),
        # DC Formatting
        0x0200: ("dc_voltage_multiplier", t.uint16_t),
        0x0201: ("dc_voltage_divisor", t.uint16_t),
        0x0202: ("dc_current_multiplier", t.uint16_t),
        0x0203: ("dc_current_divisor", t.uint16_t),
        0x0204: ("dc_power_multiplier", t.uint16_t),
        0x0205: ("dc_power_divisor", t.uint16_t),
        # AC (Non-phase Specific) Measurements
        0x0300: ("ac_frequency", t.uint16_t),
        0x0301: ("ac_frequency_min", t.uint16_t),
        0x0302: ("ac_frequency_max", t.uint16_t),
        0x0303: ("neutral_current", t.uint16_t),
        0x0304: ("total_active_power", t.int32s),
        0x0305: ("total_reactive_power", t.int32s),
        0x0306: ("total_apparent_power", t.uint32_t),
        0x0307: ("meas1st_harmonic_current", t.int16s),
        0x0308: ("meas3rd_harmonic_current", t.int16s),
        0x0309: ("meas5th_harmonic_current", t.int16s),
        0x030A: ("meas7th_harmonic_current", t.int16s),
        0x030B: ("meas9th_harmonic_current", t.int16s),
        0x030C: ("meas11th_harmonic_current", t.int16s),
        0x030D: ("meas_phase1st_harmonic_current", t.int16s),
        0x030E: ("meas_phase3rd_harmonic_current", t.int16s),
        0x030F: ("meas_phase5th_harmonic_current", t.int16s),
        0x0310: ("meas_phase7th_harmonic_current", t.int16s),
        0x0311: ("meas_phase9th_harmonic_current", t.int16s),
        0x0312: ("meas_phase11th_harmonic_current", t.int16s),
        # AC (Non-phase specific) Formatting
        0x0400: ("ac_frequency_multiplier", t.uint16_t),
        0x0401: ("ac_frequency_divisor", t.uint16_t),
        0x0402: ("power_multiplier", t.uint32_t),
        0x0403: ("power_divisor", t.uint32_t),
        0x0404: ("harmonic_current_multiplier", t.int8s),
        0x0405: ("phase_harmonic_current_multiplier", t.int8s),
        # AC (Single Phase or Phase A) Measurements
        0x0500: ("instantaneous_voltage", t.int16s),
        0x0501: ("instantaneous_line_current", t.uint16_t),
        0x0502: ("instantaneous_active_current", t.int16s),
        0x0503: ("instantaneous_reactive_current", t.int16s),
        0x0504: ("instantaneous_power", t.int16s),
        0x0505: ("rms_voltage", t.uint16_t),
        0x0506: ("rms_voltage_min", t.uint16_t),
        0x0507: ("rms_voltage_max", t.uint16_t),
        0x0508: ("rms_current", t.uint16_t),
        0x0509: ("rms_current_min", t.uint16_t),
        0x050A: ("rms_current_max", t.uint16_t),
        0x050B: ("active_power", t.int16s),
        0x050C: ("active_power_min", t.int16s),
        0x050D: ("active_power_max", t.int16s),
        0x050E: ("reactive_power", t.int16s),
        0x050F: ("apparent_power", t.uint16_t),
        0x0510: ("power_factor", t.int8s),
        0x0511: ("average_rms_voltage_meas_period", t.uint16_t),
        0x0512: ("average_rms_over_voltage_counter", t.uint16_t),
        0x0513: ("average_rms_under_voltage_counter", t.uint16_t),
        0x0514: ("rms_extreme_over_voltage_period", t.uint16_t),
        0x0515: ("rms_extreme_under_voltage_period", t.uint16_t),
        0x0516: ("rms_voltage_sag_period", t.uint16_t),
        0x0517: ("rms_voltage_swell_period", t.uint16_t),
        # AC Formatting
        0x0600: ("ac_voltage_multiplier", t.uint16_t),
        0x0601: ("ac_voltage_divisor", t.uint16_t),
        0x0602: ("ac_current_multiplier", t.uint16_t),
        0x0603: ("ac_current_divisor", t.uint16_t),
        0x0604: ("ac_power_multiplier", t.uint16_t),
        0x0605: ("ac_power_divisor", t.uint16_t),
        # DC Manufacturer Threshold Alarms
        0x0700: ("dc_overload_alarms_mask", t.bitmap8),
        0x0701: ("dc_voltage_overload", t.int16s),
        0x0702: ("dc_current_overload", t.int16s),
        # AC Manufacturer Threshold Alarms
        0x0800: ("ac_alarms_mask", t.bitmap16),
        0x0801: ("ac_voltage_overload", t.int16s),
        0x0802: ("ac_current_overload", t.int16s),
        0x0803: ("ac_active_power_overload", t.int16s),
        0x0804: ("ac_reactive_power_overload", t.int16s),
        0x0805: ("average_rms_over_voltage", t.int16s),
        0x0806: ("average_rms_under_voltage", t.int16s),
        0x0807: ("rms_extreme_over_voltage", t.int16s),
        0x0808: ("rms_extreme_under_voltage", t.int16s),
        0x0809: ("rms_voltage_sag", t.int16s),
        0x080A: ("rms_voltage_swell", t.int16s),
        # AC Phase B Measurements
        0x0901: ("line_current_ph_b", t.uint16_t),
        0x0902: ("active_current_ph_b", t.int16s),
        0x0903: ("reactive_current_ph_b", t.int16s),
        0x0905: ("rms_voltage_ph_b", t.uint16_t),
        0x0906: ("rms_voltage_min_ph_b", t.uint16_t),
        0x0907: ("rms_voltage_max_ph_b", t.uint16_t),
        0x0908: ("rms_current_ph_b", t.uint16_t),
        0x0909: ("rms_current_min_ph_b", t.uint16_t),
        0x090A: ("rms_current_max_ph_b", t.uint16_t),
        0x090B: ("active_power_ph_b", t.int16s),
        0x090C: ("active_power_min_ph_b", t.int16s),
        0x090D: ("active_power_max_ph_b", t.int16s),
        0x090E: ("reactive_power_ph_b", t.int16s),
        0x090F: ("apparent_power_ph_b", t.uint16_t),
        0x0910: ("power_factor_ph_b", t.int8s),
        0x0911: ("average_rms_voltage_measure_period_ph_b", t.uint16_t),
        0x0912: ("average_rms_over_voltage_counter_ph_b", t.uint16_t),
        0x0913: ("average_under_voltage_counter_ph_b", t.uint16_t),
        0x0914: ("rms_extreme_over_voltage_period_ph_b", t.uint16_t),
        0x0915: ("rms_extreme_under_voltage_period_ph_b", t.uint16_t),
        0x0916: ("rms_voltage_sag_period_ph_b", t.uint16_t),
        0x0917: ("rms_voltage_swell_period_ph_b", t.uint16_t),
        # AC Phase C Measurements
        0x0A01: ("line_current_ph_c", t.uint16_t),
        0x0A02: ("active_current_ph_c", t.int16s),
        0x0A03: ("reactive_current_ph_c", t.int16s),
        0x0A05: ("rms_voltage_ph_c", t.uint16_t),
        0x0A06: ("rms_voltage_min_ph_c", t.uint16_t),
        0x0A07: ("rms_voltage_max_ph_c", t.uint16_t),
        0x0A08: ("rms_current_ph_c", t.uint16_t),
        0x0A09: ("rms_current_min_ph_c", t.uint16_t),
        0x0A0A: ("rms_current_max_ph_c", t.uint16_t),
        0x0A0B: ("active_power_ph_c", t.int16s),
        0x0A0C: ("active_power_min_ph_c", t.int16s),
        0x0A0D: ("active_power_max_ph_c", t.int16s),
        0x0A0E: ("reactive_power_ph_c", t.int16s),
        0x0A0F: ("apparent_power_ph_c", t.uint16_t),
        0x0A10: ("power_factor_ph_c", t.int8s),
        0x0A11: ("average_rms_voltage_meas_period_ph_c", t.uint16_t),
        0x0A12: ("average_rms_over_voltage_counter_ph_c", t.uint16_t),
        0x0A13: ("average_under_voltage_counter_ph_c", t.uint16_t),
        0x0A14: ("rms_extreme_over_voltage_period_ph_c", t.uint16_t),
        0x0A15: ("rms_extreme_under_voltage_period_ph_c", t.uint16_t),
        0x0A16: ("rms_voltage_sag_period_ph_c", t.uint16_t),
        0x0A17: ("rms_voltage_swell_period_ph__c", t.uint16_t),
    }
    server_commands = {
        0x0000: ("get_profile_info", (), False),
        0x0001: ("get_measurement_profile", (), False),
    }
    client_commands = {
        0x0000: ("get_profile_info_response", (), True),
        0x0001: ("get_measurement_profile_response", (), True),
    }


class Diagnostic(Cluster):
    cluster_id = 0x0B05
    ep_attribute = "diagnostic"
    attributes = {
        # Hardware Information
        0x0000: ("number_of_resets", t.uint16_t),
        0x0001: ("persistent_memory_writes", t.uint16_t),
        # Stack/Network Information
        0x0100: ("mac_rx_bcast", t.uint32_t),
        0x0101: ("mac_tx_bcast", t.uint32_t),
        0x0102: ("mac_rx_ucast", t.uint32_t),
        0x0103: ("mac_tx_ucast", t.uint32_t),
        0x0104: ("mac_tx_ucast_retry", t.uint16_t),
        0x0105: ("mac_tx_ucast_fail", t.uint16_t),
        0x0106: ("aps_rx_bcast", t.uint16_t),
        0x0107: ("aps_tx_bcast", t.uint16_t),
        0x0108: ("aps_rx_ucast", t.uint16_t),
        0x0109: ("aps_tx_ucast_success", t.uint16_t),
        0x010A: ("aps_tx_ucast_retry", t.uint16_t),
        0x010B: ("aps_tx_ucast_fail", t.uint16_t),
        0x010C: ("route_disc_initiated", t.uint16_t),
        0x010D: ("neighbor_added", t.uint16_t),
        0x010E: ("neighbor_removed", t.uint16_t),
        0x010F: ("neighbor_stale", t.uint16_t),
        0x0110: ("join_indication", t.uint16_t),
        0x0111: ("child_moved", t.uint16_t),
        0x0112: ("nwk_fc_failure", t.uint16_t),
        0x0113: ("aps_fc_failure", t.uint16_t),
        0x0114: ("aps_unauthorized_key", t.uint16_t),
        0x0115: ("nwk_decrypt_failures", t.uint16_t),
        0x0116: ("aps_decrypt_failures", t.uint16_t),
        0x0117: ("packet_buffer_allocate_failures", t.uint16_t),
        0x0118: ("relayed_ucast", t.uint16_t),
        0x0119: ("phy_to_mac_queue_limit_reached", t.uint16_t),
        0x011A: ("packet_validate_drop_count", t.uint16_t),
        0x011B: ("average_mac_retry_per_aps_message_sent", t.uint16_t),
        0x011C: ("last_message_lqi", t.uint8_t),
        0x011D: ("last_message_rssi", t.int8s),
    }
    server_commands = {}
    client_commands = {}
