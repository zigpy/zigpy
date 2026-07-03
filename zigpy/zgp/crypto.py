"""Green Power security primitives: AES-128-CCM* per ZGP spec A.1.5.4."""

from __future__ import annotations

import struct

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from zigpy.types import KeyData
from zigpy.zgp.types import DEFAULT_GP_LINK_KEY, SecurityLevel

# Security level to MIC length mapping (Table 12 in ZGP spec)
# Note: Reserved uses a 2-byte counter (LSBytes only) for
# frame counter but still uses a 4-byte MIC for authentication per the spec.
# The AESCCM library requires tag_length >= 4.
SECURITY_LEVEL_MIC_LENGTH: dict[SecurityLevel, int] = {
    SecurityLevel.NoSecurity: 0,
    SecurityLevel.Reserved: 4,
    SecurityLevel.FullFrameCounterAndMIC: 4,
    SecurityLevel.Encrypted: 4,
}

# Security control byte for nonce construction
# Bits 0-2: Security level (always 0b101 = 5 for GP CCM*)
# Ref: ZGP spec A.1.5.4.1
GP_SECURITY_CONTROL_BYTE: int = 0x05


def build_nonce(source_id: int, frame_counter: int) -> bytes:
    """Construct the 13-byte CCM* nonce per ZGP spec A.1.5.4.1."""
    # srcID | srcID | frame_counter | security_control (all little-endian)
    return struct.pack(
        "<IIIB",
        source_id,
        source_id,
        frame_counter,
        GP_SECURITY_CONTROL_BYTE,
    )


def encrypt_security_key(
    source_id: int,
    security_key: bytes,
    link_key: KeyData | bytes = DEFAULT_GP_LINK_KEY,
) -> tuple[bytes, bytes]:
    """Encrypt a GP security key for a GP Commissioning Reply (A.3.7.1.2.3).

    Returns (encrypted_key, 4-byte MIC).
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")
    if len(link_key) != 16:
        raise ValueError(f"Link key must be 16 bytes, got {len(link_key)}")

    # For key encryption, frame counter = sourceID
    nonce = build_nonce(source_id, source_id)
    # CCM* associated data for ApplicationID=0b000 is the SrcID (A.3.7.1.2.3)
    header = struct.pack("<I", source_id)

    aesccm = AESCCM(bytes(link_key), tag_length=4)
    ciphertext_and_mic = aesccm.encrypt(nonce, security_key, associated_data=header)

    # Split into encrypted key (16 bytes) and MIC (4 bytes)
    encrypted_key = ciphertext_and_mic[:16]
    mic = ciphertext_and_mic[16:]

    return encrypted_key, mic


def decrypt_security_key(
    source_id: int,
    encrypted_key: bytes,
    mic: bytes,
    link_key: KeyData | bytes = DEFAULT_GP_LINK_KEY,
) -> bytes:
    """Decrypt a GP security key from a Commissioning payload (A.3.7.1.2.3)."""
    if len(encrypted_key) != 16:
        raise ValueError(f"Encrypted key must be 16 bytes, got {len(encrypted_key)}")
    if len(mic) != 4:
        raise ValueError(f"MIC must be 4 bytes, got {len(mic)}")
    if len(link_key) != 16:
        raise ValueError(f"Link key must be 16 bytes, got {len(link_key)}")

    nonce = build_nonce(source_id, source_id)
    # CCM* associated data for ApplicationID=0b000 is the SrcID (A.3.7.1.2.3)
    header = struct.pack("<I", source_id)
    aesccm = AESCCM(bytes(link_key), tag_length=4)

    return aesccm.decrypt(nonce, encrypted_key + mic, associated_data=header)


def _is_auth_only(security_level: SecurityLevel) -> bool:
    """True for levels that authenticate but do not encrypt (Table 12)."""
    return security_level in (
        SecurityLevel.FullFrameCounterAndMIC,
        SecurityLevel.Reserved,
    )


def encrypt_payload(
    source_id: int,
    frame_counter: int,
    security_key: bytes,
    payload: bytes,
    security_level: SecurityLevel = SecurityLevel.Encrypted,
) -> tuple[bytes, bytes]:
    """Encrypt (Encrypted) or MIC-only authenticate (auth-only levels) a payload.

    Returns (output_payload, mic); output_payload is the plaintext for
    auth-only levels.
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
    """Decrypt (Encrypted) or verify MIC (auth-only levels) a payload.

    Returns the plaintext; raises InvalidTag if the MIC does not verify.
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
