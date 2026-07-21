"""Tests for Green Power cryptographic primitives."""

from __future__ import annotations

import struct

from cryptography.exceptions import InvalidTag
import pytest

from zigpy.zgp.crypto import (
    build_nonce,
    decrypt_payload,
    decrypt_security_key,
    encrypt_payload,
    encrypt_security_key,
)
from zigpy.zgp.types import DEFAULT_GP_LINK_KEY, SecurityLevel


def gpdf_header(source_id: int, frame_counter: int, nwk_ext_fc: int) -> bytes:
    """Build the GPDF header authenticated as CCM* associated data.

    NWK FC (0x8C) || NWK ext FC || SrcID || security frame counter,
    per ZGP spec A.1.5.4.2.3 / A.1.5.4.3.3.
    """
    return bytes([0x8C, nwk_ext_fc]) + struct.pack("<II", source_id, frame_counter)


def test_nonce_length():
    """Nonce must always be 13 bytes."""
    nonce = build_nonce(source_id=0x12345678, frame_counter=0x00000001)
    assert len(nonce) == 13


def test_nonce_structure():
    """Verify nonce byte layout: sourceID + sourceID + frameCounter + 0x05."""
    nonce = build_nonce(source_id=0x01020304, frame_counter=0x05060708)

    # Source ID (little-endian): 04 03 02 01
    assert nonce[0:4] == b"\x04\x03\x02\x01"
    # Source ID repeated: 04 03 02 01
    assert nonce[4:8] == b"\x04\x03\x02\x01"
    # Frame counter (little-endian): 08 07 06 05
    assert nonce[8:12] == b"\x08\x07\x06\x05"
    # Security control byte
    assert nonce[12] == 0x05


def test_nonce_zero_values():
    """Nonce with zero sourceID and frameCounter."""
    nonce = build_nonce(source_id=0, frame_counter=0)
    assert nonce == b"\x00" * 8 + b"\x00" * 4 + b"\x05"


def test_nonce_max_values():
    """Nonce with maximum 32-bit values."""
    nonce = build_nonce(source_id=0xFFFFFFFF, frame_counter=0xFFFFFFFF)
    assert nonce[0:4] == b"\xff\xff\xff\xff"
    assert nonce[4:8] == b"\xff\xff\xff\xff"
    assert nonce[8:12] == b"\xff\xff\xff\xff"
    assert nonce[12] == 0x05


def test_encrypt_decrypt_roundtrip():
    """Encrypting then decrypting should return the original key."""
    source_id = 0x12345678
    original_key = bytes(range(16))

    encrypted_key, mic = encrypt_security_key(source_id, original_key)
    decrypted_key = decrypt_security_key(source_id, encrypted_key, mic)

    assert decrypted_key == original_key


def test_encrypt_produces_different_output():
    """Encrypted key should differ from plaintext."""
    source_id = 0xAABBCCDD
    original_key = b"\x01" * 16

    encrypted_key, mic = encrypt_security_key(source_id, original_key)

    # The encrypted key should be different from the original
    assert encrypted_key != original_key
    # MIC should be 4 bytes
    assert len(mic) == 4


def test_encrypted_key_length():
    """Encrypted key should be 16 bytes, MIC should be 4 bytes."""
    source_id = 0x11223344
    key = bytes(range(16))

    encrypted_key, mic = encrypt_security_key(source_id, key)

    assert len(encrypted_key) == 16
    assert len(mic) == 4


def test_different_source_ids_produce_different_ciphertext():
    """Different sourceIDs should produce different encrypted keys."""
    key = b"\xaa" * 16

    enc1, mic1 = encrypt_security_key(0x11111111, key)
    enc2, mic2 = encrypt_security_key(0x22222222, key)

    assert enc1 != enc2 or mic1 != mic2


def test_decrypt_with_wrong_mic_fails():
    """Decryption with tampered MIC should raise InvalidTag."""
    source_id = 0x12345678
    key = bytes(range(16))

    encrypted_key, mic = encrypt_security_key(source_id, key)

    # Tamper with MIC
    bad_mic = bytes((b + 1) & 0xFF for b in mic)
    with pytest.raises(InvalidTag):
        decrypt_security_key(source_id, encrypted_key, bad_mic)


def test_decrypt_with_wrong_source_id_fails():
    """Decryption with wrong sourceID should raise InvalidTag."""
    key = bytes(range(16))

    encrypted_key, mic = encrypt_security_key(0x12345678, key)

    with pytest.raises(InvalidTag):
        decrypt_security_key(0x87654321, encrypted_key, mic)


def test_custom_link_key():
    """Encryption with custom link key should work for round-trip."""
    source_id = 0xDEADBEEF
    security_key = b"\x42" * 16
    custom_link_key = b"\x55" * 16

    encrypted, mic = encrypt_security_key(
        source_id, security_key, link_key=custom_link_key
    )
    decrypted = decrypt_security_key(
        source_id, encrypted, mic, link_key=custom_link_key
    )

    assert decrypted == security_key


