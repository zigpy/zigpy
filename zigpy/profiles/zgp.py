from __future__ import annotations

import zigpy.types as t

PROFILE_ID = 41440
GREENPOWER_CLUSTER_ID = 0x0021
GREENPOWER_ENDPOINT_ID = 242
GREENPOWER_BROADCAST_GROUP = 0x0B84
# ZigBeeAlliance09, Table 32
GREENPOWER_DEFAULT_LINK_KEY = t.KeyData(
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


# Infrastructure device types
# Table 15
class DeviceType(t.enum16):
    PROXY = 0x0060
    PROXY_BASIC = 0x0061
    TARGET_PLUS = 0x0062
    TARGET = 0x0063
    COMM_TOOL = 0x0064
    COMBO = 0x0065
    COMBO_BASIC = 0x0066


CLUSTERS = {
    DeviceType.PROXY: ([0x0021], [0x0021]),
    DeviceType.PROXY_BASIC: ([], [0x0021]),
    DeviceType.TARGET_PLUS: ([0x0021], [0x0021]),
    DeviceType.TARGET: ([0x0021], [0x0021]),
    DeviceType.COMM_TOOL: ([0x0021], []),
    DeviceType.COMBO: ([0x0021], [0x0021]),
    DeviceType.COMBO_BASIC: ([0x0021], [0x0021]),
}
