from __future__ import annotations

from typing import Final

from zigpy.zcl import Cluster


class ManufacturerSpecificCluster(Cluster):
    cluster_id_range = (0xFC00, 0xFFFF)
    ep_attribute: Final = "manufacturer_specific"
    name: Final = "Manufacturer Specific"
