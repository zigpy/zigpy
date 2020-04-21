from typing import List, Union

import voluptuous as vol
import zigpy.types as t


def cv_boolean(value: Union[bool, int, str]) -> bool:
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


def cv_hex(value: Union[int, str]) -> int:
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


def cv_key(key: List[int]) -> t.KeyData:
    """Validate a key."""
    if not isinstance(key, list):
        raise vol.Invalid("key is expected to be a list of integers")

    if len(key) != 16:
        raise vol.Invalid("key list length must be 16")

    if not any((0 <= e <= 255 for e in key)):
        raise vol.Invalid("Key element myst be a within (0..255) range")

    return t.KeyData(key)
