"""Green Power Domain"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

import zigpy.types as t
from zigpy.typing import AddressingMode
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    ZCLAttributeDef,
    ZCLCommandDef,
)

class GreenPowerTarget(Cluster):
    cluster_id: Final = 0x0021
    name: Final = "Green Power Target"
    ep_attribute: Final = "green_power"
    
    class AttributeDefs(BaseAttributeDefs):
        max_sink_table_entries: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        sink_table: Final = ZCLAttributeDef(
            id=0x0001, type=t.LongOctetString, access="r", mandatory=True
        )
        communication_mode: Final = ZCLAttributeDef(
            id=0x0002, type=t.bitmap8, access="rw", mandatory=True
        )
        commissioning_exit_mode: Final = ZCLAttributeDef(
            id=0x0003, type=t.bitmap8, access="rw", mandatory=True
        )
        commissioning_window: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint16_t, access="rw"
        )
        security_level: Final = ZCLAttributeDef(
            id=0x0005, type=t.bitmap8, access="rw", mandatory=True
        )
        functionality: Final = ZCLAttributeDef(
            id=0x0006, type=t.bitmap24, access="r", mandatory=True
        )
        active_functionality: Final = ZCLAttributeDef(
            id=0x0007, type=t.bitmap24, access="r", mandatory=True
        )
        joiningAllowUntil: Final = ZCLAttributeDef(
            id=0x9997, type=t.uint32_t, access="rw"
        )
        key: Final = ZCLAttributeDef(
            id=0x9998, type=t.uint32_t, access="rw"
        )
        counter: Final = ZCLAttributeDef(
            id=0x9999, type=t.uint64_t, access="rw"
        )
    
    class ServerCommandDefs(BaseCommandDefs):
        notification: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "options": t.bitmap8,
                "gpdId": t.uint32_t,
                "frameCounter": t.uint32_t,
                "commandId": t.uint8_t,
                "payload": t.LVBytes,
                "shortAddr?": t.uint16_t,
                "distance?": t.uint8_t
            },
            direction=False,
        )
        
        pairing_search: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "options": t.bitmap16,
                "gpdId": t.uint32_t
            },
            direction=False,
        )

        commissioning_notification: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "options": t.bitmap16,
                "gpdId": t.uint32_t,
                "frameCounter": t.uint32_t,
                "commandId": t.uint8_t,
                "payload": t.LVBytes,
                "shortAddr?": t.uint16_t,
                "distance?": t.uint8_t,
                "mic?": t.uint32_t
            },
            direction=False,
        )
        
    class ClientCommandDefs(BaseCommandDefs):
        notification_response: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "options": t.bitmap8,
                "gpdId": t.uint32_t,
                "frameCounter": t.uint32_t
            },
            direction=True,
        )

        pairing: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "options": t.bitmap24,
                "gpdId": t.uint32_t,
                "sinkIEEE?": t.EUI64,
                "sinkNwkAddr?": t.NWK,
                "sinkGroup?": t.Group,
                "deviceId?": t.uint8_t,
                "frameCounter?": t.uint32_t,
                "key?": t.KeyData,
                "alias?": t.uint16_t,
                "forwardingRadius?": t.uint8_t
            },
            direction=True,
        )

        proxy_commissioning_mode: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "options": t.bitmap8,
                "window?": t.uint16_t,
                "channel?": t.uint8_t
            },
            direction=True
        )

