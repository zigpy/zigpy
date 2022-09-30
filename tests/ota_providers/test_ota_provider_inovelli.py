from unittest import mock

import pytest

from zigpy.config import CONF_OTA_INOVELLI
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from tests.async_mock import AsyncMock, patch
from tests.test_ota_image import image  # noqa: F401

INOVELLI_ID = 4655
INOVELLI_MODEL = "VZM31-SN"


@pytest.fixture
def inovelli_prov():
    p = ota_p.Inovelli()
    p.enable()
    return p


@pytest.fixture
def inovelli_image_with_version():
    def img(version=5, model=INOVELLI_MODEL):
        img = zigpy.ota.provider.INOVELLIImage(
            INOVELLI_ID, model, version, mock.sentinel.url
        )
        return img

    return img


@pytest.fixture
def inovelli_image(inovelli_image_with_version):
    return inovelli_image_with_version()


@pytest.fixture
def inovelli_key():
    return zigpy.ota.image.ImageKey(INOVELLI_ID, INOVELLI_MODEL)


async def test_inovelli_init_ota_dir(inovelli_prov):
    inovelli_prov.enable = mock.MagicMock()
    inovelli_prov.refresh_firmware_list = AsyncMock()

    r = await inovelli_prov.initialize_provider({CONF_OTA_INOVELLI: True})
    assert r is None
    assert inovelli_prov.enable.call_count == 1
    assert inovelli_prov.refresh_firmware_list.call_count == 1


async def test_inovelli_get_image_no_cache(inovelli_prov, inovelli_image):
    inovelli_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    inovelli_prov._cache = mock.MagicMock()
    inovelli_prov._cache.__getitem__.side_effect = KeyError()
    inovelli_prov.refresh_firmware_list = AsyncMock()

    # inovelli manufacturer_id, but not in cache
    assert inovelli_image.key not in inovelli_prov._cache
    r = await inovelli_prov.get_image(inovelli_image.key)
    assert r is None
    assert inovelli_prov.refresh_firmware_list.call_count == 1
    assert inovelli_prov._cache.__getitem__.call_count == 1
    assert inovelli_image.fetch_image.call_count == 0


async def test_inovelli_get_image(inovelli_prov, inovelli_key, inovelli_image):
    inovelli_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    inovelli_prov._cache = mock.MagicMock()
    inovelli_prov._cache.__getitem__.return_value = inovelli_image
    inovelli_prov.refresh_firmware_list = AsyncMock()

    r = await inovelli_prov.get_image(inovelli_key)
    assert r is mock.sentinel.image
    assert inovelli_prov._cache.__getitem__.call_count == 1
    assert inovelli_prov._cache.__getitem__.call_args[0][0] == inovelli_image.key
    assert inovelli_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_inovelli_refresh_list(
    mock_get, inovelli_prov, inovelli_image_with_version
):
    img1 = inovelli_image_with_version(version="00000005", model="VMDS00I00")
    img2 = inovelli_image_with_version(version="00000010", model="VZM31-SN")

    base = "https://files.inovelli.com/firmware"

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        side_effect=[
            {
                "VMDS00I00": [
                    {
                        "version": "00000005",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000005/00000005.ota",
                    }
                ],
                "VZM31-SN": [
                    {
                        "version": "00000005",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000005/00000005.ota",
                    },
                    {
                        "version": "00000006",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000006/00000006.ota",
                    },
                    {
                        "version": "00000010",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000010/00000010.ota",
                    },
                    {
                        "version": "00000007",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000007/00000007.ota",
                    },
                    {
                        "version": "00000008",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000008/00000008.ota",
                    },
                    {
                        "version": "00000009",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/00000009/00000009.ota",
                    },
                ],
            }
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 202
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await inovelli_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(inovelli_prov._cache) == 2
    assert img1.key in inovelli_prov._cache
    assert img2.key in inovelli_prov._cache
    cached_1 = inovelli_prov._cache[img1.key]
    assert cached_1.model == img1.model
    assert cached_1.url == f"{base}/VZM31-SN/Beta/00000005/00000005.ota"

    cached_2 = inovelli_prov._cache[img2.key]
    assert cached_2.model == img2.model
    assert cached_2.url == f"{base}/VZM31-SN/Beta/00000010/00000010.ota"

    assert not inovelli_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_inovelli_refresh_list_locked(
    mock_get, inovelli_prov, inovelli_image_with_version
):
    await inovelli_prov._locks[ota_p.LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])

    await inovelli_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_inovelli_refresh_list_failed(mock_get, inovelli_prov):

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])
    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    with patch.object(inovelli_prov, "update_expiration") as update_exp:
        await inovelli_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert update_exp.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_inovelli_fetch_image(mock_get, inovelli_image_with_version):
    header = bytes.fromhex(  # based on ikea sample but modded mfr code
        "1ef1ee0b0001380000002f12012178563412020054657374204f544120496d61"
        "676500000000000000000000000000000000000042000000"
    )

    sub_el = b"\x00\x00\x04\x00\x00\x00abcd"

    img = inovelli_image_with_version(model=INOVELLI_MODEL)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        side_effect=[header + sub_el]
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r.serialize() == header + sub_el
