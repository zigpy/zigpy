from __future__ import annotations

import zigpy.types as t

CONF_DEVICE_BAUDRATE_DEFAULT = 115200
CONF_DEVICE_FLOW_CONTROL_DEFAULT = None
CONF_STARTUP_ENERGY_SCAN_DEFAULT = True
CONF_MAX_CONCURRENT_REQUESTS_DEFAULT = 8
CONF_NWK_BACKUP_ENABLED_DEFAULT = True
CONF_NWK_BACKUP_PERIOD_DEFAULT = 24 * 60  # 24 hours
CONF_NWK_CHANNEL_DEFAULT = None
CONF_NWK_CHANNELS_DEFAULT = [11, 15, 20, 25]
CONF_NWK_EXTENDED_PAN_ID_DEFAULT = None
CONF_NWK_PAN_ID_DEFAULT = None
CONF_NWK_KEY_DEFAULT = None
CONF_NWK_KEY_SEQ_DEFAULT = 0x00
CONF_NWK_TC_ADDRESS_DEFAULT = None
CONF_NWK_TC_LINK_KEY_DEFAULT = t.KeyData(b"ZigBeeAlliance09")
CONF_NWK_UPDATE_ID_DEFAULT = 0x00
CONF_NWK_VALIDATE_SETTINGS_DEFAULT = False
CONF_OTA_IKEA_DEFAULT = False
CONF_OTA_INOVELLI_DEFAULT = True
CONF_OTA_LEDVANCE_DEFAULT = True
CONF_OTA_OTAU_DIR_DEFAULT = None
CONF_OTA_SALUS_DEFAULT = True
CONF_OTA_SONOFF_DEFAULT = True
CONF_OTA_THIRDREALITY_DEFAULT = True
CONF_SOURCE_ROUTING_DEFAULT = False
CONF_TOPO_SCAN_PERIOD_DEFAULT = 4 * 60  # 4 hours
CONF_TOPO_SCAN_ENABLED_DEFAULT = True
CONF_TOPO_SKIP_COORDINATOR_DEFAULT = False
CONF_WATCHDOG_ENABLED_DEFAULT = True
