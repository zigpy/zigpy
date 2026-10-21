"""Moes 3-gang wireless switch, Tuya product `qerh7pox`.

Captured 2026-10-14 from bellows' `gpepIncomingMessageHandler`: the GPD was
commissioned directly by the coordinator, then its buttons were pressed. Its GPDFs
are encrypted (SecurityLevel 0b11), so the command IDs on the air are ciphertext.
"""

from __future__ import annotations

from tests.zgp.fixtures import CapturedFrame, CapturedGPD
from zigpy.zgp.commands import GPNoPayload
from zigpy.zgp.types import DeviceID, GPDCommandID, SecurityLevel


def frame(
    frame_counter: int, command_id: int, mic: int, expected_command_id: GPDCommandID
) -> CapturedFrame:
    return CapturedFrame(
        frame_counter=frame_counter,
        command_id=command_id,
        payload=b"",
        mic=mic,
        expected_command_id=expected_command_id,
        expected_command=GPNoPayload(),
    )


MOES_3_GANG = CapturedGPD(
    src_id=0xE337991B,
    device_id=DeviceID.OnOffSwitch,
    security_level=SecurityLevel.Encrypted,
    commissioning_payload=bytes.fromhex(
        "02"  # DeviceID = 0x02 (On/Off Switch)
        "89"  # Options: MAC sequence number capability, ext
        "f3"  # ExtOptions: level 0b11, individual key, key present and encrypted, counter
        "d1bf9bdab4da226a58c0abe7ddbef7a1"  # SecurityKey, protected with the TC-LK
        "db1b3981"  # SecurityKey MIC
        "ed190000"  # OutgoingCounter = 6637
        "7165726837706f7840475030303031"  # Trailing "qerh7pox@GP0001": the Tuya product
        "cb"  # Varies between commissioning frames
    ),
    commissioning_sequence_number=237,
    key=bytes(range(0xC0, 0xD0)),
    outgoing_counter=6637,
    attributes={"commands": []},
    frames=[
        # The same ciphertext command ID decrypts differently under another counter
        frame(6646, 0x90, 0xC24AB775, GPDCommandID.RecallScene1),
        frame(6664, 0xD3, 0xCF4D6430, GPDCommandID.Off),
        frame(6673, 0x48, 0x8147B8F6, GPDCommandID.RecallScene1),
        frame(6682, 0x08, 0xA054C7E8, GPDCommandID.On),
        frame(6691, 0xAA, 0x26A81051, GPDCommandID.Off),
        frame(6700, 0xC8, 0x283D0D59, GPDCommandID.On),
        frame(6709, 0xA4, 0x02525F7E, GPDCommandID.On),
        frame(6718, 0x45, 0x1D04C885, GPDCommandID.RecallScene1),
        frame(6727, 0x10, 0xE872A951, GPDCommandID.RecallScene1),
        frame(6736, 0x76, 0x0ACCB005, GPDCommandID.Off),
        frame(6745, 0x60, 0x4C9E002B, GPDCommandID.Off),
        frame(6754, 0xF6, 0x96D05E6F, GPDCommandID.Off),
        frame(6763, 0x08, 0x2F20B5D1, GPDCommandID.Off),
    ],
    stale_frames=[],
)
