import hashlib
from unittest import mock

import pytest

from zigpy.ota import CachedImage
import zigpy.ota.image as firmware
import zigpy.types as t

MANUFACTURER_ID = mock.sentinel.manufacturer_id
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def image():
    img = firmware.OTAImage()
    img.header = firmware.OTAImageHeader(
        upgrade_file_id=firmware.OTAImageHeader.MAGIC_VALUE,
        header_version=256,
        header_length=56,
        field_control=0,
        manufacturer_id=9876,
        image_type=123,
        file_version=12345,
        stack_version=2,
        header_string="This is a test header!",
        image_size=56 + 2 + 4 + 4,
    )
    img.subelements = [firmware.SubElement(tag_id=0x0000, data=b"data")]

    return img


@pytest.fixture
def key():
    return firmware.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)


def test_firmware_key():
    key = firmware.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)
    assert key.manufacturer_id is MANUFACTURER_ID
    assert key.image_type is IMAGE_TYPE


def test_hw_version():
    hw = firmware.HWVersion(0x0A01)
    assert hw.version == 10
    assert hw.revision == 1

    assert "version=10" in repr(hw)
    assert "revision=1" in repr(hw)


def _test_ota_img_header(field_control, hdr_suffix=b"", extra=b""):
    d = b"\x1e\xf1\xee\x0b\x00\x018\x00"
    d += field_control
    d += (
        b"|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00~\x91\x02\x00"
    )
    d += hdr_suffix

    hdr, rest = firmware.OTAImageHeader.deserialize(d + extra)
    assert hdr.header_version == 0x0100
    assert hdr.header_length == 0x0038
    assert hdr.manufacturer_id == 4476
    assert hdr.image_type == 0x2101
    assert hdr.file_version == 0x12214572
    assert hdr.stack_version == 0x0002
    assert hdr.image_size == 0x0002917E
    assert hdr.serialize() == d

    return hdr, rest


def test_ota_image_header():
    hdr = firmware.OTAImageHeader()
    assert hdr.security_credential_version_present is None
    assert hdr.device_specific_file is None
    assert hdr.hardware_versions_present is None

    extra = b"abcdefghklmnpqr"

    hdr, rest = _test_ota_img_header(b"\x00\x00", extra=extra)
    assert rest == extra
    assert hdr.security_credential_version_present is False
    assert hdr.device_specific_file is False
    assert hdr.hardware_versions_present is False


def test_ota_image_header_security():
    extra = b"abcdefghklmnpqr"
    creds = t.uint8_t(0xAC)
    hdr, rest = _test_ota_img_header(b"\x01\x00", creds.serialize(), extra)

    assert rest == extra
    assert hdr.security_credential_version_present is True
    assert hdr.security_credential_version == creds
    assert hdr.device_specific_file is False
    assert hdr.hardware_versions_present is False


def test_ota_image_header_hardware_versions():
    extra = b"abcdefghklmnpqr"
    hw_min = firmware.HWVersion(0xBEEF)
    hw_max = firmware.HWVersion(0xABCD)
    hdr, rest = _test_ota_img_header(
        b"\x04\x00", hw_min.serialize() + hw_max.serialize(), extra
    )

    assert rest == extra
    assert hdr.security_credential_version_present is False
    assert hdr.device_specific_file is False
    assert hdr.hardware_versions_present is True
    assert hdr.minimum_hardware_version == hw_min
    assert hdr.maximum_hardware_version == hw_max


def test_ota_image_destination():
    extra = b"abcdefghklmnpqr"

    dst = t.EUI64.deserialize(b"12345678")[0]

    hdr, rest = _test_ota_img_header(b"\x02\x00", dst.serialize(), extra)
    assert rest == extra
    assert hdr.security_credential_version_present is False
    assert hdr.device_specific_file is True
    assert hdr.upgrade_file_destination == dst
    assert hdr.hardware_versions_present is False


def test_ota_img_wrong_header():
    d = b"\x1e\xf0\xee\x0b\x00\x018\x00\x00\x00"
    d += (
        b"|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00~\x91\x02\x00"
    )

    with pytest.raises(ValueError):
        firmware.OTAImageHeader.deserialize(d)

    with pytest.raises(ValueError):
        firmware.OTAImageHeader.deserialize(d + b"123abc")


def test_header_string():
    size = 32
    header_string = "This is a header String"
    data = header_string.encode("utf8").ljust(size, b"\x00")
    extra = b"cdef123"

    hdr_str, rest = firmware.HeaderString.deserialize(data + extra)
    assert rest == extra
    assert hdr_str == header_string

    hdr_str, rest = firmware.HeaderString.deserialize(data)
    assert rest == b""
    assert hdr_str == header_string
    assert firmware.HeaderString(header_string).serialize() == data


def test_header_string_too_short():
    header_string = "This is a header String"
    data = header_string.encode("utf8")

    with pytest.raises(ValueError):
        firmware.HeaderString.deserialize(data)