def test_custom_link_key_incompatible_with_default():
    """Key encrypted with custom link key can't be decrypted with default."""
    source_id = 0xDEADBEEF
    security_key = b"\x42" * 16
    custom_link_key = b"\x55" * 16

    encrypted, mic = encrypt_security_key(
        source_id, security_key, link_key=custom_link_key
    )

    with pytest.raises(InvalidTag):
        decrypt_security_key(source_id, encrypted, mic)  # default link key


def test_invalid_key_length():
    """Keys must be exactly 16 bytes."""
    with pytest.raises(ValueError, match="16 bytes"):
        encrypt_security_key(0x12345678, b"\x00" * 15)

    with pytest.raises(ValueError, match="16 bytes"):
        encrypt_security_key(0x12345678, b"\x00" * 17)


def test_invalid_link_key_length():
    """Link key must be exactly 16 bytes."""
    with pytest.raises(ValueError, match="16 bytes"):
        encrypt_security_key(0x12345678, b"\x00" * 16, link_key=b"\x00" * 15)


def test_invalid_mic_length():
    """MIC must be exactly 4 bytes for decrypt."""
    with pytest.raises(ValueError, match="4 bytes"):
        decrypt_security_key(0x12345678, b"\x00" * 16, b"\x00" * 3)


def test_invalid_encrypted_key_length():
    """Encrypted key must be 16 bytes for decrypt."""
    with pytest.raises(ValueError, match="16 bytes"):
        decrypt_security_key(0x12345678, b"\x00" * 15, b"\x00" * 4)


def test_decrypt_security_key_bad_link_key_length():
    """Decrypt must reject link_key that is not 16 bytes."""
    with pytest.raises(ValueError, match="16 bytes"):
        decrypt_security_key(
            0x12345678, b"\x00" * 16, b"\x00" * 4, link_key=b"\x00" * 10
        )


def test_encrypted_roundtrip():
    """Full encryption round-trip (SecurityLevel.Encrypted)."""
    source_id = 0xAABBCCDD
    frame_counter = 0x00000042
    key = bytes(range(16))
    payload = b"Hello GP!"

    header = gpdf_header(source_id, frame_counter, 0x18)
    encrypted, mic = encrypt_payload(
        source_id,
        frame_counter,
        key,
        payload,
        header=header,
        security_level=SecurityLevel.Encrypted,
    )
    decrypted = decrypt_payload(
        source_id,
        frame_counter,
        key,
        encrypted,
        mic,
        header=header,
        security_level=SecurityLevel.Encrypted,
    )

    assert decrypted == payload


def test_full_frame_counter_and_mic_roundtrip():
    """Authentication-only round-trip (FullFrameCounterAndMIC).

    Per ZGP spec, this level authenticates without encrypting:
    the payload remains in cleartext and only a MIC is appended.
    """
    source_id = 0x11223344
    frame_counter = 0x00000001
    key = bytes(range(16))
    payload = b"\x20"  # Toggle command

    header = gpdf_header(source_id, frame_counter, 0x10)
    output, mic = encrypt_payload(
        source_id,
        frame_counter,
        key,
        payload,
        header=header,
        security_level=SecurityLevel.FullFrameCounterAndMIC,
    )
    assert len(mic) == 4
    # Auth-only: output payload must be identical to input (NOT encrypted)
    assert output == payload

    verified = decrypt_payload(
        source_id,
        frame_counter,
        key,
        output,
        mic,
        header=header,
        security_level=SecurityLevel.FullFrameCounterAndMIC,
    )
    assert verified == payload


def test_full_frame_counter_and_mic_tampered():
    """Tampered payload should fail MIC verification in auth-only mode."""
    source_id = 0x11223344
    frame_counter = 0x00000001
    key = bytes(range(16))
    payload = b"\x20\x21\x22"

    header = gpdf_header(source_id, frame_counter, 0x10)
    output, mic = encrypt_payload(
        source_id,
        frame_counter,
        key,
        payload,
        header=header,
        security_level=SecurityLevel.FullFrameCounterAndMIC,
    )

    # Tamper with the payload
    tampered = b"\xff\x21\x22"
    with pytest.raises(InvalidTag):
        decrypt_payload(
            source_id,
            frame_counter,
            key,
            tampered,
            mic,
            header=header,
            security_level=SecurityLevel.FullFrameCounterAndMIC,
        )


