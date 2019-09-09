"""Measurement & Sensing Functional Domain"""

import zigpy.types as t
from zigpy.zcl import Cluster


class IlluminanceMeasurement(Cluster):
    cluster_id = 0x0400
    name = "Illuminance Measurement"
    ep_attribute = "illuminance"
    attributes = {
        # Illuminance Measurement Information
        0x0000: ("measured_value", t.uint16_t),
        0x0001: ("min_measured_value", t.uint16_t),
        0x0002: ("max_measured_value", t.uint16_t),
        0x0003: ("tolerance", t.uint16_t),
        0x0004: ("light_sensor_type", t.enum8),
    }
    server_commands = {}
    client_commands = {}


class IlluminanceLevelSensing(Cluster):
    cluster_id = 0x0401
    name = "Illuminance Level Sensing"
    ep_attribute = "illuminance_level"
    attributes = {
        # Illuminance Level Sensing Information
        0x0000: ("level_status", t.enum8),
        0x0001: ("light_sensor_type", t.enum8),
        # Illuminance Level Sensing Settings
        0x0010: ("illuminance_target_level", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class TemperatureMeasurement(Cluster):
    cluster_id = 0x0402
    name = "Temperature Measurement"
    ep_attribute = "temperature"
    attributes = {
        # Temperature Measurement Information
        0x0000: ("measured_value", t.int16s),
        0x0001: ("min_measured_value", t.int16s),
        0x0002: ("max_measured_value", t.int16s),
        0x0003: ("tolerance", t.uint16_t),
        # 0x0010: ('min_percent_change', UNKNOWN),
        # 0x0011: ('min_absolute_change', UNKNOWN),
    }
    server_commands = {}
    client_commands = {}


class PressureMeasurement(Cluster):
    cluster_id = 0x0403
    name = "Pressure Measurement"
    ep_attribute = "pressure"
    attributes = {
        # Pressure Measurement Information
        0x0000: ("measured_value", t.int16s),
        0x0001: ("min_measured_value", t.int16s),
        0x0002: ("max_measured_value", t.int16s),
        0x0003: ("tolerance", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class FlowMeasurement(Cluster):
    cluster_id = 0x0404
    name = "Flow Measurement"
    ep_attribute = "flow"
    attributes = {
        # Flow Measurement Information
        0x0000: ("measured_value", t.uint16_t),
        0x0001: ("min_measured_value", t.uint16_t),
        0x0002: ("max_measured_value", t.uint16_t),
        0x0003: ("tolerance", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class RelativeHumidity(Cluster):
    cluster_id = 0x0405
    name = "Relative Humidity Measurement"
    ep_attribute = "humidity"
    attributes = {
        # Relative Humidity Measurement Information
        0x0000: ("measured_value", t.uint16_t),
        0x0001: ("min_measured_value", t.uint16_t),
        0x0002: ("max_measured_value", t.uint16_t),
        0x0003: ("tolerance", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class OccupancySensing(Cluster):
    cluster_id = 0x0406
    name = "Occupancy Sensing"
    ep_attribute = "occupancy"
    attributes = {
        # Occupancy Sensor Information
        0x0000: ("occupancy", t.bitmap8),
        0x0001: ("occupancy_sensor_type", t.enum8),
        # PIR Configuration
        0x0010: ("pir_o_to_u_delay", t.uint16_t),
        0x0011: ("pir_u_to_o_delay", t.uint16_t),
        0x0012: ("pir_u_to_o_threshold", t.uint8_t),
        # Ultrasonic Configuration
        0x0020: ("ultrasonic_o_to_u_delay", t.uint16_t),
        0x0021: ("ultrasonic_u_to_o_delay", t.uint16_t),
        0x0022: ("ultrasonic_u_to_o_threshold", t.uint8_t),
    }
    server_commands = {}
    client_commands = {}