def test_subelement():
    payload = b"\x00payload\xff"
    data = b"\x01\x00" + t.uint32_t(len(payload)).serialize() + payload
    extra = b"extra"

    e, rest = firmware.SubElement.deserialize(data + extra)
    assert rest == extra
    assert e.tag_id == firmware.ElementTagId.ECDSA_SIGNATURE_CRYPTO_SUITE_1
    assert e.data == payload
    assert len(e.data) == len(payload)

    assert e.serialize() == data


def test_subelement_too_short():
    for i in range(1, 5):
        with pytest.raises(ValueError):
            firmware.SubElement.deserialize(b"".ljust(i, b"\x00"))

    e, rest = firmware.SubElement.deserialize(b"\x00\x00\x00\x00\x00\x00")
    assert e.data == b""
    assert rest == b""

    with pytest.raises(ValueError):
        firmware.SubElement.deserialize(b"\x00\x02\x02\x00\x00\x00a")


@pytest.fixture
def raw_header():
    def data(elements_size=0):
        d = b"\x1e\xf1\xee\x0b\x00\x018\x00\x00\x00"
        d += b"|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00"
        d += b"\x00\x00\x00\x00\x00\x00"
        d += t.uint32_t(elements_size + 56).serialize()
        return d

    return data


@pytest.fixture
def raw_sub_element():
    def data(tag_id, payload=b""):
        r = t.uint16_t(tag_id).serialize()
        r += t.uint32_t(len(payload)).serialize()
        return r + payload

    return data


def test_ota_image(raw_header, raw_sub_element):
    el1_payload = b"abcd"
    el2_payload = b"4321"
    el1 = raw_sub_element(0, el1_payload)
    el2 = raw_sub_element(1, el2_payload)

    extra = b"edbc321"
    img, rest = firmware.OTAImage.deserialize(
        raw_header(len(el1 + el2)) + el1 + el2 + extra
    )

    assert rest == extra
    assert len(img.subelements) == 2
    assert img.subelements[0].tag_id == 0
    assert img.subelements[0].data == el1_payload
    assert img.subelements[1].tag_id == 1
    assert img.subelements[1].data == el2_payload

    assert img.serialize() == raw_header(len(el1 + el2)) + el1 + el2

    with pytest.raises(ValueError):
        firmware.OTAImage.deserialize(raw_header(len(el1 + el2)) + el1 + el2[:-1])


def test_ota_img_should_upgrade():
    manufacturer_id = 0x2345
    image_type = 0x4567
    version = 0xABBA

    hdr = firmware.OTAImageHeader()
    hdr.manufacturer_id = manufacturer_id
    hdr.image_type = image_type
    hdr.file_version = version

    img = CachedImage(firmware.OTAImage(hdr))
    assert img.should_update(manufacturer_id, image_type, version) is False
    assert img.should_update(manufacturer_id, image_type, version - 1) is True
    assert img.should_update(manufacturer_id, image_type - 1, version - 1) is False
    assert img.should_update(manufacturer_id, image_type + 1, version - 1) is False
    assert img.should_update(manufacturer_id - 1, image_type, version - 1) is False
    assert img.should_update(manufacturer_id + 1, image_type, version - 1) is False


def test_ota_img_should_upgrade_hw_ver():
    manufacturer_id = 0x2345
    image_type = 0x4567
    version = 0xABBA

    hdr = firmware.OTAImageHeader()
    hdr.field_control = 0x0004
    hdr.manufacturer_id = manufacturer_id
    hdr.image_type = image_type
    hdr.file_version = version
    hdr.minimum_hardware_version = 2
    hdr.maximum_hardware_version = 4

    img = CachedImage(firmware.OTAImage(hdr))
    assert img.should_update(manufacturer_id, image_type, version - 1) is True

    for hw_ver in range(2, 4):
        assert (
            img.should_update(manufacturer_id, image_type, version - 1, hw_ver) is True
        )
    assert img.should_update(manufacturer_id, image_type, version - 1, 1) is False
    assert img.should_update(manufacturer_id, image_type, version - 1, 5) is False


def test_get_image_block(raw_header, raw_sub_element):
    el1_payload = b"abcd"
    el2_payload = b"4321"
    el1 = raw_sub_element(0, el1_payload)
    el2 = raw_sub_element(1, el2_payload)

    raw_data = raw_header(len(el1 + el2)) + el1 + el2
    img = CachedImage(firmware.OTAImage.deserialize(raw_data)[0])

    offset, size = 28, 20
    block = img.get_image_block(offset, size)
    assert block == raw_data[offset : offset + min(size, img.MAXIMUM_DATA_SIZE)]

    offset, size = 30, 50
    block = img.get_image_block(offset, size)
    assert block == raw_data[offset : offset + min(size, img.MAXIMUM_DATA_SIZE)]


