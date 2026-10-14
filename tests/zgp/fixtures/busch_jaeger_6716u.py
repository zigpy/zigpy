"""Captured Green Power frames from a Busch-Jaeger 6716 U "Friends of Hue" switch.

Captured 2026-04-22 on a Silabs ZBT-1 (EZSP v13): top-left button held 10 s
to commission, then normal button presses. Raw EZSP payloads pulled from the
bellows debug log.
"""

from __future__ import annotations

from typing import NamedTuple

# GPD source ID (on the wire as "86 f8 71 01", little-endian).
BJ6716U_SOURCE_ID: int = 0x0171F886

# GP Commissioning payload (command 0xE0), 46 bytes, per ZGP Tables 53-55:
#   DeviceID(1) Options(1) ExtOptions(1) SecurityKey(16) KeyMIC(4)
#   OutgoingCounter(4) AppInfo(1) NumGPDCommands(1) GPDCommands(17)
BJ6716U_COMMISSIONING_PAYLOAD: bytes = bytes.fromhex(
    "02"  # DeviceID = 0x02 (On/Off Switch)
    "c5"  # Options: MAC sequence number capability, app info, fixed location, ext
    "f2"  # ExtOptions: level 0b10, individual key, key present and encrypted, counter
    "1ce9ae2f9e4f85f15de37c1ccbd94387"  # SecurityKey (encrypted, 16 bytes)
    "0013911a"  # GPDKeyMIC (LE uint32)
    "ec1d0000"  # OutgoingCounter = 0x00001dec (LE)
    "04"  # AppInfo = 0x04 (GPDCommandsPresent)
    "11"  # NumGPDCommands = 17
    "1011121314151617"  # 0x10..0x17 (RecallScene 0-7)
    "22"  # 0x22 (Toggle)
    "6062636465666768"  # 0x60..0x68 (press/release variants)
)

# GPD key after unwrapping SecurityKey with ZigBeeAlliance09 and the SrcID AAD.
BJ6716U_DECRYPTED_KEY: bytes = bytes.fromhex("62ca321d983016720e7aaca37fc46f73")


class OperationalFrame(NamedTuple):
    """One operational GP frame captured from the device (0x68 = Short Press 2 of 2)."""

    frame_counter: int
    command_id: int
    mic: bytes


# The MIC verifies with BJ6716U_DECRYPTED_KEY at SecurityLevel 0b10
BJ6716U_OPERATIONAL_FRAME: OperationalFrame = OperationalFrame(
    0x00001DED, 0x68, bytes.fromhex("be7cc462")
)
