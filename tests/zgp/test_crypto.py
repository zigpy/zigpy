"""Tests for Green Power cryptographic primitives."""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from zigpy.zgp.crypto import (
    build_nonce,
    decrypt_payload,
    decrypt_security_key,
    encrypt_payload,
    encrypt_security_key,
)
from zigpy.zgp.types import DEFAULT_GP_LINK_KEY, SecurityLevel


class TestBuildNonce:
    """Tests for nonce construction."""

    def test_nonce_length(self) -> None:
        """Nonce must always be 13 bytes."""
        nonce = build_nonce(source_id=0x12345678, frame_counter=0x00000001)
        assert len(nonce) == 13

    def test_nonce_structure(self) -> None:
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

    def test_nonce_zero_values(self) -> None:
        """Nonce with zero sourceID and frameCounter."""
        nonce = build_nonce(source_id=0, frame_counter=0)
        assert nonce == b"\x00" * 8 + b"\x00" * 4 + b"\x05"

    def test_nonce_max_values(self) -> None:
        """Nonce with maximum 32-bit values."""
        nonce = build_nonce(source_id=0xFFFFFFFF, frame_counter=0xFFFFFFFF)
        assert nonce[0:4] == b"\xFF\xFF\xFF\xFF"
        assert nonce[4:8] == b"\xFF\xFF\xFF\xFF"
        assert nonce[8:12] == b"\xFF\xFF\xFF\xFF"
        assert nonce[12] == 0x05


class TestEncryptDecryptSecurityKey:
    """Tests for security key encryption/decryption round-trips."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Encrypting then decrypting should return the original key."""
        source_id = 0x12345678
        original_key = bytes(range(16))

        encrypted_key, mic = encrypt_security_key(source_id, original_key)
        decrypted_key = decrypt_security_key(source_id, encrypted_key, mic)

        assert decrypted_key == original_key

    def test_encrypt_produces_different_output(self) -> None:
        """Encrypted key should differ from plaintext."""
        source_id = 0xAABBCCDD
        original_key = b"\x01" * 16

        encrypted_key, mic = encrypt_security_key(source_id, original_key)

        # The encrypted key should be different from the original
        assert encrypted_key != original_key
        # MIC should be 4 bytes
        assert len(mic) == 4

    def test_encrypted_key_length(self) -> None:
        """Encrypted key should be 16 bytes, MIC should be 4 bytes."""
        source_id = 0x11223344
        key = bytes(range(16))

        encrypted_key, mic = encrypt_security_key(source_id, key)

        assert len(encrypted_key) == 16
        assert len(mic) == 4

    def test_different_source_ids_produce_different_ciphertext(self) -> None:
        """Different sourceIDs should produce different encrypted keys."""
        key = b"\xAA" * 16

        enc1, mic1 = encrypt_security_key(0x11111111, key)
        enc2, mic2 = encrypt_security_key(0x22222222, key)

        assert enc1 != enc2 or mic1 != mic2

    def test_decrypt_with_wrong_mic_fails(self) -> None:
        """Decryption with tampered MIC should raise InvalidTag."""
        source_id = 0x12345678
        key = bytes(range(16))

        encrypted_key, mic = encrypt_security_key(source_id, key)

        # Tamper with MIC
        bad_mic = bytes((b + 1) & 0xFF for b in mic)
        with pytest.raises(InvalidTag):
            decrypt_security_key(source_id, encrypted_key, bad_mic)

    def test_decrypt_with_wrong_source_id_fails(self) -> None:
        """Decryption with wrong sourceID should raise InvalidTag."""
        key = bytes(range(16))

        encrypted_key, mic = encrypt_security_key(0x12345678, key)

        with pytest.raises(InvalidTag):
            decrypt_security_key(0x87654321, encrypted_key, mic)

    def test_custom_link_key(self) -> None:
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

    def test_custom_link_key_incompatible_with_default(self) -> None:
        """Key encrypted with custom link key can't be decrypted with default."""
        source_id = 0xDEADBEEF
        security_key = b"\x42" * 16
        custom_link_key = b"\x55" * 16

        encrypted, mic = encrypt_security_key(
            source_id, security_key, link_key=custom_link_key
        )

        with pytest.raises(InvalidTag):
            decrypt_security_key(source_id, encrypted, mic)  # default link key

    def test_invalid_key_length(self) -> None:
        """Keys must be exactly 16 bytes."""
        with pytest.raises(ValueError, match="16 bytes"):
            encrypt_security_key(0x12345678, b"\x00" * 15)

        with pytest.raises(ValueError, match="16 bytes"):
            encrypt_security_key(0x12345678, b"\x00" * 17)

    def test_invalid_link_key_length(self) -> None:
        """Link key must be exactly 16 bytes."""
        with pytest.raises(ValueError, match="16 bytes"):
            encrypt_security_key(
                0x12345678, b"\x00" * 16, link_key=b"\x00" * 15
            )

    def test_invalid_mic_length(self) -> None:
        """MIC must be exactly 4 bytes for decrypt."""
        with pytest.raises(ValueError, match="4 bytes"):
            decrypt_security_key(0x12345678, b"\x00" * 16, b"\x00" * 3)

    def test_invalid_encrypted_key_length(self) -> None:
        """Encrypted key must be 16 bytes for decrypt."""
        with pytest.raises(ValueError, match="16 bytes"):
            decrypt_security_key(0x12345678, b"\x00" * 15, b"\x00" * 4)


