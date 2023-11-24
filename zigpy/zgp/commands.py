import typing
import zigpy.types as t
from .types import *

from zigpy.zcl.clusters.closures import (
    DoorLock
)
from zigpy.zcl.clusters.measurement import (
    FlowMeasurement,
    IlluminanceMeasurement,
    OccupancySensing,
    PressureMeasurement,
    TemperatureMeasurement,
)
from zigpy.zcl.clusters.general import (
    Basic,
    Scenes,
    OnOff,
    LevelControl,
)
from zigpy.zcl.clusters.lighting import (
    Color
)
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
)

class GPCommand(basic.enum8):
    Identify = 0x00
    Scene0 = 0x10
    Scene1 = 0x11
    Scene2 = 0x12
    Scene3 = 0x13
    Scene4 = 0x14
    Scene5 = 0x15
    Scene6 = 0x16
    Scene7 = 0x17
    Scene8 = 0x18
    Scene9 = 0x19
    Scene10 = 0x1A
    Scene11 = 0x1B
    Scene12 = 0x1C
    Scene13 = 0x1D
    Scene14 = 0x1E
    Scene15 = 0x1F
    Off = 0x20
    On = 0x21
    Toggle = 0x22
    Release = 0x23
    MoveUp = 0x30
    MoveDown = 0x31
    StepUp = 0x32
    StepDown = 0x33
    LevelControlStop = 0x34
    MoveUpWithOnOff = 0x35
    MoveDownWithOnOff = 0x36
    StepUpWithOnOff = 0x37
    StepDownWithOnOff = 0x38
    MoveHueStop = 0x40
    MoveHueUp = 0x41
    MoveHueDown = 0x42
    StepHueUp = 0x43
    StepHueDown = 0x44
    MoveSaturationStop = 0x45
    MoveSaturationUp = 0x46
    MoveSaturationDown = 0x47
    StepSaturationUp = 0x48
    StepSaturationDown = 0x49
    MoveColor = 0x4A
    StepColor = 0x4B
    LockDoor = 0x50
    UnlockDoor = 0x51
    Press1of1 = 0x60
    Release1of1 = 0x61
    Press1of2 = 0x62
    Release1of2 = 0x63
    Press2of2 = 0x64
    Release2of2 = 0x65
    ShortPress1of1 = 0x66
    ShortPress1of2 = 0x67
    ShortPress2of2 = 0x68
    Commissioning = 0xe0

class GPCommandType(enum.Enum):
    CLUSTER_COMMAND = 0
    GREENPOWER_COMMAND = 1

class GPCommandDescriptor:
    def __init__(self, id: t.uint8_t, cluster_id: t.uint16_t | None = None, zcl_command_id: t.uint16_t | None = None, schema: dict | t.Struct = {}, values: dict = {}, command_type: GPCommandType = GPCommandType.CLUSTER_COMMAND):
        self.id = id
        self.schema = schema
        self.cluster_id = cluster_id
        self.zcl_command_id = zcl_command_id
        self.values = values
        self.command_type = command_type   

