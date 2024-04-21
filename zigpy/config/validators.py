from __future__ import annotations

import logging
import pathlib
import typing
import warnings

import voluptuous as vol

import zigpy.types as t
import zigpy.zdo.types as zdo_t

_LOGGER = logging.getLogger(__name__)


def cv_boolean(value: bool | int | str) -> bool:
    """Validate and coerce a boolean value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.lower().strip()
        if value in ("1", "true", "yes", "on", "enable"):
            return True
        if value in ("0", "false", "no", "off", "disable"):
            return False
    elif isinstance(value, int):
        return bool(value)
    raise vol.Invalid(f"invalid boolean '{value}' value")


def cv_hex(value: int | str) -> int:
    """Convert string with possible hex number into int."""
    if isinstance(value, int):
        return value

    if not isinstance(value, str):
        raise vol.Invalid(f"{value} is not a valid hex number")

    try:
        if value.startswith("0x"):
            value = int(value, base=16)
        else:
            value = int(value)
    except ValueError:
        raise vol.Invalid(f"Could not convert '{value}' to number")

    return value


def cv_key(key: list[int]) -> t.KeyData:
    """Validate a key."""
    if not isinstance(key, list) or not all(isinstance(v, int) for v in key):
        raise vol.Invalid("key must be a list of integers")

    if len(key) != 16:
        raise vol.Invalid("key length must be 16")

    if not all(0 <= e <= 255 for e in key):
        raise vol.Invalid("Key bytes must be within (0..255) range")

    return t.KeyData(key)


def cv_simple_descriptor(obj: dict[str, typing.Any]) -> zdo_t.SimpleDescriptor:
    """Validates a ZDO simple descriptor."""
    if isinstance(obj, zdo_t.SimpleDescriptor):
        return obj
    elif not isinstance(obj, dict):
        raise vol.Invalid("Not a dictionary")

    descriptor = zdo_t.SimpleDescriptor(**obj)

    if not descriptor.is_valid:
        raise vol.Invalid(f"Invalid simple descriptor {descriptor!r}")

    return descriptor


def cv_deprecated(message: str) -> typing.Callable[[typing.Any], typing.Any]:
    """Factory function for creating a deprecation warning validator."""

    def wrapper(obj: typing.Any) -> typing.Any:
        _LOGGER.warning(message)
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        return obj

    return wrapper


def cv_exact_object(expected_value: str) -> typing.Callable[[typing.Any], bool]:
    """Factory function for creating an exact object comparison validator."""

    def wrapper(obj: typing.Any) -> typing.Any:
        if obj != expected_value:
            return False

        return expected_value

    return wrapper


def cv_json_file(value: str) -> pathlib.Path:
    """Validate a JSON file."""
    path = pathlib.Path(value)

    if not path.is_file():
        raise vol.Invalid(f"{value} is not a JSON file")

    return path


def cv_folder(value: str) -> pathlib.Path:
    """Validate a folder path."""
    path = pathlib.Path(value)

    if not path.is_dir():
        raise vol.Invalid(f"{value} is not a directory")

    return path
