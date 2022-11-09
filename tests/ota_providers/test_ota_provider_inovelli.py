from unittest import mock

import pytest

from zigpy.config import CONF_OTA_INOVELLI
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from tests.async_mock import AsyncMock, patch

INOVELLI_ID = 4655
INOVELLI_IMAGE_TYPE = 257


@pytest.fixture
def inovelli_prov():
    p = ota_p.Inovelli()
    p.enable()
    return p


@pytest.fixture
def inovelli_image_with_version():
    def img(version=0x16908807, image_type=INOVELLI_IMAGE_TYPE):
        img = zigpy.ota.provider.INOVELLIImage(
            manufacturer_id=INOVELLI_ID,
            image_type=image_type,
            version=version,
            url=mock.sentinel.url,
        )
        return img

    return img


@pytest.fixture
def inovelli_image(inovelli_image_with_version):
    return inovelli_image_with_version()


@pytest.fixture
def inovelli_key():
    return zigpy.ota.image.ImageKey(INOVELLI_ID, INOVELLI_IMAGE_TYPE)


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
    img1 = inovelli_image_with_version(version=0x16908807, image_type=257)
    img2 = inovelli_image_with_version(version=0x33619975, image_type=258)

    base = "https://files.inovelli.com/firmware"

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        side_effect=[
            {
                "VZM31-SN": [
                    {
                        "version": "0000000B",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/1.11/VZM31-SN_1.11.ota",
                        "manufacturer_id": 4655,
                        "image_type": 257,
                    },
                    {
                        "version": "16842764",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/1.12/VZM31-SN_1.12.ota",
                        "manufacturer_id": 4655,
                        "image_type": 257,
                    },
                    # Reorder these to put the most recent image in the middle
                    {
                        "version": "16908807",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/2.07/VZM31-SN_2.07.ota",
                        "manufacturer_id": 4655,
                        "image_type": 257,
                    },
                    {
                        "version": "16843021",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/1.13/VZM31-SN_1.13.ota",
                        "manufacturer_id": 4655,
                        "image_type": 257,
                    },
                    {
                        "version": "16908805",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/2.05/VZM31-SN_2.05.ota",
                        "manufacturer_id": 4655,
                        "image_type": 257,
                    },
                    {
                        "version": "16908806",
                        "channel": "beta",
                        "firmware": f"{base}/VZM31-SN/Beta/2.06/VZM31-SN_2.06.ota",
                        "manufacturer_id": 4655,
                        "image_type": 257,
                    },
                ],
                "VZM35-SN": [
                    {
                        "version": "00000004",
                        "channel": "beta",
                        "firmware": f"{base}/VZM35-SN/Beta/1.04/VZM35-SN_1.04.ota",
                        "manufacturer_id": 4655,
                        "image_type": 258,
                    },
                    # This is reordered as well
                    {
                        "version": "33619975",
                        "channel": "beta",
                        "firmware": f"{base}/VZM35-SN/Beta/1.07/VZM35-SN_1.07.ota",
                        "manufacturer_id": 4655,
                        "image_type": 258,
                    },
                    {
                        "version": "33619974",
                        "channel": "beta",
                        "firmware": f"{base}/VZM35-SN/Beta/1.06/VZM35-SN_1.06.ota",
                        "manufacturer_id": 4655,
                        "image_type": 258,
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
    assert cached_1.image_type == img1.image_type

    # Most recent image is still picked
    assert cached_1.url == f"{base}/VZM31-SN/Beta/2.07/VZM31-SN_2.07.ota"

    cached_2 = inovelli_prov._cache[img2.key]
    assert cached_2.image_type == img2.image_type
    assert cached_2.url == f"{base}/VZM35-SN/Beta/1.07/VZM35-SN_1.07.ota"

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
    image = zigpy.ota.image.OTAImage(
        header=zigpy.ota.image.OTAImageHeader(
            upgrade_file_id=200208670,
            header_version=256,
            header_length=56,
            field_control=zigpy.ota.image.FieldControl(0),
            manufacturer_id=INOVELLI_ID,
            image_type=257,
            file_version=16908807,
            stack_version=2,
            header_string="EBL VM_SWITCH",
            image_size=66,
        ),
        subelements=[
            zigpy.ota.image.SubElement(
                tag_id=zigpy.ota.image.ElementTagId.UPGRADE_IMAGE, data=b"abcd"
            )
        ],
    )

    img = inovelli_image_with_version()
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        return_value=image.serialize()
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r == image
