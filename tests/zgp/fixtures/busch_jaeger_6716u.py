"""Captured Green Power frames from a Busch-Jaeger 6716 U "Friends of Hue" switch.

Captured 2026-04-22 on a Silabs ZBT-1 (EZSP v13): top-left button held 10 s
to commission, then normal button presses. Raw EZSP payloads pulled from the
bellows debug log.

Pure data module — import the constants directly.
"""

from __future__ import annotations

from typing import NamedTuple

# GPD source ID (on the wire as "86 f8 71 01", little-endian).
BJ6716U_SOURCE_ID: int = 0x0171F886

# GP Commissioning payload (command 0xE0), 46 bytes, per ZGP Tables 53-55:
#   DeviceID(1) Options(1) ExtOptions(1) SecurityKey(16) KeyMIC(4)
#   OutgoingCounter(4) AppInfo(1) NumGPDCommands(1) GPDCommands(17)
BJ6716U_COMMISSIONING_PAYLOAD: bytes = bytes.fromhex(
    "02"  # DeviceID = 0x02 (Generic 2-state switch)
    "c5"  # Options = 0xC5
    "f2"  # ExtOptions = 0xF2
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
    """One operational GP frame captured from the device (0x68 = Press 2 of 2)."""

    frame_counter: int
    command_id: int
    mic: bytes


BJ6716U_OPERATIONAL_FRAMES: list[OperationalFrame] = [
    OperationalFrame(0x00001DED, 0x68, bytes.fromhex("be7cc462")),
    OperationalFrame(0x00001DEE, 0x68, bytes.fromhex("13aa405f")),
    OperationalFrame(0x00001DEF, 0x68, bytes.fromhex("178ad52a")),
    OperationalFrame(0x00001DF0, 0x68, bytes.fromhex("106efe9b")),
]


class ExpectedCommissioning(NamedTuple):
    """Expected values after parsing BJ6716U_COMMISSIONING_PAYLOAD."""

    device_id: int
    options_raw: int
    ext_options_raw: int
    security_key: bytes
    key_mic: int
    outgoing_counter: int
    app_info_raw: int
    gpd_commands: list[int]


BJ6716U_EXPECTED: ExpectedCommissioning = ExpectedCommissioning(
    device_id=0x02,
    options_raw=0xC5,
    ext_options_raw=0xF2,
    security_key=bytes.fromhex("1ce9ae2f9e4f85f15de37c1ccbd94387"),
    key_mic=0x1A911300,  # LE unpack of "00 13 91 1a"
    outgoing_counter=0x00001DEC,  # LE unpack of "ec 1d 00 00"
    app_info_raw=0x04,
    gpd_commands=[
        0x10,
        0x11,
        0x12,
        0x13,
        0x14,
        0x15,
        0x16,
        0x17,  # RecallScene 0-7
        0x22,  # Toggle
        0x60,
        0x62,
        0x63,
        0x64,
        0x65,
        0x66,
        0x67,
        0x68,  # press/release
    ],
)
