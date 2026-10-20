"""EnOcean PTM 215Z in a Friends of Hue wall switch.

Captured 2026-10-14 from bellows' `gpepIncomingMessageHandler`: the GPD was
commissioned directly by the coordinator, then every button and button pair was
pressed. Rebadged by many vendors, e.g. as the Busch-Jaeger 6716 U.
"""

from __future__ import annotations

from tests.zgp.fixtures import CapturedFrame, CapturedGPD
from zigpy.zgp.commands import GPNoPayload
from zigpy.zgp.types import DeviceID, GPDCommandID, SecurityLevel


def frame(frame_counter: int, command_id: GPDCommandID, mic: int) -> CapturedFrame:
    # The command ID is in the clear at SecurityLevel 0b10
    return CapturedFrame(
        frame_counter=frame_counter,
        command_id=command_id,
        payload=b"",
        mic=mic,
        expected_command_id=command_id,
        expected_command=GPNoPayload(),
    )


PTM215Z = CapturedGPD(
    src_id=0x01771CE6,
    device_id=DeviceID.OnOffSwitch,
    security_level=SecurityLevel.FullFrameCounterAndMIC,
    commissioning_payload=bytes.fromhex(
        "02"  # DeviceID = 0x02 (On/Off Switch)
        "c5"  # Options: MAC sequence number capability, app info, fixed location, ext
        "f2"  # ExtOptions: level 0b10, individual key, key present and encrypted, counter
        "10405e0513cb556a00ee94019ee66218"  # SecurityKey, protected with the TC-LK
        "118edec9"  # SecurityKey MIC
        "0c030000"  # OutgoingCounter = 780
        "04"  # AppInfo: GPD commands present
        "11"  # 17 GPD commands
        "1011121314151617"  # Recall Scene 0-7
        "22"  # Toggle
        "6062636465666768"  # Press 1 of 1, Press/Release 1 of 2 and 2 of 2, short presses
    ),
    commissioning_sequence_number=12,
    key=bytes.fromhex("221fef95f70e49c5bad870736e1d69ed"),
    outgoing_counter=780,
    attributes={
        "fixed_location": True,
        "commands": [
            *range(0x10, 0x18),  # Recall Scene 0-7
            GPDCommandID.Toggle,
            GPDCommandID.Press1of1,
            *range(0x62, 0x69),  # Press 1 of 2 to Short Press 2 of 2
        ],
    },
    frames=[
        frame(781, GPDCommandID.ShortPress2of2, 0xFCC247FF),
        frame(782, GPDCommandID.RecallScene0, 0x1CB6886A),
        frame(783, GPDCommandID.RecallScene4, 0xD15FC27E),
        frame(784, GPDCommandID.RecallScene3, 0x05E4027E),
        frame(785, GPDCommandID.RecallScene7, 0x6C9BFA8D),
        frame(786, GPDCommandID.RecallScene1, 0x6F2470A6),
        frame(787, GPDCommandID.RecallScene5, 0xB5E04CB4),
        frame(788, GPDCommandID.RecallScene2, 0x298C7F5F),
        frame(789, GPDCommandID.RecallScene6, 0xA1937F8B),
        frame(790, GPDCommandID.Press2of2, 0x754D5C53),
        frame(791, GPDCommandID.Release2of2, 0xE338AD65),
        frame(792, GPDCommandID.Press1of2, 0x9ED09D89),
        frame(793, GPDCommandID.Release1of2, 0xC99EC112),
    ],
    # Pressed before the commissioning, which announced OutgoingCounter 780
    stale_frames=[frame(779, GPDCommandID.RecallScene2, 0xE19DA529)],
)
