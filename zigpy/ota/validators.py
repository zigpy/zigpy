import typing
import zlib

from zigpy.ota.image import ElementTagId, OTAImage

VALID_SILABS_CRC = 0x2144DF1C  # CRC32(anything | CRC32(anything)) == CRC32(0x00000000)


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

        break


def parse_silabs_gbl(data: bytes) -> typing.Iterable[typing.Tuple[bytes, bytes]]:
    """
    Parses a Silicon Labs GBL firmware image.
    """

    computed_crc = zlib.crc32(data)

    if computed_crc != VALID_SILABS_CRC:
        raise ValidationError(
            f"Image CRC-32 is invalid:"
            f" expected 0x{VALID_SILABS_CRC:08X}, got 0x{computed_crc:08X}"
        )

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

        if tag != b"\xFC\x04\x04\xFC":
            continue

        if data:
            raise ValidationError("Image contains trailing data")

        break


def validate_firmware(data: bytes) -> bool:
    """
    Validates a firmware image.
    """

    parser = None

    if data.startswith(b"\xEB\x17\xA6\x03"):
        parser = parse_silabs_gbl
    elif data.startswith(b"\x00\x00\x00\x8C"):
        parser = parse_silabs_ebl
    else:
        return None

    tuple(parser(data))
    return True


def validate_ota_image(image: OTAImage) -> bool:
    """
    Validates a Zigbee OTA image's embedded firmwares.
    """

    results = []

    for subelement in image.subelements:
        if subelement.tag_id == ElementTagId.UPGRADE_IMAGE:
            results.append(validate_firmware(subelement))

    if not results or any(r is None for r in results):
        return None

    return True
