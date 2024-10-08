from __future__ import annotations

import logging
import pathlib
import typing
import warnings

import voluptuous as vol

import zigpy.config
import zigpy.types as t
import zigpy.zdo.types as zdo_t

if typing.TYPE_CHECKING:
    import zigpy.ota.providers

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
    except ValueError as err:
        raise vol.Invalid(f"Could not convert '{value}' to number") from err

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
    if not isinstance(obj, dict):
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


def cv_ota_provider_name(name: str | None) -> type[zigpy.ota.providers.BaseOtaProvider]:
    """Validate OTA provider name."""
    import zigpy.ota.providers

    if name not in zigpy.ota.providers.OTA_PROVIDER_TYPES:
        raise vol.Invalid(f"Unknown OTA provider: {name!r}")

    return zigpy.ota.providers.OTA_PROVIDER_TYPES[name]


def cv_ota_provider(obj: dict) -> zigpy.ota.providers.BaseOtaProvider:
    """Validate OTA provider."""
    provider_type = obj.get(zigpy.config.CONF_OTA_PROVIDER_TYPE)
    provider_cls = cv_ota_provider_name(provider_type)

    kwargs = provider_cls.VOL_SCHEMA(obj)
    kwargs.pop(zigpy.config.CONF_OTA_PROVIDER_TYPE)

    return provider_cls(**kwargs)
