import typing

from zigpy.zcl import Cluster
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class ManufacturerSpecificCluster(Cluster):
    cluster_id_range = (0xFC00, 0xFFFF)
    ep_attribute = "manufacturer_specific"
    name = "Manufacturer Specific"
    attributes: typing.Dict[int, ZCLAttributeDef] = {}
    server_commands: typing.Dict[int, ZCLCommandDef] = {}
    client_commands: typing.Dict[int, ZCLCommandDef] = {}