def test_get_image_block_offset_too_large(raw_header, raw_sub_element):
    el1_payload = b"abcd"
    el2_payload = b"4321"
    el1 = raw_sub_element(0, el1_payload)
    el2 = raw_sub_element(1, el2_payload)

    raw_data = raw_header(len(el1 + el2)) + el1 + el2
    img = CachedImage(firmware.OTAImage.deserialize(raw_data)[0])

    offset, size = len(raw_data) + 1, 44
    with pytest.raises(ValueError):
        img.get_image_block(offset, size)


def test_cached_image_wrapping(image):
    cached_img = CachedImage(image)
    assert cached_img.header is image.header


def test_cached_image_serialize(image):
    cached_img = CachedImage(image)
    cached_image_data = cached_img.serialize()
    assert cached_image_data == image.serialize()


def wrap_ikea(data):
    header = bytearray(100)
    header[0:4] = b"NGIS"
    header[16:20] = len(header).to_bytes(4, "little")
    header[20:24] = len(data).to_bytes(4, "little")

    return header + data + b"F" * 512


def test_parse_ota_normal(image):
    assert firmware.parse_ota_image(image.serialize()) == (image, b"")


def test_parse_ota_ikea(image):
    data = wrap_ikea(image.serialize())
    assert firmware.parse_ota_image(data) == (image, b"")


def test_parse_ota_ikea_trailing(image):
    data = wrap_ikea(image.serialize() + b"trailing")

    parsed, remaining = firmware.parse_ota_image(data)
    assert not remaining

    assert parsed.header.image_size == len(image.serialize() + b"trailing")
    assert parsed.subelements[0].data == b"data" + b"trailing"

    parsed2, remaining2 = firmware.OTAImage.deserialize(parsed.serialize())
    assert not remaining2


@pytest.mark.parametrize(
    "data",
    [
        b"NGIS" + b"truncated",
        b"NGIS" + b"long enough to container header but not actual image",
    ],
)
def test_parse_ota_ikea_truncated(data):
    with pytest.raises(ValueError):
        firmware.parse_ota_image(data)


def create_hue_ota(data):
    data = b"\x2A\x00\x01" + data

    header, _ = firmware.OTAImageHeader.deserialize(
        bytes.fromhex(
            "1ef1ee0b0001380000000b100301d5670042020000000000000000000000000000000000000000"
            "0000000000000000000000000038f00300"
        )
    )
    header.image_size = len(header.serialize()) + len(data)

    return header.serialize() + data


def test_parse_ota_hue():
    data = create_hue_ota(b"test") + b"rest"
    img, rest = firmware.parse_ota_image(data)

    assert isinstance(img, firmware.HueSBLOTAImage)
    assert rest == b"rest"
    assert img.data == b"\x2A\x00\x01" + b"test"
    assert img.serialize() + b"rest" == data


def test_parse_ota_hue_invalid():
    data = create_hue_ota(b"test")
    firmware.parse_ota_image(data)

    with pytest.raises(ValueError):
        firmware.parse_ota_image(data[:-1])

    header, rest = firmware.OTAImageHeader.deserialize(data)
    assert data == header.serialize() + rest

    with pytest.raises(ValueError):
        # Three byte sequence must be the first thing after the header
        firmware.parse_ota_image(header.serialize() + b"\xFF" + rest[1:])

    with pytest.raises(ValueError):
        # Only Hue is known to use these images
        firmware.parse_ota_image(header.replace(manufacturer_id=12).serialize() + rest)


def test_legrand_container_unwrapping(image):
    # Unwrapped size prefix and 1 + 16 byte suffix
    data = (
        t.uint32_t(len(image.serialize())).serialize()
        + image.serialize()
        + b"\x01"
        + b"abcdabcdabcdabcd"
    )

    with pytest.raises(ValueError):
        firmware.parse_ota_image(data[:-1])

    with pytest.raises(ValueError):
        firmware.parse_ota_image(b"\xFF" + data[1:])

    img, rest = firmware.parse_ota_image(data)
    assert not rest
    assert img == image


def test_thirdreality_container(image):
    image_bytes = image.serialize()

    # There's little useful information in the header
    subcontainer = (
        t.uint32_t(16).serialize()
        # Total length of image, excluding SHA512 prefix
        + t.uint32_t(len(image_bytes) + 152 - 64).serialize()
        + t.uint32_t(152).serialize()
        # Unknown four byte prefix/suffix and what looks like a second SHA512 hash
        + b"?" * (64 + 4)
        + t.uint32_t(0).serialize()
        + t.uint32_t(0).serialize()
        + image_bytes
    )

    data = hashlib.sha512(subcontainer).digest() + subcontainer

    assert data.index(image_bytes) == 152

    img, rest = firmware.parse_ota_image(data)
    assert not rest
    assert img == image

    with pytest.raises(ValueError):
        firmware.parse_ota_image(data[:-1])

    with pytest.raises(ValueError):
        firmware.parse_ota_image(b"\xFF" + data[1:])
