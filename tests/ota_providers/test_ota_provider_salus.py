import io
import tarfile
from unittest import mock

import pytest

from zigpy.config import CONF_OTA_SALUS
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from tests.async_mock import AsyncMock, patch
from tests.test_ota_image import image  # noqa: F401

SALUS_ID = 4216
SALUS_MODEL = "XY123"


@pytest.fixture
def salus_prov():
    p = ota_p.Salus()
    p.enable()
    return p


@pytest.fixture
def salus_image_with_version():
    def img(version=100, model=SALUS_MODEL):
        img = zigpy.ota.provider.SalusImage(
            SALUS_ID, model, version, 180052, mock.sentinel.url
        )
        return img

    return img


@pytest.fixture
def salus_image(salus_image_with_version):
    return salus_image_with_version()


@pytest.fixture
def salus_key():
    return zigpy.ota.image.ImageKey(SALUS_ID, SALUS_MODEL)


async def test_salus_init_ota_dir(salus_prov):
    salus_prov.enable = mock.MagicMock()
    salus_prov.refresh_firmware_list = AsyncMock()

    r = await salus_prov.initialize_provider({CONF_OTA_SALUS: True})
    assert r is None
    assert salus_prov.enable.call_count == 1
    assert salus_prov.refresh_firmware_list.call_count == 1


async def test_salus_get_image_no_cache(salus_prov, salus_image):
    salus_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    salus_prov._cache = mock.MagicMock()
    salus_prov._cache.__getitem__.side_effect = KeyError()
    salus_prov.refresh_firmware_list = AsyncMock()

    # salus manufacturer_id, but not in cache
    assert salus_image.key not in salus_prov._cache
    r = await salus_prov.get_image(salus_image.key)
    assert r is None
    assert salus_prov.refresh_firmware_list.call_count == 1
    assert salus_prov._cache.__getitem__.call_count == 1
    assert salus_image.fetch_image.call_count == 0


async def test_salus_get_image(salus_prov, salus_key, salus_image):
    salus_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    salus_prov._cache = mock.MagicMock()
    salus_prov._cache.__getitem__.return_value = salus_image
    salus_prov.refresh_firmware_list = AsyncMock()

    r = await salus_prov.get_image(salus_key)
    assert r is mock.sentinel.image
    assert salus_prov._cache.__getitem__.call_count == 1
    assert salus_prov._cache.__getitem__.call_args[0][0] == salus_image.key
    assert salus_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_salus_refresh_list(mock_get, salus_prov, salus_image_with_version):
    img1 = salus_image_with_version(version="00000006", model="45856")
    img2 = salus_image_with_version(version="00000006", model="45857")

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        side_effect=[
            {
                "versions": [
                    {
                        "model": "45856",
                        "version": "00000006",
                        "url": "http://eu.salusconnect.io/download/firmware/a65779cd-13cd-41e5-a7e0-5346f24a0f62/45856_00000006.tar.gz",
                    },
                    {
                        "model": "45857",
                        "version": "00000006",
                        "url": "http://eu.salusconnect.io/download/firmware/3319b501-98f3-4337-afbe-8d04bb9938bc/45857_00000006.tar.gz",
                    },
                ]
            }
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 202
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await salus_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(salus_prov._cache) == 2
    assert img1.key in salus_prov._cache
    assert img2.key in salus_prov._cache
    cached_1 = salus_prov._cache[img1.key]
    assert cached_1.model == img1.model
    base = "http://eu.salusconnect.io/download/firmware/"
    assert (
        cached_1.url
        == base + "a65779cd-13cd-41e5-a7e0-5346f24a0f62/45856_00000006.tar.gz"
    )

    cached_2 = salus_prov._cache[img2.key]
    assert cached_2.model == img2.model
    assert (
        cached_2.url
        == base + "3319b501-98f3-4337-afbe-8d04bb9938bc/45857_00000006.tar.gz"
    )

    assert not salus_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_salus_refresh_list_locked(
    mock_get, salus_prov, salus_image_with_version
):
    await salus_prov._locks[ota_p.LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])

    await salus_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_salus_refresh_list_failed(mock_get, salus_prov):
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])
    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    with patch.object(salus_prov, "update_expiration") as update_exp:
        await salus_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert update_exp.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_salus_fetch_image(mock_get, salus_image_with_version):
    data = bytes.fromhex(  # based on ikea sample but modded mfr code
        "1ef1ee0b0001380000007810012178563412020054657374204f544120496d61"
        "676500000000000000000000000000000000000042000000"
    )

    sub_el = b"\x00\x00\x04\x00\x00\x00abcd"
    # construct tar.gz from header + sub_el
    binstr = data + sub_el
    fh = io.BytesIO()  # don't create a real file on disk, just in RAM.
    with tarfile.open(fileobj=fh, mode="w:gz") as tar:
        info = tarfile.TarInfo("salus_sample.ota")
        info.size = len(binstr)
        tar.addfile(info, io.BytesIO(binstr))

    img = salus_image_with_version(model=SALUS_MODEL)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        side_effect=[fh.getvalue()]
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r.serialize() == data + sub_el
