from __future__ import annotations
from .ptm215z import EnoceanPTM215ZDevice
import zigpy.quirks

ALL_GP_DEVICE_TYPES = (EnoceanPTM215ZDevice,)

zigpy.quirks._GP_REGISTRY =ALL_GP_DEVICE_TYPES
