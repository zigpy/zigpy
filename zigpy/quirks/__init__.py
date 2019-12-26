import logging

import zigpy.device
import zigpy.endpoint
from zigpy.quirks.registry import DeviceRegistry
import zigpy.zcl

_LOGGER = logging.getLogger(__name__)

_DEVICE_REGISTRY = DeviceRegistry()


def get_device(device, registry=_DEVICE_REGISTRY):
    """Get a CustomDevice object, if one is available"""
    return registry.get_device(device)


class Registry(type):
    def __init__(cls, name, bases, nmspc):  # noqa: N805
        super(Registry, cls).__init__(name, bases, nmspc)
        if hasattr(cls, "signature"):
            _DEVICE_REGISTRY.add_to_registry(cls)


class CustomDevice(zigpy.device.Device, metaclass=Registry):
    replacement = {}

    def __init__(self, application, ieee, nwk, replaces):
        super().__init__(application, ieee, nwk)

        def set_device_attr(attr):
            if attr in self.replacement:
                setattr(self, attr, self.replacement[attr])
            else:
                setattr(self, attr, getattr(replaces, attr))

        set_device_attr("status")
        set_device_attr("node_desc")
        set_device_attr("manufacturer")
        set_device_attr("model")
        for endpoint_id, endpoint in self.replacement.get("endpoints", {}).items():
            self.add_endpoint(endpoint_id, replace_device=replaces)

    def add_endpoint(self, endpoint_id, replace_device=None):
        if endpoint_id not in self.replacement.get("endpoints", {}):
            return super().add_endpoint(endpoint_id)

        endpoints = self.replacement["endpoints"]

        if isinstance(endpoints[endpoint_id], tuple):
            custom_ep_type = endpoints[endpoint_id][0]
            replacement_data = endpoints[endpoint_id][1]
        else:
            custom_ep_type = CustomEndpoint
            replacement_data = endpoints[endpoint_id]

        ep = custom_ep_type(self, endpoint_id, replacement_data, replace_device)
        self.endpoints[endpoint_id] = ep
        return ep


class CustomEndpoint(zigpy.endpoint.Endpoint):
    def __init__(self, device, endpoint_id, replacement_data, replace_device):
        super().__init__(device, endpoint_id)

        def set_device_attr(attr):
            if attr in replacement_data:
                setattr(self, attr, replacement_data[attr])
            else:
                setattr(self, attr, getattr(replace_device[endpoint_id], attr))

        set_device_attr("profile_id")
        set_device_attr("device_type")
        self.status = zigpy.endpoint.Status.ZDO_INIT

        for c in replacement_data.get("input_clusters", []):
            if isinstance(c, int):
                cluster = None
                cluster_id = c
            else:
                cluster = c(self, is_server=True)
                cluster_id = cluster.cluster_id
            self.add_input_cluster(cluster_id, cluster)

        for c in replacement_data.get("output_clusters", []):
            if isinstance(c, int):
                cluster = None
                cluster_id = c
            else:
                cluster = c(self, is_server=False)
                cluster_id = cluster.cluster_id
            self.add_output_cluster(cluster_id, cluster)


class CustomCluster(zigpy.zcl.Cluster):
    _skip_registry = True