GPCommandToZCLMapping: typing.Dict[GPCommand, GPCommandDescriptor] = {
    GPCommand.Identify: GPCommandDescriptor(GPCommand.Identify),
    GPCommand.Scene0: GPCommandDescriptor(GPCommand.Scene0, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 0}),
    GPCommand.Scene1: GPCommandDescriptor(GPCommand.Scene1, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 1}),
    GPCommand.Scene2: GPCommandDescriptor(GPCommand.Scene2, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 2}),
    GPCommand.Scene3: GPCommandDescriptor(GPCommand.Scene3, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 3}),
    GPCommand.Scene4: GPCommandDescriptor(GPCommand.Scene4, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 4}),
    GPCommand.Scene5: GPCommandDescriptor(GPCommand.Scene5, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 5}),
    GPCommand.Scene6: GPCommandDescriptor(GPCommand.Scene6, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 6}),
    GPCommand.Scene7: GPCommandDescriptor(GPCommand.Scene7, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 7}),
    GPCommand.Scene8: GPCommandDescriptor(GPCommand.Scene8, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 8}),
    GPCommand.Scene9: GPCommandDescriptor(GPCommand.Scene9, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 9}),
    GPCommand.Scene10: GPCommandDescriptor(GPCommand.Scene10, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 10}),
    GPCommand.Scene11: GPCommandDescriptor(GPCommand.Scene11, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 11}),
    GPCommand.Scene12: GPCommandDescriptor(GPCommand.Scene12, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 12}),
    GPCommand.Scene13: GPCommandDescriptor(GPCommand.Scene13, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 13}),
    GPCommand.Scene14: GPCommandDescriptor(GPCommand.Scene14, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 14}),
    GPCommand.Scene15: GPCommandDescriptor(GPCommand.Scene15, Scenes.cluster_id, Scenes.ServerCommandDefs.view.id, {}, {"group_id": 0, "scene_id": 15}),
    GPCommand.Off: GPCommandDescriptor(GPCommand.Off, OnOff.cluster_id, OnOff.ServerCommandDefs.off.id),
    GPCommand.On: GPCommandDescriptor(GPCommand.On, OnOff.cluster_id, OnOff.ServerCommandDefs.on.id),
    GPCommand.Toggle: GPCommandDescriptor(GPCommand.Toggle, OnOff.cluster_id, OnOff.ServerCommandDefs.toggle.id),
    GPCommand.Release: GPCommandDescriptor(GPCommand.Release),
    GPCommand.MoveUp: GPCommandDescriptor(
        GPCommand.MoveUp, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.move.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": LevelControl.MoveMode.Up}
    ),
    GPCommand.MoveDown: GPCommandDescriptor(
        GPCommand.MoveDown, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.move.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": LevelControl.MoveMode.Down}
    ),
    GPCommand.StepUp: GPCommandDescriptor(
        GPCommand.StepUp, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.step.id, 
        {
            "step_size": t.uint8_t, 
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": LevelControl.StepMode.Up
        }
    ),
    GPCommand.StepDown: GPCommandDescriptor(
        GPCommand.StepDown, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.step.id, 
        {
            "step_size": t.uint8_t, 
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": LevelControl.StepMode.Down
        }
    ),
    GPCommand.LevelControlStop: GPCommandDescriptor(
        GPCommand.LevelControlStop,
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.stop_with_on_off.id
    ),
    GPCommand.MoveUpWithOnOff: GPCommandDescriptor(
        GPCommand.MoveUpWithOnOff, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.move_with_on_off.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": LevelControl.MoveMode.Up}
    ),
    GPCommand.MoveDownWithOnOff: GPCommandDescriptor(
        GPCommand.MoveDownWithOnOff, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.move_with_on_off.id, 
        {
            "rate?": t.uint8_t
        }, 
        {
            "move_mode": LevelControl.MoveMode.Down
        }
    ),
    GPCommand.StepUpWithOnOff: GPCommandDescriptor(
        GPCommand.StepUpWithOnOff, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.step_with_on_off.id, 
        {
            "step_size": t.uint8_t, 
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": LevelControl.StepMode.Up
        }
    ),
    GPCommand.StepDownWithOnOff: GPCommandDescriptor(
        GPCommand.StepDownWithOnOff, 
        LevelControl.cluster_id, 
        LevelControl.ServerCommandDefs.step_with_on_off.id, 
        {
            "step_size": t.uint8_t, 
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": LevelControl.StepMode.Down
        }),
    GPCommand.MoveHueStop: GPCommandDescriptor(
        GPCommand.MoveHueStop,
        Color.cluster_id,
        Color.ServerCommandDefs.stop_move_step
    ),
    GPCommand.MoveHueUp: GPCommandDescriptor(
        GPCommand.MoveHueUp, 
        Color.cluster_id, 
        Color.ServerCommandDefs.move_hue.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": Color.MoveMode.Up}
    ),
    GPCommand.MoveHueDown: GPCommandDescriptor(
        GPCommand.MoveHueDown, 
        Color.cluster_id, 
        Color.ServerCommandDefs.move_hue.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": Color.MoveMode.Down}
    ),
    GPCommand.StepHueUp: GPCommandDescriptor(
        GPCommand.StepHueUp, 
        Color.cluster_id, 
        Color.ServerCommandDefs.step_hue.id, 
        {
            "step_size": t.uint8_t,
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": Color.StepMode.Up
        }
    ),
    GPCommand.StepHueDown: GPCommandDescriptor(
        GPCommand.StepHueDown, 
        Color.cluster_id, 
        Color.ServerCommandDefs.step_hue.id, 
        {
            "step_size": t.uint8_t,
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": Color.StepMode.Down
        }
    ),
    GPCommand.MoveSaturationStop: GPCommandDescriptor(
        GPCommand.MoveSaturationStop,
        Color.cluster_id,
        Color.ServerCommandDefs.stop_move_step.id
    ),
    GPCommand.MoveSaturationUp: GPCommandDescriptor(
        GPCommand.MoveSaturationUp, 
        Color.cluster_id, 
        Color.ServerCommandDefs.move_saturation.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": Color.MoveMode.Up}
    ),
    GPCommand.MoveSaturationDown: GPCommandDescriptor(
        GPCommand.MoveSaturationDown, 
        Color.cluster_id, 
        Color.ServerCommandDefs.move_saturation.id, 
        {"rate?": t.uint8_t}, 
        {"move_mode": Color.MoveMode.Down}
    ),
    GPCommand.StepSaturationUp: GPCommandDescriptor(
        GPCommand.StepSaturationUp, 
        Color.cluster_id, 
        Color.ServerCommandDefs.step_saturation.id, 
        {
            "step_size": t.uint8_t,
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": Color.StepMode.Up
        }
    ),
    GPCommand.StepSaturationDown: GPCommandDescriptor(
        GPCommand.StepSaturationDown, 
        Color.cluster_id, 
        Color.ServerCommandDefs.step_saturation.id, 
        {
            "step_size": t.uint8_t,
            "transition_time?": t.uint16_t
        }, 
        {
            "step_mode": Color.StepMode.Down
        }
    ),
    GPCommand.MoveColor: GPCommandDescriptor(
        GPCommand.MoveColor,
        Color.cluster_id,
        Color.ServerCommandDefs.move_color.id,
        {
            "rate_x": t.uint16_t,
            "rate_y": t.uint16_t,
        }
    ),
    GPCommand.StepColor: GPCommandDescriptor(
        GPCommand.StepColor,
        Color.cluster_id,
        Color.ServerCommandDefs.step_color.id,
        {
            "step_x": t.int16s,
            "step_y": t.int16s,
            "transition_time?": t.uint16_t
        }
    ),
    GPCommand.LockDoor: GPCommandDescriptor(GPCommand.LockDoor, DoorLock.cluster_id, DoorLock.ServerCommandDefs.lock_door.id),
    GPCommand.UnlockDoor: GPCommandDescriptor(GPCommand.UnlockDoor, DoorLock.cluster_id, DoorLock.ServerCommandDefs.unlock_door.id),
    GPCommand.Press1of1: GPCommandDescriptor(GPCommand.Press1of1),
    GPCommand.Release1of1: GPCommandDescriptor(GPCommand.Release1of1),
    GPCommand.Press1of2: GPCommandDescriptor(GPCommand.Press1of2),
    GPCommand.Release1of2: GPCommandDescriptor(GPCommand.Release1of2),
    GPCommand.Press2of2: GPCommandDescriptor(GPCommand.Press2of2),
    GPCommand.Release2of2: GPCommandDescriptor(GPCommand.Release2of2),
    GPCommand.ShortPress1of1: GPCommandDescriptor(GPCommand.ShortPress1of1),
    GPCommand.ShortPress1of2: GPCommandDescriptor(GPCommand.ShortPress1of2),
    GPCommand.ShortPress2of2: GPCommandDescriptor(GPCommand.ShortPress2of2),
}
