from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    ZCLAttributeDef,
    ZCLCommandDef,
)


class ApplianceIdentification(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0B00
    name: Final = "Appliance Identification"
    ep_attribute: Final = "appliance_id"

    class AttributeDefs(BaseAttributeDefs):
        basic_identification: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint56_t, access="r", mandatory=True
        )
        company_name: Final = ZCLAttributeDef(
            id=0x0010, type=t.LimitedCharString(16), access="r"
        )
        company_id: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t, access="r")
        brand_name: Final = ZCLAttributeDef(
            id=0x0012, type=t.LimitedCharString(16), access="r"
        )
        brand_id: Final = ZCLAttributeDef(id=0x0013, type=t.uint16_t, access="r")
        model: Final = ZCLAttributeDef(id=0x0014, type=t.LimitedLVBytes(16), access="r")
        part_number: Final = ZCLAttributeDef(
            id=0x0015, type=t.LimitedLVBytes(16), access="r"
        )
        product_revision: Final = ZCLAttributeDef(
            id=0x0016, type=t.LimitedLVBytes(6), access="r"
        )
        software_revision: Final = ZCLAttributeDef(
            id=0x0017, type=t.LimitedLVBytes(6), access="r"
        )
        product_type_name: Final = ZCLAttributeDef(
            id=0x0018, type=t.LVBytesSize2, access="r"
        )
        product_type_id: Final = ZCLAttributeDef(id=0x0019, type=t.uint16_t, access="r")
        ceced_specification_version: Final = ZCLAttributeDef(
            id=0x001A, type=t.uint8_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class MeterIdentification(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0B01
    name: Final = "Meter Identification"
    ep_attribute: Final = "meter_id"

    class AttributeDefs(BaseAttributeDefs):
        company_name: Final = ZCLAttributeDef(
            id=0x0000, type=t.LimitedCharString(16), access="r", mandatory=True
        )
        meter_type_id: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        data_quality_id: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint16_t, access="r", mandatory=True
        )
        customer_name: Final = ZCLAttributeDef(
            id=0x0005, type=t.LimitedCharString(16), access="rw"
        )
        model: Final = ZCLAttributeDef(id=0x0006, type=t.LimitedLVBytes(16), access="r")
        part_number: Final = ZCLAttributeDef(
            id=0x0007, type=t.LimitedLVBytes(16), access="r"
        )
        product_revision: Final = ZCLAttributeDef(
            id=0x0008, type=t.LimitedLVBytes(6), access="r"
        )
        software_revision: Final = ZCLAttributeDef(
            id=0x000A, type=t.LimitedLVBytes(6), access="r"
        )
        utility_name: Final = ZCLAttributeDef(
            id=0x000B, type=t.LimitedCharString(16), access="r"
        )
        pod: Final = ZCLAttributeDef(
            id=0x000C, type=t.LimitedCharString(16), access="r", mandatory=True
        )
        available_power: Final = ZCLAttributeDef(
            id=0x000D, type=t.int24s, access="r", mandatory=True
        )
        power_threshold: Final = ZCLAttributeDef(
            id=0x000E, type=t.int24s, access="r", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class ApplianceEventAlerts(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0B02
    name: Final = "Appliance Event Alerts"
    ep_attribute: Final = "appliance_event"

    class AttributeDefs(BaseAttributeDefs):
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        get_alerts: Final = ZCLCommandDef(id=0x00, schema={}, direction=False)

    class ClientCommandDefs(BaseCommandDefs):
        get_alerts_response: Final = ZCLCommandDef(id=0x00, schema={}, direction=True)
        alerts_notification: Final = ZCLCommandDef(id=0x01, schema={}, direction=False)
        event_notification: Final = ZCLCommandDef(id=0x02, schema={}, direction=False)


class ApplianceStatistics(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0B03
    name: Final = "Appliance Statistics"
    ep_attribute: Final = "appliance_stats"

    class AttributeDefs(BaseAttributeDefs):
        log_max_size: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint32_t, access="r", mandatory=True
        )
        log_queue_max_size: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint8_t, access="r", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        log: Final = ZCLCommandDef(id=0x00, schema={}, direction=False)
        log_queue: Final = ZCLCommandDef(id=0x01, schema={}, direction=False)

    class ClientCommandDefs(BaseCommandDefs):
        log_notification: Final = ZCLCommandDef(id=0x00, schema={}, direction=False)
        log_response: Final = ZCLCommandDef(id=0x01, schema={}, direction=True)
        log_queue_response: Final = ZCLCommandDef(id=0x02, schema={}, direction=True)
        statistics_available: Final = ZCLCommandDef(id=0x03, schema={}, direction=False)


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


class ElectricalMeasurement(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0B04
    name: Final = "Electrical Measurement"
    ep_attribute: Final = "electrical_measurement"

    MeasurementType: Final = MeasurementType
    DCOverloadAlarmMark: Final = DCOverloadAlarmMark
    ACAlarmsMask: Final = ACAlarmsMask

    class AttributeDefs(BaseAttributeDefs):
        # Basic Information
        measurement_type: Final = ZCLAttributeDef(
            id=0x0000, type=MeasurementType, access="r", mandatory=True
        )
        # DC Measurement
        dc_voltage: Final = ZCLAttributeDef(id=0x0100, type=t.int16s, access="rp")
        dc_voltage_min: Final = ZCLAttributeDef(id=0x0101, type=t.int16s, access="r")
        dc_voltage_max: Final = ZCLAttributeDef(id=0x0102, type=t.int16s, access="r")
        dc_current: Final = ZCLAttributeDef(id=0x0103, type=t.int16s, access="rp")
        dc_current_min: Final = ZCLAttributeDef(id=0x0104, type=t.int16s, access="r")
        dc_current_max: Final = ZCLAttributeDef(id=0x0105, type=t.int16s, access="r")
        dc_power: Final = ZCLAttributeDef(id=0x0106, type=t.int16s, access="rp")
        dc_power_min: Final = ZCLAttributeDef(id=0x0107, type=t.int16s, access="r")
        dc_power_max: Final = ZCLAttributeDef(id=0x0108, type=t.int16s, access="r")
        # DC Formatting
        dc_voltage_multiplier: Final = ZCLAttributeDef(
            id=0x0200, type=t.uint16_t, access="rp"
        )
        dc_voltage_divisor: Final = ZCLAttributeDef(
            id=0x0201, type=t.uint16_t, access="rp"
        )
        dc_current_multiplier: Final = ZCLAttributeDef(
            id=0x0202, type=t.uint16_t, access="rp"
        )
        dc_current_divisor: Final = ZCLAttributeDef(
            id=0x0203, type=t.uint16_t, access="rp"
        )
        dc_power_multiplier: Final = ZCLAttributeDef(
            id=0x0204, type=t.uint16_t, access="rp"
        )
        dc_power_divisor: Final = ZCLAttributeDef(
            id=0x0205, type=t.uint16_t, access="rp"
        )
        # AC (Non-phase Specific) Measurements
        ac_frequency: Final = ZCLAttributeDef(id=0x0300, type=t.uint16_t, access="rp")
        ac_frequency_min: Final = ZCLAttributeDef(
            id=0x0301, type=t.uint16_t, access="r"
        )
        ac_frequency_max: Final = ZCLAttributeDef(
            id=0x0302, type=t.uint16_t, access="r"
        )
        neutral_current: Final = ZCLAttributeDef(
            id=0x0303, type=t.uint16_t, access="rp"
        )
        total_active_power: Final = ZCLAttributeDef(
            id=0x0304, type=t.int32s, access="rp"
        )
        total_reactive_power: Final = ZCLAttributeDef(
            id=0x0305, type=t.int32s, access="rp"
        )
        total_apparent_power: Final = ZCLAttributeDef(
            id=0x0306, type=t.uint32_t, access="rp"
        )
        meas1st_harmonic_current: Final = ZCLAttributeDef(
            id=0x0307, type=t.int16s, access="rp"
        )
        meas3rd_harmonic_current: Final = ZCLAttributeDef(
            id=0x0308, type=t.int16s, access="rp"
        )
        meas5th_harmonic_current: Final = ZCLAttributeDef(
            id=0x0309, type=t.int16s, access="rp"
        )
        meas7th_harmonic_current: Final = ZCLAttributeDef(
            id=0x030A, type=t.int16s, access="rp"
        )
        meas9th_harmonic_current: Final = ZCLAttributeDef(
            id=0x030B, type=t.int16s, access="rp"
        )
        meas11th_harmonic_current: Final = ZCLAttributeDef(
            id=0x030C, type=t.int16s, access="rp"
        )
        meas_phase1st_harmonic_current: Final = ZCLAttributeDef(
            id=0x030D, type=t.int16s, access="rp"
        )
        meas_phase3rd_harmonic_current: Final = ZCLAttributeDef(
            id=0x030E, type=t.int16s, access="rp"
        )
        meas_phase5th_harmonic_current: Final = ZCLAttributeDef(
            id=0x030F, type=t.int16s, access="rp"
        )
        meas_phase7th_harmonic_current: Final = ZCLAttributeDef(
            id=0x0310, type=t.int16s, access="rp"
        )
        meas_phase9th_harmonic_current: Final = ZCLAttributeDef(
            id=0x0311, type=t.int16s, access="rp"
        )
        meas_phase11th_harmonic_current: Final = ZCLAttributeDef(
            id=0x0312, type=t.int16s, access="rp"
        )
        # AC (Non-phase specific) Formatting
        ac_frequency_multiplier: Final = ZCLAttributeDef(
            id=0x0400, type=t.uint16_t, access="rp"
        )
        ac_frequency_divisor: Final = ZCLAttributeDef(
            id=0x0401, type=t.uint16_t, access="rp"
        )
        power_multiplier: Final = ZCLAttributeDef(
            id=0x0402, type=t.uint32_t, access="rp"
        )
        power_divisor: Final = ZCLAttributeDef(id=0x0403, type=t.uint32_t, access="rp")
        harmonic_current_multiplier: Final = ZCLAttributeDef(
            id=0x0404, type=t.int8s, access="rp"
        )
        phase_harmonic_current_multiplier: Final = ZCLAttributeDef(
            id=0x0405, type=t.int8s, access="rp"
        )
        # AC (Single Phase or Phase A) Measurements
        instantaneous_voltage: Final = ZCLAttributeDef(
            id=0x0500, type=t.int16s, access="rp"
        )
        instantaneous_line_current: Final = ZCLAttributeDef(
            id=0x0501, type=t.uint16_t, access="rp"
        )
        instantaneous_active_current: Final = ZCLAttributeDef(
            id=0x0502, type=t.int16s, access="rp"
        )
        instantaneous_reactive_current: Final = ZCLAttributeDef(
            id=0x0503, type=t.int16s, access="rp"
        )
        instantaneous_power: Final = ZCLAttributeDef(
            id=0x0504, type=t.int16s, access="rp"
        )
        rms_voltage: Final = ZCLAttributeDef(id=0x0505, type=t.uint16_t, access="rp")
        rms_voltage_min: Final = ZCLAttributeDef(id=0x0506, type=t.uint16_t, access="r")
        rms_voltage_max: Final = ZCLAttributeDef(id=0x0507, type=t.uint16_t, access="r")
        rms_current: Final = ZCLAttributeDef(id=0x0508, type=t.uint16_t, access="rp")
        rms_current_min: Final = ZCLAttributeDef(id=0x0509, type=t.uint16_t, access="r")
        rms_current_max: Final = ZCLAttributeDef(id=0x050A, type=t.uint16_t, access="r")
        active_power: Final = ZCLAttributeDef(id=0x050B, type=t.int16s, access="rp")
        active_power_min: Final = ZCLAttributeDef(id=0x050C, type=t.int16s, access="r")
        active_power_max: Final = ZCLAttributeDef(id=0x050D, type=t.int16s, access="r")
        reactive_power: Final = ZCLAttributeDef(id=0x050E, type=t.int16s, access="rp")
        apparent_power: Final = ZCLAttributeDef(id=0x050F, type=t.uint16_t, access="rp")
        power_factor: Final = ZCLAttributeDef(id=0x0510, type=t.int8s, access="r")
        average_rms_voltage_meas_period: Final = ZCLAttributeDef(
            id=0x0511, type=t.uint16_t, access="rw"
        )
        average_rms_over_voltage_counter: Final = ZCLAttributeDef(
            id=0x0512, type=t.uint16_t, access="rw"
        )
        average_rms_under_voltage_counter: Final = ZCLAttributeDef(
            id=0x0513, type=t.uint16_t, access="rw"
        )
        rms_extreme_over_voltage_period: Final = ZCLAttributeDef(
            id=0x0514, type=t.uint16_t, access="rw"
        )
        rms_extreme_under_voltage_period: Final = ZCLAttributeDef(
            id=0x0515, type=t.uint16_t, access="rw"
        )
        rms_voltage_sag_period: Final = ZCLAttributeDef(
            id=0x0516, type=t.uint16_t, access="rw"
        )
        rms_voltage_swell_period: Final = ZCLAttributeDef(
            id=0x0517, type=t.uint16_t, access="rw"
        )
        # AC Formatting
        ac_voltage_multiplier: Final = ZCLAttributeDef(
            id=0x0600, type=t.uint16_t, access="rp"
        )
        ac_voltage_divisor: Final = ZCLAttributeDef(
            id=0x0601, type=t.uint16_t, access="rp"
        )
        ac_current_multiplier: Final = ZCLAttributeDef(
            id=0x0602, type=t.uint16_t, access="rp"
        )
        ac_current_divisor: Final = ZCLAttributeDef(
            id=0x0603, type=t.uint16_t, access="rp"
        )
        ac_power_multiplier: Final = ZCLAttributeDef(
            id=0x0604, type=t.uint16_t, access="rp"
        )
        ac_power_divisor: Final = ZCLAttributeDef(
            id=0x0605, type=t.uint16_t, access="rp"
        )
        # DC Manufacturer Threshold Alarms
        dc_overload_alarms_mask: Final = ZCLAttributeDef(
            id=0x0700, type=DCOverloadAlarmMark, access="rp"
        )
        dc_voltage_overload: Final = ZCLAttributeDef(
            id=0x0701, type=t.int16s, access="rp"
        )
        dc_current_overload: Final = ZCLAttributeDef(
            id=0x0702, type=t.int16s, access="rp"
        )
        # AC Manufacturer Threshold Alarms
        ac_alarms_mask: Final = ZCLAttributeDef(
            id=0x0800, type=ACAlarmsMask, access="rw"
        )
        ac_voltage_overload: Final = ZCLAttributeDef(
            id=0x0801, type=t.int16s, access="r"
        )
        ac_current_overload: Final = ZCLAttributeDef(
            id=0x0802, type=t.int16s, access="r"
        )
        ac_active_power_overload: Final = ZCLAttributeDef(
            id=0x0803, type=t.int16s, access="r"
        )
        ac_reactive_power_overload: Final = ZCLAttributeDef(
            id=0x0804, type=t.int16s, access="r"
        )
        average_rms_over_voltage: Final = ZCLAttributeDef(
            id=0x0805, type=t.int16s, access="r"
        )
        average_rms_under_voltage: Final = ZCLAttributeDef(
            id=0x0806, type=t.int16s, access="r"
        )
        rms_extreme_over_voltage: Final = ZCLAttributeDef(
            id=0x0807, type=t.int16s, access="rw"
        )
        rms_extreme_under_voltage: Final = ZCLAttributeDef(
            id=0x0808, type=t.int16s, access="rw"
        )
        rms_voltage_sag: Final = ZCLAttributeDef(id=0x0809, type=t.int16s, access="rw")
        rms_voltage_swell: Final = ZCLAttributeDef(
            id=0x080A, type=t.int16s, access="rw"
        )
        # AC Phase B Measurements
        line_current_ph_b: Final = ZCLAttributeDef(
            id=0x0901, type=t.uint16_t, access="rp"
        )
        active_current_ph_b: Final = ZCLAttributeDef(
            id=0x0902, type=t.int16s, access="rp"
        )
        reactive_current_ph_b: Final = ZCLAttributeDef(
            id=0x0903, type=t.int16s, access="rp"
        )
        rms_voltage_ph_b: Final = ZCLAttributeDef(
            id=0x0905, type=t.uint16_t, access="rp"
        )
        rms_voltage_min_ph_b: Final = ZCLAttributeDef(
            id=0x0906, type=t.uint16_t, access="r"
        )
        rms_voltage_max_ph_b: Final = ZCLAttributeDef(
            id=0x0907, type=t.uint16_t, access="r"
        )
        rms_current_ph_b: Final = ZCLAttributeDef(
            id=0x0908, type=t.uint16_t, access="rp"
        )
        rms_current_min_ph_b: Final = ZCLAttributeDef(
            id=0x0909, type=t.uint16_t, access="r"
        )
        rms_current_max_ph_b: Final = ZCLAttributeDef(
            id=0x090A, type=t.uint16_t, access="r"
        )
        active_power_ph_b: Final = ZCLAttributeDef(
            id=0x090B, type=t.int16s, access="rp"
        )
        active_power_min_ph_b: Final = ZCLAttributeDef(
            id=0x090C, type=t.int16s, access="r"
        )
        active_power_max_ph_b: Final = ZCLAttributeDef(
            id=0x090D, type=t.int16s, access="r"
        )
        reactive_power_ph_b: Final = ZCLAttributeDef(
            id=0x090E, type=t.int16s, access="rp"
        )
        apparent_power_ph_b: Final = ZCLAttributeDef(
            id=0x090F, type=t.uint16_t, access="rp"
        )
        power_factor_ph_b: Final = ZCLAttributeDef(id=0x0910, type=t.int8s, access="r")
        average_rms_voltage_measure_period_ph_b: Final = ZCLAttributeDef(
            id=0x0911, type=t.uint16_t, access="rw"
        )
        average_rms_over_voltage_counter_ph_b: Final = ZCLAttributeDef(
            id=0x0912, type=t.uint16_t, access="rw"
        )
        average_under_voltage_counter_ph_b: Final = ZCLAttributeDef(
            id=0x0913, type=t.uint16_t, access="rw"
        )
        rms_extreme_over_voltage_period_ph_b: Final = ZCLAttributeDef(
            id=0x0914, type=t.uint16_t, access="rw"
        )
        rms_extreme_under_voltage_period_ph_b: Final = ZCLAttributeDef(
            id=0x0915, type=t.uint16_t, access="rw"
        )
        rms_voltage_sag_period_ph_b: Final = ZCLAttributeDef(
            id=0x0916, type=t.uint16_t, access="rw"
        )
        rms_voltage_swell_period_ph_b: Final = ZCLAttributeDef(
            id=0x0917, type=t.uint16_t, access="rw"
        )
        # AC Phase C Measurements
        line_current_ph_c: Final = ZCLAttributeDef(
            id=0x0A01, type=t.uint16_t, access="rp"
        )
        active_current_ph_c: Final = ZCLAttributeDef(
            id=0x0A02, type=t.int16s, access="rp"
        )
        reactive_current_ph_c: Final = ZCLAttributeDef(
            id=0x0A03, type=t.int16s, access="rp"
        )
        rms_voltage_ph_c: Final = ZCLAttributeDef(
            id=0x0A05, type=t.uint16_t, access="rp"
        )
        rms_voltage_min_ph_c: Final = ZCLAttributeDef(
            id=0x0A06, type=t.uint16_t, access="r"
        )
        rms_voltage_max_ph_c: Final = ZCLAttributeDef(
            id=0x0A07, type=t.uint16_t, access="r"
        )
        rms_current_ph_c: Final = ZCLAttributeDef(
            id=0x0A08, type=t.uint16_t, access="rp"
        )
        rms_current_min_ph_c: Final = ZCLAttributeDef(
            id=0x0A09, type=t.uint16_t, access="r"
        )
        rms_current_max_ph_c: Final = ZCLAttributeDef(
            id=0x0A0A, type=t.uint16_t, access="r"
        )
        active_power_ph_c: Final = ZCLAttributeDef(
            id=0x0A0B, type=t.int16s, access="rp"
        )
        active_power_min_ph_c: Final = ZCLAttributeDef(
            id=0x0A0C, type=t.int16s, access="r"
        )
        active_power_max_ph_c: Final = ZCLAttributeDef(
            id=0x0A0D, type=t.int16s, access="r"
        )
        reactive_power_ph_c: Final = ZCLAttributeDef(
            id=0x0A0E, type=t.int16s, access="rp"
        )
        apparent_power_ph_c: Final = ZCLAttributeDef(
            id=0x0A0F, type=t.uint16_t, access="rp"
        )
        power_factor_ph_c: Final = ZCLAttributeDef(id=0x0A10, type=t.int8s, access="r")
        average_rms_voltage_meas_period_ph_c: Final = ZCLAttributeDef(
            id=0x0A11, type=t.uint16_t, access="rw"
        )
        average_rms_over_voltage_counter_ph_c: Final = ZCLAttributeDef(
            id=0x0A12, type=t.uint16_t, access="rw"
        )
        average_under_voltage_counter_ph_c: Final = ZCLAttributeDef(
            id=0x0A13, type=t.uint16_t, access="rw"
        )
        rms_extreme_over_voltage_period_ph_c: Final = ZCLAttributeDef(
            id=0x0A14, type=t.uint16_t, access="rw"
        )
        rms_extreme_under_voltage_period_ph_c: Final = ZCLAttributeDef(
            id=0x0A15, type=t.uint16_t, access="rw"
        )
        rms_voltage_sag_period_ph_c: Final = ZCLAttributeDef(
            id=0x0A16, type=t.uint16_t, access="rw"
        )
        rms_voltage_swell_period_ph_c: Final = ZCLAttributeDef(
            id=0x0A17, type=t.uint16_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        get_profile_info: Final = ZCLCommandDef(id=0x00, schema={}, direction=False)
        get_measurement_profile: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=False
        )

    class ClientCommandDefs(BaseCommandDefs):
        get_profile_info_response: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=True
        )
        get_measurement_profile_response: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=True
        )


class Diagnostic(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0B05
    ep_attribute: Final = "diagnostic"

    class AttributeDefs(BaseAttributeDefs):
        # Hardware Information
        number_of_resets: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="r"
        )
        persistent_memory_writes: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r"
        )
        # Stack/Network Information
        mac_rx_bcast: Final = ZCLAttributeDef(id=0x0100, type=t.uint32_t, access="r")
        mac_tx_bcast: Final = ZCLAttributeDef(id=0x0101, type=t.uint32_t, access="r")
        mac_rx_ucast: Final = ZCLAttributeDef(id=0x0102, type=t.uint32_t, access="r")
        mac_tx_ucast: Final = ZCLAttributeDef(id=0x0103, type=t.uint32_t, access="r")
        mac_tx_ucast_retry: Final = ZCLAttributeDef(
            id=0x0104, type=t.uint16_t, access="r"
        )
        mac_tx_ucast_fail: Final = ZCLAttributeDef(
            id=0x0105, type=t.uint16_t, access="r"
        )
        aps_rx_bcast: Final = ZCLAttributeDef(id=0x0106, type=t.uint16_t, access="r")
        aps_tx_bcast: Final = ZCLAttributeDef(id=0x0107, type=t.uint16_t, access="r")
        aps_rx_ucast: Final = ZCLAttributeDef(id=0x0108, type=t.uint16_t, access="r")
        aps_tx_ucast_success: Final = ZCLAttributeDef(
            id=0x0109, type=t.uint16_t, access="r"
        )
        aps_tx_ucast_retry: Final = ZCLAttributeDef(
            id=0x010A, type=t.uint16_t, access="r"
        )
        aps_tx_ucast_fail: Final = ZCLAttributeDef(
            id=0x010B, type=t.uint16_t, access="r"
        )
        route_disc_initiated: Final = ZCLAttributeDef(
            id=0x010C, type=t.uint16_t, access="r"
        )
        neighbor_added: Final = ZCLAttributeDef(id=0x010D, type=t.uint16_t, access="r")
        neighbor_removed: Final = ZCLAttributeDef(
            id=0x010E, type=t.uint16_t, access="r"
        )
        neighbor_stale: Final = ZCLAttributeDef(id=0x010F, type=t.uint16_t, access="r")
        join_indication: Final = ZCLAttributeDef(id=0x0110, type=t.uint16_t, access="r")
        child_moved: Final = ZCLAttributeDef(id=0x0111, type=t.uint16_t, access="r")
        nwk_fc_failure: Final = ZCLAttributeDef(id=0x0112, type=t.uint16_t, access="r")
        aps_fc_failure: Final = ZCLAttributeDef(id=0x0113, type=t.uint16_t, access="r")
        aps_unauthorized_key: Final = ZCLAttributeDef(
            id=0x0114, type=t.uint16_t, access="r"
        )
        nwk_decrypt_failures: Final = ZCLAttributeDef(
            id=0x0115, type=t.uint16_t, access="r"
        )
        aps_decrypt_failures: Final = ZCLAttributeDef(
            id=0x0116, type=t.uint16_t, access="r"
        )
        packet_buffer_allocate_failures: Final = ZCLAttributeDef(
            id=0x0117, type=t.uint16_t, access="r"
        )
        relayed_ucast: Final = ZCLAttributeDef(id=0x0118, type=t.uint16_t, access="r")
        phy_to_mac_queue_limit_reached: Final = ZCLAttributeDef(
            id=0x0119, type=t.uint16_t, access="r"
        )
        packet_validate_drop_count: Final = ZCLAttributeDef(
            id=0x011A, type=t.uint16_t, access="r"
        )
        average_mac_retry_per_aps_message_sent: Final = ZCLAttributeDef(
            id=0x011B, type=t.uint16_t, access="r"
        )
        last_message_lqi: Final = ZCLAttributeDef(id=0x011C, type=t.uint8_t, access="r")
        last_message_rssi: Final = ZCLAttributeDef(id=0x011D, type=t.int8s, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR
