"""Green Power security primitives.

Implements AES-128-CCM encryption/decryption for Zigbee Green Power frames
as specified in the ZGP specification (A.1.5.4).

The GP security uses CCM* (CCM-star) mode with:
- 128-bit AES key
- 13-byte nonce constructed from sourceID and frame counter
- Variable MIC length depending on SecurityLevel
"""

from __future__ import annotations

import struct

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from zigpy.zgp.types import DEFAULT_GP_LINK_KEY, SecurityLevel

# Security level to MIC length mapping (Table 12 in ZGP spec)
# Note: ShortFrameCounterAndMIC uses a 2-byte counter (LSBytes only) for
# frame counter but still uses a 4-byte MIC for authentication per the spec.
# The AESCCM library requires tag_length >= 4.
SECURITY_LEVEL_MIC_LENGTH: dict[SecurityLevel, int] = {
    SecurityLevel.NoSecurity: 0,
    SecurityLevel.ShortFrameCounterAndMIC: 4,
    SecurityLevel.FullFrameCounterAndMIC: 4,
    SecurityLevel.Encrypted: 4,
}

# Security control byte for nonce construction
# Bits 0-2: Security level (always 0b101 = 5 for GP CCM*)
# Ref: ZGP spec A.1.5.4.1
GP_SECURITY_CONTROL_BYTE: int = 0x05


def build_nonce(source_id: int, frame_counter: int) -> bytes:
    """Construct the 13-byte CCM nonce per ZGP spec A.1.5.4.1.

    Nonce structure (13 bytes):
    - Bytes 0-3: Source ID (little-endian)
    - Bytes 4-7: Source ID (repeated, little-endian)
    - Bytes 8-11: Frame counter (little-endian)
    - Byte 12: Security control byte (0x05)

    Args:
        source_id: 32-bit GP device source identifier.
        frame_counter: 32-bit frame counter value.

    Returns:
        13-byte nonce for AES-CCM.
    """
    return struct.pack(
        "<IIIb",
        source_id,
        source_id,
        frame_counter,
        GP_SECURITY_CONTROL_BYTE,
    )


