"""Deprecation shim: the v1 quirks registry moved to `zhaquirks.legacy.registry`."""

from __future__ import annotations

import importlib
import typing
import warnings


def __getattr__(name: str) -> typing.Any:
    if name != "DeviceRegistry":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    warnings.warn(
        "`zigpy.quirks.registry.DeviceRegistry` is deprecated, import it from"
        " `zhaquirks.legacy.registry` instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return importlib.import_module("zhaquirks.legacy.registry").LegacyDeviceRegistry
