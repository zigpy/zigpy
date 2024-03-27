from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# Huge thanks to https://lucidar.me/en/zigbee/zigbee-frame-encryption-with-aes-128-ccm/
def __pad(x: bytes) -> bytes:
    n = (16 - len(x) % 16) % 16
    return x + bytes([0x00] * n)


def __build_authdata(authHeader: bytes, plaintextData: bytes) -> bytes:
    addAuthData = len(authHeader).to_bytes(2, byteorder="big") + authHeader
    addAuthData = __pad(addAuthData)
    return addAuthData + plaintextData


def calculate_mic(
    key: bytes, nonce: bytes, authData: bytes, plaintextData: bytes
) -> bytes:
    B0 = __pad(bytes([0x49]) + nonce + len(plaintextData).to_bytes(2, byteorder="big"))
    X0 = bytes([0x00] * 16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(X0))
    encryptor = cipher.encryptor()
    X1 = encryptor.update(B0 + authData) + encryptor.finalize()
    mic = X1[-16:-12]

    A0 = bytes([0x01]) + nonce + bytes([0x00, 0x00])
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    S0 = encryptor.update(A0) + encryptor.finalize()
    enc_mic = bytes(a ^ b for (a, b) in zip(S0[0:4], mic))
    return enc_mic


def zgp_encrypt(
    key: bytes, nonce: bytes, authHeader: bytes, plaintextData: bytes
) -> tuple[bytes, bytes]:
    assert len(nonce) == 13
    plaintextData = __pad(plaintextData)
    authData = __build_authdata(authHeader, plaintextData)
    A1 = bytes([0x01]) + nonce + bytes([0x00, 0x01])
    cipher = Cipher(algorithms.AES(key), modes.CTR(A1))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintextData) + encryptor.finalize()
    enc_mic = calculate_mic(key, nonce, authData, plaintextData)
    return (ciphertext, enc_mic)


def zgp_decrypt(
    key: bytes, nonce: bytes, authHeader: bytes, ciphertext: bytes, enc_mic: bytes
) -> tuple[bytes, bool, bytes]:
    assert len(nonce) == 13
    ciphertext = __pad(ciphertext)
    A1 = bytes([0x01]) + nonce + bytes([0x00, 0x01])
    cipher = Cipher(algorithms.AES(key), modes.CTR(A1))
    decryptor = cipher.decryptor()
    plaintextData = decryptor.update(ciphertext) + decryptor.finalize()
    authData = __build_authdata(authHeader, plaintextData)
    calculated_mic = calculate_mic(key, nonce, authData, plaintextData)
    return (plaintextData, enc_mic == calculated_mic, calculated_mic)
