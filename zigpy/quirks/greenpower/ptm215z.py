from __future__ import annotations
import typing
from zigpy.profiles.zgp import (
    GREENPOWER_ENDPOINT_ID,
    GREENPOWER_CLUSTER_ID
)
from zigpy.zcl.clusters.greenpower import GPNotificationSchema
from zigpy.zgp import GPDeviceType
from zigpy.zgp.device import GreenPowerDevice
from zigpy.zgp.types import GPSecurityKeyType, GPSecurityLevel, GreenPowerExtData

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

class EnoceanPTM215ZDevice(GreenPowerDevice):
    @classmethod
    def match(cls, device: GreenPowerDevice) -> bool:
        # First check simple security and type parameters
        if device.ext_data.device_id != GPDeviceType.SWITCH_ON_OFF:
            return False
        if device.ext_data.security_key_type != GPSecurityKeyType.IndividualKey:
            return False
        if device.ext_data.security_level != GPSecurityLevel.FullFrameCounterAndMIC:
            return False
        # Finally match against GPD ID prefix
        return str(device.ext_data.gpd_id).startswith("0x017")
    
    def __init__(self, application: ControllerApplication, ext: GreenPowerExtData):
        super().__init__(application, ext)
        self.manufacturer = "EnOcean"
        self.model = "PTM215Z"
    
    device_automation_triggers = {
        ("initial_switch_press", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x10}
        },
        ("release", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x14}
        },
        ("initial_switch_press", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x11}
        },
        ("release", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x15}
        },
        ("initial_switch_press", "button_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x13}
        },
        ("release", "button_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x17}
        },
        ("initial_switch_press", "button_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x12}
        },
        ("release", "button_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x16}
        },
        ("initial_switch_press", "button_1_and_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x64}
        },
        ("release", "button_1_and_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x65}
        },
        ("initial_switch_press", "button_2_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x62}
        },
        ("release", "button_2_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x63}
        },
        ("initial_switch_press", "energy_bar"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x22}
        },
    }