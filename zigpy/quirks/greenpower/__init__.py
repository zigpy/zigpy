from __future__ import annotations
from .ptm215z import EnoceanPTM215ZDevice
from .tuya_selfpowered import TuyaSelfPoweredSwitch
import zigpy.quirks

ALL_GP_DEVICE_TYPES = (EnoceanPTM215ZDevice,TuyaSelfPoweredSwitch)

zigpy.quirks._GP_REGISTRY =ALL_GP_DEVICE_TYPES
