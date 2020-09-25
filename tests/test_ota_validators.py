import pytest

from zigpy.ota import validators
from zigpy.ota.image import ElementTagId, OTAImage, SubElement
from zigpy.ota.validators import ValidationResult

VALID_EBL_IMAGE = (
    b"\x00\x00\x00\x8C" + b"\xAB" * 140 + b"\xFC\x04\x00\x00" + b"\xFF" * 44
)
VALID_GBL_IMAGE = b"\xEB\x17\xA6\x03\x00\x00\x00\x00"


def create_subelement(tag_id, value):
    return SubElement.deserialize(
        tag_id.serialize() + len(value).to_bytes(4, "little") + value
    )[0]


def test_parse_silabs_ebl():
    img = b"AA" + b"\x00\x04" + b"test" + b"\xFC\x04\x00\x00" + b"\xFF" * 52

    assert list(validators.parse_silabs_ebl(img)) == [
        (b"AA", b"test"),
        (b"\xFC\x04", b""),
    ]

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(b""))

    # Needs to be a multiple of 64 bytes
    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(img[:-1]))

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(img + b"\xFF"))

    # Bad length
    with pytest.raises(AssertionError):
        list(validators.parse_silabs_ebl(b"AA\xFF\xFF" + b"\xFF" * 60))

    img2 = (
        b"AA"
        + b"\x00\x05"
        + b"test1"
        + b"BB"
        + b"\x00\x04"
        + b"test"
        + b"\xFC\x04\x00\x00"
        + b"\xFF" * 43
    )

    assert list(validators.parse_silabs_ebl(img2)) == [
        (b"AA", b"test1"),
        (b"BB", b"test"),
        (b"\xFC\x04", b""),
    ]


def test_parse_silabs_gbl():
    img = b"AAAA" + b"\x04\x00\x00\x00" + b"test"

    assert list(validators.parse_silabs_gbl(img)) == [(b"AAAA", b"test")]

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_gbl(b""))

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_gbl(img[:-1]))

    with pytest.raises(AssertionError):
        list(validators.parse_silabs_gbl(img + b"\xFF"))

    # Bad length
    with pytest.raises(AssertionError):
        list(validators.parse_silabs_gbl(b"AAAA\xFF\xFF\xFF\xFF"))

    img2 = (
        b"AAAA"
        + b"\x05\x00\x00\x00"
        + b"test1"
        + b"BBBB"
        + b"\x04\x00\x00\x00"
        + b"test"
    )

    assert list(validators.parse_silabs_gbl(img2)) == [
        (b"AAAA", b"test1"),
        (b"BBBB", b"test"),
    ]


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
