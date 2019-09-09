import collections
import itertools
import logging
import zigpy.quirks

_LOGGER = logging.getLogger(__name__)

SIG_MODELS_INFO = "models_info"


class DeviceRegistry:
    def __init__(self, *args, **kwargs):
        dd = collections.defaultdict
        self._registry = dd(lambda: dd(list))

    def add_to_registry(self, custom_device):
        """Add a device to the registry"""
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                self.registry[manuf][model].append(custom_device)
        else:
            manufacturer = self.get_manufacturer(custom_device)
            model = self.get_model(custom_device)
            self.registry[manufacturer][model].append(custom_device)

    def remove(self, custom_device):
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                self.registry[manuf][model].remove(custom_device)
        else:
            manufacturer = self.get_manufacturer(custom_device)
            model = self.get_model(custom_device)
            self.registry[manufacturer][model].remove(custom_device)

    def get_device(self, device):
        """Get a CustomDevice object, if one is available"""
        if isinstance(device, zigpy.quirks.CustomDevice):
            return device
        dev_ep = set(device.endpoints) - set([0])
        _LOGGER.debug(
            "Checking quirks for %s %s (%s)",
            device.manufacturer,
            device.model,
            device.ieee,
        )
        for candidate in itertools.chain(
            self.registry[device.manufacturer][device.model],
            self.registry[device.manufacturer][None],
            self.registry[None][None],
        ):
            _LOGGER.debug("Considering %s", candidate)
            sig = candidate.signature.get("endpoints", {})
            if not sig:
                _LOGGER.warning(
                    (
                        "%s signature update is required. Support for "
                        "`signature = {1: { replacement }}`"
                        " will be removed in the future releases. Use "
                        "`signature = {'endpoints': {1: { replacement }}}"
                    ),
                    candidate,
                )
                sig = {
                    eid: ep
                    for eid, ep in candidate.signature.items()
                    if isinstance(eid, int)
                }
            if not device.model == candidate.signature.get("model", device.model):
                _LOGGER.debug("Fail, because device model mismatch: '%s'", device.model)
                continue

            if not (
                device.manufacturer
                == candidate.signature.get("manufacturer", device.manufacturer)
            ):
                _LOGGER.debug(
                    "Fail, because device manufacturer mismatch: '%s'",
                    device.manufacturer,
                )
                continue

            if not self._match(sig, dev_ep):
                _LOGGER.debug(
                    "Fail because endpoint list mismatch: %s %s",
                    set(sig.keys()),
                    dev_ep,
                )
                continue

            if not all(
                [
                    device[eid].profile_id
                    == sig[eid].get("profile_id", device[eid].profile_id)
                    for eid in sig
                ]
            ):
                _LOGGER.debug(
                    "Fail because profile_id mismatch on at least one endpoint"
                )
                continue

            if not all(
                [
                    device[eid].device_type
                    == sig[eid].get("device_type", device[eid].device_type)
                    for eid in sig
                ]
            ):
                _LOGGER.debug(
                    "Fail because device_type mismatch on at least one endpoint"
                )
                continue

            if not all(
                [
                    device[eid].model == sig[eid].get("model", device[eid].model)
                    for eid in sig
                ]
            ):
                _LOGGER.debug("Fail because model mismatch on at least one endpoint")
                continue

            if not all(
                [
                    device[eid].manufacturer
                    == sig[eid].get("manufacturer", device[eid].manufacturer)
                    for eid in sig
                ]
            ):
                _LOGGER.debug(
                    "Fail because manufacturer mismatch on at least one endpoint"
                )
                continue

            if not all(
                [
                    self._match(device[eid].in_clusters, ep.get("input_clusters", []))
                    for eid, ep in sig.items()
                ]
            ):
                _LOGGER.debug(
                    "Fail because input cluster mismatch on at least one endpoint"
                )
                continue

            if not all(
                [
                    self._match(device[eid].out_clusters, ep.get("output_clusters", []))
                    for eid, ep in sig.items()
                ]
            ):
                _LOGGER.debug(
                    "Fail because output cluster mismatch on at least one endpoint"
                )
                continue

            _LOGGER.debug(
                "Found custom device replacement for %s: %s", device.ieee, candidate
            )
            device = candidate(device._application, device.ieee, device.nwk, device)
            break

        return device

    @staticmethod
    def get_manufacturer(custom_dev):
        manuf = custom_dev.signature.get("manufacturer")
        if manuf is None:
            # Get manufacturer from legacy endpoint sig
            sig = {
                eid: ep
                for eid, ep in custom_dev.signature.items()
                if isinstance(eid, int)
            }
            manuf = next(
                (ep["manufacturer"] for ep in sig.values() if "manufacturer" in ep),
                None,
            )
        return manuf

    @staticmethod
    def get_model(custom_dev):
        model = custom_dev.signature.get("model")
        if model is None:
            # Get model from legacy endpoint sig
            sig = {
                eid: ep
                for eid, ep in custom_dev.signature.items()
                if isinstance(eid, int)
            }
            model = next((ep["model"] for ep in sig.values() if "model" in ep), None)
        return model

    @staticmethod
    def _match(a, b):
        return set(a) == set(b)

    @property
    def registry(self):
        return self._registry

    def __contains__(self, device):
        manufacturer, model = device.signature.get(
            SIG_MODELS_INFO, [(self.get_manufacturer(device), self.get_model(device))]
        )[0]

        return device in itertools.chain(
            self.registry[manufacturer][model],
            self.registry[manufacturer][None],
            self.registry[None][None],
        )
