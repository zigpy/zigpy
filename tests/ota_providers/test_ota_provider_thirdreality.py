from unittest import mock

import pytest

from zigpy.config import CONF_OTA_THIRDREALITY
import zigpy.ota
import zigpy.ota.image
from zigpy.ota.provider import LOCK_REFRESH, ThirdReality, ThirdRealityImage

from tests.async_mock import AsyncMock, patch

MANUFACTURER_ID = 4659


@pytest.fixture
def thirdreality_prov():
    p = ThirdReality()
    p.enable()
    return p


@pytest.fixture
def thirdreality_image():
    return ThirdRealityImage.from_json(
        {
            "modelId": "3RSB22BZ",
            "url": "https://tr-zha.s3.amazonaws.com/firmwares/SmartButton_Zigbee_PROD_OTA_V21_1.00.21.ota",
            "version": "1.00.21",
            "imageType": 54184,
            "manufacturerId": 4659,
            "fileVersion": 33,
        }
    )


async def test_thirdreality_init(thirdreality_prov):
    thirdreality_prov.enable = mock.MagicMock()
    thirdreality_prov.refresh_firmware_list = AsyncMock()

    r = await thirdreality_prov.initialize_provider({CONF_OTA_THIRDREALITY: True})
    assert r is None
    assert thirdreality_prov.enable.call_count == 1
    assert thirdreality_prov.refresh_firmware_list.call_count == 1


async def test_thirdreality_get_image_no_cache(thirdreality_prov, thirdreality_image):
    thirdreality_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    thirdreality_prov._cache = mock.MagicMock()
    thirdreality_prov._cache.__getitem__.side_effect = KeyError()
    thirdreality_prov.refresh_firmware_list = AsyncMock()

    # ThirdReality manufacturer_id, but not in cache
    assert thirdreality_image.key not in thirdreality_prov._cache
    r = await thirdreality_prov.get_image(thirdreality_image.key)
    assert r is None
    assert thirdreality_prov.refresh_firmware_list.call_count == 1
    assert thirdreality_prov._cache.__getitem__.call_count == 1
    assert thirdreality_image.fetch_image.call_count == 0


async def test_thirdreality_get_image(thirdreality_prov, thirdreality_image):
    thirdreality_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    thirdreality_prov._cache = mock.MagicMock()
    thirdreality_prov._cache.__getitem__.return_value = thirdreality_image
    thirdreality_prov.refresh_firmware_list = AsyncMock()

    r = await thirdreality_prov.get_image(thirdreality_image.key)
    assert r is mock.sentinel.image
    assert thirdreality_prov._cache.__getitem__.call_count == 1
    assert (
        thirdreality_prov._cache.__getitem__.mock_calls[0].args[0]
        == thirdreality_image.key
    )
    assert thirdreality_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_thirdreality_refresh_list(
    mock_get, thirdreality_prov, thirdreality_image
):
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        return_value={
            "versions": [
                {
                    "modelId": "3RSB22BZ",
                    "url": "https://tr-zha.s3.amazonaws.com/firmwares/SmartButton_Zigbee_PROD_OTA_V21_1.00.21.ota",
                    "version": "1.00.21",
                    "imageType": 54184,
                    "manufacturerId": 4659,
                    "fileVersion": 33,
                }
            ]
        }
    )
    mock_get.return_value.__aenter__.return_value.status = 200
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await thirdreality_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(thirdreality_prov._cache) == 1
    assert thirdreality_image.key in thirdreality_prov._cache

    cached = thirdreality_prov._cache[thirdreality_image.key]
    assert cached.image_type == thirdreality_image.image_type
    assert (
        cached.url
        == "https://tr-zha.s3.amazonaws.com/firmwares/SmartButton_Zigbee_PROD_OTA_V21_1.00.21.ota"
    )

    assert not thirdreality_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_thirdreality_refresh_list_locked(mock_get, thirdreality_prov):
    await thirdreality_prov._locks[LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])

    await thirdreality_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_thirdreality_refresh_list_failed(mock_get, thirdreality_prov):
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])
    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    with patch.object(thirdreality_prov, "update_expiration") as update_exp:
        await thirdreality_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert update_exp.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_thirdreality_fetch_image(mock_get, thirdreality_image):
    image = zigpy.ota.image.OTAImage(
        header=zigpy.ota.image.OTAImageHeader(
            upgrade_file_id=200208670,
            header_version=256,
            header_length=56,
            field_control=zigpy.ota.image.FieldControl(0),
            manufacturer_id=MANUFACTURER_ID,
            image_type=54184,
            file_version=33,
            stack_version=2,
            header_string="Telink OTA Sample Usage",
            image_size=66,
        ),
        subelements=[
            zigpy.ota.image.SubElement(
                tag_id=zigpy.ota.image.ElementTagId.UPGRADE_IMAGE, data=b"abcd"
            )
        ],
    )

    thirdreality_image.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        return_value=image.serialize()
    )

    r = await thirdreality_image.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.mock_calls[0].args[0] == mock.sentinel.url
    assert r == image
