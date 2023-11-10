from __future__ import annotations

import zigpy.types as t

PROFILE_ID = 41440

# Table 51
class GPDeviceType(t.enum16):
    SWITCH_SIMPLE_ONE_STATE = 0x00
    SWITCH_SIMPLE_TWO_STATE = 0x01
    SWITCH_ON_OFF = 0x02
    SWITCH_LEVEL_CONTROL = 0x03
    SENSOR_SIMPLE = 0x04
    SWITCH_ADVANCED_ONE_STATE = 0x05
    SWITCH_ADVANCED_TWO_STATE = 0x06

    SWITCH_COLOR_DIMMER = 0x10
    SENSOR_LIGHT = 0x11
    SENSOR_OCCUPANCY = 0x12

    DOOR_LOCK_CONTROLLER = 0x20

    SENSOR_TEMPERATURE = 0x30
    SENSOR_PRESSURE = 0x31
    SENSOR_FLOW = 0x32
    SENSOR_ENVIRONMENT_INDOOR = 0x33

# Infrastructure device types
# Table 15
class DeviceType(t.enum16):
    PROXY = 0x0060
    PROXY_BASIC = 0x0061
    TARGET_PLUS = 0x0062
    TARGET = 0x0063
    COMM_TOOL = 0x0064
    COMBO = 0x0065
    COMBO_BASIC = 0x0066


CLUSTERS = {
    DeviceType.PROXY: ([0x0021], [0x0021]),
    DeviceType.PROXY_BASIC: ([], [0x0021]),
    DeviceType.TARGET_PLUS: ([0x0021], [0x0021]),
    DeviceType.TARGET: ([0x0021], [0x0021]),
    DeviceType.COMM_TOOL: ([0x0021], []),
    DeviceType.COMBO: ([0x0021], [0x0021]),
    DeviceType.COMBO_BASIC: ([0x0021], [0x0021]),
}
