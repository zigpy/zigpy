"""Zigpy Constants."""

from __future__ import annotations

SIG_ENDPOINTS = "endpoints"
SIG_EP_INPUT = "input_clusters"
SIG_EP_OUTPUT = "output_clusters"
SIG_EP_PROFILE = "profile_id"
SIG_EP_TYPE = "device_type"
SIG_MANUFACTURER = "manufacturer"
SIG_MODEL = "model"
SIG_MODELS_INFO = "models_info"
SIG_NODE_DESC = "node_desc"
SIG_SKIP_CONFIG = "skip_configuration"

INTERFERENCE_MESSAGE = (
    "If you are having problems joining new devices, are missing sensor"
    " updates, or have issues keeping devices joined, ensure your"
    " coordinator is away from interference sources such as USB 3.0"
    " devices, SSDs, WiFi routers, etc."
)

APS_REPLY_TIMEOUT = 5
APS_REPLY_TIMEOUT_EXTENDED = 28
