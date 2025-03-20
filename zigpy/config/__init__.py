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
    CONF_NWK_MAX_RETRIES_DEFAULT,
    CONF_NWK_PAN_ID_DEFAULT,
    CONF_NWK_TC_ADDRESS_DEFAULT,
    CONF_NWK_TC_LINK_KEY_DEFAULT,
    CONF_NWK_UPDATE_ID_DEFAULT,
    CONF_NWK_VALIDATE_SETTINGS_DEFAULT,
    CONF_OTA_BROADCAST_ENABLED_DEFAULT,
    CONF_OTA_BROADCAST_INITIAL_DELAY_DEFAULT,
    CONF_OTA_BROADCAST_INTERVAL_DEFAULT,
    CONF_OTA_DISABLE_DEFAULT_PROVIDERS_DEFAULT,
    CONF_OTA_ENABLED_DEFAULT,
    CONF_OTA_EXTRA_PROVIDERS_DEFAULT,
    CONF_OTA_PROVIDERS_DEFAULT,
    CONF_SOURCE_ROUTING_DEFAULT,
    CONF_TOPO_SCAN_ENABLED_DEFAULT,
    CONF_TOPO_SCAN_PERIOD_DEFAULT,
    CONF_TOPO_SKIP_COORDINATOR_DEFAULT,
    CONF_WATCHDOG_ENABLED_DEFAULT,
)
from zigpy.config.validators import (
    cv_boolean,
    cv_deprecated,
    cv_folder,
    cv_hex,
    cv_json_file,
    cv_key,
    cv_ota_provider,
    cv_ota_provider_name,
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
CONF_NWK_MAX_RETRIES = "max_retries"
CONF_NWK_TC_ADDRESS = "tc_address"
CONF_NWK_TC_LINK_KEY = "tc_link_key"
CONF_NWK_UPDATE_ID = "update_id"
CONF_NWK_BACKUP_ENABLED = "backup_enabled"
CONF_NWK_BACKUP_PERIOD = "backup_period"
CONF_NWK_VALIDATE_SETTINGS = "validate_network_settings"
CONF_OTA = "ota"
CONF_OTA_PROVIDERS = "providers"
CONF_OTA_ENABLED = "enabled"
CONF_OTA_EXTRA_PROVIDERS = "extra_providers"
CONF_OTA_DISABLE_DEFAULT_PROVIDERS = "disable_default_providers"
CONF_OTA_PROVIDER_TYPE = "type"
CONF_OTA_PROVIDER_URL = "url"
CONF_OTA_PROVIDER_PATH = "path"
CONF_OTA_PROVIDER_INDEX_FILE = "index_file"
CONF_OTA_PROVIDER_OVERRIDE_PREVIOUS = "override_previous"
CONF_OTA_PROVIDER_WARNING = "warning"
CONF_OTA_BROADCAST_ENABLED = "broadcast_enabled"
CONF_OTA_BROADCAST_INITIAL_DELAY = "broadcast_initial_delay"
CONF_OTA_BROADCAST_INTERVAL = "broadcast_interval"
CONF_OTA_PROVIDER_MANUF_IDS = "manufacturer_ids"
CONF_SOURCE_ROUTING = "source_routing"
CONF_STARTUP_ENERGY_SCAN = (
    "startup_energy_scan"  # Unused, kept to avoid breaking imports in dependencies
)
CONF_TOPO_SCAN_PERIOD = "topology_scan_period"
CONF_TOPO_SCAN_ENABLED = "topology_scan_enabled"
CONF_TOPO_SKIP_COORDINATOR = "topology_scan_skip_coordinator"
CONF_WATCHDOG_ENABLED = "watchdog_enabled"

CONF_OTA_ALLOW_ADVANCED_DIR_STRING = (
    "I understand I can *destroy* my devices by enabling OTA updates from files."
    " Some OTA updates can be mistakenly applied to the wrong device, breaking it."
    " I am consciously using this at my own risk."
)

# Deprecated keys
CONF_OTA_ADVANCED_DIR = "advanced_ota_dir"
CONF_OTA_ALLOW_ADVANCED_DIR = "allow_advanced_ota_dir"
CONF_OTA_DIR = "otau_dir"
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

SCHEMA_OTA_PROVIDER_BASE = vol.Schema(
    {
        vol.Required(CONF_OTA_PROVIDER_TYPE): cv_ota_provider_name,
        vol.Optional(CONF_OTA_PROVIDER_OVERRIDE_PREVIOUS, default=False): bool,
        vol.Optional(CONF_OTA_PROVIDER_MANUF_IDS, default=None): vol.Any(
            None, [cv_hex]
        ),
    }
)

SCHEMA_OTA_PROVIDER_URL = SCHEMA_OTA_PROVIDER_BASE.extend(
    {vol.Optional(CONF_OTA_PROVIDER_URL): vol.Url()}
)

SCHEMA_OTA_PROVIDER_URL_REQUIRED = SCHEMA_OTA_PROVIDER_BASE.extend(
    {vol.Required(CONF_OTA_PROVIDER_URL): vol.Url()}
)

SCHEMA_OTA_PROVIDER_JSON_INDEX = SCHEMA_OTA_PROVIDER_BASE.extend(
    {vol.Required(CONF_OTA_PROVIDER_INDEX_FILE): cv_json_file}
)

SCHEMA_OTA_PROVIDER_FOLDER = SCHEMA_OTA_PROVIDER_BASE.extend(
    {
        vol.Required(CONF_OTA_PROVIDER_PATH): cv_folder,
        vol.Required(CONF_OTA_PROVIDER_WARNING): vol.Equal(
            CONF_OTA_ALLOW_ADVANCED_DIR_STRING
        ),
    }
)

# Deprecated
SCHEMA_OTA_PROVIDER_REMOTE = vol.Schema(
    {
        vol.Required(CONF_OTA_PROVIDER_URL): str,
        vol.Optional(CONF_OTA_PROVIDER_MANUF_IDS, default=[]): [cv_hex],
    }
)

SCHEMA_OTA_BASE = {
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
    vol.Optional(CONF_OTA_PROVIDERS, default=CONF_OTA_PROVIDERS_DEFAULT): [
        cv_ota_provider
    ],
    vol.Optional(
        CONF_OTA_DISABLE_DEFAULT_PROVIDERS,
        default=CONF_OTA_DISABLE_DEFAULT_PROVIDERS_DEFAULT,
    ): [cv_ota_provider_name],
    vol.Optional(CONF_OTA_EXTRA_PROVIDERS, default=CONF_OTA_EXTRA_PROVIDERS_DEFAULT): [
        cv_ota_provider
    ],
}

SCHEMA_OTA_DEPRECATED = {
    # Deprecated OTA providers
    vol.Optional(CONF_OTA_IKEA): vol.All(
        cv_deprecated(
            "The `ikea_provider` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'ikea'}]`"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    vol.Optional(CONF_OTA_INOVELLI): vol.All(
        cv_deprecated(
            "The `inovelli_provider` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'inovelli'}]`"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    vol.Optional(CONF_OTA_LEDVANCE): vol.All(
        cv_deprecated(
            "The `ledvance_provider` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'ledvance'}]`"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    vol.Optional(CONF_OTA_SALUS): vol.All(
        cv_deprecated(
            "The `salus_provider` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'salus'}]`"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    vol.Optional(CONF_OTA_SONOFF): vol.All(
        cv_deprecated(
            "The `sonoff_provider` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'sonoff'}]`"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    vol.Optional(CONF_OTA_THIRDREALITY): vol.All(
        cv_deprecated(
            "The `thirdreality_provider` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'thirdreality'}]`"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    # Z2M OTA providers
    vol.Optional(CONF_OTA_Z2M_LOCAL_INDEX): vol.All(
        cv_deprecated(
            "The `z2m_local_index` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'z2m_local',"
            " 'index_file': '/path/to/index.json'}]`"
        ),
        cv_json_file,
    ),
    vol.Optional(CONF_OTA_Z2M_REMOTE_INDEX): vol.All(
        cv_deprecated(
            "The `z2m_index` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'z2m'}]"
        ),
        vol.Any(
            cv_boolean,
            vol.Url(),
        ),
    ),
    # Advanced OTA config. You *do not* need to use this unless you're testing a new
    # OTA firmware that has no known metadata.
    vol.Optional(CONF_OTA_ADVANCED_DIR): vol.All(
        cv_deprecated(
            "The `advanced_ota_dir` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'advanced',"
            " 'warning': 'I understand ...'}]"
        ),
        cv_folder,
    ),
    # Unused keys
    vol.Optional(CONF_OTA_ALLOW_ADVANCED_DIR): vol.All(
        cv_deprecated(
            "The `allow_advanced_ota_dir` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'advanced',"
            " 'warning': 'I understand ...'}]"
        ),
        vol.Equal(CONF_OTA_ALLOW_ADVANCED_DIR_STRING),
    ),
    vol.Optional(CONF_OTA_REMOTE_PROVIDERS): vol.All(
        cv_deprecated(
            "The `remote_providers` key is deprecated, migrate your configuration"
            " to the `extra_providers` list instead: `extra_providers: [{'type': 'remote',"
            " 'url': 'https://example.com'}]`"
        ),
        [SCHEMA_OTA_PROVIDER_REMOTE],
    ),
    vol.Optional(CONF_OTA_SONOFF_URL): vol.All(
        cv_deprecated("The `sonoff_update_url` key has been removed")
    ),
    vol.Optional(CONF_OTA_DIR): vol.All(
        cv_deprecated(
            "`otau_dir` has been removed, use the `z2m` or `zigpy` providers instead"
        )
    ),
    vol.Optional(CONF_OTA_IKEA_URL): vol.All(
        cv_deprecated("The `ikea_update_url` key has been removed")
    ),
}

SCHEMA_OTA = vol.Schema(
    {**SCHEMA_OTA_BASE, **SCHEMA_OTA_DEPRECATED}, extra=vol.ALLOW_EXTRA
)

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
        vol.Optional(
            CONF_NWK_MAX_RETRIES, default=CONF_NWK_MAX_RETRIES_DEFAULT
        ): vol.All(int, vol.Range(min=0)),
        vol.Optional(CONF_ADDITIONAL_ENDPOINTS, default=[]): [cv_simple_descriptor],
        vol.Optional(
            CONF_MAX_CONCURRENT_REQUESTS, default=CONF_MAX_CONCURRENT_REQUESTS_DEFAULT
        ): vol.All(int, vol.Range(min=0)),
        vol.Optional(CONF_SOURCE_ROUTING, default=CONF_SOURCE_ROUTING_DEFAULT): (
            cv_boolean
        ),
        vol.Optional(
            CONF_WATCHDOG_ENABLED, default=CONF_WATCHDOG_ENABLED_DEFAULT
        ): cv_boolean,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = ZIGPY_SCHEMA.extend(
    {vol.Required(CONF_DEVICE): SCHEMA_DEVICE}, extra=vol.ALLOW_EXTRA
)