def encrypt_security_key(
    source_id: int,
    security_key: bytes,
    link_key: bytes = DEFAULT_GP_LINK_KEY,
) -> tuple[bytes, bytes]:
    """Encrypt a GP security key for transmission during commissioning.

    Used when the sink sends a security key to an RX-capable GPD via
    a GP Commissioning Reply. The key is encrypted using AES-128-CCM
    with the GP link key and a nonce derived from the sourceID.

    For key encryption, the frame counter in the nonce is set to the
    sourceID value itself (per ZGP spec A.1.5.4.3).

    Args:
        source_id: 32-bit GPD source identifier.
        security_key: 16-byte security key to encrypt.
        link_key: 16-byte link key for encryption (default: ZigBeeAlliance09).

    Returns:
        Tuple of (encrypted_key, mic) where:
        - encrypted_key is the 16-byte encrypted security key
        - mic is the 4-byte Message Integrity Code
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")
    if len(link_key) != 16:
        raise ValueError(f"Link key must be 16 bytes, got {len(link_key)}")

    # For key encryption, frame counter = sourceID
    nonce = build_nonce(source_id, source_id)

    # AES-CCM with 4-byte tag (MIC)
    aesccm = AESCCM(link_key, tag_length=4)
    ciphertext_and_mic = aesccm.encrypt(nonce, security_key, associated_data=None)

    # Split into encrypted key (16 bytes) and MIC (4 bytes)
    encrypted_key = ciphertext_and_mic[:16]
    mic = ciphertext_and_mic[16:]

    return encrypted_key, mic


def decrypt_security_key(
    source_id: int,
    encrypted_key: bytes,
    mic: bytes,
    link_key: bytes = DEFAULT_GP_LINK_KEY,
) -> bytes:
    """Decrypt a GP security key received during commissioning.

    Args:
        source_id: 32-bit GPD source identifier.
        encrypted_key: 16-byte encrypted security key.
        mic: 4-byte Message Integrity Code.
        link_key: 16-byte link key for decryption (default: ZigBeeAlliance09).

    Returns:
        16-byte decrypted security key.

    Raises:
        cryptography.exceptions.InvalidTag: If MIC verification fails.
    """
    if len(encrypted_key) != 16:
        raise ValueError(
            f"Encrypted key must be 16 bytes, got {len(encrypted_key)}"
        )
    if len(mic) != 4:
        raise ValueError(f"MIC must be 4 bytes, got {len(mic)}")
    if len(link_key) != 16:
        raise ValueError(f"Link key must be 16 bytes, got {len(link_key)}")

    nonce = build_nonce(source_id, source_id)
    aesccm = AESCCM(link_key, tag_length=4)

    return aesccm.decrypt(nonce, encrypted_key + mic, associated_data=None)


def _is_auth_only(security_level: SecurityLevel) -> bool:
    """Return True if the security level uses authentication only (no encryption).

    Per ZGP spec Table 12:
    - SecurityLevel 0b10 (FullFrameCounterAndMIC): 4-byte FC + 4-byte MIC, no encryption
    - SecurityLevel 0b01 (Reserved/Short): similar auth-only semantics
    - SecurityLevel 0b11 (Encrypted): full encryption + authentication
    """
    return security_level in (
        SecurityLevel.FullFrameCounterAndMIC,
        SecurityLevel.ShortFrameCounterAndMIC,
    )


def encrypt_payload(
    source_id: int,
    frame_counter: int,
    security_key: bytes,
    payload: bytes,
    security_level: SecurityLevel = SecurityLevel.Encrypted,
) -> tuple[bytes, bytes]:
    """Encrypt or authenticate a GP frame payload.

    For SecurityLevel.Encrypted: payload is encrypted and authenticated.
    For FullFrameCounterAndMIC/ShortFrameCounterAndMIC: payload is
    authenticated only (MIC computed over plaintext, payload not encrypted).

    Args:
        source_id: 32-bit GPD source identifier.
        frame_counter: 32-bit frame counter.
        security_key: 16-byte security key.
        payload: Plaintext payload.
        security_level: Security level determining behavior.

    Returns:
        Tuple of (output_payload, mic) where output_payload is the
        encrypted payload (Encrypted level) or the original plaintext
        (auth-only levels).
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")

    mic_length = SECURITY_LEVEL_MIC_LENGTH[security_level]
    if mic_length == 0:
        raise ValueError("Cannot encrypt with SecurityLevel.NoSecurity")

    nonce = build_nonce(source_id, frame_counter)
    aesccm = AESCCM(security_key, tag_length=mic_length)

    if _is_auth_only(security_level):
        # Authentication only: payload is passed as associated data (AAD),
        # plaintext message is empty. The MIC authenticates the payload
        # without encrypting it. Per ZGP spec, FullFrameCounterAndMIC
        # provides integrity protection but the payload remains in cleartext.
        mic = aesccm.encrypt(nonce, b"", associated_data=payload)
        return payload, mic
    else:
        # Full encryption: payload is encrypted and authenticated
        ciphertext_and_mic = aesccm.encrypt(nonce, payload, associated_data=None)
        encrypted = ciphertext_and_mic[:-mic_length]
        mic = ciphertext_and_mic[-mic_length:]
        return encrypted, mic


def decrypt_payload(
    source_id: int,
    frame_counter: int,
    security_key: bytes,
    payload: bytes,
    mic: bytes,
    security_level: SecurityLevel = SecurityLevel.Encrypted,
) -> bytes:
    """Decrypt or verify a GP frame payload.

    For SecurityLevel.Encrypted: payload is decrypted and MIC verified.
    For FullFrameCounterAndMIC/ShortFrameCounterAndMIC: MIC is verified
    against the plaintext payload (no decryption needed).

    Args:
        source_id: 32-bit GPD source identifier.
        frame_counter: 32-bit frame counter.
        security_key: 16-byte security key.
        payload: Encrypted payload (Encrypted level) or plaintext (auth-only).
        mic: Message Integrity Code.
        security_level: Security level determining behavior.

    Returns:
        Decrypted/verified payload bytes.

    Raises:
        cryptography.exceptions.InvalidTag: If MIC verification fails.
        ValueError: If security level is NoSecurity.
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")

    mic_length = SECURITY_LEVEL_MIC_LENGTH[security_level]
    if mic_length == 0:
        raise ValueError("Cannot decrypt with SecurityLevel.NoSecurity")
    if len(mic) != mic_length:
        raise ValueError(f"MIC must be {mic_length} bytes, got {len(mic)}")

    nonce = build_nonce(source_id, frame_counter)
    aesccm = AESCCM(security_key, tag_length=mic_length)

    if _is_auth_only(security_level):
        # Authentication only: verify MIC with payload as AAD.
        # The "ciphertext" is empty, only the MIC tag is present.
        aesccm.decrypt(nonce, mic, associated_data=payload)
        return payload
    else:
        # Full decryption: ciphertext + MIC concatenated
        return aesccm.decrypt(nonce, payload + mic, associated_data=None)
