"""Lighting Functional Domain"""

from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class Color(Cluster):
    """Attributes and commands for controlling the color
    properties of a color-capable light"""

    class ColorMode(t.enum8):
        Hue_and_saturation = 0x00
        X_and_Y = 0x01
        Color_temperature = 0x02

    class EnhancedColorMode(t.enum8):
        Hue_and_saturation = 0x00
        X_and_Y = 0x01
        Color_temperature = 0x02
        Enhanced_hue_and_saturation = 0x03

    class ColorCapabilities(t.bitmap16):
        Hue_and_saturation = 0b00000000_00000001
        Enhanced_hue = 0b00000000_00000010
        Color_loop = 0b00000000_00000100
        XY_attributes = 0b00000000_00001000
        Color_temperature = 0b00000000_00010000

    class Direction(t.enum8):
        Shortest_distance = 0x00
        Longest_distance = 0x01
        Up = 0x02
        Down = 0x03

    class MoveMode(t.enum8):
        Stop = 0x00
        Up = 0x01
        Down = 0x03

    class StepMode(t.enum8):
        Up = 0x01
        Down = 0x03

    class ColorLoopUpdateFlags(t.bitmap8):
        Action = 0b0000_0001
        Direction = 0b0000_0010
        Time = 0b0000_0100
        Start_Hue = 0b0000_1000

    class ColorLoopAction(t.enum8):
        Deactivate = 0x00
        Activate_from_color_loop_hue = 0x01
        Activate_from_current_hue = 0x02

    class ColorLoopDirection(t.enum8):
        Decrement = 0x00
        Increment = 0x01

    class DriftCompensation(t.enum8):
        NONE = 0x00
        Other_or_unknown = 0x01
        Temperature_monitoring = 0x02
        Luminance_monitoring = 0x03
        Color_monitoring = 0x03

    class Options(t.bitmap8):
        Execute_if_off = 0b00000001

    cluster_id = 0x0300
    name = "Color Control"
    ep_attribute = "light_color"
    attributes: dict[int, ZCLAttributeDef] = {
        # Color Information
        0x0000: ZCLAttributeDef("current_hue", type=t.uint8_t, access="rp"),
        0x0001: ZCLAttributeDef("current_saturation", type=t.uint8_t, access="rps"),
        0x0002: ZCLAttributeDef("remaining_time", type=t.uint16_t, access="r"),
        0x0003: ZCLAttributeDef("current_x", type=t.uint16_t, access="rps"),
        0x0004: ZCLAttributeDef("current_y", type=t.uint16_t, access="rps"),
        0x0005: ZCLAttributeDef(
            "drift_compensation", type=DriftCompensation, access="r"
        ),
        0x0006: ZCLAttributeDef(
            "compensation_text", type=t.CharacterString, access="r"
        ),
        0x0007: ZCLAttributeDef("color_temperature", type=t.uint16_t, access="rps"),
        0x0008: ZCLAttributeDef(
            "color_mode", type=ColorMode, access="r", mandatory=True
        ),
        0x000F: ZCLAttributeDef("options", type=Options, access="rw", mandatory=True),
        # Defined Primaries Information
        0x0010: ZCLAttributeDef("num_primaries", type=t.uint8_t, access="r"),
        0x0011: ZCLAttributeDef("primary1_x", type=t.uint16_t, access="r"),
        0x0012: ZCLAttributeDef("primary1_y", type=t.uint16_t, access="r"),
        0x0013: ZCLAttributeDef("primary1_intensity", type=t.uint8_t, access="r"),
        0x0015: ZCLAttributeDef("primary2_x", type=t.uint16_t, access="r"),
        0x0016: ZCLAttributeDef("primary2_y", type=t.uint16_t, access="r"),
        0x0017: ZCLAttributeDef("primary2_intensity", type=t.uint8_t, access="r"),
        0x0019: ZCLAttributeDef("primary3_x", type=t.uint16_t, access="r"),
        0x001A: ZCLAttributeDef("primary3_y", type=t.uint16_t, access="r"),
        0x001B: ZCLAttributeDef("primary3_intensity", type=t.uint8_t, access="r"),
        # Additional Defined Primaries Information
        0x0020: ZCLAttributeDef("primary4_x", type=t.uint16_t, access="r"),
        0x0021: ZCLAttributeDef("primary4_y", type=t.uint16_t, access="r"),
        0x0022: ZCLAttributeDef("primary4_intensity", type=t.uint8_t, access="r"),
        0x0024: ZCLAttributeDef("primary5_x", type=t.uint16_t, access="r"),
        0x0025: ZCLAttributeDef("primary5_y", type=t.uint16_t, access="r"),
        0x0026: ZCLAttributeDef("primary5_intensity", type=t.uint8_t, access="r"),
        0x0028: ZCLAttributeDef("primary6_x", type=t.uint16_t, access="r"),
        0x0029: ZCLAttributeDef("primary6_y", type=t.uint16_t, access="r"),
        0x002A: ZCLAttributeDef("primary6_intensity", type=t.uint8_t, access="r"),
        # Defined Color Point Settings
        0x0030: ZCLAttributeDef("white_point_x", type=t.uint16_t, access="r"),
        0x0031: ZCLAttributeDef("white_point_y", type=t.uint16_t, access="r"),
        0x0032: ZCLAttributeDef("color_point_r_x", type=t.uint16_t, access="r"),
        0x0033: ZCLAttributeDef("color_point_r_y", type=t.uint16_t, access="r"),
        0x0034: ZCLAttributeDef("color_point_r_intensity", type=t.uint8_t, access="r"),
        0x0036: ZCLAttributeDef("color_point_g_x", type=t.uint16_t, access="r"),
        0x0037: ZCLAttributeDef("color_point_g_y", type=t.uint16_t, access="r"),
        0x0038: ZCLAttributeDef("color_point_g_intensity", type=t.uint8_t, access="r"),
        0x003A: ZCLAttributeDef("color_point_b_x", type=t.uint16_t, access="r"),
        0x003B: ZCLAttributeDef("color_point_b_y", type=t.uint16_t, access="r"),
        0x003C: ZCLAttributeDef("color_point_b_intensity", type=t.uint8_t, access="r"),
        # ...
        0x4000: ZCLAttributeDef("enhanced_current_hue", type=t.uint16_t, access="rs"),
        0x4001: ZCLAttributeDef(
            "enhanced_color_mode", type=EnhancedColorMode, access="r", mandatory=True
        ),
        0x4002: ZCLAttributeDef("color_loop_active", type=t.uint8_t, access="rs"),
        0x4003: ZCLAttributeDef("color_loop_direction", type=t.uint8_t, access="rs"),
        0x4004: ZCLAttributeDef("color_loop_time", type=t.uint16_t, access="rs"),
        0x4005: ZCLAttributeDef(
            "color_loop_start_enhanced_hue", type=t.uint16_t, access="r"
        ),
        0x4006: ZCLAttributeDef(
            "color_loop_stored_enhanced_hue", type=t.uint16_t, access="r"
        ),
        0x400A: ZCLAttributeDef(
            "color_capabilities", type=ColorCapabilities, access="r", mandatory=True
        ),
        0x400B: ZCLAttributeDef("color_temp_physical_min", type=t.uint16_t, access="r"),
        0x400C: ZCLAttributeDef("color_temp_physical_max", type=t.uint16_t, access="r"),
        0x400D: ZCLAttributeDef(
            "couple_color_temp_to_level_min", type=t.uint16_t, access="r"
        ),
        0x4010: ZCLAttributeDef(
            "start_up_color_temperature", type=t.uint16_t, access="rw"
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {
        0x00: ZCLCommandDef(
            "move_to_hue",
            {
                "hue": t.uint8_t,
                "direction": Direction,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x01: ZCLCommandDef(
            "move_hue",
            {
                "move_mode": MoveMode,
                "rate": t.uint8_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x02: ZCLCommandDef(
            "step_hue",
            {
                "step_mode": StepMode,
                "step_size": t.uint8_t,
                "transition_time": t.uint8_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x03: ZCLCommandDef(
            "move_to_saturation",
            {
                "saturation": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x04: ZCLCommandDef(
            "move_saturation",
            {
                "move_mode": MoveMode,
                "rate": t.uint8_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x05: ZCLCommandDef(
            "step_saturation",
            {
                "step_mode": StepMode,
                "step_size": t.uint8_t,
                "transition_time": t.uint8_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x06: ZCLCommandDef(
            "move_to_hue_and_saturation",
            {
                "hue": t.uint8_t,
                "saturation": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x07: ZCLCommandDef(
            "move_to_color",
            {
                "color_x": t.uint16_t,
                "color_y": t.uint16_t,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x08: ZCLCommandDef(
            "move_color",
            {
                "rate_x": t.uint16_t,
                "rate_y": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x09: ZCLCommandDef(
            "step_color",
            {
                "step_x": t.uint16_t,
                "step_y": t.uint16_t,
                "duration": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x0A: ZCLCommandDef(
            "move_to_color_temp",
            {
                "color_temp_mireds": t.uint16_t,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x40: ZCLCommandDef(
            "enhanced_move_to_hue",
            {
                "enhanced_hue": t.uint16_t,
                "direction": Direction,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x41: ZCLCommandDef(
            "enhanced_move_hue",
            {
                "move_mode": MoveMode,
                "rate": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x42: ZCLCommandDef(
            "enhanced_step_hue",
            {
                "step_mode": StepMode,
                "step_size": t.uint16_t,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x43: ZCLCommandDef(
            "enhanced_move_to_hue_and_saturation",
            {
                "enhanced_hue": t.uint16_t,
                "saturation": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x44: ZCLCommandDef(
            "color_loop_set",
            {
                "update_flags": ColorLoopUpdateFlags,
                "action": ColorLoopAction,
                "direction": ColorLoopDirection,
                "time": t.uint16_t,
                "start_hue": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x47: ZCLCommandDef(
            "stop_move_step",
            {
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x4B: ZCLCommandDef(
            "move_color_temp",
            {
                "move_mode": MoveMode,
                "rate": t.uint16_t,
                "color_temp_min_mireds": t.uint16_t,
                "color_temp_max_mireds": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
        0x4C: ZCLCommandDef(
            "step_color_temp",
            {
                "step_mode": StepMode,
                "step_size": t.uint16_t,
                "transition_time": t.uint16_t,
                "color_temp_min_mireds": t.uint16_t,
                "color_temp_max_mireds": t.uint16_t,
                "options_mask?": t.bitmap8,
                "options_override?": t.bitmap8,
            },
            False,
        ),
    }
    client_commands: dict[int, ZCLCommandDef] = {}


class Ballast(Cluster):
    """Attributes and commands for configuring a lighting
    ballast"""

    class BallastStatus(t.bitmap8):
        Non_operational = 0b00000001
        Lamp_failure = 0b00000010

    class LampAlarmMode(t.bitmap8):
        Lamp_burn_hours = 0b00000001

    cluster_id = 0x0301
    ep_attribute = "light_ballast"
    attributes: dict[int, ZCLAttributeDef] = {
        # Ballast Information
        0x0000: ZCLAttributeDef(
            "physical_min_level", type=t.uint8_t, access="r", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "physical_max_level", type=t.uint8_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef("ballast_status", type=BallastStatus, access="r"),
        # Ballast Settings
        0x0010: ZCLAttributeDef(
            "min_level", type=t.uint8_t, access="rw", mandatory=True
        ),
        0x0011: ZCLAttributeDef(
            "max_level", type=t.uint8_t, access="rw", mandatory=True
        ),
        0x0012: ZCLAttributeDef("power_on_level", type=t.uint8_t, access="rw"),
        0x0013: ZCLAttributeDef("power_on_fade_time", type=t.uint16_t, access="rw"),
        0x0014: ZCLAttributeDef(
            "intrinsic_ballast_factor", type=t.uint8_t, access="rw"
        ),
        0x0015: ZCLAttributeDef(
            "ballast_factor_adjustment", type=t.uint8_t, access="rw"
        ),
        # Lamp Information
        0x0020: ZCLAttributeDef("lamp_quantity", type=t.uint8_t, access="r"),
        # Lamp Settings
        0x0030: ZCLAttributeDef("lamp_type", type=t.LimitedCharString(16), access="rw"),
        0x0031: ZCLAttributeDef(
            "lamp_manufacturer", type=t.LimitedCharString(16), access="rw"
        ),
        0x0032: ZCLAttributeDef("lamp_rated_hours", type=t.uint24_t, access="rw"),
        0x0033: ZCLAttributeDef("lamp_burn_hours", type=t.uint24_t, access="rw"),
        0x0034: ZCLAttributeDef("lamp_alarm_mode", type=LampAlarmMode, access="rw"),
        0x0035: ZCLAttributeDef(
            "lamp_burn_hours_trip_point", type=t.uint24_t, access="rw"
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
