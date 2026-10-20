"""Tests for Green Power cryptographic primitives."""

from __future__ import annotations

import struct

from cryptography.exceptions import InvalidTag
import pytest

from zigpy.zgp.crypto import (
    build_gpdf_header,
    build_nonce,
    decrypt_payload,
    decrypt_security_key,
    encrypt_payload,
    encrypt_security_key,
)
from zigpy.zgp.types import CommunicationDirection, SecurityLevel


def gpdf_header(source_id: int, frame_counter: int, nwk_ext_fc: int) -> bytes:
    """NWK FC (0x8C) || NWK ext FC || SrcID || security frame counter (A.1.5.4)."""
    return bytes([0x8C, nwk_ext_fc]) + struct.pack("<II", source_id, frame_counter)


# ZGP spec A.1.5.4 common settings: SrcID 0x87654321, security frame counter 2,
# GP security key C0..CF, payload 0x20 (Off command)
SPEC_SRC_ID = 0x87654321
SPEC_FRAME_COUNTER = 0x00000002
SPEC_KEY = bytes(range(0xC0, 0xD0))
SPEC_PAYLOAD = b"\x20"
# NWK ext FC is 0x10 for SecurityLevel 0b10 and 0x18 for 0b11 (A.1.5.4.2.2/.3.2)
SPEC_HEADER_0B10 = gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x10)
SPEC_HEADER_0B11 = gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x18)

# ZGP spec A.1.5.8: SrcID 0x12345678, the key C0..CF protected with the TC-LK
SPEC_KEY_SRC_ID = 0x12345678


def test_nonce():
    """SrcID || SrcID || frame counter || security control 0x05 (A.1.5.4.1)."""
    nonce = build_nonce(source_id=0x12345678, frame_counter=0x42)
    assert nonce == bytes.fromhex("78563412785634124200000005")


@pytest.mark.parametrize(
    ("direction", "frame_counter", "encrypted_key", "mic"),
    [
        # A.1.5.8.1: OOB key in a Commissioning GPDF (by-GPD)
        (
            CommunicationDirection.GPDtoGPP,
            None,
            "7d177bd29ea0fda6b017036587dc2600",
            "61f163a9",
        ),
        # A.1.5.8.3: shared key in a Commissioning Reply (to-GPD). The triggering
        # GPDF's security frame counter is 3, so the reply's Frame Counter is 4.
        (
            CommunicationDirection.GPPtoGPD,
            4,
            "e90006631d0dfdc638068e5e6967d325",
            "27559f75",
        ),
    ],
)
def test_key_spec_vector(direction, frame_counter, encrypted_key, mic):
    assert encrypt_security_key(
        SPEC_KEY_SRC_ID,
        SPEC_KEY,
        direction=direction,
        frame_counter=frame_counter,
    ) == (bytes.fromhex(encrypted_key), bytes.fromhex(mic))

    assert (
        decrypt_security_key(
            SPEC_KEY_SRC_ID,
            bytes.fromhex(encrypted_key),
            bytes.fromhex(mic),
            direction=direction,
            frame_counter=frame_counter,
        )
        == SPEC_KEY
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_id": 0x87654321},
        {"mic": bytes.fromhex("61f163aa")},
        {"link_key": b"\x55" * 16},
    ],
)
def test_key_decryption_fails(kwargs):
    with pytest.raises(InvalidTag):
        decrypt_security_key(
            **{
                "source_id": SPEC_KEY_SRC_ID,
                "encrypted_key": bytes.fromhex("7d177bd29ea0fda6b017036587dc2600"),
                "mic": bytes.fromhex("61f163a9"),
                **kwargs,
            }
        )


@pytest.mark.parametrize(
    ("security_level", "header", "output", "mic"),
    [
        # A.1.5.4.2: SecurityLevel 0b10 authenticates without encrypting
        (SecurityLevel.FullFrameCounterAndMIC, SPEC_HEADER_0B10, "20", "cf787e72"),
        # A.1.5.4.3: SecurityLevel 0b11
        (SecurityLevel.Encrypted, SPEC_HEADER_0B11, "83", "ca4324dd"),
    ],
)
def test_payload_spec_vector(security_level, header, output, mic):
    assert encrypt_payload(
        SPEC_SRC_ID,
        SPEC_FRAME_COUNTER,
        SPEC_KEY,
        SPEC_PAYLOAD,
        header=header,
        security_level=security_level,
    ) == (bytes.fromhex(output), bytes.fromhex(mic))

    assert (
        decrypt_payload(
            SPEC_SRC_ID,
            SPEC_FRAME_COUNTER,
            SPEC_KEY,
            bytes.fromhex(output),
            bytes.fromhex(mic),
            header=header,
            security_level=security_level,
        )
        == SPEC_PAYLOAD
    )


@pytest.mark.parametrize(
    "security_level",
    [SecurityLevel.FullFrameCounterAndMIC, SecurityLevel.Encrypted],
)
@pytest.mark.parametrize(
    "kwargs",
    [
        {"payload": b"\x21"},
        {"mic": b"\x00" * 4},
        {"frame_counter": SPEC_FRAME_COUNTER + 1},
        {"security_key": bytes(16)},
        # The header is authenticated: here, the SecurityKey sub-field
        {"header": gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x38)},
    ],
)
def test_payload_decryption_fails(security_level, kwargs):
    header = build_gpdf_header(
        SPEC_SRC_ID,
        SPEC_FRAME_COUNTER,
        security_level=security_level,
        individual_key=False,
        auto_commissioning=False,
        rx_after_tx=False,
    )
    output, mic = encrypt_payload(
        SPEC_SRC_ID,
        SPEC_FRAME_COUNTER,
        SPEC_KEY,
        SPEC_PAYLOAD,
        header=header,
        security_level=security_level,
    )

    with pytest.raises(InvalidTag):
        decrypt_payload(
            **{
                "source_id": SPEC_SRC_ID,
                "frame_counter": SPEC_FRAME_COUNTER,
                "security_key": SPEC_KEY,
                "payload": output,
                "mic": mic,
                "header": header,
                "security_level": security_level,
                **kwargs,
            }
        )


@pytest.mark.parametrize(
    (
        "security_level",
        "individual_key",
        "auto_commissioning",
        "rx_after_tx",
        "expected",
    ),
    [
        # The headers of the A.1.5.4 test vectors
        (SecurityLevel.FullFrameCounterAndMIC, False, False, False, SPEC_HEADER_0B10),
        (SecurityLevel.Encrypted, False, False, False, SPEC_HEADER_0B11),
        # SecurityKey, Auto-Commissioning and RxAfterTx sub-fields (A.1.4.1.2/.3)
        (
            SecurityLevel.Encrypted,
            True,
            False,
            False,
            gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x38),
        ),
        (
            SecurityLevel.Encrypted,
            False,
            False,
            True,
            gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x58),
        ),
        (
            SecurityLevel.Encrypted,
            False,
            True,
            False,
            b"\xcc" + SPEC_HEADER_0B11[1:],
        ),
    ],
)
def test_build_gpdf_header(
    security_level, individual_key, auto_commissioning, rx_after_tx, expected
):
    header = build_gpdf_header(
        SPEC_SRC_ID,
        SPEC_FRAME_COUNTER,
        security_level=security_level,
        individual_key=individual_key,
        auto_commissioning=auto_commissioning,
        rx_after_tx=rx_after_tx,
    )

    assert header == expected
