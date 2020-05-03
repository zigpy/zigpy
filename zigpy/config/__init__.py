"""Config schemas and validation."""

import voluptuous as vol
from zigpy.config.defaults import (
    CONF_NWK_CHANNEL_DEFAULT,
    CONF_NWK_CHANNELS_DEFAULT,
    CONF_NWK_EXTENDED_PAN_ID_DEFAULT,
    CONF_NWK_KEY_DEFAULT,
    CONF_NWK_KEY_SEQ_DEFAULT,
    CONF_NWK_PAN_ID_DEFAULT,
    CONF_NWK_TC_ADDRESS_DEFAULT,
    CONF_NWK_TC_LINK_KEY_DEFAULT,
    CONF_NWK_UPDATE_ID_DEFAULT,
    CONF_OTA_IKEA_DEFAULT,
    CONF_OTA_LEDVANCE_DEFAULT,
    CONF_OTA_OTAU_DIR_DEFAULT,
)
from zigpy.config.validators import cv_boolean, cv_hex, cv_key
import zigpy.types as t

CONF_DATABASE = "database_path"
CONF_DEVICE = "device"
CONF_DEVICE_PATH = "path"
CONF_NWK = "network"
CONF_NWK_CHANNEL = "channel"
CONF_NWK_CHANNELS = "channels"
CONF_NWK_EXTENDED_PAN_ID = "extended_pan_id"
CONF_NWK_PAN_ID = "pan_id"
CONF_NWK_KEY = "key"
CONF_NWK_KEY_SEQ = "key_sequence_number"
CONF_NWK_TC_ADDRESS = "tc_address"
CONF_NWK_TC_LINK_KEY = "tc_link_key"
CONF_NWK_UPDATE_ID = "update_id"
CONF_OTA = "ota"
CONF_OTA_DIR = "otau_directory"
CONF_OTA_IKEA = "ikea_provider"
CONF_OTA_LEDVANCE = "ledvance_provider"

SCHEMA_DEVICE = vol.Schema({vol.Required(CONF_DEVICE_PATH): str})
SCHEMA_NETWORK = vol.Schema(
    {
        vol.Optional(CONF_NWK_CHANNEL, default=CONF_NWK_CHANNEL_DEFAULT): vol.All(
            cv_hex, vol.Range(min=11, max=26)
        ),
        vol.Optional(CONF_NWK_CHANNELS, default=CONF_NWK_CHANNELS_DEFAULT): vol.Any(
            t.Channels, vol.All(list, t.Channels.from_channel_list)
        ),
        vol.Optional(
            CONF_NWK_EXTENDED_PAN_ID, default=CONF_NWK_EXTENDED_PAN_ID_DEFAULT
        ): vol.Any(None, t.ExtendedPanId, t.ExtendedPanId.convert),
        vol.Optional(CONF_NWK_KEY, default=CONF_NWK_KEY_DEFAULT): vol.Any(None, cv_key),
        vol.Optional(CONF_NWK_KEY_SEQ, default=CONF_NWK_KEY_SEQ_DEFAULT): vol.Range(
            min=0, max=255
        ),
        vol.Optional(CONF_NWK_PAN_ID, default=CONF_NWK_PAN_ID_DEFAULT): vol.Any(
            None, t.PanId, vol.All(cv_hex, vol.Coerce(t.PanId))
        ),
        vol.Optional(CONF_NWK_TC_ADDRESS, default=CONF_NWK_TC_ADDRESS_DEFAULT): vol.Any(
            None, t.EUI64, t.EUI64.convert
        ),
        vol.Optional(
            CONF_NWK_TC_LINK_KEY, default=CONF_NWK_TC_LINK_KEY_DEFAULT
        ): cv_key,
        vol.Optional(CONF_NWK_UPDATE_ID, default=CONF_NWK_UPDATE_ID_DEFAULT): vol.All(
            cv_hex, vol.Range(min=0, max=255)
        ),
    }
)
SCHEMA_OTA = {
    vol.Optional(CONF_OTA_DIR, default=CONF_OTA_OTAU_DIR_DEFAULT): vol.Any(None, str),
    vol.Optional(CONF_OTA_IKEA, default=CONF_OTA_IKEA_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_LEDVANCE, default=CONF_OTA_LEDVANCE_DEFAULT): cv_boolean,
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
