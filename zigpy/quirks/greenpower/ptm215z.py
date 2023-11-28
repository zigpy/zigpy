from __future__ import annotations
import typing
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
    
    def handle_notification(self, notification: GPNotificationSchema):
        
        pass
    
    
