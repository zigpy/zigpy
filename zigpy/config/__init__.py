"""Config schemas and validation."""

import voluptuous as vol

from zigpy.config.defaults import (
    CONF_MAX_CONCURRENT_REQUESTS_DEFAULT,
    CONF_NWK_BACKUP_ENABLED_DEFAULT,
    CONF_NWK_BACKUP_PERIOD_DEFAULT,
    CONF_NWK_CHANNEL_DEFAULT,
    CONF_NWK_CHANNELS_DEFAULT,
    CONF_NWK_EXTENDED_PAN_ID_DEFAULT,
    CONF_NWK_KEY_DEFAULT,
    CONF_NWK_KEY_SEQ_DEFAULT,
    CONF_NWK_PAN_ID_DEFAULT,
    CONF_NWK_TC_ADDRESS_DEFAULT,
    CONF_NWK_TC_LINK_KEY_DEFAULT,
    CONF_NWK_UPDATE_ID_DEFAULT,
    CONF_NWK_VALIDATE_SETTINGS_DEFAULT,
    CONF_OTA_IKEA_DEFAULT,
    CONF_OTA_INOVELLI_DEFAULT,
    CONF_OTA_LEDVANCE_DEFAULT,
    CONF_OTA_OTAU_DIR_DEFAULT,
    CONF_OTA_SALUS_DEFAULT,
    CONF_OTA_SONOFF_DEFAULT,
    CONF_SOURCE_ROUTING_DEFAULT,
    CONF_TOPO_SCAN_ENABLED_DEFAULT,
    CONF_TOPO_SCAN_PERIOD_DEFAULT,
    CONF_TOPO_SKIP_COORDINATOR_DEFAULT,
)
from zigpy.config.validators import cv_boolean, cv_hex, cv_key, cv_simple_descriptor
import zigpy.types as t

CONF_DATABASE = "database_path"
CONF_DEVICE = "device"
CONF_DEVICE_PATH = "path"
CONF_MAX_CONCURRENT_REQUESTS = "max_concurrent_requests"
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
CONF_NWK_BACKUP_ENABLED = "backup_enabled"
CONF_NWK_BACKUP_PERIOD = "backup_period"
CONF_NWK_VALIDATE_SETTINGS = "validate_network_settings"
CONF_OTA = "ota"
CONF_OTA_DIR = "otau_directory"
CONF_OTA_IKEA = "ikea_provider"
CONF_OTA_IKEA_URL = "ikea_update_url"
CONF_OTA_INOVELLI = "inovelli_provider"
CONF_OTA_LEDVANCE = "ledvance_provider"
CONF_OTA_SALUS = "salus_provider"
CONF_OTA_SONOFF = "sonoff_provider"
CONF_OTA_SONOFF_URL = "sonoff_update_url"
CONF_SOURCE_ROUTING = "source_routing"
CONF_TOPO_SCAN_PERIOD = "topology_scan_period"
CONF_TOPO_SCAN_ENABLED = "topology_scan_enabled"
CONF_TOPO_SKIP_COORDINATOR = "topology_scan_skip_coordinator"
CONF_ADDITIONAL_ENDPOINTS = "additional_endpoints"


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
    vol.Optional(CONF_OTA_IKEA_URL): vol.Url(),
    vol.Optional(CONF_OTA_INOVELLI, default=CONF_OTA_INOVELLI_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_LEDVANCE, default=CONF_OTA_LEDVANCE_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_SALUS, default=CONF_OTA_SALUS_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_SONOFF, default=CONF_OTA_SONOFF_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_SONOFF_URL): vol.Url(),
}

ZIGPY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DATABASE, default=None): vol.Any(None, str),
        vol.Optional(CONF_NWK, default={}): SCHEMA_NETWORK,
        vol.Optional(CONF_OTA, default={}): SCHEMA_OTA,
        vol.Optional(
            CONF_TOPO_SCAN_PERIOD, default=CONF_TOPO_SCAN_PERIOD_DEFAULT
        ): vol.All(int, vol.Range(min=20)),
        vol.Optional(
            CONF_TOPO_SCAN_ENABLED, default=CONF_TOPO_SCAN_ENABLED_DEFAULT
        ): cv_boolean,
        vol.Optional(
            CONF_TOPO_SKIP_COORDINATOR, default=CONF_TOPO_SKIP_COORDINATOR_DEFAULT
        ): cv_boolean,
        vol.Optional(
            CONF_NWK_BACKUP_ENABLED, default=CONF_NWK_BACKUP_ENABLED_DEFAULT
        ): cv_boolean,
        vol.Optional(
            CONF_NWK_BACKUP_PERIOD, default=CONF_NWK_BACKUP_PERIOD_DEFAULT
        ): vol.All(cv_hex, vol.Range(min=1)),
        vol.Optional(
            CONF_NWK_VALIDATE_SETTINGS, default=CONF_NWK_VALIDATE_SETTINGS_DEFAULT
        ): cv_boolean,
        vol.Optional(CONF_ADDITIONAL_ENDPOINTS, default=[]): [cv_simple_descriptor],
        vol.Optional(
            CONF_MAX_CONCURRENT_REQUESTS, default=CONF_MAX_CONCURRENT_REQUESTS_DEFAULT
        ): vol.All(int, vol.Range(min=0)),
        vol.Optional(CONF_SOURCE_ROUTING, default=CONF_SOURCE_ROUTING_DEFAULT): (
            cv_boolean
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = ZIGPY_SCHEMA.extend(
    {vol.Required(CONF_DEVICE): SCHEMA_DEVICE}, extra=vol.ALLOW_EXTRA
)
