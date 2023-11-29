from __future__ import annotations
import typing
from zigpy.profiles.zgp import GREENPOWER_CLUSTER_ID
from zigpy.zcl.clusters.greenpower import GPNotificationSchema
from zigpy.zgp import GPDeviceType
from zigpy.zgp.device import GreenPowerDevice
from zigpy.zgp.types import GPSecurityKeyType, GPSecurityLevel, GreenPowerDeviceData

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

class TuyaSelfPoweredSwitch(GreenPowerDevice):
    @classmethod
    def match(cls, device: GreenPowerDevice) -> bool:
        if device.green_power_data.device_id is not GPDeviceType.SWITCH_ON_OFF:
            return False
        if device.green_power_data.security_level is not GPSecurityLevel.Encrypted:
            return False
        if device.green_power_data.security_key_type is not GPSecurityKeyType.IndividualKey:
            return False

        # This thing has a mutable GPD ID, which is miserable.
        # It is, however, the only device which posts an Encrypted
        # security level, so we can at least use that to our advantage in
        # combination with the device_id
        return True
    
    def __init__(self, application: ControllerApplication, ext: GreenPowerDeviceData):
        super().__init__(application, ext)
        self.manufacturer = "TuYa"
        self.model = "Self-Powered Switch"
    
    device_automation_triggers = {
        ("press", "button_1"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x20}
        },
        ("press", "button_2"): {
            "command": "notification",
            "cluster_id": GREENPOWER_CLUSTER_ID,
            "params": {"command_id": 0x21}
        },
    }
