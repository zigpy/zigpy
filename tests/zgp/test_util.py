"""Tests for Green Power helper functions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import zigpy.types as t
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
)
from zigpy.zgp.util import derive_alias, parse_gpdf, synthetic_ieee


@pytest.mark.parametrize(
    ("gpd_id", "alias"),
    [
        # The two LSBs are directly usable
        (0x12345678, 0x5678),
        # The two LSBs are the coordinator address and so is the XOR fallback
        (0x00000000, 0x0007),
        # The two LSBs are reserved but the XOR with the next two bytes is usable
        (0x1234FFF8, 0xEDCC),
        # Both the two LSBs and the XOR are reserved: subtract 0x0008
        (0xFFF8FFF8, 0xFFF0),
        (0x0000FFFF, 0xFFF7),
        # IEEE-addressed GPDs derive the alias from the EUI64
        (t.EUI64.convert("00:00:00:00:12:34:56:78"), 0x5678),
        (t.EUI64.convert("11:22:33:44:55:66:77:88"), 0x7788),
    ],
)
def test_derive_alias(gpd_id, alias):
    assert derive_alias(gpd_id) == t.NWK(alias)


def test_synthetic_ieee():
    ieee = synthetic_ieee(0x12345678)

    assert ieee == t.EUI64.convert("00:00:00:00:12:34:56:78")
    assert derive_alias(ieee) == derive_alias(0x12345678)


# The NWK frames of the transmitted packets of the spec's test vectors (A.1.5.4)
SPEC_LEVEL_2 = bytes.fromhex("8C 10 21 43 65 87 02 00 00 00 20 CF 78 7E 72")
SPEC_LEVEL_3 = bytes.fromhex("8C 18 21 43 65 87 02 00 00 00 83 CA 43 24 DD")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            SPEC_LEVEL_2,
            {
                "src_id": SrcID(0x87654321),
                "command_id": GPDCommandID.Off,
                "payload": t.SerializableBytes(b""),
                "frame_counter": 2,
                "security_level": SecurityLevel.FullFrameCounterAndMIC,
                "security_key_type": None,
                "security_status": SecurityStatus.Unprocessed,
                "mic": 0x727E78CF,
                "individual_key": False,
            },
        ),
        # The command ID is ciphertext
        (
            SPEC_LEVEL_3,
            {
                "command_id": 0x83,
                "security_level": SecurityLevel.Encrypted,
                "security_status": SecurityStatus.Unprocessed,
                "mic": 0xDD2443CA,
            },
        ),
        # Extended NWK Frame Control 0x60: unprotected, individual key bit ignored,
        # RxAfterTx. A Commissioning GPDF listening for its reply
        (
            bytes.fromhex("8C 60 44 33 22 11 E0 02 00"),
            {
                "src_id": SrcID(0x11223344),
                "command_id": GPDCommandID.CommissioningRequest,
                "payload": t.SerializableBytes(b"\x02\x00"),
                "frame_counter": None,
                "security_level": SecurityLevel.NoSecurity,
                "security_key_type": SecurityKeyType.NoKey,
                "security_status": SecurityStatus.NoSecurity,
                "mic": None,
                "rx_after_tx": True,
                "individual_key": None,
            },
        ),
        # No Extended NWK Frame Control: the defaults apply (A.1.4.1.3)
        (
            bytes.fromhex("0C 44 33 22 11 22"),
            {
                "src_id": SrcID(0x11223344),
                "command_id": GPDCommandID.Toggle,
                "security_level": SecurityLevel.NoSecurity,
                "rx_after_tx": False,
                "auto_commissioning": False,
            },
        ),
        # Auto-Commissioning Data GPDF
        (
            bytes.fromhex("4C 44 33 22 11 22"),
            {"auto_commissioning": True},
        ),
        # A Maintenance GPDF without the Extended NWK Frame Control has no SrcID: a
        # Channel Request (A.3.9.1 step 6.b)
        (
            bytes.fromhex("0D E3 85"),
            {
                "src_id": SrcID(0x00000000),
                "command_id": GPDCommandID.ChannelRequest,
                "payload": t.SerializableBytes(b"\x85"),
            },
        ),
        # With it, the SrcID is present
        (
            bytes.fromhex("8D 00 44 33 22 11 E3 85"),
            {"src_id": SrcID(0x11223344), "command_id": GPDCommandID.ChannelRequest},
        ),
        # IEEE addressing (0b010) carries the endpoint, the IEEE is in the MAC header
        (
            bytes.fromhex("8C 02 03 22"),
            {
                "application_id": ApplicationID.IEEE,
                "src_id": None,
                "ieee": None,
                "endpoint": 3,
                "command_id": GPDCommandID.Toggle,
            },
        ),
    ],
)
def test_parse_gpdf(data: bytes, expected: dict) -> None:
    packet = parse_gpdf(data)

    for name, value in expected.items():
        assert getattr(packet, name) == value, name


def test_parse_gpdf_kwargs() -> None:
    """The radio supplies what only the MAC header or the radio itself knows."""
    timestamp = datetime(2026, 10, 19, tzinfo=UTC)
    ieee = t.EUI64.convert("00:11:22:33:44:55:66:77")

    packet = parse_gpdf(
        bytes.fromhex("8C 02 03 22"),
        timestamp=timestamp,
        ieee=ieee,
        frame_counter=t.uint32_t(0x12),
        lqi=t.uint8_t(200),
        rssi=t.int8s(-40),
    )

    assert packet.timestamp == timestamp
    assert packet.ieee == ieee
    assert packet.frame_counter == 0x12
    assert packet.lqi == 200
    assert packet.rssi == -40


@pytest.mark.parametrize(
    ("data", "match"),
    [
        # Zigbee protocol version 2
        (bytes.fromhex("08 44 33 22 11 22"), "protocol version"),
        # Direction 0b1: a Channel Configuration sent by another sink
        (bytes.fromhex("8D 80 F3 1F"), "sent to a GPD"),
        # LPED (0b001)
        (bytes.fromhex("8C 01 22"), "ApplicationID"),
        # Reserved security level 0b01
        (bytes.fromhex("8C 08 44 33 22 11 22"), "Reserved security level"),
        # Protected, but no room for a command ID and MIC after the frame counter
        (bytes.fromhex("8C 10 21 43 65 87 02 00 00 00 CF 78 7E 72"), "too short"),
        (b"", "Data is too short"),
    ],
)
def test_parse_gpdf_invalid(data: bytes, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_gpdf(data)
