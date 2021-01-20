import collections
import itertools
import logging
from typing import Dict, List, Optional, Union

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_MODELS_INFO,
)
import zigpy.quirks
from zigpy.typing import CustomDeviceType, DeviceType

_LOGGER = logging.getLogger(__name__)

TYPE_MODEL_QUIRKS_LIST = Dict[Optional[str], List["zigpy.quirks.CustomDevice"]]
TYPE_MANUF_QUIRKS_DICT = Dict[Optional[str], TYPE_MODEL_QUIRKS_LIST]


class DeviceRegistry:
    def __init__(self, *args, **kwargs):
        self._registry: TYPE_MANUF_QUIRKS_DICT = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )

    def add_to_registry(self, custom_device: CustomDeviceType) -> None:
        """Add a device to the registry"""
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                if custom_device not in self.registry[manuf][model]:
                    self.registry[manuf][model].insert(0, custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            if custom_device not in self.registry[manufacturer][model]:
                self.registry[manufacturer][model].insert(0, custom_device)

    def remove(self, custom_device: CustomDeviceType) -> None:
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                self.registry[manuf][model].remove(custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            self.registry[manufacturer][model].remove(custom_device)

    def get_device(self, device: DeviceType) -> Union[CustomDeviceType, DeviceType]:
        """Get a CustomDevice object, if one is available"""
        if isinstance(device, zigpy.quirks.CustomDevice):
            return device
        dev_ep = set(device.endpoints) - {0}
        _LOGGER.debug(
            "Checking quirks for %s %s (%s)",
            device.manufacturer,
            device.model,
            device.ieee,
        )
        for candidate in itertools.chain(
            self.registry[device.manufacturer][device.model],
            self.registry[device.manufacturer][None],
            self.registry[None][device.model],
            self.registry[None][None],
        ):
            _LOGGER.debug("Considering %s", candidate)

            if not device.model == candidate.signature.get(SIG_MODEL, device.model):
                _LOGGER.debug("Fail, because device model mismatch: '%s'", device.model)
                continue

            if not (
                device.manufacturer
                == candidate.signature.get(SIG_MANUFACTURER, device.manufacturer)
            ):
                _LOGGER.debug(
                    "Fail, because device manufacturer mismatch: '%s'",
                    device.manufacturer,
                )
                continue

            sig = candidate.signature.get(SIG_ENDPOINTS)
            if sig is None:
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
                    == sig[eid].get(SIG_EP_PROFILE, device[eid].profile_id)
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
                    == sig[eid].get(SIG_EP_TYPE, device[eid].device_type)
                    for eid in sig
                ]
            ):
                _LOGGER.debug(
                    "Fail because device_type mismatch on at least one endpoint"
                )
                continue

            if not all(
                [
                    self._match(device[eid].in_clusters, ep.get(SIG_EP_INPUT, []))
                    for eid, ep in sig.items()
                ]
            ):
                _LOGGER.debug(
                    "Fail because input cluster mismatch on at least one endpoint"
                )
                continue

            if not all(
                [
                    self._match(device[eid].out_clusters, ep.get(SIG_EP_OUTPUT, []))
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
    def _match(a, b):
        return set(a) == set(b)

    @property
    def registry(self):
        return self._registry

    def __contains__(self, device: CustomDeviceType) -> bool:
        manufacturer, model = device.signature.get(
            SIG_MODELS_INFO,
            [(device.signature.get(SIG_MANUFACTURER), device.signature.get(SIG_MODEL))],
        )[0]

        return device in itertools.chain(
            self.registry[manufacturer][model],
            self.registry[manufacturer][None],
            self.registry[None][None],
        )
