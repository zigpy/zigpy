from unittest import mock

import pytest

from zigpy.config import CONF_OTA_SONOFF
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from tests.async_mock import AsyncMock, patch

MANUFACTURER_ID = 4742
IMAGE_TYPE = 1


@pytest.fixture
def sonoff_prov():
    p = ota_p.Sonoff()
    p.enable()
    return p


@pytest.fixture
def sonoff_image_with_version():
    def img(version=4353, image_type=IMAGE_TYPE):
        img = zigpy.ota.provider.SONOFFImage(
            manufacturer_id=MANUFACTURER_ID,
            image_type=image_type,
            version=version,
            image_size=131086,
            url=mock.sentinel.url,
        )
        return img

    return img


@pytest.fixture
def sonoff_image(sonoff_image_with_version):
    return sonoff_image_with_version()


@pytest.fixture
def sonoff_key():
    return zigpy.ota.image.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)


async def test_sonoff_init(sonoff_prov):
    sonoff_prov.enable = mock.MagicMock()
    sonoff_prov.refresh_firmware_list = AsyncMock()

    r = await sonoff_prov.initialize_provider({CONF_OTA_SONOFF: True})
    assert r is None
    assert sonoff_prov.enable.call_count == 1
    assert sonoff_prov.refresh_firmware_list.call_count == 1


async def test_sonoff_get_image_no_cache(sonoff_prov, sonoff_image):
    sonoff_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    sonoff_prov._cache = mock.MagicMock()
    sonoff_prov._cache.__getitem__.side_effect = KeyError()
    sonoff_prov.refresh_firmware_list = AsyncMock()

    # SONOFF manufacturer_id, but not in cache
    assert sonoff_image.key not in sonoff_prov._cache
    r = await sonoff_prov.get_image(sonoff_image.key)
    assert r is None
    assert sonoff_prov.refresh_firmware_list.call_count == 1
    assert sonoff_prov._cache.__getitem__.call_count == 1
    assert sonoff_image.fetch_image.call_count == 0


async def test_sonoff_get_image(sonoff_prov, sonoff_key, sonoff_image):
    sonoff_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    sonoff_prov._cache = mock.MagicMock()
    sonoff_prov._cache.__getitem__.return_value = sonoff_image
    sonoff_prov.refresh_firmware_list = AsyncMock()

    r = await sonoff_prov.get_image(sonoff_key)
    assert r is mock.sentinel.image
    assert sonoff_prov._cache.__getitem__.call_count == 1
    assert sonoff_prov._cache.__getitem__.call_args[0][0] == sonoff_image.key
    assert sonoff_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_sonoff_refresh_list(mock_get, sonoff_prov, sonoff_image_with_version):
    img = sonoff_image_with_version(version=4353, image_type=1)

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        return_value=[
            {
                "fw_binary_url": "https://zigbee-ota.sonoff.tech/releases/86-0001-00001101.zigbee",
                "fw_file_version": 4353,
                "fw_filesize": 131086,
                "fw_image_type": 1,
                "fw_manufacturer_id": 4742,
                "model_id": "ZBMINI-L",
            }
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 200
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await sonoff_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(sonoff_prov._cache) == 1
    assert img.key in sonoff_prov._cache

    cached = sonoff_prov._cache[img.key]
    assert cached.image_type == img.image_type
    assert (
        cached.url == "https://zigbee-ota.sonoff.tech/releases/86-0001-00001101.zigbee"
    )

    assert not sonoff_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_sonoff_refresh_list_locked(
    mock_get, sonoff_prov, sonoff_image_with_version
):
    await sonoff_prov._locks[ota_p.LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])

    await sonoff_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_sonoff_refresh_list_failed(mock_get, sonoff_prov):

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])
    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    with patch.object(sonoff_prov, "update_expiration") as update_exp:
        await sonoff_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert update_exp.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_sonoff_fetch_image(mock_get, sonoff_image_with_version):
    image = zigpy.ota.image.OTAImage(
        header=zigpy.ota.image.OTAImageHeader(
            upgrade_file_id=200208670,
            header_version=256,
            header_length=56,
            field_control=zigpy.ota.image.FieldControl(0),
            manufacturer_id=4742,
            image_type=1,
            file_version=4353,
            stack_version=2,
            header_string="",
            image_size=66,
        ),
        subelements=[
            zigpy.ota.image.SubElement(
                tag_id=zigpy.ota.image.ElementTagId.UPGRADE_IMAGE, data=b"abcd"
            )
        ],
    )

    img = sonoff_image_with_version(version=4353, image_type=1)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        return_value=image.serialize()
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r == image
