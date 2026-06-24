"""Compatibility shims: entity constants and units moved into ZHA.

`EntityType` and `EntityPlatform` live in `zha.application`; units and other
measurement constants live in `zha.units`.
"""

from __future__ import annotations

import importlib
import typing
import warnings

_MOVED_MODULES = ("zha.application", "zha.units")


def __getattr__(name: str) -> typing.Any:
    for module_path in _MOVED_MODULES:
        module = importlib.import_module(module_path)
        if hasattr(module, name):
            warnings.warn(
                f"`{__name__}.{name}` is deprecated, import it from"
                f" `{module_path}` instead",
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
