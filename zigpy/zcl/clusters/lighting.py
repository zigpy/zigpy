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
        0x0000: ("current_hue", t.uint8_t),
        0x0001: ("current_saturation", t.uint8_t),
        0x0002: ("remaining_time", t.uint16_t),
        0x0003: ("current_x", t.uint16_t),
        0x0004: ("current_y", t.uint16_t),
        0x0005: ("drift_compensation", DriftCompensation),
        0x0006: ("compensation_text", t.CharacterString),
        0x0007: ("color_temperature", t.uint16_t),
        0x0008: ("color_mode", t.enum8),
        0x000F: ("options", Options),
        # Defined Primaries Information
        0x0010: ("num_primaries", t.uint8_t),
        0x0011: ("primary1_x", t.uint16_t),
        0x0012: ("primary1_y", t.uint16_t),
        0x0013: ("primary1_intensity", t.uint8_t),
        0x0015: ("primary2_x", t.uint16_t),
        0x0016: ("primary2_y", t.uint16_t),
        0x0017: ("primary2_intensity", t.uint8_t),
        0x0019: ("primary3_x", t.uint16_t),
        0x001A: ("primary3_y", t.uint16_t),
        0x001B: ("primary3_intensity", t.uint8_t),
        # Additional Defined Primaries Information
        0x0020: ("primary4_x", t.uint16_t),
        0x0021: ("primary4_y", t.uint16_t),
        0x0022: ("primary4_intensity", t.uint8_t),
        0x0024: ("primary5_x", t.uint16_t),
        0x0025: ("primary5_y", t.uint16_t),
        0x0026: ("primary5_intensity", t.uint8_t),
        0x0028: ("primary6_x", t.uint16_t),
        0x0029: ("primary6_y", t.uint16_t),
        0x002A: ("primary6_intensity", t.uint8_t),
        # Defined Color Point Settings
        0x0030: ("white_point_x", t.uint16_t),
        0x0031: ("white_point_y", t.uint16_t),
        0x0032: ("color_point_r_x", t.uint16_t),
        0x0033: ("color_point_r_y", t.uint16_t),
        0x0034: ("color_point_r_intensity", t.uint8_t),
        0x0036: ("color_point_g_x", t.uint16_t),
        0x0037: ("color_point_g_y", t.uint16_t),
        0x0038: ("color_point_g_intensity", t.uint8_t),
        0x003A: ("color_point_b_x", t.uint16_t),
        0x003B: ("color_point_b_y", t.uint16_t),
        0x003C: ("color_point_b_intensity", t.uint8_t),
        # ...
        0x4000: ("enhanced_current_hue", t.uint16_t),
        0x4001: ("enhanced_color_mode", EnhancedColorMode),
        0x4002: ("color_loop_active", t.uint8_t),
        0x4003: ("color_loop_direction", t.uint8_t),
        0x4004: ("color_loop_time", t.uint16_t),
        0x4005: ("color_loop_start_enhanced_hue", t.uint16_t),
        0x4006: ("color_loop_stored_enhanced_hue", t.uint16_t),
        0x400A: ("color_capabilities", ColorCapabilities),
        0x400B: ("color_temp_physical_min", t.uint16_t),
        0x400C: ("color_temp_physical_max", t.uint16_t),
        0x400D: ("couple_color_temp_to_level_min", t.uint16_t),
        0x4010: ("start_up_color_temperature", t.uint16_t),
        0xFFFD: ("cluster_revision", t.uint16_t),
        0xFFFE: ("attr_reporting_status", foundation.AttributeReportingStatus),
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
        0x0000: ("physical_min_level", t.uint8_t),
        0x0001: ("physical_max_level", t.uint8_t),
        0x0002: ("ballast_status", BallastStatus),
        # Ballast Settings
        0x0010: ("min_level", t.uint8_t),
        0x0011: ("max_level", t.uint8_t),
        0x0012: ("power_on_level", t.uint8_t),
        0x0013: ("power_on_fade_time", t.uint16_t),
        0x0014: ("intrinsic_ballast_factor", t.uint8_t),
        0x0015: ("ballast_factor_adjustment", t.uint8_t),
        # Lamp Information
        0x0020: ("lamp_quantity", t.uint8_t),
        # Lamp Settings
        0x0030: ("lamp_type", t.LimitedCharString(16)),
        0x0031: ("lamp_manufacturer", t.LimitedCharString(16)),
        0x0032: ("lamp_rated_hours", t.uint24_t),
        0x0033: ("lamp_burn_hours", t.uint24_t),
        0x0034: ("lamp_alarm_mode", LampAlarmMode),
        0x0035: ("lamp_burn_hours_trip_point", t.uint24_t),
        0xFFFD: ("cluster_revision", t.uint16_t),
        0xFFFE: ("attr_reporting_status", foundation.AttributeReportingStatus),
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
