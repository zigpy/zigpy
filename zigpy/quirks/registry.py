"""Zigpy quirks registry."""

from __future__ import annotations

from collections import defaultdict, deque
import inspect
import itertools
import logging
import pathlib
from typing import TYPE_CHECKING

from zigpy.const import SIG_MANUFACTURER, SIG_MODEL, SIG_MODELS_INFO
import zigpy.quirks
from zigpy.typing import CustomDeviceType, DeviceType
from zigpy.util import deprecated

if TYPE_CHECKING:
    from zigpy.quirks import CustomDevice
    from zigpy.quirks.v2 import QuirksV2RegistryEntry

_LOGGER = logging.getLogger(__name__)


class DeviceRegistry:
    """Device registry for Zigpy quirks."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the registry."""
        self._registry_v1: dict[str | None, dict[str | None, deque[CustomDevice]]] = (
            defaultdict(lambda: defaultdict(deque))
        )

        self._registry_v2: dict[tuple[str, str], deque[QuirksV2RegistryEntry]] = (
            defaultdict(deque)
        )

    def purge_custom_quirks(self, custom_quirks_root: pathlib.Path) -> None:
        # If zhaquirks aren't being used, we can't tell if a quirk is custom or not
        for model_registry in self._registry_v1.values():
            for quirks in model_registry.values():
                to_remove = []

                for quirk in quirks:
                    module = inspect.getmodule(quirk)
                    assert module is not None  # All quirks should have modules

                    quirk_module = pathlib.Path(module.__file__)

                    if quirk_module.is_relative_to(custom_quirks_root):
                        to_remove.append(quirk)

                for quirk in to_remove:
                    _LOGGER.debug("Removing stale custom v1 quirk: %s", quirk)
                    quirks.remove(quirk)

        for registry in self._registry_v2.values():
            to_remove = []

            for entry in registry:
                if entry.quirk_file.is_relative_to(custom_quirks_root):
                    to_remove.append(entry)

            for entry in to_remove:
                _LOGGER.debug("Removing stale custom v2 quirk: %s", entry)
                registry.remove(entry)

    def add_to_registry(self, custom_device: CustomDeviceType) -> None:
        """Add a device to the registry"""
        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                if custom_device not in self.registry_v1[manuf][model]:
                    self.registry_v1[manuf][model].appendleft(custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            if custom_device not in self.registry_v1[manufacturer][model]:
                self.registry_v1[manufacturer][model].appendleft(custom_device)

    def add_to_registry_v2(
        self, manufacturer: str, model: str, entry: QuirksV2RegistryEntry
    ) -> None:
        """Add an entry to the registry."""
        self._registry_v2[(manufacturer, model)].appendleft(entry)

    def remove(self, custom_device: CustomDeviceType) -> None:
        """Remove a device from the registry"""

        if hasattr(custom_device, "quirk_metadata"):
            key = (custom_device.manufacturer, custom_device.model)
            self._registry_v2[key].remove(custom_device.quirk_metadata)
            return

        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                self.registry_v1[manuf][model].remove(custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            self.registry_v1[manufacturer][model].remove(custom_device)

    def get_device(self, device: DeviceType) -> CustomDeviceType | DeviceType:
        """Get a CustomDevice object, if one is available"""
        if isinstance(device, zigpy.quirks.BaseCustomDevice):
            return device

        _LOGGER.debug(
            "Checking quirks for %s %s (%s)",
            device.manufacturer,
            device.model,
            device.ieee,
        )

        # Try v2 quirks first
        key = (device.manufacturer, device.model)
        if key in self._registry_v2:
            for entry in self._registry_v2[key]:
                if entry.matches_device(device):
                    return entry.create_device(device)

        # Then, fall back to v1 quirks
        for candidate in itertools.chain(
            self.registry_v1[device.manufacturer][device.model],
            self.registry_v1[device.manufacturer][None],
            self.registry_v1[None][device.model],
            self.registry_v1[None][None],
        ):
            matcher = zigpy.quirks.signature_matches(candidate.signature)
            _LOGGER.debug("Considering %s", candidate)

            if not matcher(device):
                continue

            _LOGGER.debug(
                "Found custom device replacement for %s: %s", device.ieee, candidate
            )
            return candidate(device._application, device.ieee, device.nwk, device)

        # If none match, return the original device
        return device

    @property
    @deprecated("The `registry` property is deprecated, use `registry_v1` instead.")
    def registry(self) -> dict[str | None, dict[str | None, deque[CustomDevice]]]:
        """Return the v1 registry."""
        return self._registry_v1

    @property
    def registry_v1(self) -> dict[str | None, dict[str | None, deque[CustomDevice]]]:
        """Return the v1 registry."""
        return self._registry_v1

    @property
    def registry_v2(self) -> dict[tuple[str, str], deque[QuirksV2RegistryEntry]]:
        """Return the v2 registry."""
        return self._registry_v2

    def __contains__(self, device: CustomDeviceType) -> bool:
        """Check if a device is in the registry."""

        if hasattr(device, "quirk_metadata"):
            manufacturer, model = device.manufacturer, device.model
            return device.quirk_metadata in self._registry_v2[(manufacturer, model)]

        manufacturer, model = device.signature.get(
            SIG_MODELS_INFO,
            [
                (
                    device.signature.get(SIG_MANUFACTURER),
                    device.signature.get(SIG_MODEL),
                )
            ],
        )[0]
        return device in itertools.chain(
            self.registry_v1[manufacturer][model],
            self.registry_v1[manufacturer][None],
            self.registry_v1[None][None],
        )
