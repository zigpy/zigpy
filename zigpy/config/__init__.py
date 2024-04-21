"""Config schemas and validation."""

from __future__ import annotations

import voluptuous as vol

from zigpy.config.defaults import (
    CONF_DEVICE_BAUDRATE_DEFAULT,
    CONF_DEVICE_FLOW_CONTROL_DEFAULT,
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
    CONF_OTA_ADVANCED_DIR_DEFAULT,
    CONF_OTA_ALLOW_ADVANCED_DIR_DEFAULT,
    CONF_OTA_BROADCAST_ENABLED_DEFAULT,
    CONF_OTA_BROADCAST_INITIAL_DELAY_DEFAULT,
    CONF_OTA_BROADCAST_INTERVAL_DEFAULT,
    CONF_OTA_ENABLED_DEFAULT,
    CONF_OTA_IKEA_DEFAULT,
    CONF_OTA_INOVELLI_DEFAULT,
    CONF_OTA_LEDVANCE_DEFAULT,
    CONF_OTA_SALUS_DEFAULT,
    CONF_OTA_SONOFF_DEFAULT,
    CONF_OTA_THIRDREALITY_DEFAULT,
    CONF_OTA_Z2M_LOCAL_INDEX_DEFAULT,
    CONF_OTA_Z2M_REMOTE_INDEX_DEFAULT,
    CONF_SOURCE_ROUTING_DEFAULT,
    CONF_STARTUP_ENERGY_SCAN_DEFAULT,
    CONF_TOPO_SCAN_ENABLED_DEFAULT,
    CONF_TOPO_SCAN_PERIOD_DEFAULT,
    CONF_TOPO_SKIP_COORDINATOR_DEFAULT,
    CONF_WATCHDOG_ENABLED_DEFAULT,
)
from zigpy.config.validators import (
    cv_boolean,
    cv_deprecated,
    cv_exact_object,
    cv_folder,
    cv_hex,
    cv_json_file,
    cv_key,
    cv_simple_descriptor,
)
import zigpy.types as t

CONF_ADDITIONAL_ENDPOINTS = "additional_endpoints"
CONF_DATABASE = "database_path"
CONF_DEVICE = "device"
CONF_DEVICE_PATH = "path"
CONF_DEVICE_BAUDRATE = "baudrate"
CONF_DEVICE_FLOW_CONTROL = "flow_control"
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
CONF_OTA_ADVANCED_DIR = "advanced_ota_dir"
CONF_OTA_ALLOW_ADVANCED_DIR = "allow_advanced_ota_dir"
CONF_OTA_BROADCAST_ENABLED = "broadcast_enabled"
CONF_OTA_BROADCAST_INITIAL_DELAY = "broadcast_initial_delay"
CONF_OTA_BROADCAST_INTERVAL = "broadcast_interval"
CONF_OTA_DIR = "otau_dir"
CONF_OTA_ENABLED = "enabled"
CONF_OTA_IKEA = "ikea_provider"
CONF_OTA_IKEA_URL = "ikea_update_url"
CONF_OTA_INOVELLI = "inovelli_provider"
CONF_OTA_LEDVANCE = "ledvance_provider"
CONF_OTA_SALUS = "salus_provider"
CONF_OTA_SONOFF = "sonoff_provider"
CONF_OTA_SONOFF_URL = "sonoff_update_url"
CONF_OTA_THIRDREALITY = "thirdreality_provider"
CONF_OTA_REMOTE_PROVIDERS = "remote_providers"
CONF_OTA_Z2M_LOCAL_INDEX = "z2m_local_index"
CONF_OTA_Z2M_REMOTE_INDEX = "z2m_remote_index"
CONF_OTA_PROVIDER_URL = "url"
CONF_OTA_PROVIDER_MANUF_IDS = "manufacturer_ids"
CONF_SOURCE_ROUTING = "source_routing"
CONF_STARTUP_ENERGY_SCAN = "startup_energy_scan"
CONF_TOPO_SCAN_PERIOD = "topology_scan_period"
CONF_TOPO_SCAN_ENABLED = "topology_scan_enabled"
CONF_TOPO_SKIP_COORDINATOR = "topology_scan_skip_coordinator"
CONF_WATCHDOG_ENABLED = "watchdog_enabled"

CONF_OTA_ALLOW_ADVANCED_DIR_STRING = (
    "I understand I can *destroy* my devices by enabling OTA updates from files."
    " Some OTA updates can be mistakenly applied to the wrong device, breaking it."
    " I am consciously using this at my own risk."
)


