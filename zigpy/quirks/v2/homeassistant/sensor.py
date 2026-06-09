"""Compatibility shim: sensor device classes moved into ZHA."""

from __future__ import annotations

import importlib
import typing
import warnings


def __getattr__(name: str) -> typing.Any:
    warnings.warn(
        f"`{__name__}.{name}` is deprecated, import it from"
        " `zha.application.platforms.sensor.device_class` instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return getattr(
        importlib.import_module("zha.application.platforms.sensor.device_class"), name
    )
