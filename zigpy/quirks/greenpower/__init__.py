from __future__ import annotations
from .ptm215z import EnoceanPTM215ZDevice
from .ptm215ze import EnoceanPTM215ZEDevice
from .sws200 import PhilipsSWS200
from .tuya_selfpowered import TuyaSelfPoweredSwitch
import zigpy.quirks

ALL_GP_DEVICE_TYPES = (EnoceanPTM215ZDevice,EnoceanPTM215ZEDevice,PhilipsSWS200,TuyaSelfPoweredSwitch)

zigpy.quirks._GP_REGISTRY = ALL_GP_DEVICE_TYPES