class TestEncryptDecryptPayload:
    """Tests for GP frame payload encryption/decryption."""

    def test_encrypted_roundtrip(self) -> None:
        """Full encryption round-trip (SecurityLevel.Encrypted)."""
        source_id = 0xAABBCCDD
        frame_counter = 0x00000042
        key = bytes(range(16))
        payload = b"Hello GP!"

        encrypted, mic = encrypt_payload(
            source_id, frame_counter, key, payload, SecurityLevel.Encrypted
        )
        decrypted = decrypt_payload(
            source_id, frame_counter, key, encrypted, mic, SecurityLevel.Encrypted
        )

        assert decrypted == payload

    def test_full_frame_counter_and_mic_roundtrip(self) -> None:
        """Authentication-only round-trip (FullFrameCounterAndMIC)."""
        source_id = 0x11223344
        frame_counter = 0x00000001
        key = bytes(range(16))
        payload = b"\x20"  # Toggle command

        encrypted, mic = encrypt_payload(
            source_id,
            frame_counter,
            key,
            payload,
            SecurityLevel.FullFrameCounterAndMIC,
        )
        # For auth-only, encrypted == original payload (no encryption, only MIC)
        assert len(mic) == 4

        decrypted = decrypt_payload(
            source_id,
            frame_counter,
            key,
            encrypted,
            mic,
            SecurityLevel.FullFrameCounterAndMIC,
        )
        assert decrypted == payload

    def test_short_frame_counter_and_mic(self) -> None:
        """ShortFrameCounterAndMIC uses 4-byte MIC (same as Full)."""
        source_id = 0x55667788
        frame_counter = 0x00000010
        key = bytes(range(16))
        payload = b"\x22"  # Toggle

        encrypted, mic = encrypt_payload(
            source_id,
            frame_counter,
            key,
            payload,
            SecurityLevel.ShortFrameCounterAndMIC,
        )
        assert len(mic) == 4

        decrypted = decrypt_payload(
            source_id,
            frame_counter,
            key,
            encrypted,
            mic,
            SecurityLevel.ShortFrameCounterAndMIC,
        )
        assert decrypted == payload

    def test_no_security_encrypt_raises(self) -> None:
        """Cannot encrypt with NoSecurity level."""
        with pytest.raises(ValueError, match="NoSecurity"):
            encrypt_payload(
                0x12345678, 0, bytes(range(16)), b"test", SecurityLevel.NoSecurity
            )

    def test_no_security_decrypt_raises(self) -> None:
        """Cannot decrypt with NoSecurity level."""
        with pytest.raises(ValueError, match="NoSecurity"):
            decrypt_payload(
                0x12345678, 0, bytes(range(16)), b"test", b"", SecurityLevel.NoSecurity
            )

    def test_tampered_payload_fails(self) -> None:
        """Tampered ciphertext should cause decryption failure."""
        source_id = 0xDEADBEEF
        frame_counter = 1
        key = bytes(range(16))
        payload = b"secret data here"

        encrypted, mic = encrypt_payload(
            source_id, frame_counter, key, payload, SecurityLevel.Encrypted
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
                SecurityLevel.Encrypted,
            )

    def test_wrong_frame_counter_fails(self) -> None:
        """Decryption with wrong frame counter should fail."""
        source_id = 0xDEADBEEF
        key = bytes(range(16))
        payload = b"test"

        encrypted, mic = encrypt_payload(
            source_id, 1, key, payload, SecurityLevel.Encrypted
        )

        with pytest.raises(InvalidTag):
            decrypt_payload(
                source_id, 2, key, encrypted, mic, SecurityLevel.Encrypted
            )

    def test_invalid_key_length(self) -> None:
        """Security key must be 16 bytes."""
        with pytest.raises(ValueError, match="16 bytes"):
            encrypt_payload(0, 0, b"\x00" * 15, b"test", SecurityLevel.Encrypted)

    def test_wrong_mic_length(self) -> None:
        """MIC length must match security level."""
        with pytest.raises(ValueError, match="4 bytes"):
            decrypt_payload(
                0, 0, bytes(range(16)), b"test", b"\x00" * 2, SecurityLevel.Encrypted
            )

    def test_empty_payload_encrypted(self) -> None:
        """Empty payload encryption should work."""
        source_id = 0x12345678
        key = bytes(range(16))

        encrypted, mic = encrypt_payload(
            source_id, 0, key, b"", SecurityLevel.Encrypted
        )
        decrypted = decrypt_payload(
            source_id, 0, key, encrypted, mic, SecurityLevel.Encrypted
        )
        assert decrypted == b""


class TestDefaultLinkKey:
    """Tests for the default GP link key constant."""

    def test_default_link_key_is_zigbee_alliance(self) -> None:
        """Default GP link key should be 'ZigBeeAlliance09' in ASCII."""
        assert DEFAULT_GP_LINK_KEY == b"ZigBeeAlliance09"
        assert len(DEFAULT_GP_LINK_KEY) == 16
