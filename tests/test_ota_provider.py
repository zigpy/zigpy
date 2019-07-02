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
    def img(version=100, image_type=IMAGE_TYPE):
        img = zigpy.ota.provider.IKEAImage(
            MANUFACTURER_ID, image_type, version, 66, mock.sentinel.url
        )
        return img
    return img


@pytest.fixture
def image(image_with_version):
    return image_with_version()


@pytest.fixture
def basic_prov():
    return ota_p.Basic()


@pytest.fixture
def ikea_prov():
    return ota_p.Trådfri()


@pytest.fixture
def key():
    return zigpy.ota.image.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)


def test_expiration(ikea_prov):
    # if we never refreshed firmware list then we should be expired
    assert ikea_prov.expired


@pytest.mark.asyncio
async def test_initialize_provider(basic_prov):
    await basic_prov.initialize_provider(mock.sentinel.ota_dir)


@pytest.mark.asyncio
async def test_basic_refresh_firmware_list(basic_prov):
    with pytest.raises(NotImplementedError):
        await basic_prov.refresh_firmware_list()


@pytest.mark.asyncio
async def test_basic_get_image(basic_prov, key):
    image = mock.MagicMock()
    image.fetch_image = CoroutineMock(return_value=mock.sentinel.image)
    basic_prov._cache = mock.MagicMock()
    basic_prov._cache.__getitem__.return_value = image
    basic_prov.refresh_firmware_list = CoroutineMock()

    await basic_prov._locks[key].acquire()

    # locked image
    r = await basic_prov.get_image(key)
    assert r is None
    assert basic_prov.refresh_firmware_list.call_count == 0
    assert basic_prov._cache.__getitem__.call_count == 0
    assert image.fetch_image.call_count == 0

    # unlocked image
    basic_prov._locks.pop(key)

    r = await basic_prov.get_image(key)
    assert r is mock.sentinel.image
    assert basic_prov.refresh_firmware_list.call_count == 1
    assert basic_prov._cache.__getitem__.call_count == 1
    assert basic_prov._cache.__getitem__.call_args[0][0] == key
    assert image.fetch_image.call_count == 1


@pytest.mark.asyncio
async def test_get_image_no_cache(ikea_prov, image):
    image.fetch_image = CoroutineMock(return_value=mock.sentinel.image)
    ikea_prov._cache = mock.MagicMock()
    ikea_prov._cache.__getitem__.side_effect = KeyError()
    ikea_prov.refresh_firmware_list = CoroutineMock()

    non_ikea = zigpy.ota.image.ImageKey(mock.sentinel.manufacturer,
                                        IMAGE_TYPE)

    # Non IKEA manufacturer_id, don't bother doing anything at all
    r = await ikea_prov.get_image(non_ikea)
    assert r is None
    assert ikea_prov._cache.__getitem__.call_count == 0
    assert ikea_prov.refresh_firmware_list.call_count == 0
    assert non_ikea not in ikea_prov._cache

    # IKEA manufacturer_id, but not in cache
    assert image.key not in ikea_prov._cache
    r = await ikea_prov.get_image(image.key)
    assert r is None
    assert ikea_prov.refresh_firmware_list.call_count == 1
    assert ikea_prov._cache.__getitem__.call_count == 1
    assert image.fetch_image.call_count == 0


@pytest.mark.asyncio
async def test_get_image(ikea_prov, key, image):
    image.fetch_image = CoroutineMock(return_value=mock.sentinel.image)
    ikea_prov._cache = mock.MagicMock()
    ikea_prov._cache.__getitem__.return_value = image
    ikea_prov.refresh_firmware_list = CoroutineMock()

    r = await ikea_prov.get_image(key)
    assert r is mock.sentinel.image
    assert ikea_prov._cache.__getitem__.call_count == 1
    assert ikea_prov._cache.__getitem__.call_args[0][0] == image.key
    assert image.fetch_image.call_count == 1


@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_ikea_refresh_list(mock_get, ikea_prov, image_with_version):
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
                    "fw_image_type": img1.image_type,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_type": 2
                },
                {
                    "fw_binary_url": "http://localhost/ota2.ota.signed",
                    "fw_file_version_MSB": img2.version >> 16,
                    "fw_file_version_LSB": img2.version & 0xffff,
                    "fw_filesize": 130,
                    "fw_image_type": img2.image_type,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_type": 2
                }
            ],
        ]
    )

    await ikea_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(ikea_prov._cache) == 2
    assert img1.key in ikea_prov._cache
    assert img2.key in ikea_prov._cache
    cached_1 = ikea_prov._cache[img1.key]
    assert cached_1.image_type == img1.image_type
    assert cached_1.url == 'http://localhost/ota1.ota.signed'

    cached_2 = ikea_prov._cache[img2.key]
    assert cached_2.image_type == img2.image_type
    assert cached_2.url == 'http://localhost/ota2.ota.signed'

    assert not ikea_prov.expired


@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_ikea_refresh_list_locked(mock_get, ikea_prov, image_with_version):
    await ikea_prov._locks[ota_p.LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = CoroutineMock(
        side_effect=[[]]
    )

    await ikea_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_ikea_fetch_image(mock_get, image_with_version):
    prefix = b'\x00This is extra data\x00\x55\xaa'
    data = ('1ef1ee0b0001380000007c11012178563412020054657374204f544120496d61'
            '676500000000000000000000000000000000000042000000')
    data = binascii.unhexlify(data)
    sub_el = b'\x00\x00\x04\x00\x00\x00abcd'
    img = image_with_version(image_type=0x2101)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = CoroutineMock(
        side_effect=[prefix + data + sub_el]
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r.serialize() == data + sub_el