def test_short_frame_counter_and_mic():
    """Reserved: auth-only with 4-byte MIC."""
    source_id = 0x55667788
    frame_counter = 0x00000010
    key = bytes(range(16))
    payload = b"\x22"  # Toggle

    header = gpdf_header(source_id, frame_counter, 0x08)
    output, mic = encrypt_payload(
        source_id,
        frame_counter,
        key,
        payload,
        header=header,
        security_level=SecurityLevel.Reserved,
    )
    assert len(mic) == 4
    # Auth-only: payload must NOT be encrypted
    assert output == payload

    verified = decrypt_payload(
        source_id,
        frame_counter,
        key,
        output,
        mic,
        header=header,
        security_level=SecurityLevel.Reserved,
    )
    assert verified == payload


def test_no_security_encrypt_raises():
    """Cannot encrypt with NoSecurity level."""
    with pytest.raises(ValueError, match="NoSecurity"):
        encrypt_payload(
            0x12345678,
            0,
            bytes(range(16)),
            b"test",
            header=gpdf_header(0x12345678, 0, 0x00),
            security_level=SecurityLevel.NoSecurity,
        )


def test_no_security_decrypt_raises():
    """Cannot decrypt with NoSecurity level."""
    with pytest.raises(ValueError, match="NoSecurity"):
        decrypt_payload(
            0x12345678,
            0,
            bytes(range(16)),
            b"test",
            b"",
            header=gpdf_header(0x12345678, 0, 0x00),
            security_level=SecurityLevel.NoSecurity,
        )


def test_tampered_payload_fails():
    """Tampered ciphertext should cause decryption failure."""
    source_id = 0xDEADBEEF
    frame_counter = 1
    key = bytes(range(16))
    payload = b"secret data here"

    header = gpdf_header(source_id, frame_counter, 0x18)
    encrypted, mic = encrypt_payload(
        source_id,
        frame_counter,
        key,
        payload,
        header=header,
        security_level=SecurityLevel.Encrypted,
    )

    # Tamper with encrypted payload
    tampered = bytearray(encrypted)
    tampered[0] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt_payload(
            source_id,
            frame_counter,
            key,
            bytes(tampered),
            mic,
            header=header,
            security_level=SecurityLevel.Encrypted,
        )


def test_wrong_frame_counter_fails():
    """Decryption with wrong frame counter should fail."""
    source_id = 0xDEADBEEF
    key = bytes(range(16))
    payload = b"test"

    encrypted, mic = encrypt_payload(
        source_id,
        1,
        key,
        payload,
        header=gpdf_header(source_id, 1, 0x18),
        security_level=SecurityLevel.Encrypted,
    )

    with pytest.raises(InvalidTag):
        decrypt_payload(
            source_id,
            2,
            key,
            encrypted,
            mic,
            header=gpdf_header(source_id, 2, 0x18),
            security_level=SecurityLevel.Encrypted,
        )


def test_payload_invalid_key_length():
    """Security key must be 16 bytes."""
    with pytest.raises(ValueError, match="16 bytes"):
        encrypt_payload(
            0,
            0,
            b"\x00" * 15,
            b"test",
            header=gpdf_header(0, 0, 0x18),
            security_level=SecurityLevel.Encrypted,
        )


def test_decrypt_payload_bad_key_length():
    """Decrypt must reject security_key that is not 16 bytes."""
    with pytest.raises(ValueError, match="16 bytes"):
        decrypt_payload(
            0,
            0,
            b"\x00" * 15,
            b"test",
            b"\x00" * 4,
            header=gpdf_header(0, 0, 0x18),
            security_level=SecurityLevel.Encrypted,
        )


def test_wrong_mic_length():
    """MIC length must match security level."""
    with pytest.raises(ValueError, match="4 bytes"):
        decrypt_payload(
            0,
            0,
            bytes(range(16)),
            b"test",
            b"\x00" * 2,
            header=gpdf_header(0, 0, 0x18),
            security_level=SecurityLevel.Encrypted,
        )


def test_empty_payload_encrypted():
    """Empty payload encryption should work."""
    source_id = 0x12345678
    key = bytes(range(16))

    header = gpdf_header(source_id, 0, 0x18)
    encrypted, mic = encrypt_payload(
        source_id, 0, key, b"", header=header, security_level=SecurityLevel.Encrypted
    )
    decrypted = decrypt_payload(
        source_id,
        0,
        key,
        encrypted,
        mic,
        header=header,
        security_level=SecurityLevel.Encrypted,
    )
    assert decrypted == b""


def test_default_link_key_is_zigbee_alliance():
    """Default GP link key should be 'ZigBeeAlliance09' in ASCII."""
    assert bytes(DEFAULT_GP_LINK_KEY) == b"ZigBeeAlliance09"
    assert len(DEFAULT_GP_LINK_KEY) == 16


