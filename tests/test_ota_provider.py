import asyncio
import binascii
from unittest import mock

import pytest
from asynctest import CoroutineMock, patch

import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

MANUFACTURER_ID = 4476
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def image_with_version():
    def img(version=100, empty_image=False, image_type=IMAGE_TYPE):
        img = zigpy.ota.provider.IKEAImage()
        img.header.manufacturer_id = MANUFACTURER_ID
        img.header.image_type = image_type
        img.header.file_version = version
        if not empty_image:
            img.subelements.append(
                zigpy.ota.image.SubElement.deserialize(
                    b'\x00\x00\x04\x00\x00\x00abcd')[0])
        return img
    return img


@pytest.fixture
def image(image_with_version):
    return image_with_version()


@pytest.fixture
def empty_image(image_with_version):
    return image_with_version(empty_image=True)


@pytest.fixture
def ikea_prov():
    return ota_p.Trådfri()


@pytest.fixture
def key():
    return zigpy.ota.image.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)


@pytest.mark.asyncio
async def test_get_image_no_cache(ikea_prov, key):
    ikea_prov.fetch_firmware = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    non_ikea = zigpy.ota.image.ImageKey(mock.sentinel.manufacturer,
                                        IMAGE_TYPE)

    r = ikea_prov.get_image(non_ikea)
    assert r is None
    assert ikea_prov.fetch_firmware.call_count == 0
    assert non_ikea not in ikea_prov._cache

    assert key not in ikea_prov._cache
    r = ikea_prov.get_image(key)
    assert r is None
    assert ikea_prov.fetch_firmware.call_count == 0


@pytest.mark.asyncio
async def test_get_image_empty(ikea_prov, key, empty_image):
    ikea_prov.fetch_firmware = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    ikea_prov._cache = mock.MagicMock()
    ikea_prov._cache.__getitem__.return_value = empty_image

    assert key not in ikea_prov._cache
    r = ikea_prov.get_image(key)
    assert r is None
    assert ikea_prov.fetch_firmware.call_count == 1


@pytest.mark.asyncio
async def test_get_image(ikea_prov, key, image):
    ikea_prov.fetch_firmware = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    ikea_prov._cache = mock.MagicMock()
    ikea_prov._cache.__getitem__.return_value = image

    assert key not in ikea_prov._cache
    r = ikea_prov.get_image(key)
    assert r is image
    assert ikea_prov.fetch_firmware.call_count == 0


@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_ikea_initialize_provider(mock_get, ikea_prov, image_with_version):
    ver1, img_type1 = (0x12345678, mock.sentinel.img_type_1)
    ver2, img_type2 = (0x23456789, mock.sentinel.img_type_2)
    img1 = image_with_version(version=ver1, image_type=img_type1)
    img2 = image_with_version(version=ver2, image_type=img_type2)

    mock_get.return_value.__aenter__.return_value.json = CoroutineMock(
        side_effect=[
            [
                {
                    "fw_binary_url": "http://localhost/ota.ota.signed",
                    "fw_build_version": 123,
                    "fw_filesize": 128,
                    "fw_hotfix_version": 1,
                    "fw_image_type": 2,
                    "fw_major_version": 3,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_minor_version": 4,
                    "fw_type": 2
                },
                {
                    "fw_binary_url": "http://localhost/ota1.ota.signed",
                    "fw_file_version_MSB": img1.version >> 16,
                    "fw_file_version_LSB": img1.version & 0xffff,
                    "fw_filesize": 129,
                    "fw_image_type": img1.header.image_type,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_type": 2
                },
                {
                    "fw_binary_url": "http://localhost/ota2.ota.signed",
                    "fw_file_version_MSB": img2.version >> 16,
                    "fw_file_version_LSB": img2.version & 0xffff,
                    "fw_filesize": 130,
                    "fw_image_type": img2.header.image_type,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_type": 2
                }
            ],
        ]
    )

    await ikea_prov.initialize_provider()
    assert mock_get.call_count == 1
    assert len(ikea_prov._cache) == 2
    assert img1.key in ikea_prov._cache
    assert img2.key in ikea_prov._cache
    cached_1 = ikea_prov._cache[img1.key]
    assert cached_1.header.image_type == img1.header.image_type
    assert cached_1.url == 'http://localhost/ota1.ota.signed'

    cached_2 = ikea_prov._cache[img2.key]
    assert cached_2.header.image_type == img2.header.image_type
    assert cached_2.url == 'http://localhost/ota2.ota.signed'


@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_ikea_fetch_image(mock_get, ikea_prov, image_with_version):
    prefix = b'\x00This is extra data\x00\x55\xaa'
    data = ('1ef1ee0b0001380000007c11012178563412020054657374204f544120496d61'
            '676500000000000000000000000000000000000042000000')
    sub_el = b'\x00\x00\x04\x00\x00\x00abcd'
    img = image_with_version(image_type=0x2101)
    img.url = mock.sentinel.url
    img.subelements = []
    ikea_prov._cache[img.key] = img

    mock_get.return_value.__aenter__.return_value.read = CoroutineMock(
        side_effect=[prefix + binascii.unhexlify(data) + sub_el]
    )

    assert not ikea_prov._cache[img.key].subelements
    await ikea_prov.fetch_firmware(img.key)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert ikea_prov._cache[img.key].subelements


@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_ikea_fetch_image_lock(mock_get, ikea_prov, image_with_version):
    img = image_with_version(image_type=0x2101)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = CoroutineMock(
        side_effect=[b'']
    )

    await ikea_prov._locks[img.key].acquire()
    await ikea_prov.fetch_firmware(img.key)
    assert mock_get.call_count == 0
