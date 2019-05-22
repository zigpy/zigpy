from unittest import mock

import pytest

from zigpy.ota.firmware import Firmware, FirmwareKey

MANUFACTURER_ID = mock.sentinel.manufacturer_id
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def key():
    return FirmwareKey(MANUFACTURER_ID, IMAGE_TYPE)


def test_firmware_key():
    key = FirmwareKey(MANUFACTURER_ID, IMAGE_TYPE)
    assert key.manufacturer_id is MANUFACTURER_ID
    assert key.image_type is IMAGE_TYPE


def test_firmware(key):
    s = mock.sentinel
    frm = Firmware(key, s.ver, s.size, s.url)

    assert frm.key == key
    assert frm.version is s.ver
    assert frm.size is s.size
    assert frm.url is s.url

    assert frm.is_valid is False
    frm.data = s.data
    assert frm.is_valid is True


def test_upgradeable(key):
    s = mock.sentinel
    frm = Firmware(key, 100, s.size, s.url, s.data)

    assert not frm.upgradeable(MANUFACTURER_ID, IMAGE_TYPE, 100, None)
    assert not frm.upgradeable(MANUFACTURER_ID, IMAGE_TYPE, 101, None)
    assert frm.upgradeable(MANUFACTURER_ID, IMAGE_TYPE, 99, None)
