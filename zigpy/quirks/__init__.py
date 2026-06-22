"""Deprecation shim: quirks v1 moved to zha-device-handlers."""

from __future__ import annotations

import importlib
import typing
import warnings

_MOVED_NAMES: dict[str, tuple[str, str]] = {
    "CustomCluster": ("zhaquirks.clusters", "CustomCluster"),
    "BaseCustomDevice": ("zhaquirks.device", "BaseCustomDevice"),
    "CustomEndpoint": ("zhaquirks.device", "CustomEndpoint"),
    "CustomDeviceV2": ("zhaquirks.device", "CustomZigpyDevice"),
    "CustomDevice": ("zhaquirks.legacy", "CustomDevice"),
    "DeviceRegistry": ("zhaquirks.legacy", "LegacyDeviceRegistry"),
    "DEVICE_REGISTRY": ("zhaquirks.legacy", "DEVICE_REGISTRY"),
    "FilterType": ("zhaquirks.legacy", "FilterType"),
    "get_device": ("zhaquirks.legacy", "get_device"),
    "get_quirk_list": ("zhaquirks.legacy", "get_quirk_list"),
    "signature_matches": ("zhaquirks.legacy", "signature_matches"),
    "register_uninitialized_device_message_handler": (
        "zhaquirks.legacy",
        "register_uninitialized_device_message_handler",
    ),
    "handle_message_from_uninitialized_sender": (
        "zhaquirks.legacy",
        "handle_message_from_uninitialized_sender",
    ),
}


def __getattr__(name: str) -> typing.Any:
    if name not in _MOVED_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr = _MOVED_NAMES[name]
    warnings.warn(
        f"`zigpy.quirks.{name}` is deprecated, import `{attr}` from"
        f" `{module_path}` instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return getattr(importlib.import_module(module_path), attr)
