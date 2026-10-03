"""Green Power security primitives: AES-128-CCM* per ZGP spec A.1.5.4."""

from __future__ import annotations

import struct

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from zigpy.types import KeyData
from zigpy.zgp.types import DEFAULT_GP_LINK_KEY, CommunicationDirection, SecurityLevel

# Security level to MIC length mapping (Table 11 in ZGP spec).
# NoSecurity carries no MIC, and level 0b01 is Reserved with no defined
# transformation — per A.1.5.2.2 frames with an unsupported SecurityLevel
# (including 0b01) are silently dropped, so neither is a valid input here.
SECURITY_LEVEL_MIC_LENGTH: dict[SecurityLevel, int] = {
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


def _key_protection_nonce(
    source_id: int,
    direction: CommunicationDirection,
    frame_counter: int | None,
) -> bytes:
    """Nonce for TC-LK protection of the GPD key (A.3.7.1.2.3).

    For a GPDF sent by the GPD (the key in a Commissioning GPDF), the source
    address is {SrcID || SrcID} and the frame counter is the SrcID. For a
    GPDF sent to the GPD (a Commissioning Reply), the source address is
    {0x00000000 || SrcID} and the frame counter is the value transmitted in
    the reply's Frame Counter field (the triggering GPDF's security frame
    counter + 1).
    """
    if direction == CommunicationDirection.GPDtoGPP:
        if frame_counter is not None:
            raise ValueError("frame_counter only applies to the GPPtoGPD direction")
        return build_nonce(source_id, source_id)

    if frame_counter is None:
        raise ValueError("frame_counter is required for the GPPtoGPD direction")
    return struct.pack(
        "<IIIB", 0x00000000, source_id, frame_counter, GP_SECURITY_CONTROL_BYTE
    )


def encrypt_security_key(
    source_id: int,
    security_key: bytes,
    link_key: KeyData | bytes = DEFAULT_GP_LINK_KEY,
    *,
    direction: CommunicationDirection = CommunicationDirection.GPDtoGPP,
    frame_counter: int | None = None,
) -> tuple[bytes, bytes]:
    """Protect a GP security key with the TC link key (A.3.7.1.2.3).

    `GPDtoGPP` (the default) is the by-GPD form used for the encrypted key in
    a GPD Commissioning frame; `GPPtoGPD` is the form a sink uses in a GP
    Commissioning Reply and requires `frame_counter` (the value transmitted
    in the reply's Frame Counter field).

    Returns (encrypted_key, 4-byte MIC).
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")
    if len(link_key) != 16:
        raise ValueError(f"Link key must be 16 bytes, got {len(link_key)}")

    nonce = _key_protection_nonce(source_id, direction, frame_counter)
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
    *,
    direction: CommunicationDirection = CommunicationDirection.GPDtoGPP,
    frame_counter: int | None = None,
) -> bytes:
    """Unwrap a TC-LK protected GP security key (A.3.7.1.2.3).

    `GPDtoGPP` (the default) unwraps the key from a GPD Commissioning frame;
    `GPPtoGPD` unwraps the key from a GP Commissioning Reply and requires
    `frame_counter` (the value from the reply's Frame Counter field).
    """
    if len(encrypted_key) != 16:
        raise ValueError(f"Encrypted key must be 16 bytes, got {len(encrypted_key)}")
    if len(mic) != 4:
        raise ValueError(f"MIC must be 4 bytes, got {len(mic)}")
    if len(link_key) != 16:
        raise ValueError(f"Link key must be 16 bytes, got {len(link_key)}")

    nonce = _key_protection_nonce(source_id, direction, frame_counter)
    # CCM* associated data for ApplicationID=0b000 is the SrcID (A.3.7.1.2.3)
    header = struct.pack("<I", source_id)
    aesccm = AESCCM(bytes(link_key), tag_length=4)

    return aesccm.decrypt(nonce, encrypted_key + mic, associated_data=header)


def encrypt_payload(
    source_id: int,
    frame_counter: int,
    security_key: bytes,
    payload: bytes,
    *,
    header: bytes,
    security_level: SecurityLevel = SecurityLevel.Encrypted,
) -> tuple[bytes, bytes]:
    """Encrypt (Encrypted) or MIC-only authenticate (FullFrameCounterAndMIC) a payload.

    `header` is the over-the-air GPDF header (NWK FC || NWK ext FC || SrcID ||
    security frame counter); it is authenticated but never encrypted.

    Returns (output_payload, mic); output_payload is the plaintext for
    the auth-only level.
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")
    if not header:
        raise ValueError("GPDF header must not be empty")

    mic_length = SECURITY_LEVEL_MIC_LENGTH.get(security_level)
    if mic_length is None:
        raise ValueError(f"Cannot encrypt with security level {security_level!r}")

    nonce = build_nonce(source_id, frame_counter)
    aesccm = AESCCM(security_key, tag_length=mic_length)

    if security_level == SecurityLevel.FullFrameCounterAndMIC:
        # Authentication only: a = header || payload, plaintext message is
        # empty (A.1.5.4.2.3). The MIC authenticates the whole frame without
        # encrypting it; the payload remains in cleartext on the air.
        mic = aesccm.encrypt(nonce, b"", associated_data=header + payload)
        return payload, mic
    else:
        # Full encryption: a = header, m = payload (A.1.5.4.3.3)
        ciphertext_and_mic = aesccm.encrypt(nonce, payload, associated_data=header)
        encrypted = ciphertext_and_mic[:-mic_length]
        mic = ciphertext_and_mic[-mic_length:]
        return encrypted, mic


def decrypt_payload(
    source_id: int,
    frame_counter: int,
    security_key: bytes,
    payload: bytes,
    mic: bytes,
    *,
    header: bytes,
    security_level: SecurityLevel = SecurityLevel.Encrypted,
) -> bytes:
    """Decrypt (Encrypted) or verify MIC (FullFrameCounterAndMIC) a payload.

    `header` is the over-the-air GPDF header (NWK FC || NWK ext FC || SrcID ||
    security frame counter), as received.

    Returns the plaintext; raises InvalidTag if the MIC does not verify.
    """
    if len(security_key) != 16:
        raise ValueError(f"Security key must be 16 bytes, got {len(security_key)}")
    if not header:
        raise ValueError("GPDF header must not be empty")

    mic_length = SECURITY_LEVEL_MIC_LENGTH.get(security_level)
    if mic_length is None:
        raise ValueError(f"Cannot decrypt with security level {security_level!r}")
    if len(mic) != mic_length:
        raise ValueError(f"MIC must be {mic_length} bytes, got {len(mic)}")

    nonce = build_nonce(source_id, frame_counter)
    aesccm = AESCCM(security_key, tag_length=mic_length)

    if security_level == SecurityLevel.FullFrameCounterAndMIC:
        # Authentication only: verify the MIC with a = header || payload
        # (A.1.5.4.2.3). The "ciphertext" is empty, only the MIC tag is present.
        aesccm.decrypt(nonce, mic, associated_data=header + payload)
        return payload
    else:
        # Full decryption: a = header, ciphertext + MIC concatenated (A.1.5.4.3.3)
        return aesccm.decrypt(nonce, payload + mic, associated_data=header)
