import typing
import zigpy.zcl
from .types import *


from zigpy.zcl import Cluster, foundation
from zigpy.zcl.clusters.closures import (
    DoorLock
)
import zigpy.zcl.clusters.lighting
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

class GPDeviceTypeDescriptor:
    name: str
    in_clusters: typing.List[Cluster]
    out_clusters: typing.List[Cluster]
    def __init__(self, name: str, in_clusters: typing.List[zigpy.zcl.Cluster] = [], out_clusters: typing.List[zigpy.zcl.Cluster] = []) -> None:
        self.name = name
        self.in_clusters = in_clusters
        self.out_clusters = out_clusters

GPClustersByDeviceType: typing.Dict[GPDeviceType, GPDeviceTypeDescriptor] = {
    GPDeviceType.SWITCH_SIMPLE_ONE_STATE: GPDeviceTypeDescriptor(
        "Simple Generic 1-state", 
        out_clusters=[OnOff]
    ),
    GPDeviceType.SWITCH_SIMPLE_TWO_STATE: GPDeviceTypeDescriptor(
        "Simple Generic 2-state",
        out_clusters=[OnOff]
    ),
    GPDeviceType.SWITCH_ON_OFF: GPDeviceTypeDescriptor(
        "On/Off Switch", 
        out_clusters=[Scenes, OnOff]
    ),
    GPDeviceType.SWITCH_LEVEL_CONTROL: GPDeviceTypeDescriptor(
        "Level Control Switch",
        out_clusters=[LevelControl]
    ),
    GPDeviceType.SENSOR_SIMPLE: GPDeviceTypeDescriptor("Simple Sensor"),
    GPDeviceType.SWITCH_ADVANCED_ONE_STATE: GPDeviceTypeDescriptor(
        "Advanced Generic 1-state Switch",
        out_clusters=[Scenes, OnOff]
    ),
    GPDeviceType.SWITCH_ADVANCED_TWO_STATE: GPDeviceTypeDescriptor(
        "Advanced Generic 2-state Switch",
        out_clusters=[Scenes, OnOff]
    ),
    GPDeviceType.SWITCH_GENERIC: GPDeviceTypeDescriptor(
        "Generic Switch", 
        out_clusters=[Scenes, OnOff]
    ),
    GPDeviceType.SWITCH_COLOR_DIMMER: GPDeviceTypeDescriptor(
        "Color Dimmer Switch",
        out_clusters=[Color]
    ),
    GPDeviceType.SENSOR_LIGHT: GPDeviceTypeDescriptor(
        "Light Sensor", 
        in_clusters=[IlluminanceMeasurement]
    ),
    GPDeviceType.SENSOR_OCCUPANCY: GPDeviceTypeDescriptor(
        "Occupancy Sensor", 
        in_clusters=[OccupancySensing]
    ),
    GPDeviceType.DOOR_LOCK_CONTROLLER: GPDeviceTypeDescriptor(
        "Door Lock Controller",
        out_clusters=[DoorLock]
    ),
    GPDeviceType.SENSOR_TEMPERATURE: GPDeviceTypeDescriptor(
        "Temperature Sensor",
        in_clusters=[TemperatureMeasurement]
    ),
    GPDeviceType.SENSOR_PRESSURE: GPDeviceTypeDescriptor(
        "Pressure Sensor",
        in_clusters=[PressureMeasurement]
    ),
    GPDeviceType.SENSOR_FLOW: GPDeviceTypeDescriptor(
        "Flow Sensor", 
        in_clusters=[FlowMeasurement]
    ),
    GPDeviceType.SENSOR_ENVIRONMENT_INDOOR: GPDeviceTypeDescriptor("Indoor Environment Sensor")
}

