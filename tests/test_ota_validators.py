import zlib

import pytest

from zigpy.ota import validators
from zigpy.ota.image import ElementTagId, OTAImage, SubElement
from zigpy.ota.validators import ValidationResult


def create_ebl_image(tags):
    # All images start with a 140-byte "0x0000" header
    tags = [(b"\x00\x00", b"test" * 35)] + tags

    assert all([len(tag) == 2 for tag, value in tags])
    image = b"".join(tag + len(value).to_bytes(2, "big") + value for tag, value in tags)

    # And end with a checksum
    image += b"\xFC\x04\x00\x04" + zlib.crc32(image + b"\xFC\x04\x00\x04").to_bytes(
        4, "little"
    )

    if len(image) % 64 != 0:
        image += b"\xFF" * (64 - len(image) % 64)

    return image


def create_gbl_image(tags):
    # All images start with an 8-byte header
    tags = [(b"\xEB\x17\xA6\x03", b"\x00\x00\x00\x03\x01\x01\x00\x00")] + tags

    assert all([len(tag) == 4 for tag, value in tags])
    image = b"".join(
        tag + len(value).to_bytes(4, "little") + value for tag, value in tags
    )

    # And end with a checksum
    image += (
        b"\xFC\x04\x04\xFC"
        + b"\x04\x00\x00\x00"
        + zlib.crc32(image + b"\xFC\x04\x04\xFC" + b"\x04\x00\x00\x00").to_bytes(
            4, "little"
        )
    )

    return image


VALID_EBL_IMAGE = create_ebl_image([(b"ab", b"foo")])
VALID_GBL_IMAGE = create_gbl_image([(b"test", b"foo")])


def create_subelement(tag_id, value):
    return SubElement.deserialize(
        tag_id.serialize() + len(value).to_bytes(4, "little") + value
    )[0]


def test_parse_silabs_ebl():
    list(validators.parse_silabs_ebl(VALID_EBL_IMAGE))

    image = create_ebl_image([(b"AA", b"test"), (b"BB", b"foo" * 20)])

    header, tag1, tag2, checksum = validators.parse_silabs_ebl(image)
    assert len(image) % 64 == 0
    assert header[0] == b"\x00\x00" and len(header[1]) == 140
    assert tag1 == (b"AA", b"test")
    assert tag2 == (b"BB", b"foo" * 20)
    assert checksum[0] == b"\xFC\x04" and len(checksum[1]) == 4

    # Padding needs to be a multiple of 64 bytes
    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(image[:-1]))

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(image + b"\xFF"))

    # Corrupted images are detected
    corrupted_image = image.replace(b"foo", b"goo", 1)
    assert image != corrupted_image

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(corrupted_image))


def test_parse_silabs_gbl():
    list(validators.parse_silabs_gbl(VALID_GBL_IMAGE))

    image = create_gbl_image([(b"AAAA", b"test"), (b"BBBB", b"foo" * 20)])

    header, tag1, tag2, checksum = validators.parse_silabs_gbl(image)
    assert header[0] == b"\xEB\x17\xA6\x03" and len(header[1]) == 8
    assert tag1 == (b"AAAA", b"test")
    assert tag2 == (b"BBBB", b"foo" * 20)
    assert checksum[0] == b"\xFC\x04\x04\xFC" and len(checksum[1]) == 4

    # No padding is allowed
    with pytest.raises(AssertionError):
        list(validators.parse_silabs_gbl(image + b"\xFF"))

    # Corrupted images are detected
    corrupted_image = image.replace(b"foo", b"goo", 1)
    assert image != corrupted_image

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_gbl(corrupted_image))


def test_validate_firmware():
    assert validators.validate_firmware(VALID_EBL_IMAGE) == ValidationResult.VALID
    assert (
        validators.validate_firmware(VALID_EBL_IMAGE[:-1]) == ValidationResult.INVALID
    )
    assert (
        validators.validate_firmware(VALID_EBL_IMAGE + b"\xFF")
        == ValidationResult.INVALID
    )

    assert validators.validate_firmware(VALID_GBL_IMAGE) == ValidationResult.VALID
    assert (
        validators.validate_firmware(VALID_GBL_IMAGE[:-1]) == ValidationResult.INVALID
    )

    assert validators.validate_firmware(b"UNKNOWN") == ValidationResult.UNKNOWN


def test_validate_ota_image_simple_valid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.VALID


def test_validate_ota_image_complex_valid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.ECDSA_SIGNATURE, b"asd"),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_GBL_IMAGE),
        create_subelement(ElementTagId.ECDSA_SIGNING_CERTIFICATE, b"foo"),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.VALID


def test_validate_ota_image_invalid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE[:-1]),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.INVALID


def test_validate_ota_image_mixed_invalid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, b"unknown"),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE[:-1]),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.INVALID


def test_validate_ota_image_mixed_valid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, b"unknown1"),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.UNKNOWN


def test_validate_ota_image_empty():
    image = OTAImage()

    assert validators.validate_ota_image(image) == ValidationResult.UNKNOWN
