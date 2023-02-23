from unittest import mock

import pytest

from zigpy.config import CONF_OTA_LEDVANCE
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from tests.async_mock import AsyncMock, patch
from tests.test_ota_image import image  # noqa: F401

LEDVANCE_ID = 4489
LEDVANCE_IMAGE_TYPE = 25


@pytest.fixture
def ledvance_prov():
    p = ota_p.Ledvance()
    p.enable()
    return p


@pytest.fixture
def ledvance_image_with_version():
    def img(version=100, image_type=LEDVANCE_IMAGE_TYPE):
        img = zigpy.ota.provider.LedvanceImage(
            LEDVANCE_ID, image_type, version, 180052, mock.sentinel.url
        )
        return img

    return img


@pytest.fixture
def ledvance_image(ledvance_image_with_version):
    return ledvance_image_with_version()


@pytest.fixture
def ledvance_key():
    return zigpy.ota.image.ImageKey(LEDVANCE_ID, LEDVANCE_IMAGE_TYPE)


async def test_ledvance_init_ota_dir(ledvance_prov):
    ledvance_prov.enable = mock.MagicMock()
    ledvance_prov.refresh_firmware_list = AsyncMock()

    r = await ledvance_prov.initialize_provider({CONF_OTA_LEDVANCE: True})
    assert r is None
    assert ledvance_prov.enable.call_count == 1
    assert ledvance_prov.refresh_firmware_list.call_count == 1


async def test_ledvance_get_image_no_cache(ledvance_prov, ledvance_image):
    ledvance_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    ledvance_prov._cache = mock.MagicMock()
    ledvance_prov._cache.__getitem__.side_effect = KeyError()
    ledvance_prov.refresh_firmware_list = AsyncMock()

    # LEDVANCE manufacturer_id, but not in cache
    assert ledvance_image.key not in ledvance_prov._cache
    r = await ledvance_prov.get_image(ledvance_image.key)
    assert r is None
    assert ledvance_prov.refresh_firmware_list.call_count == 1
    assert ledvance_prov._cache.__getitem__.call_count == 1
    assert ledvance_image.fetch_image.call_count == 0


async def test_ledvance_get_image(ledvance_prov, ledvance_key, ledvance_image):
    ledvance_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    ledvance_prov._cache = mock.MagicMock()
    ledvance_prov._cache.__getitem__.return_value = ledvance_image
    ledvance_prov.refresh_firmware_list = AsyncMock()

    r = await ledvance_prov.get_image(ledvance_key)
    assert r is mock.sentinel.image
    assert ledvance_prov._cache.__getitem__.call_count == 1
    assert ledvance_prov._cache.__getitem__.call_args[0][0] == ledvance_image.key
    assert ledvance_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_ledvance_refresh_list(
    mock_get, ledvance_prov, ledvance_image_with_version
):
    ver1, img_type1 = (0x00102428, 25)
    ver2, img_type2 = (0x00102428, 13)
    img1 = ledvance_image_with_version(version=ver1, image_type=img_type1)
    img2 = ledvance_image_with_version(version=ver2, image_type=img_type2)

    sha_1 = "ffe0298312f63fa0be5e568886e419d714146652ff4747a8afed2de"
    fn_1 = "A19 RGBW/00102428/A19_RGBW_IMG0019_00102428-encrypted"
    sha_2 = "fa5ab550bde3e8c877cf40aa460fc9836405a7843df040e75bfdb2f"
    fn_2 = "A19 TW 10 year/00102428/A19_TW_10_year_IMG000D_001024"
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        side_effect=[
            {
                "firmwares": [
                    {
                        "blob": None,
                        "identity": {
                            "company": 4489,
                            "product": 25,
                            "version": {
                                "major": 1,
                                "minor": 2,
                                "build": 428,
                                "revision": 40,
                            },
                        },
                        "releaseNotes": "",
                        "shA256": sha_1,
                        "name": "A19_RGBW_IMG0019_00102428-encrypted.ota",
                        "productName": "A19 RGBW",
                        "fullName": fn_1,
                        "extension": ".ota",
                        "released": "2019-02-28T16:36:28",
                        "salesRegion": "us",
                        "length": 180052,
                    },
                    {
                        "blob": None,
                        "identity": {
                            "company": 4489,
                            "product": 13,
                            "version": {
                                "major": 1,
                                "minor": 2,
                                "build": 428,
                                "revision": 40,
                            },
                        },
                        "releaseNotes": "",
                        "shA256": sha_2,
                        "name": "A19_TW_10_year_IMG000D_00102428-encrypted.ota",
                        "productName": "A19 TW 10 year",
                        "fullName": fn_2,
                        "extension": ".ota",
                        "released": "2019-02-28T16:42:50",
                        "salesRegion": "us",
                        "length": 170800,
                    },
                    # Old version but shows up after the new version in the OTA list
                    {
                        "blob": None,
                        "identity": {
                            "company": 4489,
                            "product": 13,
                            "version": {
                                "major": 0,
                                "minor": 2,
                                "build": 428,
                                "revision": 40,
                            },
                        },
                        "releaseNotes": "",
                        "shA256": sha_2,
                        "name": "A19_TW_10_year_IMG000D_00102428-encrypted.ota",
                        "productName": "A19 TW 10 year",
                        "fullName": fn_2,
                        "extension": ".ota",
                        "released": "2015-02-28T16:42:50",
                        "salesRegion": "us",
                        "length": 170800,
                    },
                ]
            }
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 202
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await ledvance_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(ledvance_prov._cache) == 2
    assert img1.key in ledvance_prov._cache
    assert img2.key in ledvance_prov._cache
    cached_1 = ledvance_prov._cache[img1.key]
    assert cached_1.image_type == img1.image_type
    base = "https://api.update.ledvance.com/v1/zigbee/firmwares/download"
    assert cached_1.url == base + "?Company=4489&Product=25&Version=1.2.428.40"

    cached_2 = ledvance_prov._cache[img2.key]
    assert cached_2.image_type == img2.image_type
    assert cached_2.url == base + "?Company=4489&Product=13&Version=1.2.428.40"

    assert not ledvance_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_ledvance_refresh_list_locked(
    mock_get, ledvance_prov, ledvance_image_with_version
):
    await ledvance_prov._locks[ota_p.LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])

    await ledvance_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_ledvance_refresh_list_failed(mock_get, ledvance_prov):
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])
    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    with patch.object(ledvance_prov, "update_expiration") as update_exp:
        await ledvance_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert update_exp.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_ledvance_fetch_image(mock_get, ledvance_image_with_version):
    data = bytes.fromhex(
        "1ef1ee0b0001380000008911012178563412020054657374204f544120496d61"
        "676500000000000000000000000000000000000042000000"
    )
    sub_el = b"\x00\x00\x04\x00\x00\x00abcd"

    img = ledvance_image_with_version(image_type=0x2101)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        side_effect=[data + sub_el]
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r.serialize() == data + sub_el
