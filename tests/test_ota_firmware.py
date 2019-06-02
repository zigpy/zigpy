from unittest import mock

import pytest

import zigpy.ota.firmware as firmware
import zigpy.types as t

MANUFACTURER_ID = mock.sentinel.manufacturer_id
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def key():
    return firmware.FirmwareKey(MANUFACTURER_ID, IMAGE_TYPE)


def test_firmware_key():
    key = firmware.FirmwareKey(MANUFACTURER_ID, IMAGE_TYPE)
    assert key.manufacturer_id is MANUFACTURER_ID
    assert key.image_type is IMAGE_TYPE


def test_firmware(key):
    s = mock.sentinel
    frm = firmware.Firmware(key, s.ver, s.size, s.url)

    assert frm.key == key
    assert frm.version is s.ver
    assert frm.size is s.size
    assert frm.url is s.url

    assert frm.is_valid is False
    frm.data = s.data
    assert frm.is_valid is True


def test_upgradeable(key):
    s = mock.sentinel
    frm = firmware.Firmware(key, 100, s.size, s.url, s.data)

    assert not frm.upgradeable(MANUFACTURER_ID, IMAGE_TYPE, 100, None)
    assert not frm.upgradeable(MANUFACTURER_ID, IMAGE_TYPE, 101, None)
    assert frm.upgradeable(MANUFACTURER_ID, IMAGE_TYPE, 99, None)


def test_hw_version():
    hw = firmware.HWVersion(0x0a01)
    assert hw.version == 10
    assert hw.revision == 1

    assert 'version=10' in repr(hw)
    assert 'revision=1' in repr(hw)


def _test_ota_img_header(field_control, hdr_suffix=b'', extra=b''):
    d = b'\x1e\xf1\xee\x0b\x00\x018\x00'
    d += field_control
    d += b'|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00' \
         b'\x00\x00\x00\x00\x00\x00~\x91\x02\x00'
    d += hdr_suffix

    hdr, rest = firmware.OTAImageHeader.deserialize(d + extra)
    assert hdr.header_version == 0x0100
    assert hdr.header_length == 0x0038
    assert hdr.manufacturer_id == 4476
    assert hdr.image_type == 0x2101
    assert hdr.file_version == 0x12214572
    assert hdr.stack_version == 0x0002
    assert hdr.image_size == 0x0002917e
    assert hdr.serialize() == d

    return hdr, rest


def test_ota_image_header():
    hdr = firmware.OTAImageHeader()
    assert hdr.security_credential_version_present is None
    assert hdr.device_specific_file is None
    assert hdr.hardware_versions_present is None

    extra = b'abcdefghklmnpqr'

    hdr, rest = _test_ota_img_header(b'\x00\x00', extra=extra)
    assert rest == extra
    assert hdr.security_credential_version_present is False
    assert hdr.device_specific_file is False
    assert hdr.hardware_versions_present is False


def test_ota_image_header_security():
    extra = b'abcdefghklmnpqr'
    creds = t.uint8_t(0xac)
    hdr, rest = _test_ota_img_header(b'\x01\x00', creds.serialize(), extra)

    assert rest == extra
    assert hdr.security_credential_version_present is True
    assert hdr.security_credential_version == creds
    assert hdr.device_specific_file is False
    assert hdr.hardware_versions_present is False


def test_ota_image_header_hardware_versions():
    extra = b'abcdefghklmnpqr'
    hw_min = firmware.HWVersion(0xbeef)
    hw_max = firmware.HWVersion(0xabcd)
    hdr, rest = _test_ota_img_header(b'\x04\x00',
                                     hw_min.serialize() + hw_max.serialize(),
                                     extra)

    assert rest == extra
    assert hdr.security_credential_version_present is False
    assert hdr.device_specific_file is False
    assert hdr.hardware_versions_present is True
    assert hdr.minimum_hardware_version == hw_min
    assert hdr.maximum_hardware_version == hw_max


def test_ota_image_destination():
    extra = b'abcdefghklmnpqr'

    dst = t.EUI64.deserialize(b'12345678')[0]

    hdr, rest = _test_ota_img_header(b'\x02\x00', dst.serialize(), extra)
    assert rest == extra
    assert hdr.security_credential_version_present is False
    assert hdr.device_specific_file is True
    assert hdr.upgrade_file_destination == dst
    assert hdr.hardware_versions_present is False


def test_ota_img_wrong_header():
    d = b'\x1e\xf0\xee\x0b\x00\x018\x00\x00\x00'
    d += b'|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00' \
         b'\x00\x00\x00\x00\x00\x00~\x91\x02\x00'

    with pytest.raises(ValueError):
        firmware.OTAImageHeader.deserialize(d)

    with pytest.raises(ValueError):
        firmware.OTAImageHeader.deserialize(d + b'123abc')


def test_header_string():
    size = 32
    header_string = "This is a header String"
    data = header_string.encode('utf8').ljust(size, b'\x00')
    extra = b'cdef123'

    hdr_str, rest = firmware.HeaderString.deserialize(data + extra)
    assert rest == extra
    assert hdr_str == header_string

    hdr_str, rest = firmware.HeaderString.deserialize(data)
    assert rest == b''
    assert hdr_str == header_string
    assert firmware.HeaderString(header_string).serialize() == data


def test_header_string_too_short():
    header_string = "This is a header String"
    data = header_string.encode('utf8')

    with pytest.raises(ValueError):
        firmware.HeaderString.deserialize(data)