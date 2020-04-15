"""Config schemas and validation."""
from typing import Union

import voluptuous as vol

CONF_DATABASE = "database_path"
CONF_DEVICE = "device"
CONF_DEVICE_PATH = "path"
CONF_OTA = "ota"
CONF_OTA_DIR = "otau_directory"
CONF_OTA_IKEA = "ikea_provider"
CONF_OTA_LEDVANCE = "ledvance_provider"


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
    raise vol.Invalid("invalid boolean value {}".format(value))


SCHEMA_DEVICE = vol.Schema({vol.Required(CONF_DEVICE_PATH): str})
SCHEMA_OTA = {
    vol.Optional(CONF_OTA_IKEA, default=False): cv_boolean,
    vol.Optional(CONF_OTA_LEDVANCE, default=False): cv_boolean,
    vol.Optional(CONF_OTA_DIR, default=None): vol.Any(None, str),
}

ZIGPY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DATABASE, default=None): vol.Any(None, str),
        vol.Optional(CONF_OTA, default={}): SCHEMA_OTA,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = ZIGPY_SCHEMA.extend(
    {vol.Required(CONF_DEVICE): SCHEMA_DEVICE}, extra=vol.ALLOW_EXTRA
)
