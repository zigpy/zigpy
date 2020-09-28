import enum
import typing
import zlib

from zigpy.ota.image import ElementTagId, OTAImage

VALID_SILABS_CRC = 0x2144DF1C  # CRC32(anything | CRC32(anything)) == CRC32(0x00000000)


class ValidationResult(enum.Enum):
    VALID = 0
    INVALID = 1
    UNKNOWN = 2


def parse_silabs_ebl(data: bytes) -> typing.Iterable[typing.Tuple[bytes, bytes]]:
    """
    Parses a Silicon Labs EBL firmware image.
    """

    assert data
    assert len(data) % 64 == 0

    orig_data = data

    while True:
        assert len(data) >= 4
        tag = data[:2]
        length = int.from_bytes(data[2:4], "big")

        value = data[4 : 4 + length]
        assert len(value) == length

        data = data[4 + length :]
        yield tag, value

        if tag != b"\xFC\x04":
            continue

        # At this point the EBL should contain nothing but padding
        assert not data.strip(b"\xFF")

        unpadded_image = orig_data[: -len(data)] if data else orig_data
        assert zlib.crc32(unpadded_image) == VALID_SILABS_CRC

        break


def parse_silabs_gbl(data: bytes) -> typing.Iterable[typing.Tuple[bytes, bytes]]:
    """
    Parses a Silicon Labs GBL firmware image.
    """

    assert data

    orig_data = data

    while True:
        assert len(data) >= 8
        tag = data[:4]
        length = int.from_bytes(data[4:8], "little")

        value = data[8 : 8 + length]
        assert len(value) == length

        data = data[8 + length :]
        yield tag, value

        if tag != b"\xFC\x04\x04\xFC":
            continue

        assert not data

        # We could replace this entire function with the below line but validating the
        # image structure along with the checksum is better.
        assert zlib.crc32(orig_data) == VALID_SILABS_CRC
        break


def validate_firmware(data: bytes) -> ValidationResult:
    """
    Validates a firmware image.
    """

    parser = None

    if data.startswith(b"\xEB\x17\xA6\x03"):
        parser = parse_silabs_gbl
    elif data.startswith(b"\x00\x00\x00\x8C"):
        parser = parse_silabs_ebl
    else:
        return ValidationResult.UNKNOWN

    try:
        tuple(parser(data))
        return ValidationResult.VALID
    except Exception:
        return ValidationResult.INVALID


def validate_ota_image(image: OTAImage) -> ValidationResult:
    """
    Validates a Zigbee OTA image's embedded firmwares.
    """

    results = []

    for subelement in image.subelements:
        if subelement.tag_id == ElementTagId.UPGRADE_IMAGE:
            results.append(validate_firmware(subelement))

    if not results:
        return ValidationResult.UNKNOWN

    if ValidationResult.INVALID in results:
        # If any firmware is invalid, the image is invalid
        return ValidationResult.INVALID
    elif ValidationResult.UNKNOWN in results:
        # If no firmware can be parsed, the image cannot be validated but is not invalid
        return ValidationResult.UNKNOWN
    else:
        # Otherwise, if every subelement can be parsed, the image is valid
        return ValidationResult.VALID
