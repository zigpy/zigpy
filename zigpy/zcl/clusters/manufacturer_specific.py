from __future__ import annotations

from zigpy.zcl import Cluster
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class ManufacturerSpecificCluster(Cluster):
    cluster_id_range = (0xFC00, 0xFFFF)
    ep_attribute = "manufacturer_specific"
    name = "Manufacturer Specific"
    attributes: dict[int, ZCLAttributeDef] = {}
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}
