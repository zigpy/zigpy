import io
import tarfile
from unittest import mock

import pytest

from zigpy.config import CONF_OTA_THIRDREALITY
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from tests.async_mock import AsyncMock, patch
from tests.test_ota_image import image  # noqa: F401

# THIRDREALITY_ID = 4877
THIRDREALITY_ID = 4659
THIRDREALITY_MODEL = "3RSS009Z_1"


@pytest.fixture
def thirdreality_prov():
    p = ota_p.ThirdReality()
    p.enable()
    return p


@pytest.fixture
def thirdreality_image_with_version():
    def img(version=100, model=THIRDREALITY_MODEL):
        img = zigpy.ota.provider.ThirdRealityImage(
            THIRDREALITY_ID, model, version, 180052, mock.sentinel.url
        )
        return img

    return img


@pytest.fixture
def thirdreality_image(thirdreality_image_with_version):
    return thirdreality_image_with_version()


@pytest.fixture
def thirdreality_key():
    return zigpy.ota.image.ImageKey(THIRDREALITY_ID, THIRDREALITY_MODEL)


async def test_thirdreality_init_ota_dir(thirdreality_prov):
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

    # thirdreality manufacturer_id, but not in cache
    assert thirdreality_image.key not in thirdreality_prov._cache
    r = await thirdreality_prov.get_image(thirdreality_image.key)
    assert r is None
    assert thirdreality_prov.refresh_firmware_list.call_count == 1
    assert thirdreality_prov._cache.__getitem__.call_count == 1
    assert thirdreality_image.fetch_image.call_count == 0


async def test_thirdreality_get_image(
    thirdreality_prov, thirdreality_key, thirdreality_image
):
    thirdreality_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    thirdreality_prov._cache = mock.MagicMock()
    thirdreality_prov._cache.__getitem__.return_value = thirdreality_image
    thirdreality_prov.refresh_firmware_list = AsyncMock()

    r = await thirdreality_prov.get_image(thirdreality_key)
    assert r is mock.sentinel.image
    assert thirdreality_prov._cache.__getitem__.call_count == 1
    assert (
        thirdreality_prov._cache.__getitem__.call_args[0][0] == thirdreality_image.key
    )
    assert thirdreality_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_thirdreality_refresh_list(
    mock_get, thirdreality_prov, thirdreality_image_with_version
):
    img1 = thirdreality_image_with_version(version="02.00.11.00", model="3RSS009Z")
    img2 = thirdreality_image_with_version(version="02.00.11.00", model="3RMS16BZ")

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        side_effect=[
            {
                "versions": [
                    {
                        "modelId": "3RSS009Z",
                        "version": "012",
                        "url": "https://s3.amazonaws.com/tr-ota-us-prod/3RSS009Z_1_099_20220922_062427.bin",
                    },
                    {
                        "modelId": "3RMS16BZ",
                        "version": "012",
                        "url": "https://s3.amazonaws.com/tr-ota-us-prod/3RSS009B_1_088_20210319_070742.bin",
                    },
                ]
            }
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 202
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await thirdreality_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(thirdreality_prov._cache) == 2
    assert img1.key in thirdreality_prov._cache
    assert img2.key in thirdreality_prov._cache
    cached_1 = thirdreality_prov._cache[img1.key]
    assert cached_1.model == img1.model
    assert (
        cached_1.url
        == "https://s3.amazonaws.com/tr-ota-us-prod/3RSS009Z_1_099_20220922_062427.bin"
    )

    cached_2 = thirdreality_prov._cache[img2.key]
    assert cached_2.model == img2.model
    assert (
        cached_2.url
        == "https://s3.amazonaws.com/tr-ota-us-prod/3RSS009B_1_088_20210319_070742.bin"
    )

    assert not thirdreality_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_thirdreality_refresh_list_locked(
    mock_get, thirdreality_prov, thirdreality_image_with_version
):
    await thirdreality_prov._locks[ota_p.LOCK_REFRESH].acquire()

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
async def test_thirdreality_fetch_image(mock_get, thirdreality_image_with_version):
    # data = bytes.fromhex(  # based on ikea sample but modded mfr code
    #     "1ef1ee0b0001380000007810012178563412020054657374204f544120496d61"
    #     "676500000000000000000000000000000000000042000000"
    # )
    data = bytes.fromhex(  # based on ikea sample but modded mfr code
        "1ef1ee0b0001380000003312a5d312000000020054656c696e6b204f54412053616d706c6520557361"
        "67650000000000000000000000000000000000923b02000000"
    )

    sub_el = b"\x00\x00\x04\x00\x00\x00abcd"
    # construct tar.gz from header + sub_el
    binstr = data + sub_el

    # print(f"binstr : {binstr}")
    fh = io.BytesIO()  # don't create a real file on disk, just in RAM.
    with tarfile.open(fileobj=fh, mode="w:gz") as tar:
        info = tarfile.TarInfo("thirdreality_sample.ota")
        info.size = len(binstr)
        tar.addfile(info, io.BytesIO(binstr))

    img = thirdreality_image_with_version(model=THIRDREALITY_MODEL)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        side_effect=[fh.getvalue()]
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    # assert r.serialize() == data + sub_el
    # assert r.serialize() == data + sub_el
