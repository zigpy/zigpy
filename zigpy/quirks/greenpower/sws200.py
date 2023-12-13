from __future__ import annotations
import typing
from zigpy.profiles.zgp import GREENPOWER_CLUSTER_ID
from zigpy.zgp import GPDeviceType
from zigpy.zgp.device import GreenPowerDevice
from zigpy.zgp.types import GPSecurityKeyType, GPSecurityLevel, GreenPowerDeviceData

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

class PhilipsSWS200(GreenPowerDevice):
    @classmethod
    def match(cls, device: GreenPowerDevice) -> bool:
        # behold, we actually have enough data to do something smart!
        return device.green_power_data.manufacturer_id == 0x100b and device.green_power_data.model_id == 0x0103
    
    def __init__(self, application: ControllerApplication, ext: GreenPowerDeviceData):
        super().__init__(application, ext)
        self.manufacturer = "Philips"
        self.model = "SWS200"
    
    device_automation_triggers = {
        ("initial_switch_press", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x10}
        },
        ("release", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x18}
        },

        ("initial_switch_press", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x11}
        },
        ("release", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x19}
        },

        ("initial_switch_press", "button_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x12}
        },
        ("release", "button_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1A}
        },

        ("initial_switch_press", "button_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x22}
        },
        ("release", "button_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x23}
        },
    }
