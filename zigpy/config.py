"""Config schemas and validation."""
from typing import Union

import voluptuous as vol
import zigpy.types as t

CONF_DATABASE = "database_path"
CONF_DEVICE = "device"
CONF_DEVICE_PATH = "path"
CONF_NWK = "network"
CONF_NWK_CHANNEL = "channel"
CONF_NWK_CHANNEL_DEFAULT = 15
CONF_NWK_CHANNELS = "channels"
CONF_NWK_CHANNELS_DEFAULT = [15, 20, 25]
CONF_NWK_EXTENDED_PAN_ID = "extended_pan_id"
CONF_NWK_EXTENDED_PAN_ID_DEFAULT = t.ExtendedPanId(
    [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
)
CONF_NWK_PAN_ID = "pan_id"
CONF_NWK_PAN_ID_DEFAULT = t.PanId(0x0000)
CONF_NWK_KEY = "key"
CONF_NWK_KEY_DEFAULT = t.KeyData(
    [
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)
CONF_NWK_TC_LINK_KEY = "tc_link_key"
CONF_NWK_TC_LINK_KEY_DEFAULT = t.KeyData(
    [
        0x5A,
        0x69,
        0x67,
        0x42,
        0x65,
        0x65,
        0x41,
        0x6C,
        0x6C,
        0x69,
        0x61,
        0x6E,
        0x63,
        0x65,
        0x30,
        0x39,
    ]
)
CONF_NWK_UPDATE_ID = "update_id"
CONF_NWK_UPDATE_ID_DEFAULT = 0x00
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
SCHEMA_NETWORK = vol.Schema(
    {
        vol.Optional(CONF_NWK_CHANNEL, default=CONF_NWK_CHANNEL_DEFAULT): vol.All(
            int, vol.Range(min=11, max=26)
        ),
        vol.Optional(CONF_NWK_CHANNELS, default=CONF_NWK_CHANNELS_DEFAULT): vol.All(
            list, t.Channels.from_channel_list
        ),
        vol.Optional(CONF_NWK_PAN_ID, default=CONF_NWK_PAN_ID_DEFAULT): vol.Coerce(
            t.PanId
        ),
        vol.Optional(
            CONF_NWK_EXTENDED_PAN_ID, default=CONF_NWK_EXTENDED_PAN_ID_DEFAULT
        ): t.ExtendedPanId,
        vol.Optional(CONF_NWK_UPDATE_ID, default=CONF_NWK_UPDATE_ID_DEFAULT): vol.Range(
            min=0, max=255
        ),
        vol.Optional(CONF_NWK_KEY, default=CONF_NWK_KEY_DEFAULT): vol.All(
            list, vol.Coerce(t.KeyData)
        ),
    }
)
SCHEMA_NETWORK_UPDATE = vol.Schema(
    {
        vol.Optional(CONF_NWK_CHANNEL): vol.All(int, vol.Range(min=11, max=26)),
        vol.Optional(CONF_NWK_CHANNELS): vol.All(list, t.Channels.from_channel_list),
        vol.Optional(CONF_NWK_PAN_ID): vol.Coerce(t.PanId),
        vol.Optional(CONF_NWK_EXTENDED_PAN_ID): t.ExtendedPanId,
        vol.Optional(CONF_NWK_UPDATE_ID): vol.Range(min=0, max=255),
        vol.Optional(CONF_NWK_KEY): vol.All(list, vol.Coerce(t.KeyData)),
    }
)

SCHEMA_OTA = {
    vol.Optional(CONF_OTA_IKEA, default=False): cv_boolean,
    vol.Optional(CONF_OTA_LEDVANCE, default=False): cv_boolean,
    vol.Optional(CONF_OTA_DIR, default=None): vol.Any(None, str),
}

ZIGPY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DATABASE, default=None): vol.Any(None, str),
        vol.Optional(CONF_NWK, default={}): SCHEMA_NETWORK,
        vol.Optional(CONF_OTA, default={}): SCHEMA_OTA,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = ZIGPY_SCHEMA.extend(
    {vol.Required(CONF_DEVICE): SCHEMA_DEVICE}, extra=vol.ALLOW_EXTRA
)
