from __future__ import annotations

import inspect

from .. import Cluster
from . import (
    closures,
    general,
    general_const as general_const,  # noqa: PLC0414
    homeautomation,
    hvac,
    lighting,
    lightlink,
    manufacturer_specific,
    measurement,
    protocol,
    security,
    smartenergy,
)

CLUSTERS_BY_ID: dict[int, Cluster] = {}
CLUSTERS_BY_NAME: dict[str, Cluster] = {}

for cls in (
    closures,
    general,
    homeautomation,
    hvac,
    lighting,
    lightlink,
    manufacturer_specific,
    measurement,
    protocol,
    security,
    smartenergy,
):
    for name in dir(cls):
        obj = getattr(cls, name)

        # Object must be a concrete Cluster subclass
        if (
            not inspect.isclass(obj)
            or not issubclass(obj, Cluster)
            or obj.cluster_id is None
        ):
            continue

        assert CLUSTERS_BY_ID.get(obj.cluster_id, obj) is obj
        assert CLUSTERS_BY_NAME.get(obj.ep_attribute, obj) is obj

        CLUSTERS_BY_ID[obj.cluster_id] = obj
        CLUSTERS_BY_NAME[obj.ep_attribute] = obj