SCHEMA_DEVICE = vol.Schema(
    {
        vol.Required(CONF_DEVICE_PATH): str,
        vol.Optional(CONF_DEVICE_BAUDRATE, default=CONF_DEVICE_BAUDRATE_DEFAULT): int,
        vol.Optional(
            CONF_DEVICE_FLOW_CONTROL, default=CONF_DEVICE_FLOW_CONTROL_DEFAULT
        ): vol.In(["hardware", "software", None]),
    }
)

SCHEMA_NETWORK = vol.Schema(
    {
        vol.Optional(CONF_NWK_CHANNEL, default=CONF_NWK_CHANNEL_DEFAULT): vol.Any(
            None, vol.All(cv_hex, vol.Range(min=11, max=26))
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

SCHEMA_OTA_PROVIDER = vol.Schema(
    {
        vol.Required(CONF_OTA_PROVIDER_URL): str,
        vol.Optional(CONF_OTA_PROVIDER_MANUF_IDS, default=[]): [cv_hex],
    }
)

SCHEMA_OTA = {
    vol.Optional(CONF_OTA_ENABLED, default=CONF_OTA_ENABLED_DEFAULT): cv_boolean,
    vol.Optional(
        CONF_OTA_BROADCAST_ENABLED, default=CONF_OTA_BROADCAST_ENABLED_DEFAULT
    ): cv_boolean,
    vol.Optional(
        CONF_OTA_BROADCAST_INITIAL_DELAY,
        default=CONF_OTA_BROADCAST_INITIAL_DELAY_DEFAULT,
    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(
        CONF_OTA_BROADCAST_INTERVAL, default=CONF_OTA_BROADCAST_INTERVAL_DEFAULT
    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(CONF_OTA_IKEA, default=CONF_OTA_IKEA_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_INOVELLI, default=CONF_OTA_INOVELLI_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_LEDVANCE, default=CONF_OTA_LEDVANCE_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_SALUS, default=CONF_OTA_SALUS_DEFAULT): cv_boolean,
    vol.Optional(CONF_OTA_SONOFF, default=CONF_OTA_SONOFF_DEFAULT): cv_boolean,
    vol.Optional(
        CONF_OTA_THIRDREALITY, default=CONF_OTA_THIRDREALITY_DEFAULT
    ): cv_boolean,
    vol.Optional(CONF_OTA_REMOTE_PROVIDERS, default=[]): [SCHEMA_OTA_PROVIDER],
    # Z2M OTA providers
    vol.Optional(
        CONF_OTA_Z2M_LOCAL_INDEX, default=CONF_OTA_Z2M_LOCAL_INDEX_DEFAULT
    ): vol.Any(None, cv_json_file),
    vol.Optional(
        CONF_OTA_Z2M_REMOTE_INDEX, default=CONF_OTA_Z2M_REMOTE_INDEX_DEFAULT
    ): vol.Any(None, vol.Url()),
    # Advanced OTA config. You *do not* need to use this unless you're testing a new
    # OTA firmware that has no known metadata.
    vol.Optional(CONF_OTA_ADVANCED_DIR, default=CONF_OTA_ADVANCED_DIR_DEFAULT): vol.Any(
        None, cv_folder
    ),
    vol.Optional(
        CONF_OTA_ALLOW_ADVANCED_DIR, default=CONF_OTA_ALLOW_ADVANCED_DIR_DEFAULT
    ): vol.All(cv_exact_object(CONF_OTA_ALLOW_ADVANCED_DIR_STRING)),
    # Deprecated keys
    vol.Optional(CONF_OTA_SONOFF_URL): vol.Any(
        cv_deprecated("The `sonoff_update_url` key has been removed")
    ),
    vol.Optional(CONF_OTA_DIR): vol.Any(
        cv_deprecated(
            "`otau_dir` has been removed, use `z2m_local_index` or `z2m_remote_index`"
        )
    ),
    vol.Optional(CONF_OTA_IKEA_URL): vol.All(
        cv_deprecated("The `ikea_update_url` key is deprecated and should be removed"),
        vol.Url(),
    ),
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
        vol.Optional(
            CONF_STARTUP_ENERGY_SCAN, default=CONF_STARTUP_ENERGY_SCAN_DEFAULT
        ): cv_boolean,
        vol.Optional(
            CONF_WATCHDOG_ENABLED, default=CONF_WATCHDOG_ENABLED_DEFAULT
        ): cv_boolean,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = ZIGPY_SCHEMA.extend(
    {vol.Required(CONF_DEVICE): SCHEMA_DEVICE}, extra=vol.ALLOW_EXTRA
)
