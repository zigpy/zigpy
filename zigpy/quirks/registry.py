"""Zigpy quirks registry."""

from __future__ import annotations

import collections
import itertools
import logging
import typing
from typing import TYPE_CHECKING

from zigpy.const import SIG_MANUFACTURER, SIG_MODEL, SIG_MODELS_INFO
from zigpy.exceptions import MultipleQuirksMatchException
import zigpy.quirks
from zigpy.typing import CustomDeviceType, DeviceType

if TYPE_CHECKING:
    from zigpy.quirks.v2 import QuirksV2RegistryEntry

_LOGGER = logging.getLogger(__name__)

TYPE_MANUF_QUIRKS_DICT = typing.Dict[
    typing.Optional[str],
    typing.Dict[typing.Optional[str], typing.List["zigpy.quirks.CustomDevice"]],
]


class DeviceRegistry:
    """Device registry for Zigpy quirks."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the registry."""
        self._registry: TYPE_MANUF_QUIRKS_DICT = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        self._registry_v2: dict[
            tuple[str, str], list[QuirksV2RegistryEntry]
        ] = collections.defaultdict(list)

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

    def add_to_registry_v2(
        self, manufacturer: str, model: str, entry: QuirksV2RegistryEntry
    ) -> QuirksV2RegistryEntry:
        """Add an entry to the registry."""
        key = (manufacturer, model)
        if not entry.registry:
            entry.registry = self
        self._registry_v2[key].append(entry)
        return entry

    def remove(self, custom_device: CustomDeviceType) -> None:
        """Remove a device from the registry"""

        if hasattr(custom_device, "quirk_metadata"):
            key = (custom_device.manufacturer, custom_device.model)
            self._registry_v2[key].remove(custom_device.quirk_metadata)
            return

        models_info = custom_device.signature.get(SIG_MODELS_INFO)
        if models_info:
            for manuf, model in models_info:
                self.registry[manuf][model].remove(custom_device)
        else:
            manufacturer = custom_device.signature.get(SIG_MANUFACTURER)
            model = custom_device.signature.get(SIG_MODEL)
            self.registry[manufacturer][model].remove(custom_device)

    def get_device(self, device: DeviceType) -> CustomDeviceType | DeviceType:
        """Get a CustomDevice object, if one is available"""
        if isinstance(device, zigpy.quirks.CustomDevice):
            return device

        key = (device.manufacturer, device.model)
        if key in self._registry_v2:
            matches: list[QuirksV2RegistryEntry] = []
            entries = self._registry_v2[key]
            if len(entries) == 1:
                if entries[0].matches_device(device):
                    matches.append(entries[0])
            else:
                for entry in entries:
                    if entry.matches_device(device):
                        matches.append(entry)
            if len(matches) > 1:
                raise MultipleQuirksMatchException(
                    f"Multiple matches found for device {device}: {matches}"
                )
            if len(matches) == 1:
                quirk_entry: QuirksV2RegistryEntry = matches[0]
                return quirk_entry.create_device(device)

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
            matcher = zigpy.quirks.signature_matches(candidate.signature)
            _LOGGER.debug("Considering %s", candidate)

            if not matcher(device):
                continue

            _LOGGER.debug(
                "Found custom device replacement for %s: %s", device.ieee, candidate
            )
            device = candidate(device._application, device.ieee, device.nwk, device)
            break

        return device

    @property
    def registry(self) -> TYPE_MANUF_QUIRKS_DICT:
        """Return the registry."""
        return self._registry

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
            self.registry[manufacturer][model],
            self.registry[manufacturer][None],
            self.registry[None][None],
        )
