import enum
import logging
import typing
import zlib

from zigpy.ota.image import BaseOTAImage, ElementTagId, OTAImage

VALID_SILABS_CRC = 0x2144DF1C  # CRC32(anything | CRC32(anything)) == CRC32(0x00000000)
LOGGER = logging.getLogger(__name__)


class ValidationResult(enum.Enum):
    INVALID = 0
    VALID = 1
    UNKNOWN = 2


class ValidationError(Exception):
    pass


def parse_silabs_ebl(data: bytes) -> typing.Iterable[typing.Tuple[bytes, bytes]]:
    """
    Parses a Silicon Labs EBL firmware image.
    """

    if len(data) % 64 != 0:
        raise ValidationError(
            f"Image size ({len(data)}) must be a multiple of 64 bytes"
        )

    orig_data = data

    while True:
        if len(data) < 4:
            raise ValidationError(
                "Image is truncated: not long enough to contain a valid tag"
            )

        tag = data[:2]
        length = int.from_bytes(data[2:4], "big")

        value = data[4 : 4 + length]

        if len(value) < length:
            raise ValidationError("Image is truncated: tag value is cut off")

        data = data[4 + length :]
        yield tag, value

        # EBL end tag
        if tag != b"\xFC\x04":
            continue

        # At this point the EBL should contain nothing but padding
        if data.strip(b"\xFF"):
            raise ValidationError("Image padding contains invalid bytes")

        unpadded_image = orig_data[: -len(data)] if data else orig_data
        computed_crc = zlib.crc32(unpadded_image)

        if computed_crc != VALID_SILABS_CRC:
            raise ValidationError(
                f"Image CRC-32 is invalid:"
                f" expected 0x{VALID_SILABS_CRC:08X}, got 0x{computed_crc:08X}"
            )

        break  # pragma: no cover


def parse_silabs_gbl(data: bytes) -> typing.Iterable[typing.Tuple[bytes, bytes]]:
    """
    Parses a Silicon Labs GBL firmware image.
    """

    orig_data = data

    while True:
        if len(data) < 8:
            raise ValidationError(
                "Image is truncated: not long enough to contain a valid tag"
            )

        tag = data[:4]
        length = int.from_bytes(data[4:8], "little")

        value = data[8 : 8 + length]

        if len(value) < length:
            raise ValidationError("Image is truncated: tag value is cut off")

        data = data[8 + length :]
        yield tag, value

        # GBL end tag
        if tag != b"\xFC\x04\x04\xFC":
            continue

        # GBL images aren't expected to contain padding but Hue images are padded with
        # null bytes
        if data.strip(b"\x00"):
            raise ValidationError("Image padding contains invalid bytes")

        unpadded_image = orig_data[: -len(data)] if data else orig_data
        computed_crc = zlib.crc32(unpadded_image)

        if computed_crc != VALID_SILABS_CRC:
            raise ValidationError(
                f"Image CRC-32 is invalid:"
                f" expected 0x{VALID_SILABS_CRC:08X}, got 0x{computed_crc:08X}"
            )

        break  # pragma: no cover


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

    tuple(parser(data))
    return ValidationResult.VALID


def validate_ota_image(image: OTAImage) -> ValidationResult:
    """
    Validates a Zigbee OTA image's embedded firmwares and indicates if an image is
    valid, invalid, or of an unknown type.
    """

    results = []

    for subelement in image.subelements:
        if subelement.tag_id == ElementTagId.UPGRADE_IMAGE:
            results.append(validate_firmware(subelement.data))

    if not results or any(r == ValidationResult.UNKNOWN for r in results):
        return ValidationResult.UNKNOWN

    return ValidationResult.VALID


def check_invalid(image: BaseOTAImage) -> bool:
    """
    Checks if an image is invalid or not. Unknown image types are considered valid.
    """

    if not isinstance(image, OTAImage):
        return False

    try:
        validate_ota_image(image)
        return False
    except ValidationError as e:
        LOGGER.warning("Image %s is invalid: %s", image.header, e)
        return True
