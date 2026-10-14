"""EnOcean PTM 216Z pushbutton transmitter module.

Captured with EZSP v19 from `gpepIncomingMessageHandler`, from the bellows test suite:
the GPD was commissioned directly on channel 11 (long press B0), then pressed. A
GenericSwitch, it reports which contacts are closed in an 8-bit vector.
"""

from __future__ import annotations

from tests.zgp.fixtures import CapturedFrame, CapturedGPD
import zigpy.types as t
from zigpy.zgp.commands import (
    GPContactStatusPayload,
    GPGenericSwitchConfiguration,
    GPNoPayload,
)
from zigpy.zgp.types import DeviceID, GPDCommandID, SecurityLevel, SwitchType


def frame(
    frame_counter: int, command_id: GPDCommandID, payload: bytes, mic: int
) -> CapturedFrame:
    # The command ID and payload are in the clear at SecurityLevel 0b10
    return CapturedFrame(
        frame_counter=frame_counter,
        command_id=command_id,
        payload=payload,
        mic=mic,
        expected_command_id=command_id,
        expected_command=(
            GPContactStatusPayload(contact_status=t.bitmap8(payload[0]))
            if payload
            else GPNoPayload()
        ),
    )


PTM216Z = CapturedGPD(
    src_id=0x0155F443,
    device_id=DeviceID.GenericSwitch,
    security_level=SecurityLevel.FullFrameCounterAndMIC,
    commissioning_payload=bytes.fromhex(
        "07"  # DeviceID = 0x07 (Generic Switch)
        "85"  # Options: MAC sequence number capability, app info, ext
        "f2"  # ExtOptions: level 0b10, individual key, key present and encrypted, counter
        "6761efc264c893701987babda7238ce9"  # SecurityKey, protected with the TC-LK
        "102e934a"  # SecurityKey MIC
        "76000000"  # OutgoingCounter = 118
        "10"  # AppInfo: switch information present
        "020504"  # Switch information: length 2, 5 contacts, contact status 0x04
    ),
    commissioning_sequence_number=0x76,
    key=bytes.fromhex("17c80184eb5433ecef08a54c8778ddbb"),
    outgoing_counter=0x76,
    attributes={
        "switch_configuration": GPGenericSwitchConfiguration(
            num_contacts=5, switch_type=SwitchType.Unknown, _reserved=0
        ),
    },
    frames=[
        # The AI+B0 radio channel confirmation
        frame(0x77, GPDCommandID.ShortPress2of2, b"", 0x858EDB75),
        # Press/release pairs, one per rocker contact
        frame(0x78, GPDCommandID.Press8BitVector, b"\x01", 0x3E1D662A),
        frame(0x79, GPDCommandID.Release8BitVector, b"\x00", 0x27BF6138),
        frame(0x7C, GPDCommandID.Press8BitVector, b"\x02", 0x0BFBB477),
        frame(0x7E, GPDCommandID.Press8BitVector, b"\x06", 0x4D7C8799),
    ],
    # From an earlier session, before this commissioning
    stale_frames=[frame(0x1B, GPDCommandID.Press8BitVector, b"\x01", 0xD093D06F)],
)
