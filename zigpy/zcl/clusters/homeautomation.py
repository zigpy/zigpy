from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class ApplianceIdentification(Cluster):
    cluster_id = 0x0B00
    name = "Appliance Identification"
    ep_attribute = "appliance_id"
    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef(
            "basic_identification", type=t.uint56_t, access="r", mandatory=True
        ),
        0x0010: ZCLAttributeDef(
            "company_name", type=t.LimitedCharString(16), access="r"
        ),
        0x0011: ZCLAttributeDef("company_id", type=t.uint16_t, access="r"),
        0x0012: ZCLAttributeDef("brand_name", type=t.LimitedCharString(16), access="r"),
        0x0013: ZCLAttributeDef("brand_id", type=t.uint16_t, access="r"),
        0x0014: ZCLAttributeDef("model", type=t.LimitedLVBytes(16), access="r"),
        0x0015: ZCLAttributeDef("part_number", type=t.LimitedLVBytes(16), access="r"),
        0x0016: ZCLAttributeDef(
            "product_revision", type=t.LimitedLVBytes(6), access="r"
        ),
        0x0017: ZCLAttributeDef(
            "software_revision", type=t.LimitedLVBytes(6), access="r"
        ),
        0x0018: ZCLAttributeDef("product_type_name", type=t.LVBytesSize2, access="r"),
        0x0019: ZCLAttributeDef("product_type_id", type=t.uint16_t, access="r"),
        0x001A: ZCLAttributeDef(
            "ceced_specification_version", type=t.uint8_t, access="r"
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class MeterIdentification(Cluster):
    cluster_id = 0x0B01
    name = "Meter Identification"
    ep_attribute = "meter_id"
    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef(
            "company_name", type=t.LimitedCharString(16), access="r", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "meter_type_id", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0004: ZCLAttributeDef(
            "data_quality_id", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0005: ZCLAttributeDef(
            "customer_name", type=t.LimitedCharString(16), access="rw"
        ),
        0x0006: ZCLAttributeDef("model", type=t.LimitedLVBytes(16), access="r"),
        0x0007: ZCLAttributeDef("part_number", type=t.LimitedLVBytes(16), access="r"),
        0x0008: ZCLAttributeDef(
            "product_revision", type=t.LimitedLVBytes(6), access="r"
        ),
        0x000A: ZCLAttributeDef(
            "software_revision", type=t.LimitedLVBytes(6), access="r"
        ),
        0x000B: ZCLAttributeDef(
            "utility_name", type=t.LimitedCharString(16), access="r"
        ),
        0x000C: ZCLAttributeDef(
            "pod", type=t.LimitedCharString(16), access="r", mandatory=True
        ),
        0x000D: ZCLAttributeDef(
            "available_power", type=t.int24s, access="r", mandatory=True
        ),
        0x000E: ZCLAttributeDef(
            "power_threshold", type=t.int24s, access="r", mandatory=True
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class ApplianceEventAlerts(Cluster):
    cluster_id = 0x0B02
    name = "Appliance Event Alerts"
    ep_attribute = "appliance_event"
    attributes: dict[int, ZCLAttributeDef] = {
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("get_alerts", {}, False)
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("get_alerts_response", {}, True),
        0x01: ZCLCommandDef("alerts_notification", {}, False),
        0x02: ZCLCommandDef("event_notification", {}, False),
    }


class ApplianceStatistics(Cluster):
    cluster_id = 0x0B03
    name = "Appliance Statistics"
    ep_attribute = "appliance_stats"
    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef(
            "log_max_size", type=t.uint32_t, access="r", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "log_queue_max_size", type=t.uint8_t, access="r", mandatory=True
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("log", {}, False),
        0x01: ZCLCommandDef("log_queue", {}, False),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("log_notification", {}, False),
        0x01: ZCLCommandDef("log_response", {}, True),
        0x02: ZCLCommandDef("log_queue_response", {}, True),
        0x03: ZCLCommandDef("statistics_available", {}, False),
    }


class ElectricalMeasurement(Cluster):
    cluster_id = 0x0B04
    name = "Electrical Measurement"
    ep_attribute = "electrical_measurement"

    class MeasurementType(t.bitmap32):
        Active_measurement_AC = 2 << 0
        Reactive_measurement_AC = 2 << 1
        Apparent_measurement_AC = 2 << 2
        Phase_A_measurement = 2 << 3
        Phase_B_measurement = 2 << 4
        Phase_C_measurement = 2 << 5
        DC_measurement = 2 << 6
        Harmonics_measurement = 2 << 7
        Power_quality_measurement = 2 << 8

    class DCOverloadAlarmMark(t.bitmap8):
        Voltage_Overload = 0b00000001
        Current_Overload = 0b00000010

    class ACAlarmsMask(t.bitmap16):
        Voltage_Overload = 2 << 0
        Current_Overload = 2 << 1
        Active_Power_Overload = 2 << 2
        Reactive_Power_Overload = 2 << 3
        Average_RMS_Over_Voltage = 2 << 4
        Average_RMS_Under_Voltage = 2 << 5
        RMS_Extreme_Over_Voltage = 2 << 6
        RMS_Extreme_Under_Voltage = 2 << 7
        RMS_Voltage_Sag = 2 << 8
        RMS_Voltage_Swell = 2 << 9

    attributes: dict[int, ZCLAttributeDef] = {
        # Basic Information
        0x0000: ZCLAttributeDef(
            "measurement_type", type=MeasurementType, access="r", mandatory=True
        ),
        # DC Measurement
        0x0100: ZCLAttributeDef("dc_voltage", type=t.int16s, access="rp"),
        0x0101: ZCLAttributeDef("dc_voltage_min", type=t.int16s, access="r"),
        0x0102: ZCLAttributeDef("dc_voltage_max", type=t.int16s, access="r"),
        0x0103: ZCLAttributeDef("dc_current", type=t.int16s, access="rp"),
        0x0104: ZCLAttributeDef("dc_current_min", type=t.int16s, access="r"),
        0x0105: ZCLAttributeDef("dc_current_max", type=t.int16s, access="r"),
        0x0106: ZCLAttributeDef("dc_power", type=t.int16s, access="rp"),
        0x0107: ZCLAttributeDef("dc_power_min", type=t.int16s, access="r"),
        0x0108: ZCLAttributeDef("dc_power_max", type=t.int16s, access="r"),
        # DC Formatting
        0x0200: ZCLAttributeDef("dc_voltage_multiplier", type=t.uint16_t, access="rp"),
        0x0201: ZCLAttributeDef("dc_voltage_divisor", type=t.uint16_t, access="rp"),
        0x0202: ZCLAttributeDef("dc_current_multiplier", type=t.uint16_t, access="rp"),
        0x0203: ZCLAttributeDef("dc_current_divisor", type=t.uint16_t, access="rp"),
        0x0204: ZCLAttributeDef("dc_power_multiplier", type=t.uint16_t, access="rp"),
        0x0205: ZCLAttributeDef("dc_power_divisor", type=t.uint16_t, access="rp"),
        # AC (Non-phase Specific) Measurements
        0x0300: ZCLAttributeDef("ac_frequency", type=t.uint16_t, access="rp"),
        0x0301: ZCLAttributeDef("ac_frequency_min", type=t.uint16_t, access="r"),
        0x0302: ZCLAttributeDef("ac_frequency_max", type=t.uint16_t, access="r"),
        0x0303: ZCLAttributeDef("neutral_current", type=t.uint16_t, access="rp"),
        0x0304: ZCLAttributeDef("total_active_power", type=t.int32s, access="rp"),
        0x0305: ZCLAttributeDef("total_reactive_power", type=t.int32s, access="rp"),
        0x0306: ZCLAttributeDef("total_apparent_power", type=t.uint32_t, access="rp"),
        0x0307: ZCLAttributeDef("meas1st_harmonic_current", type=t.int16s, access="rp"),
        0x0308: ZCLAttributeDef("meas3rd_harmonic_current", type=t.int16s, access="rp"),
        0x0309: ZCLAttributeDef("meas5th_harmonic_current", type=t.int16s, access="rp"),
        0x030A: ZCLAttributeDef("meas7th_harmonic_current", type=t.int16s, access="rp"),
        0x030B: ZCLAttributeDef("meas9th_harmonic_current", type=t.int16s, access="rp"),
        0x030C: ZCLAttributeDef(
            "meas11th_harmonic_current", type=t.int16s, access="rp"
        ),
        0x030D: ZCLAttributeDef(
            "meas_phase1st_harmonic_current", type=t.int16s, access="rp"
        ),
        0x030E: ZCLAttributeDef(
            "meas_phase3rd_harmonic_current", type=t.int16s, access="rp"
        ),
        0x030F: ZCLAttributeDef(
            "meas_phase5th_harmonic_current", type=t.int16s, access="rp"
        ),
        0x0310: ZCLAttributeDef(
            "meas_phase7th_harmonic_current", type=t.int16s, access="rp"
        ),
        0x0311: ZCLAttributeDef(
            "meas_phase9th_harmonic_current", type=t.int16s, access="rp"
        ),
        0x0312: ZCLAttributeDef(
            "meas_phase11th_harmonic_current", type=t.int16s, access="rp"
        ),
        # AC (Non-phase specific) Formatting
        0x0400: ZCLAttributeDef(
            "ac_frequency_multiplier", type=t.uint16_t, access="rp"
        ),
        0x0401: ZCLAttributeDef("ac_frequency_divisor", type=t.uint16_t, access="rp"),
        0x0402: ZCLAttributeDef("power_multiplier", type=t.uint32_t, access="rp"),
        0x0403: ZCLAttributeDef("power_divisor", type=t.uint32_t, access="rp"),
        0x0404: ZCLAttributeDef(
            "harmonic_current_multiplier", type=t.int8s, access="rp"
        ),
        0x0405: ZCLAttributeDef(
            "phase_harmonic_current_multiplier", type=t.int8s, access="rp"
        ),
        # AC (Single Phase or Phase A) Measurements
        0x0500: ZCLAttributeDef("instantaneous_voltage", type=t.int16s, access="rp"),
        0x0501: ZCLAttributeDef(
            "instantaneous_line_current", type=t.uint16_t, access="rp"
        ),
        0x0502: ZCLAttributeDef(
            "instantaneous_active_current", type=t.int16s, access="rp"
        ),
        0x0503: ZCLAttributeDef(
            "instantaneous_reactive_current", type=t.int16s, access="rp"
        ),
        0x0504: ZCLAttributeDef("instantaneous_power", type=t.int16s, access="rp"),
        0x0505: ZCLAttributeDef("rms_voltage", type=t.uint16_t, access="rp"),
        0x0506: ZCLAttributeDef("rms_voltage_min", type=t.uint16_t, access="r"),
        0x0507: ZCLAttributeDef("rms_voltage_max", type=t.uint16_t, access="r"),
        0x0508: ZCLAttributeDef("rms_current", type=t.uint16_t, access="rp"),
        0x0509: ZCLAttributeDef("rms_current_min", type=t.uint16_t, access="r"),
        0x050A: ZCLAttributeDef("rms_current_max", type=t.uint16_t, access="r"),
        0x050B: ZCLAttributeDef("active_power", type=t.int16s, access="rp"),
        0x050C: ZCLAttributeDef("active_power_min", type=t.int16s, access="r"),
        0x050D: ZCLAttributeDef("active_power_max", type=t.int16s, access="r"),
        0x050E: ZCLAttributeDef("reactive_power", type=t.int16s, access="rp"),
        0x050F: ZCLAttributeDef("apparent_power", type=t.uint16_t, access="rp"),
        0x0510: ZCLAttributeDef("power_factor", type=t.int8s, access="r"),
        0x0511: ZCLAttributeDef(
            "average_rms_voltage_meas_period", type=t.uint16_t, access="rw"
        ),
        0x0512: ZCLAttributeDef(
            "average_rms_over_voltage_counter", type=t.uint16_t, access="rw"
        ),
        0x0513: ZCLAttributeDef(
            "average_rms_under_voltage_counter", type=t.uint16_t, access="rw"
        ),
        0x0514: ZCLAttributeDef(
            "rms_extreme_over_voltage_period", type=t.uint16_t, access="rw"
        ),
        0x0515: ZCLAttributeDef(
            "rms_extreme_under_voltage_period", type=t.uint16_t, access="rw"
        ),
        0x0516: ZCLAttributeDef("rms_voltage_sag_period", type=t.uint16_t, access="rw"),
        0x0517: ZCLAttributeDef(
            "rms_voltage_swell_period", type=t.uint16_t, access="rw"
        ),
        # AC Formatting
        0x0600: ZCLAttributeDef("ac_voltage_multiplier", type=t.uint16_t, access="rp"),
        0x0601: ZCLAttributeDef("ac_voltage_divisor", type=t.uint16_t, access="rp"),
        0x0602: ZCLAttributeDef("ac_current_multiplier", type=t.uint16_t, access="rp"),
        0x0603: ZCLAttributeDef("ac_current_divisor", type=t.uint16_t, access="rp"),
        0x0604: ZCLAttributeDef("ac_power_multiplier", type=t.uint16_t, access="rp"),
        0x0605: ZCLAttributeDef("ac_power_divisor", type=t.uint16_t, access="rp"),
        # DC Manufacturer Threshold Alarms
        0x0700: ZCLAttributeDef(
            "dc_overload_alarms_mask", type=DCOverloadAlarmMark, access="rp"
        ),
        0x0701: ZCLAttributeDef("dc_voltage_overload", type=t.int16s, access="rp"),
        0x0702: ZCLAttributeDef("dc_current_overload", type=t.int16s, access="rp"),
        # AC Manufacturer Threshold Alarms
        0x0800: ZCLAttributeDef("ac_alarms_mask", type=ACAlarmsMask, access="rw"),
        0x0801: ZCLAttributeDef("ac_voltage_overload", type=t.int16s, access="r"),
        0x0802: ZCLAttributeDef("ac_current_overload", type=t.int16s, access="r"),
        0x0803: ZCLAttributeDef("ac_active_power_overload", type=t.int16s, access="r"),
        0x0804: ZCLAttributeDef(
            "ac_reactive_power_overload", type=t.int16s, access="r"
        ),
        0x0805: ZCLAttributeDef("average_rms_over_voltage", type=t.int16s, access="r"),
        0x0806: ZCLAttributeDef("average_rms_under_voltage", type=t.int16s, access="r"),
        0x0807: ZCLAttributeDef("rms_extreme_over_voltage", type=t.int16s, access="rw"),
        0x0808: ZCLAttributeDef(
            "rms_extreme_under_voltage", type=t.int16s, access="rw"
        ),
        0x0809: ZCLAttributeDef("rms_voltage_sag", type=t.int16s, access="rw"),
        0x080A: ZCLAttributeDef("rms_voltage_swell", type=t.int16s, access="rw"),
        # AC Phase B Measurements
        0x0901: ZCLAttributeDef("line_current_ph_b", type=t.uint16_t, access="rp"),
        0x0902: ZCLAttributeDef("active_current_ph_b", type=t.int16s, access="rp"),
        0x0903: ZCLAttributeDef("reactive_current_ph_b", type=t.int16s, access="rp"),
        0x0905: ZCLAttributeDef("rms_voltage_ph_b", type=t.uint16_t, access="rp"),
        0x0906: ZCLAttributeDef("rms_voltage_min_ph_b", type=t.uint16_t, access="r"),
        0x0907: ZCLAttributeDef("rms_voltage_max_ph_b", type=t.uint16_t, access="r"),
        0x0908: ZCLAttributeDef("rms_current_ph_b", type=t.uint16_t, access="rp"),
        0x0909: ZCLAttributeDef("rms_current_min_ph_b", type=t.uint16_t, access="r"),
        0x090A: ZCLAttributeDef("rms_current_max_ph_b", type=t.uint16_t, access="r"),
        0x090B: ZCLAttributeDef("active_power_ph_b", type=t.int16s, access="rp"),
        0x090C: ZCLAttributeDef("active_power_min_ph_b", type=t.int16s, access="r"),
        0x090D: ZCLAttributeDef("active_power_max_ph_b", type=t.int16s, access="r"),
        0x090E: ZCLAttributeDef("reactive_power_ph_b", type=t.int16s, access="rp"),
        0x090F: ZCLAttributeDef("apparent_power_ph_b", type=t.uint16_t, access="rp"),
        0x0910: ZCLAttributeDef("power_factor_ph_b", type=t.int8s, access="r"),
        0x0911: ZCLAttributeDef(
            "average_rms_voltage_measure_period_ph_b", type=t.uint16_t, access="rw"
        ),
        0x0912: ZCLAttributeDef(
            "average_rms_over_voltage_counter_ph_b", type=t.uint16_t, access="rw"
        ),
        0x0913: ZCLAttributeDef(
            "average_under_voltage_counter_ph_b", type=t.uint16_t, access="rw"
        ),
        0x0914: ZCLAttributeDef(
            "rms_extreme_over_voltage_period_ph_b", type=t.uint16_t, access="rw"
        ),
        0x0915: ZCLAttributeDef(
            "rms_extreme_under_voltage_period_ph_b", type=t.uint16_t, access="rw"
        ),
        0x0916: ZCLAttributeDef(
            "rms_voltage_sag_period_ph_b", type=t.uint16_t, access="rw"
        ),
        0x0917: ZCLAttributeDef(
            "rms_voltage_swell_period_ph_b", type=t.uint16_t, access="rw"
        ),
        # AC Phase C Measurements
        0x0A01: ZCLAttributeDef("line_current_ph_c", type=t.uint16_t, access="rp"),
        0x0A02: ZCLAttributeDef("active_current_ph_c", type=t.int16s, access="rp"),
        0x0A03: ZCLAttributeDef("reactive_current_ph_c", type=t.int16s, access="rp"),
        0x0A05: ZCLAttributeDef("rms_voltage_ph_c", type=t.uint16_t, access="rp"),
        0x0A06: ZCLAttributeDef("rms_voltage_min_ph_c", type=t.uint16_t, access="r"),
        0x0A07: ZCLAttributeDef("rms_voltage_max_ph_c", type=t.uint16_t, access="r"),
        0x0A08: ZCLAttributeDef("rms_current_ph_c", type=t.uint16_t, access="rp"),
        0x0A09: ZCLAttributeDef("rms_current_min_ph_c", type=t.uint16_t, access="r"),
        0x0A0A: ZCLAttributeDef("rms_current_max_ph_c", type=t.uint16_t, access="r"),
        0x0A0B: ZCLAttributeDef("active_power_ph_c", type=t.int16s, access="rp"),
        0x0A0C: ZCLAttributeDef("active_power_min_ph_c", type=t.int16s, access="r"),
        0x0A0D: ZCLAttributeDef("active_power_max_ph_c", type=t.int16s, access="r"),
        0x0A0E: ZCLAttributeDef("reactive_power_ph_c", type=t.int16s, access="rp"),
        0x0A0F: ZCLAttributeDef("apparent_power_ph_c", type=t.uint16_t, access="rp"),
        0x0A10: ZCLAttributeDef("power_factor_ph_c", type=t.int8s, access="r"),
        0x0A11: ZCLAttributeDef(
            "average_rms_voltage_meas_period_ph_c", type=t.uint16_t, access="rw"
        ),
        0x0A12: ZCLAttributeDef(
            "average_rms_over_voltage_counter_ph_c", type=t.uint16_t, access="rw"
        ),
        0x0A13: ZCLAttributeDef(
            "average_under_voltage_counter_ph_c", type=t.uint16_t, access="rw"
        ),
        0x0A14: ZCLAttributeDef(
            "rms_extreme_over_voltage_period_ph_c", type=t.uint16_t, access="rw"
        ),
        0x0A15: ZCLAttributeDef(
            "rms_extreme_under_voltage_period_ph_c", type=t.uint16_t, access="rw"
        ),
        0x0A16: ZCLAttributeDef(
            "rms_voltage_sag_period_ph_c", type=t.uint16_t, access="rw"
        ),
        0x0A17: ZCLAttributeDef(
            "rms_voltage_swell_period_ph_c", type=t.uint16_t, access="rw"
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("get_profile_info", {}, False),
        0x01: ZCLCommandDef("get_measurement_profile", {}, False),
    }
    client_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef("get_profile_info_response", {}, True),
        0x01: ZCLCommandDef("get_measurement_profile_response", {}, True),
    }


class Diagnostic(Cluster):
    cluster_id = 0x0B05
    ep_attribute = "diagnostic"
    attributes: dict[int, ZCLAttributeDef] = {
        # Hardware Information
        0x0000: ZCLAttributeDef("number_of_resets", type=t.uint16_t, access="r"),
        0x0001: ZCLAttributeDef(
            "persistent_memory_writes", type=t.uint16_t, access="r"
        ),
        # Stack/Network Information
        0x0100: ZCLAttributeDef("mac_rx_bcast", type=t.uint32_t, access="r"),
        0x0101: ZCLAttributeDef("mac_tx_bcast", type=t.uint32_t, access="r"),
        0x0102: ZCLAttributeDef("mac_rx_ucast", type=t.uint32_t, access="r"),
        0x0103: ZCLAttributeDef("mac_tx_ucast", type=t.uint32_t, access="r"),
        0x0104: ZCLAttributeDef("mac_tx_ucast_retry", type=t.uint16_t, access="r"),
        0x0105: ZCLAttributeDef("mac_tx_ucast_fail", type=t.uint16_t, access="r"),
        0x0106: ZCLAttributeDef("aps_rx_bcast", type=t.uint16_t, access="r"),
        0x0107: ZCLAttributeDef("aps_tx_bcast", type=t.uint16_t, access="r"),
        0x0108: ZCLAttributeDef("aps_rx_ucast", type=t.uint16_t, access="r"),
        0x0109: ZCLAttributeDef("aps_tx_ucast_success", type=t.uint16_t, access="r"),
        0x010A: ZCLAttributeDef("aps_tx_ucast_retry", type=t.uint16_t, access="r"),
        0x010B: ZCLAttributeDef("aps_tx_ucast_fail", type=t.uint16_t, access="r"),
        0x010C: ZCLAttributeDef("route_disc_initiated", type=t.uint16_t, access="r"),
        0x010D: ZCLAttributeDef("neighbor_added", type=t.uint16_t, access="r"),
        0x010E: ZCLAttributeDef("neighbor_removed", type=t.uint16_t, access="r"),
        0x010F: ZCLAttributeDef("neighbor_stale", type=t.uint16_t, access="r"),
        0x0110: ZCLAttributeDef("join_indication", type=t.uint16_t, access="r"),
        0x0111: ZCLAttributeDef("child_moved", type=t.uint16_t, access="r"),
        0x0112: ZCLAttributeDef("nwk_fc_failure", type=t.uint16_t, access="r"),
        0x0113: ZCLAttributeDef("aps_fc_failure", type=t.uint16_t, access="r"),
        0x0114: ZCLAttributeDef("aps_unauthorized_key", type=t.uint16_t, access="r"),
        0x0115: ZCLAttributeDef("nwk_decrypt_failures", type=t.uint16_t, access="r"),
        0x0116: ZCLAttributeDef("aps_decrypt_failures", type=t.uint16_t, access="r"),
        0x0117: ZCLAttributeDef(
            "packet_buffer_allocate_failures", type=t.uint16_t, access="r"
        ),
        0x0118: ZCLAttributeDef("relayed_ucast", type=t.uint16_t, access="r"),
        0x0119: ZCLAttributeDef(
            "phy_to_mac_queue_limit_reached", type=t.uint16_t, access="r"
        ),
        0x011A: ZCLAttributeDef(
            "packet_validate_drop_count", type=t.uint16_t, access="r"
        ),
        0x011B: ZCLAttributeDef(
            "average_mac_retry_per_aps_message_sent", type=t.uint16_t, access="r"
        ),
        0x011C: ZCLAttributeDef("last_message_lqi", type=t.uint8_t, access="r"),
        0x011D: ZCLAttributeDef("last_message_rssi", type=t.int8s, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
