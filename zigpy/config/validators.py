from __future__ import annotations

import logging
import pathlib
import typing
import warnings

import voluptuous as vol

import zigpy.types as t
import zigpy.zdo.types as zdo_t
import zigpy.config

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


def cv_exact_object(expected_value: str) -> typing.Callable[[typing.Any], typing.Literal[True]]:
    """Factory function for creating an exact object comparison validator."""

    def wrapper(obj: typing.Any) -> typing.Literal[True]:
        if obj != expected_value:
            raise vol.Invalid(f"Expected {expected_value!r}, got {obj!r}")

        return True

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


def cv_ota_provider(obj: dict) -> zigpy.ota.providers.BaseOtaProvider:
    """Validate OTA provider."""
    import zigpy.ota.providers

    provider_type = obj.get(zigpy.config.CONF_OTA_PROVIDER_TYPE)

    if provider_type not in zigpy.ota.providers.OTA_PROVIDERS:
        raise vol.Invalid(f"Unsupported OTA provider type: {provider_type!r}")

    provider_cls = zigpy.ota.providers.OTA_PROVIDERS[provider_type]

    if provider_type in (
        "ikea",
        "ledvance",
        "sonoff",
        "inovelli",
        "thirdreality",
        "z2m",
    ):
        return provider_cls(**zigpy.config.SCHEMA_OTA_PROVIDER_URL(obj))
    elif provider_type in (
        "z2m_local",
        "zigpy_local",
    ):
        return provider_cls(**zigpy.config.SCHEMA_OTA_PROVIDER_JSON_INDEX(obj))
    elif provider_type in ("advanced_file",):
        config = zigpy.config.SCHEMA_OTA_PROVIDER_FOLDER(obj)
        config.pop("warning")  # The warning is just for the user

        return provider_cls(**config)
    elif provider_type in ("zigpy",):
        return provider_cls(**zigpy.config.SCHEMA_OTA_PROVIDER_URL_REQUIRED(obj))
    else:
        raise RuntimeError("Unknown OTA provider type")  # pragma: no cover
