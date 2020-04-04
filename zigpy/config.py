"""Config schemas and validation."""
import voluptuous as vol

CONF_DATABASE = "database_path"
CONF_DEVICE = "device"
CONF_DEVICE_PATH = "path"
CONF_OTA = "ota"
CONF_OTA_DIR = "otau_directory"
CONF_OTA_IKEA = "ikea_provider"
CONF_OTA_LEDVANCE = "ledvance_provider"

SCHEMA_DEVICE = vol.Schema({vol.Required(CONF_DEVICE_PATH): vol.PathExists()})
SCHEMA_OTA = {
    vol.Optional(CONF_OTA_IKEA, default=False): vol.Boolean(),
    vol.Optional(CONF_OTA_LEDVANCE, default=False): vol.Boolean(),
    vol.Optional(CONF_OTA_DIR, default=None): vol.Any(None, vol.IsDir()),
}

SCHEMA = {
    vol.Optional(CONF_DATABASE, default=None): vol.IsFile(),
    vol.Optional(CONF_OTA, default={}): SCHEMA_OTA,
    vol.Required(CONF_DEVICE): SCHEMA_DEVICE,
}