def test_key_encryption_known_vector():
    """Regression fixture for key encryption.

    sourceID=0x12345678, link_key=ZigBeeAlliance09, plaintext=00..0F.
    AAD is the 4-byte SrcID (A.3.7.1.2.3), so it changes the MIC but not
    the ciphertext.
    """
    encrypted, mic = encrypt_security_key(
        source_id=0x12345678, security_key=bytes(range(16))
    )
    assert encrypted == bytes.fromhex("bdd7bb125e603d6670d7c3a5471ce6c0")
    assert mic == bytes.fromhex("d24ca0a9")


def test_key_decryption_known_vector():
    """Verify key decryption matches the known plaintext."""
    decrypted = decrypt_security_key(
        source_id=0x12345678,
        encrypted_key=bytes.fromhex("bdd7bb125e603d6670d7c3a5471ce6c0"),
        mic=bytes.fromhex("d24ca0a9"),
    )
    assert decrypted == bytes(range(16))


# ZGP spec A.1.5.4 common settings: SrcID 0x87654321, security frame counter 2,
# GP security key C0..CF, payload 0x20 (Off command)
SPEC_SRC_ID = 0x87654321
SPEC_FRAME_COUNTER = 0x00000002
SPEC_KEY = bytes(range(0xC0, 0xD0))
SPEC_PAYLOAD = b"\x20"
# NWK ext FC is 0x10 for SecurityLevel 0b10 and 0x18 for 0b11 (A.1.5.4.2.2/.3.2)
SPEC_HEADER_0B10 = gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x10)
SPEC_HEADER_0B11 = gpdf_header(SPEC_SRC_ID, SPEC_FRAME_COUNTER, 0x18)


def test_payload_encryption_spec_vector():
    """ZGP spec A.1.5.4.3: SecurityLevel 0b11 test vector."""
    encrypted, mic = encrypt_payload(
        source_id=SPEC_SRC_ID,
        frame_counter=SPEC_FRAME_COUNTER,
        security_key=SPEC_KEY,
        payload=SPEC_PAYLOAD,
        header=SPEC_HEADER_0B11,
        security_level=SecurityLevel.Encrypted,
    )
    assert encrypted == bytes.fromhex("83")
    assert mic == bytes.fromhex("ca4324dd")


def test_payload_decryption_spec_vector():
    """ZGP spec A.1.5.4.3: decrypting the published packet yields the payload."""
    decrypted = decrypt_payload(
        source_id=SPEC_SRC_ID,
        frame_counter=SPEC_FRAME_COUNTER,
        security_key=SPEC_KEY,
        payload=bytes.fromhex("83"),
        mic=bytes.fromhex("ca4324dd"),
        header=SPEC_HEADER_0B11,
        security_level=SecurityLevel.Encrypted,
    )
    assert decrypted == SPEC_PAYLOAD


def test_auth_only_spec_vector():
    """ZGP spec A.1.5.4.2: SecurityLevel 0b10 test vector.

    Payload must NOT be encrypted (auth-only).
    """
    output, mic = encrypt_payload(
        source_id=SPEC_SRC_ID,
        frame_counter=SPEC_FRAME_COUNTER,
        security_key=SPEC_KEY,
        payload=SPEC_PAYLOAD,
        header=SPEC_HEADER_0B10,
        security_level=SecurityLevel.FullFrameCounterAndMIC,
    )
    assert output == SPEC_PAYLOAD  # unchanged, not encrypted
    assert mic == bytes.fromhex("cf787e72")


def test_auth_only_verification_spec_vector():
    """ZGP spec A.1.5.4.2: MIC check passes for the published packet."""
    verified = decrypt_payload(
        source_id=SPEC_SRC_ID,
        frame_counter=SPEC_FRAME_COUNTER,
        security_key=SPEC_KEY,
        payload=SPEC_PAYLOAD,
        mic=bytes.fromhex("cf787e72"),
        header=SPEC_HEADER_0B10,
        security_level=SecurityLevel.FullFrameCounterAndMIC,
    )
    assert verified == SPEC_PAYLOAD


def test_empty_header_raises():
    """The GPDF header is mandatory associated data."""
    with pytest.raises(ValueError, match="header"):
        encrypt_payload(
            SPEC_SRC_ID,
            SPEC_FRAME_COUNTER,
            SPEC_KEY,
            SPEC_PAYLOAD,
            header=b"",
        )
    with pytest.raises(ValueError, match="header"):
        decrypt_payload(
            SPEC_SRC_ID,
            SPEC_FRAME_COUNTER,
            SPEC_KEY,
            SPEC_PAYLOAD,
            b"\x00" * 4,
            header=b"",
        )


def test_nonce_known_vector():
    """Verify nonce construction against manually computed value.

    Per ZGP spec A.1.5.4.1, security control byte = 0x05.
    """
    nonce = build_nonce(source_id=0x12345678, frame_counter=0x42)
    assert nonce == bytes.fromhex("78563412785634124200000005")
