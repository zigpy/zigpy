import logging

import zigpy.device
import zigpy.endpoint
import zigpy.zcl

_DEVICE_REGISTRY = []
_LOGGER = logging.getLogger(__name__)


def add_to_registry(device):
    """Add a device to the registry"""
    _DEVICE_REGISTRY.append(device)


def get_device(device, registry=_DEVICE_REGISTRY):
    """Get a CustomDevice object, if one is available"""
    dev_ep = set(device.endpoints.keys()) - set([0])
    for candidate in registry:
        _LOGGER.debug("Considering %s", candidate)
        sig = candidate.signature
        if not _match(sig.keys(), dev_ep):
            _LOGGER.debug("Fail because endpoint list mismatch: %s %s", sig.keys(), dev_ep)
            continue

        if not all([device[eid].profile_id == sig[eid].get('profile_id', device[eid].profile_id) for eid in sig.keys()]):
            _LOGGER.debug("Fail because profile_id mismatch on at least one endpoint")
            continue

        if not all([device[eid].device_type == sig[eid].get('device_type', device[eid].device_type) for eid in sig.keys()]):
            _LOGGER.debug("Fail because device_type mismatch on at least one endpoint")
            continue

        if not all([device[eid].model == sig[eid].get('model', device[eid].model) for eid in sig.keys()]):
            _LOGGER.debug("Fail because model mismatch on at least one endpoint")
            continue

        if not all([device[eid].manufacturer == sig[eid].get('manufacturer', device[eid].manufacturer) for eid in sig.keys()]):
            _LOGGER.debug("Fail because manufacturer mismatch on at least one endpoint")
            continue

        if not all([_match(device[eid].in_clusters.keys(),
                           ep.get('input_clusters', []))
                    for eid, ep in sig.items()]):
            _LOGGER.debug("Fail because input cluster mismatch on at least one endpoint")
            continue

        if not all([_match(device[eid].out_clusters.keys(),
                           ep.get('output_clusters', []))
                    for eid, ep in sig.items()]):
            _LOGGER.debug("Fail because output cluster mismatch on at least one endpoint")
            continue

        _LOGGER.debug("Found custom device replacement for %s: %s",
                      device.ieee, candidate)
        device = candidate(device._application, device.ieee, device.nwk, device)
        break

    return device


class Registry(type):
    def __init__(cls, name, bases, nmspc):  # noqa: N805
        super(Registry, cls).__init__(name, bases, nmspc)
        if hasattr(cls, 'signature'):
            add_to_registry(cls)


class CustomDevice(zigpy.device.Device, metaclass=Registry):
    replacement = {}

    def __init__(self, application, ieee, nwk, replaces):
        super().__init__(application, ieee, nwk)
        self.status = zigpy.device.Status.ENDPOINTS_INIT
        self.node_desc = replaces.node_desc
        for endpoint_id, endpoint in self.replacement.get('endpoints', {}).items():
            self.add_endpoint(endpoint_id, replace_device=replaces)

    def add_endpoint(self, endpoint_id, replace_device=None):
        if endpoint_id not in self.replacement.get('endpoints', {}):
            return super().add_endpoint(endpoint_id)

        endpoints = self.replacement['endpoints']

        if isinstance(endpoints[endpoint_id], tuple):
            custom_ep_type = endpoints[endpoint_id][0]
            replacement_data = endpoints[endpoint_id][1]
        else:
            custom_ep_type = CustomEndpoint
            replacement_data = endpoints[endpoint_id]

        ep = custom_ep_type(
            self,
            endpoint_id,
            replacement_data,
            replace_device,
        )
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

        set_device_attr('profile_id')
        set_device_attr('device_type')
        set_device_attr('manufacturer')
        set_device_attr('model')
        self.status = zigpy.endpoint.Status.ZDO_INIT

        for c in replacement_data.get('input_clusters', []):
            if isinstance(c, int):
                cluster = None
                cluster_id = c
            else:
                cluster = c(self)
                cluster_id = cluster.cluster_id
            self.add_input_cluster(cluster_id, cluster)

        for c in replacement_data.get('output_clusters', []):
            if isinstance(c, int):
                cluster = None
                cluster_id = c
            else:
                cluster = c(self)
                cluster_id = cluster.cluster_id
            self.add_output_cluster(cluster_id, cluster)


class CustomCluster(zigpy.zcl.Cluster):
    _skip_registry = True


def _match(a, b):
    return set(a) == set(b)


from . import xiaomi  # noqa: F401, F402
from . import smartthings  # noqa: F401, F402
from . import kof  # noqa: F401, F402
from . import keen  # noqa: F401, F402
from . import ikea  # noqa: F401, F402
