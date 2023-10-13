from __future__ import annotations

from zigpy.zcl import Cluster


class ManufacturerSpecificCluster(Cluster):
    cluster_id_range = (0xFC00, 0xFFFF)
    ep_attribute = "manufacturer_specific"
    name = "Manufacturer Specific"
