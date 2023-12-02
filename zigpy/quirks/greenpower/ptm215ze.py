from __future__ import annotations
import typing
from zigpy.profiles.zgp import GREENPOWER_CLUSTER_ID
from zigpy.zgp import GPDeviceType
from zigpy.zgp.device import GreenPowerDevice
from zigpy.zgp.types import GPSecurityKeyType, GPSecurityLevel, GreenPowerDeviceData

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

class EnoceanPTM215ZEDevice(GreenPowerDevice):
    @classmethod
    def match(cls, device: GreenPowerDevice) -> bool:
        # First check simple security and type parameters
        if device.green_power_data.device_id != GPDeviceType.SWITCH_ON_OFF:
            return False
        if device.green_power_data.security_key_type != GPSecurityKeyType.IndividualKey:
            return False
        if device.green_power_data.security_level != GPSecurityLevel.FullFrameCounterAndMIC:
            return False
        # Finally match against GPD ID prefix
        return str(device.green_power_data.gpd_id).startswith("0x015")
    
    def __init__(self, application: ControllerApplication, ext: GreenPowerDeviceData):
        super().__init__(application, ext)
        self.manufacturer = "EnOcean"
        self.model = "PTM215ZE"
    
    device_automation_triggers = {
        ("initial_switch_press", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x22}
        },
        ("release", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x23}
        },
        ("initial_switch_press", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x18}
        },
        ("release", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x19}
        },
        ("initial_switch_press", "button_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x14}
        },
        ("release", "button_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x15}
        },
        ("initial_switch_press", "button_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x12}
        },
        ("release", "button_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x13}
        },

        ("initial_switch_press", "button_1_and_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x64}
        },
        ("release", "button_1_and_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x65}
        },

        ("initial_switch_press", "button_1_and_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x62}
        },
        ("release", "button_1_and_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x63}
        },

        ("initial_switch_press", "button_1_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1e}
        },
        ("release", "button_1_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1f}
        },

        ("initial_switch_press", "button_2_and_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1c}
        },
        ("release", "button_2_and_3"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1d}
        },

        ("initial_switch_press", "button_2_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1a}
        },
        ("release", "button_2_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x1b}
        },

        ("initial_switch_press", "button_3_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x16}
        },
        ("release", "button_3_and_4"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x17}
        },

        ("initial_switch_press", "energy_bar"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x10}
        },
        ("release", "energy_bar"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x11}
        },
    }
