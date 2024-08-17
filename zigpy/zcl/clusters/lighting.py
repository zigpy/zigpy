"""Lighting Functional Domain"""

from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    Direction as CommandDirection,
    ZCLAttributeDef,
    ZCLCommandDef,
)


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


class OptionsMask(t.bitmap8):
    Execute_if_off_present = 0b00000001


class Options(t.bitmap8):
    Execute_if_off = 0b00000001


class Color(Cluster):
    """Attributes and commands for controlling the color
    properties of a color-capable light
    """

    ColorMode: Final = ColorMode
    EnhancedColorMode: Final = EnhancedColorMode
    ColorCapabilities: Final = ColorCapabilities
    Direction: Final = Direction
    MoveMode: Final = MoveMode
    StepMode: Final = StepMode
    ColorLoopUpdateFlags: Final = ColorLoopUpdateFlags
    ColorLoopAction: Final = ColorLoopAction
    ColorLoopDirection: Final = ColorLoopDirection
    DriftCompensation: Final = DriftCompensation
    Options: Final = Options
    OptionsMask: Final = OptionsMask

    cluster_id: Final[t.uint16_t] = 0x0300
    name: Final = "Color Control"
    ep_attribute: Final = "light_color"

    class AttributeDefs(BaseAttributeDefs):
        current_hue: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t, access="rp")
        current_saturation: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint8_t, access="rps"
        )
        remaining_time: Final = ZCLAttributeDef(id=0x0002, type=t.uint16_t, access="r")
        current_x: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="rps")
        current_y: Final = ZCLAttributeDef(id=0x0004, type=t.uint16_t, access="rps")
        drift_compensation: Final = ZCLAttributeDef(
            id=0x0005, type=DriftCompensation, access="r"
        )
        compensation_text: Final = ZCLAttributeDef(
            id=0x0006, type=t.CharacterString, access="r"
        )
        color_temperature: Final = ZCLAttributeDef(
            id=0x0007, type=t.uint16_t, access="rps"
        )
        color_mode: Final = ZCLAttributeDef(
            id=0x0008, type=ColorMode, access="r", mandatory=True
        )
        options: Final = ZCLAttributeDef(
            id=0x000F, type=Options, access="rw", mandatory=True
        )
        # Defined Primaries Information
        num_primaries: Final = ZCLAttributeDef(id=0x0010, type=t.uint8_t, access="r")
        primary1_x: Final = ZCLAttributeDef(id=0x0011, type=t.uint16_t, access="r")
        primary1_y: Final = ZCLAttributeDef(id=0x0012, type=t.uint16_t, access="r")
        primary1_intensity: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint8_t, access="r"
        )
        primary2_x: Final = ZCLAttributeDef(id=0x0015, type=t.uint16_t, access="r")
        primary2_y: Final = ZCLAttributeDef(id=0x0016, type=t.uint16_t, access="r")
        primary2_intensity: Final = ZCLAttributeDef(
            id=0x0017, type=t.uint8_t, access="r"
        )
        primary3_x: Final = ZCLAttributeDef(id=0x0019, type=t.uint16_t, access="r")
        primary3_y: Final = ZCLAttributeDef(id=0x001A, type=t.uint16_t, access="r")
        primary3_intensity: Final = ZCLAttributeDef(
            id=0x001B, type=t.uint8_t, access="r"
        )
        # Additional Defined Primaries Information
        primary4_x: Final = ZCLAttributeDef(id=0x0020, type=t.uint16_t, access="r")
        primary4_y: Final = ZCLAttributeDef(id=0x0021, type=t.uint16_t, access="r")
        primary4_intensity: Final = ZCLAttributeDef(
            id=0x0022, type=t.uint8_t, access="r"
        )
        primary5_x: Final = ZCLAttributeDef(id=0x0024, type=t.uint16_t, access="r")
        primary5_y: Final = ZCLAttributeDef(id=0x0025, type=t.uint16_t, access="r")
        primary5_intensity: Final = ZCLAttributeDef(
            id=0x0026, type=t.uint8_t, access="r"
        )
        primary6_x: Final = ZCLAttributeDef(id=0x0028, type=t.uint16_t, access="r")
        primary6_y: Final = ZCLAttributeDef(id=0x0029, type=t.uint16_t, access="r")
        primary6_intensity: Final = ZCLAttributeDef(
            id=0x002A, type=t.uint8_t, access="r"
        )
        # Defined Color Point Settings
        white_point_x: Final = ZCLAttributeDef(id=0x0030, type=t.uint16_t, access="r")
        white_point_y: Final = ZCLAttributeDef(id=0x0031, type=t.uint16_t, access="r")
        color_point_r_x: Final = ZCLAttributeDef(id=0x0032, type=t.uint16_t, access="r")
        color_point_r_y: Final = ZCLAttributeDef(id=0x0033, type=t.uint16_t, access="r")
        color_point_r_intensity: Final = ZCLAttributeDef(
            id=0x0034, type=t.uint8_t, access="r"
        )
        color_point_g_x: Final = ZCLAttributeDef(id=0x0036, type=t.uint16_t, access="r")
        color_point_g_y: Final = ZCLAttributeDef(id=0x0037, type=t.uint16_t, access="r")
        color_point_g_intensity: Final = ZCLAttributeDef(
            id=0x0038, type=t.uint8_t, access="r"
        )
        color_point_b_x: Final = ZCLAttributeDef(id=0x003A, type=t.uint16_t, access="r")
        color_point_b_y: Final = ZCLAttributeDef(id=0x003B, type=t.uint16_t, access="r")
        color_point_b_intensity: Final = ZCLAttributeDef(
            id=0x003C, type=t.uint8_t, access="r"
        )
        # ...
        enhanced_current_hue: Final = ZCLAttributeDef(
            id=0x4000, type=t.uint16_t, access="rs"
        )
        enhanced_color_mode: Final = ZCLAttributeDef(
            id=0x4001, type=EnhancedColorMode, access="r", mandatory=True
        )
        color_loop_active: Final = ZCLAttributeDef(
            id=0x4002, type=t.uint8_t, access="rs"
        )
        color_loop_direction: Final = ZCLAttributeDef(
            id=0x4003, type=t.uint8_t, access="rs"
        )
        color_loop_time: Final = ZCLAttributeDef(
            id=0x4004, type=t.uint16_t, access="rs"
        )
        color_loop_start_enhanced_hue: Final = ZCLAttributeDef(
            id=0x4005, type=t.uint16_t, access="r"
        )
        color_loop_stored_enhanced_hue: Final = ZCLAttributeDef(
            id=0x4006, type=t.uint16_t, access="r"
        )
        color_capabilities: Final = ZCLAttributeDef(
            id=0x400A, type=ColorCapabilities, access="r", mandatory=True
        )
        color_temp_physical_min: Final = ZCLAttributeDef(
            id=0x400B, type=t.uint16_t, access="r"
        )
        color_temp_physical_max: Final = ZCLAttributeDef(
            id=0x400C, type=t.uint16_t, access="r"
        )
        couple_color_temp_to_level_min: Final = ZCLAttributeDef(
            id=0x400D, type=t.uint16_t, access="r"
        )
        start_up_color_temperature: Final = ZCLAttributeDef(
            id=0x4010, type=t.uint16_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        move_to_hue: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "hue": t.uint8_t,
                "direction": Direction,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_hue: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "move_mode": MoveMode,
                "rate": t.uint8_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        step_hue: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "step_mode": StepMode,
                "step_size": t.uint8_t,
                "transition_time": t.uint8_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_to_saturation: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "saturation": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_saturation: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "move_mode": MoveMode,
                "rate": t.uint8_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        step_saturation: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "step_mode": StepMode,
                "step_size": t.uint8_t,
                "transition_time": t.uint8_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_to_hue_and_saturation: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "hue": t.uint8_t,
                "saturation": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_to_color: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "color_x": t.uint16_t,
                "color_y": t.uint16_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_color: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "rate_x": t.uint16_t,
                "rate_y": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        step_color: Final = ZCLCommandDef(
            id=0x09,
            schema={
                "step_x": t.uint16_t,
                "step_y": t.uint16_t,
                "duration": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_to_color_temp: Final = ZCLCommandDef(
            id=0x0A,
            schema={
                "color_temp_mireds": t.uint16_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        enhanced_move_to_hue: Final = ZCLCommandDef(
            id=0x40,
            schema={
                "enhanced_hue": t.uint16_t,
                "direction": Direction,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        enhanced_move_hue: Final = ZCLCommandDef(
            id=0x41,
            schema={
                "move_mode": MoveMode,
                "rate": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        enhanced_step_hue: Final = ZCLCommandDef(
            id=0x42,
            schema={
                "step_mode": StepMode,
                "step_size": t.uint16_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        enhanced_move_to_hue_and_saturation: Final = ZCLCommandDef(
            id=0x43,
            schema={
                "enhanced_hue": t.uint16_t,
                "saturation": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        color_loop_set: Final = ZCLCommandDef(
            id=0x44,
            schema={
                "update_flags": ColorLoopUpdateFlags,
                "action": ColorLoopAction,
                "direction": ColorLoopDirection,
                "time": t.uint16_t,
                "start_hue": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        stop_move_step: Final = ZCLCommandDef(
            id=0x47,
            schema={
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        move_color_temp: Final = ZCLCommandDef(
            id=0x4B,
            schema={
                "move_mode": MoveMode,
                "rate": t.uint16_t,
                "color_temp_min_mireds": t.uint16_t,
                "color_temp_max_mireds": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )
        step_color_temp: Final = ZCLCommandDef(
            id=0x4C,
            schema={
                "step_mode": StepMode,
                "step_size": t.uint16_t,
                "transition_time": t.uint16_t,
                "color_temp_min_mireds": t.uint16_t,
                "color_temp_max_mireds": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=CommandDirection.Client_to_Server,
        )


class BallastStatus(t.bitmap8):
    Non_operational = 0b00000001
    Lamp_failure = 0b00000010


class LampAlarmMode(t.bitmap8):
    Lamp_burn_hours = 0b00000001


class Ballast(Cluster):
    """Attributes and commands for configuring a lighting
    ballast
    """

    BallastStatus: Final = BallastStatus
    LampAlarmMode: Final = LampAlarmMode

    cluster_id: Final[t.uint16_t] = 0x0301
    ep_attribute: Final = "light_ballast"

    class AttributeDefs(BaseAttributeDefs):
        physical_min_level: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        physical_max_level: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint8_t, access="r", mandatory=True
        )
        ballast_status: Final = ZCLAttributeDef(
            id=0x0002, type=BallastStatus, access="r"
        )
        # Ballast Settings
        min_level: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint8_t, access="rw", mandatory=True
        )
        max_level: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint8_t, access="rw", mandatory=True
        )
        power_on_level: Final = ZCLAttributeDef(id=0x0012, type=t.uint8_t, access="rw")
        power_on_fade_time: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint16_t, access="rw"
        )
        intrinsic_ballast_factor: Final = ZCLAttributeDef(
            id=0x0014, type=t.uint8_t, access="rw"
        )
        ballast_factor_adjustment: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint8_t, access="rw"
        )
        # Lamp Information
        lamp_quantity: Final = ZCLAttributeDef(id=0x0020, type=t.uint8_t, access="r")
        # Lamp Settings
        lamp_type: Final = ZCLAttributeDef(
            id=0x0030, type=t.LimitedCharString(16), access="rw"
        )
        lamp_manufacturer: Final = ZCLAttributeDef(
            id=0x0031, type=t.LimitedCharString(16), access="rw"
        )
        lamp_rated_hours: Final = ZCLAttributeDef(
            id=0x0032, type=t.uint24_t, access="rw"
        )
        lamp_burn_hours: Final = ZCLAttributeDef(
            id=0x0033, type=t.uint24_t, access="rw"
        )
        lamp_alarm_mode: Final = ZCLAttributeDef(
            id=0x0034, type=LampAlarmMode, access="rw"
        )
        lamp_burn_hours_trip_point: Final = ZCLAttributeDef(
            id=0x0035, type=t.uint24_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR
