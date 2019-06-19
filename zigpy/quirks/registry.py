import logging

_LOGGER = logging.getLogger(__name__)


class DeviceRegistry(list):
    def add_to_registry(self, device):
        """Add a device to the registry"""
        self.append(device)

    def get_device(self, device):
        """Get a CustomDevice object, if one is available"""
        dev_ep = set(device.endpoints) - set([0])
        _LOGGER.debug("Checking quirks for %s %s (%s)",
                      device.manufacturer, device.model, device.ieee)
        for candidate in self:
            _LOGGER.debug("Considering %s", candidate)
            sig = candidate.signature.get('endpoints', {})
            if not sig:
                _LOGGER.warning(
                    ("%s signature update is required. Support for `signature = {1: { replacement }}`"
                     " will be removed in the future releases. Use "
                     "`signature = {'endpoints': {1: { replacement }}}"), candidate
                )
                sig = {
                    eid: ep for eid, ep in candidate.signature.items() if isinstance(eid, int)
                }
            if not device.model == candidate.signature.get('model', device.model):
                _LOGGER.debug("Fail, because device model mismatch: '%s'",
                              device.model)
                continue

            if not (device.manufacturer ==
                    candidate.signature.get('manufacturer', device.manufacturer)):
                _LOGGER.debug("Fail, because device manufacturer mismatch: '%s'",
                              device.manufacturer)
                continue

            if not self._match(sig, dev_ep):
                _LOGGER.debug("Fail because endpoint list mismatch: %s %s", set(sig.keys()), dev_ep)
                continue

            if not all([device[eid].profile_id == sig[eid].get('profile_id', device[eid].profile_id) for eid in sig]):
                _LOGGER.debug("Fail because profile_id mismatch on at least one endpoint")
                continue

            if not all([device[eid].device_type == sig[eid].get('device_type', device[eid].device_type) for eid in sig]):
                _LOGGER.debug("Fail because device_type mismatch on at least one endpoint")
                continue

            if not all([device[eid].model == sig[eid].get('model', device[eid].model) for eid in sig]):
                _LOGGER.debug("Fail because model mismatch on at least one endpoint")
                continue

            if not all([device[eid].manufacturer == sig[eid].get('manufacturer', device[eid].manufacturer) for eid in sig]):
                _LOGGER.debug("Fail because manufacturer mismatch on at least one endpoint")
                continue

            if not all([self._match(device[eid].in_clusters,
                                    ep.get('input_clusters', []))
                        for eid, ep in sig.items()]):
                _LOGGER.debug("Fail because input cluster mismatch on at least one endpoint")
                continue

            if not all([self._match(device[eid].out_clusters,
                                    ep.get('output_clusters', []))
                        for eid, ep in sig.items()]):
                _LOGGER.debug("Fail because output cluster mismatch on at least one endpoint")
                continue

            _LOGGER.debug("Found custom device replacement for %s: %s",
                          device.ieee, candidate)
            device = candidate(device._application, device.ieee, device.nwk, device)
            break

        return device

    @staticmethod
    def _match(a, b):
        return set(a) == set(b)
