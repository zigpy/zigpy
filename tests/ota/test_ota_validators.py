from unittest import mock
import zlib

import pytest

from zigpy.ota import validators
from zigpy.ota.image import ElementTagId, OTAImage, SubElement
from zigpy.ota.validators import ValidationError, ValidationResult


def create_ebl_image(tags):
    # All images start with a 140-byte "0x0000" header
    tags = [(b"\x00\x00", b"jklm" * 35)] + tags

    assert all(len(tag) == 2 for tag, value in tags)
    image = b"".join(tag + len(value).to_bytes(2, "big") + value for tag, value in tags)

    # And end with a checksum
    image += b"\xFC\x04\x00\x04" + zlib.crc32(image + b"\xFC\x04\x00\x04").to_bytes(
        4, "little"
    )

    if len(image) % 64 != 0:
        image += b"\xFF" * (64 - len(image) % 64)

    assert list(validators.parse_silabs_ebl(image))

    return image


def create_gbl_image(tags):
    # All images start with an 8-byte header
    tags = [(b"\xEB\x17\xA6\x03", b"\x00\x00\x00\x03\x01\x01\x00\x00")] + tags

    assert all(len(tag) == 4 for tag, value in tags)
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

    assert list(validators.parse_silabs_gbl(image))

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
    with pytest.raises(ValidationError):
        list(validators.parse_silabs_ebl(image[:-1]))

    with pytest.raises(ValidationError):
        list(validators.parse_silabs_ebl(image + b"\xFF"))

    # Nothing can come after the padding
    assert list(validators.parse_silabs_ebl(image[:-1] + b"\xFF"))

    with pytest.raises(ValidationError):
        list(validators.parse_silabs_ebl(image[:-1] + b"\xAB"))

    # Truncated images are detected
    with pytest.raises(ValidationError):
        list(validators.parse_silabs_ebl(image[: image.index(b"test")] + b"\xFF" * 44))

    # As are corrupted images of the correct length but with bad tag lengths
    with pytest.raises(ValidationError):
        index = image.index(b"test")
        bad_image = image[: index - 2] + b"\xFF\xFF" + image[index:]
        list(validators.parse_silabs_ebl(bad_image))

    # Truncated but at a 64-byte boundary, missing CRC footer
    with pytest.raises(ValidationError):
        bad_image = create_ebl_image([(b"AA", b"test" * 11)])
        bad_image = bad_image[: bad_image.rindex(b"test") + 4]
        list(validators.parse_silabs_ebl(bad_image))

    # Corrupted images are detected
    corrupted_image = image.replace(b"foo", b"goo", 1)
    assert image != corrupted_image

    with pytest.raises(ValidationError):
        list(validators.parse_silabs_ebl(corrupted_image))


def test_parse_silabs_gbl():
    list(validators.parse_silabs_gbl(VALID_GBL_IMAGE))

    image = create_gbl_image([(b"AAAA", b"test"), (b"BBBB", b"foo" * 20)])

    header, tag1, tag2, checksum = validators.parse_silabs_gbl(image)

    assert header[0] == b"\xEB\x17\xA6\x03" and len(header[1]) == 8
    assert tag1 == (b"AAAA", b"test")
    assert tag2 == (b"BBBB", b"foo" * 20)
    assert checksum[0] == b"\xFC\x04\x04\xFC" and len(checksum[1]) == 4

    # Arbitrary padding is allowed
    parsed_image = [header, tag1, tag2, checksum]
    assert list(validators.parse_silabs_gbl(image + b"\x00")) == parsed_image
    assert list(validators.parse_silabs_gbl(image + b"\xAB\xCD\xEF")) == parsed_image

    # Normal truncated images are detected
    with pytest.raises(ValidationError):
        list(validators.parse_silabs_gbl(image[-10:]))

    # Structurally sound but truncated images are detected
    with pytest.raises(ValidationError):
        offset = image.index(b"test")
        bad_image = image[: offset - 8]

        list(validators.parse_silabs_gbl(bad_image))

    # Corrupted images are detected
    with pytest.raises(ValidationError):
        corrupted_image = image.replace(b"foo", b"goo", 1)
        assert image != corrupted_image

        list(validators.parse_silabs_gbl(corrupted_image))


def test_validate_firmware():
    assert validators.validate_firmware(VALID_EBL_IMAGE) == ValidationResult.VALID

    with pytest.raises(ValidationError):
        validators.validate_firmware(VALID_EBL_IMAGE[:-1])

    with pytest.raises(ValidationError):
        validators.validate_firmware(VALID_EBL_IMAGE + b"\xFF")

    assert validators.validate_firmware(VALID_GBL_IMAGE) == ValidationResult.VALID

    with pytest.raises(ValidationError):
        validators.validate_firmware(VALID_GBL_IMAGE[:-1])

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
        create_subelement(ElementTagId.ECDSA_SIGNATURE_CRYPTO_SUITE_1, b"asd"),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_GBL_IMAGE),
        create_subelement(ElementTagId.ECDSA_SIGNING_CERTIFICATE_CRYPTO_SUITE_1, b"ab"),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.VALID


def test_validate_ota_image_invalid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE[:-1]),
    ]

    with pytest.raises(ValidationError):
        validators.validate_ota_image(image)


def test_validate_ota_image_mixed_invalid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, b"unknown"),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE[:-1]),
    ]

    with pytest.raises(ValidationError):
        validators.validate_ota_image(image)


def test_validate_ota_image_mixed_valid():
    image = OTAImage()
    image.subelements = [
        create_subelement(ElementTagId.UPGRADE_IMAGE, b"unknown1"),
        create_subelement(ElementTagId.UPGRADE_IMAGE, VALID_EBL_IMAGE),
    ]

    assert validators.validate_ota_image(image) == ValidationResult.UNKNOWN


def test_validate_ota_image_empty():
    image = OTAImage()
    image.subelements = []

    assert validators.validate_ota_image(image) == ValidationResult.UNKNOWN


def test_check_invalid_unknown():
    image = mock.Mock()

    assert validators.validate_ota_image(image) == ValidationResult.UNKNOWN


def test_check_invalid():
    image = OTAImage()

    with mock.patch("zigpy.ota.validators.validate_ota_image") as m:
        m.side_effect = [ValidationResult.VALID]
        assert not validators.check_invalid(image)

    with mock.patch("zigpy.ota.validators.validate_ota_image") as m:
        m.side_effect = [ValidationResult.UNKNOWN]
        assert not validators.check_invalid(image)

    with mock.patch("zigpy.ota.validators.validate_ota_image") as m:
        m.side_effect = [ValidationError("error")]
        assert validators.check_invalid(image)
