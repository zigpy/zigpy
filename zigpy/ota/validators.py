import enum
import typing

from zigpy.ota.image import ElementTagId, OTAImage


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

    while data:
        assert len(data) >= 4
        tag = data[:2]
        length = int.from_bytes(data[2:4], "big")

        value = data[4 : 4 + length]
        assert len(value) == length

        data = data[4 + length :]
        yield tag, value

        if tag == b"\xFC\x04":
            assert not data.strip(b"\xFF")
            break


def parse_silabs_gbl(data: bytes) -> typing.Iterable[typing.Tuple[bytes, bytes]]:
    """
    Parses a Silicon Labs GBL firmware image.
    """

    assert data

    while data:
        assert len(data) >= 8
        tag = data[:4]
        length = int.from_bytes(data[4:8], "little")

        value = data[8 : 8 + length]
        assert len(value) == length

        data = data[8 + length :]
        yield tag, value


def validate_firmware(data: bytes) -> ValidationResult:
    """
    Validates a firmware image.
    """

    if data.startswith(b"\xEB\x17\xA6\x03"):
        parsed = parse_silabs_gbl(data)
    elif data.startswith(b"\x00\x00\x00\x8C"):
        parsed = parse_silabs_ebl(data)
    else:
        return ValidationResult.UNKNOWN

    try:
        list(parsed)
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
