import zigpy.types as t

# Table 51
class GPDeviceType(t.enum8):
    SWITCH_SIMPLE_ONE_STATE = 0x00
    SWITCH_SIMPLE_TWO_STATE = 0x01
    SWITCH_ON_OFF = 0x02
    SWITCH_LEVEL_CONTROL = 0x03
    SENSOR_SIMPLE = 0x04
    SWITCH_ADVANCED_ONE_STATE = 0x05
    SWITCH_ADVANCED_TWO_STATE = 0x06
    SWITCH_GENERIC = 0x07

    SWITCH_COLOR_DIMMER = 0x10
    SENSOR_LIGHT = 0x11
    SENSOR_OCCUPANCY = 0x12

    DOOR_LOCK_CONTROLLER = 0x20

    SENSOR_TEMPERATURE = 0x30
    SENSOR_PRESSURE = 0x31
    SENSOR_FLOW = 0x32
    SENSOR_ENVIRONMENT_INDOOR = 0x33

class GPCommand(t.enum8):
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
    AttributeReporting = 0xA0
    ManufacturerSpecificReporting = 0xA1
    Commissioning = 0xe0
    CommissionSuccess = 0xe2
    ChannelSearch = 0xe3
    CommissioningResponse = 0xf0
    ChannelSearchResponse = 0xf3

GPDeviceDescriptors = {
    GPDeviceType.SWITCH_SIMPLE_ONE_STATE: "Simple Generic 1-state",
    GPDeviceType.SWITCH_SIMPLE_TWO_STATE: "Simple Generic 2-state",
    GPDeviceType.SWITCH_ON_OFF: "On/Off Switch",
    GPDeviceType.SWITCH_LEVEL_CONTROL: "Level Control Switch",
    GPDeviceType.SENSOR_SIMPLE: "Simple Sensor",
    GPDeviceType.SWITCH_ADVANCED_ONE_STATE: "Advanced Generic 1-state Switch",
    GPDeviceType.SWITCH_ADVANCED_TWO_STATE: "Advanced Generic 2-state Switch",
    GPDeviceType.SWITCH_GENERIC: "Generic Switch",
    GPDeviceType.SWITCH_COLOR_DIMMER: "Color Dimmer Switch",
    GPDeviceType.SENSOR_LIGHT: "Light Sensor",
    GPDeviceType.SENSOR_OCCUPANCY: "Occupancy Sensor",
    GPDeviceType.DOOR_LOCK_CONTROLLER: "Door Lock Controller",
    GPDeviceType.SENSOR_TEMPERATURE: "Temperature Sensor",
    GPDeviceType.SENSOR_PRESSURE: "Pressure Sensor",
    GPDeviceType.SENSOR_FLOW: "Flow Sensor",
    GPDeviceType.SENSOR_ENVIRONMENT_INDOOR: "Indoor Environment Sensor"
}
