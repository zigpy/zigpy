from __future__ import annotations

import zigpy.types as t

PROFILE_ID = 41440


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
