import io
import os.path
import tarfile
from unittest import mock
import uuid

import pytest

from zigpy.config import (
    CONF_OTA_DIR,
    CONF_OTA_IKEA,
    CONF_OTA_INOVELLI,
    CONF_OTA_LEDVANCE,
    CONF_OTA_SALUS,
)
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from .async_mock import AsyncMock, patch
from .test_ota_image import image  # noqa: F401

MANUFACTURER_ID = 4476
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def file_image_name(tmpdir, image):  # noqa: F811
    def ota_img_filename(name="ota-image"):
        file_name = os.path.join(str(tmpdir), name + "-" + str(uuid.uuid4()))
        with open(os.path.join(file_name), mode="bw+") as file:
            file.write(image.serialize())
        return file_name

    return ota_img_filename


@pytest.fixture
def file_image(file_image_name):
    img = ota_p.FileImage()
    img.file_name = file_image_name()
    img.manufacturer_id = MANUFACTURER_ID
    img.image_type = IMAGE_TYPE
    return img


@pytest.fixture
def file_prov():
    p = ota_p.FileStore()
    p.enable()
    return p


@pytest.fixture
def file_image_with_version(file_image_name):
    def img(version=100, image_type=IMAGE_TYPE):
        img = ota_p.FileImage()
        img.file_name = file_image_name()
        img.header.file_version = version
        img.header.manufacturer_id = MANUFACTURER_ID
        img.header.image_type = image_type
        return img

    return img


@pytest.fixture
def ikea_image_with_version():
    def img(version=100, image_type=IMAGE_TYPE):
        img = zigpy.ota.provider.IKEAImage(
            MANUFACTURER_ID, image_type, version, 66, mock.sentinel.url
        )
        return img

    return img


@pytest.fixture
def ikea_image(ikea_image_with_version):
    return ikea_image_with_version()


@pytest.fixture
def basic_prov():
    class Prov(ota_p.Basic):
        async def initialize_provider(self, ota_config):
            return None

        async def refresh_firmware_list(self):
            return None

    p = Prov()
    p.enable()
    return p


@pytest.fixture
def ikea_prov():
    p = ota_p.Trådfri()
    p.enable()
    return p


@pytest.fixture
def key():
    return zigpy.ota.image.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)


def test_expiration(ikea_prov):
    # if we never refreshed firmware list then we should be expired
    assert ikea_prov.expired


async def test_initialize_provider(basic_prov):
    await basic_prov.initialize_provider(mock.sentinel.ota_dir)


async def test_basic_get_image(basic_prov, key):
    image = mock.MagicMock()  # noqa: F811
    image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    basic_prov._cache = mock.MagicMock()
    basic_prov._cache.__getitem__.return_value = image
    basic_prov.refresh_firmware_list = AsyncMock()

    # check when disabled
    basic_prov.disable()
    r = await basic_prov.get_image(key)
    assert r is None
    assert basic_prov.refresh_firmware_list.call_count == 0
    assert basic_prov._cache.__getitem__.call_count == 0
    assert image.fetch_image.call_count == 0

    # check with locked image
    basic_prov.enable()
    await basic_prov._locks[key].acquire()

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


def test_basic_enable_provider(key, basic_prov):
    assert basic_prov.is_enabled is True

    basic_prov.disable()
    assert basic_prov.is_enabled is False

    basic_prov.enable()
    assert basic_prov.is_enabled is True


async def test_basic_get_image_filtered(basic_prov, key):
    image = mock.MagicMock()  # noqa: F811
    image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    basic_prov._cache = mock.MagicMock()
    basic_prov._cache.__getitem__.return_value = image
    basic_prov.refresh_firmware_list = AsyncMock()
    basic_prov.filter_get_image = AsyncMock(return_value=True)

    r = await basic_prov.get_image(key)
    assert r is None
    assert basic_prov.filter_get_image.call_count == 1
    assert basic_prov.filter_get_image.call_args[0][0] == key
    assert basic_prov.refresh_firmware_list.call_count == 0
    assert basic_prov._cache.__getitem__.call_count == 0
    assert image.fetch_image.call_count == 0


async def test_ikea_init_ota_dir(ikea_prov, tmpdir):
    ikea_prov.enable = mock.MagicMock()
    ikea_prov.refresh_firmware_list = AsyncMock()

    r = await ikea_prov.initialize_provider({CONF_OTA_IKEA: True})
    assert r is None
    assert ikea_prov.enable.call_count == 1
    assert ikea_prov.refresh_firmware_list.call_count == 1


async def test_ikea_get_image_no_cache(ikea_prov, ikea_image):
    ikea_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    ikea_prov._cache = mock.MagicMock()
    ikea_prov._cache.__getitem__.side_effect = KeyError()
    ikea_prov.refresh_firmware_list = AsyncMock()

    non_ikea = zigpy.ota.image.ImageKey(mock.sentinel.manufacturer, IMAGE_TYPE)

    # Non IKEA manufacturer_id, don't bother doing anything at all
    r = await ikea_prov.get_image(non_ikea)
    assert r is None
    assert ikea_prov._cache.__getitem__.call_count == 0
    assert ikea_prov.refresh_firmware_list.call_count == 0
    assert non_ikea not in ikea_prov._cache

    # IKEA manufacturer_id, but not in cache
    assert ikea_image.key not in ikea_prov._cache
    r = await ikea_prov.get_image(ikea_image.key)
    assert r is None
    assert ikea_prov.refresh_firmware_list.call_count == 1
    assert ikea_prov._cache.__getitem__.call_count == 1
    assert ikea_image.fetch_image.call_count == 0


async def test_ikea_get_image(ikea_prov, key, ikea_image):
    ikea_image.fetch_image = AsyncMock(return_value=mock.sentinel.image)
    ikea_prov._cache = mock.MagicMock()
    ikea_prov._cache.__getitem__.return_value = ikea_image
    ikea_prov.refresh_firmware_list = AsyncMock()

    r = await ikea_prov.get_image(key)
    assert r is mock.sentinel.image
    assert ikea_prov._cache.__getitem__.call_count == 1
    assert ikea_prov._cache.__getitem__.call_args[0][0] == ikea_image.key
    assert ikea_image.fetch_image.call_count == 1


@patch("aiohttp.ClientSession.get")
async def test_ikea_refresh_list(mock_get, ikea_prov, ikea_image_with_version):
    ver1, img_type1 = (0x12345678, mock.sentinel.img_type_1)
    ver2, img_type2 = (0x23456789, mock.sentinel.img_type_2)
    img1 = ikea_image_with_version(version=ver1, image_type=img_type1)
    img2 = ikea_image_with_version(version=ver2, image_type=img_type2)

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
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
                    "fw_type": 2,
                },
                {
                    "fw_binary_url": "http://localhost/ota1.ota.signed",
                    "fw_file_version_MSB": img1.version >> 16,
                    "fw_file_version_LSB": img1.version & 0xFFFF,
                    "fw_filesize": 129,
                    "fw_image_type": img1.image_type,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_type": 2,
                },
                {
                    "fw_binary_url": "http://localhost/ota2.ota.signed",
                    "fw_file_version_MSB": img2.version >> 16,
                    "fw_file_version_LSB": img2.version & 0xFFFF,
                    "fw_filesize": 130,
                    "fw_image_type": img2.image_type,
                    "fw_manufacturer_id": MANUFACTURER_ID,
                    "fw_type": 2,
                },
            ]
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 202
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await ikea_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(ikea_prov._cache) == 2
    assert img1.key in ikea_prov._cache
    assert img2.key in ikea_prov._cache
    cached_1 = ikea_prov._cache[img1.key]
    assert cached_1.image_type == img1.image_type
    assert cached_1.url == "http://localhost/ota1.ota.signed"

    cached_2 = ikea_prov._cache[img2.key]
    assert cached_2.image_type == img2.image_type
    assert cached_2.url == "http://localhost/ota2.ota.signed"

    assert not ikea_prov.expired


@patch("aiohttp.ClientSession.get")
async def test_ikea_refresh_list_locked(mock_get, ikea_prov, ikea_image_with_version):
    await ikea_prov._locks[ota_p.LOCK_REFRESH].acquire()

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])
    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    await ikea_prov.refresh_firmware_list()
    assert mock_get.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_ikea_refresh_list_failed(mock_get, ikea_prov):

    mock_get.return_value.__aenter__.return_value.json = AsyncMock(side_effect=[[]])

    mock_get.return_value.__aenter__.return_value.status = 434
    mock_get.return_value.__aenter__.return_value.reason = "UNK"

    with patch.object(ikea_prov, "update_expiration") as update_exp:
        await ikea_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert update_exp.call_count == 0


@patch("aiohttp.ClientSession.get")
async def test_ikea_fetch_image(mock_get, ikea_image_with_version):
    data = bytes.fromhex(
        "1ef1ee0b0001380000007c11012178563412020054657374204f544120496d61"
        "676500000000000000000000000000000000000042000000"
    )
    sub_el = b"\x00\x00\x04\x00\x00\x00abcd"

    container = bytearray(b"\x00This is extra data\x00\x55\xaa" * 100)
    container[0:4] = b"NGIS"
    container[16:20] = (512).to_bytes(4, "little")  # offset
    container[20:24] = len(data + sub_el).to_bytes(4, "little")  # size
    container[512 : 512 + len(data) + len(sub_el)] = data + sub_el

    img = ikea_image_with_version(image_type=0x2101)
    img.url = mock.sentinel.url

    mock_get.return_value.__aenter__.return_value.read = AsyncMock(
        side_effect=[container]
    )

    r = await img.fetch_image()
    assert isinstance(r, zigpy.ota.image.OTAImage)
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == mock.sentinel.url
    assert r.serialize() == data + sub_el


def test_file_image_key(key):
    fimg = ota_p.FileImage()
    fimg.header.manufacturer_id = MANUFACTURER_ID
    fimg.header.image_type = IMAGE_TYPE
    fimg.header.file_version = mock.sentinel.version

    assert fimg.key == key
    assert fimg.version == mock.sentinel.version


def test_filestore_scan(file_image_name):
    file_name = file_image_name()
    r = ota_p.FileImage.scan_image(file_name)

    assert isinstance(r, ota_p.FileImage)
    assert r.file_name == file_name


def test_filestore_scan_exc(file_image_name):
    ota_file = file_image_name()
    with patch("builtins.open", mock.mock_open()) as mock_file:
        mock_file.side_effect = IOError()

        r = ota_p.FileImage.scan_image(ota_file)
        assert r is None
        assert mock_file.call_count == 1
        assert mock_file.call_args[0][0] == ota_file

    with patch("builtins.open", mock.mock_open()) as mock_file:
        mock_file.side_effect = ValueError()

        r = ota_p.FileImage.scan_image(ota_file)
        assert r is None
        assert mock_file.call_count == 1
        assert mock_file.call_args[0][0] == ota_file


def test_filestore_scan_uncaught_exc(file_image_name):
    ota_file = file_image_name()
    with pytest.raises(RuntimeError):
        with patch("builtins.open", mock.mock_open()) as mock_file:
            mock_file.side_effect = RuntimeError()

            ota_p.FileImage.scan_image(ota_file)
    assert mock_file.call_count == 1
    assert mock_file.call_args[0][0] == ota_file


async def test_filestore_fetch_image(file_image):
    r = await ota_p.FileImage.fetch_image(file_image)

    assert isinstance(r, zigpy.ota.image.OTAImage)


async def test_filestore_fetch_image_exc(file_image):
    with mock.patch("builtins.open", mock.mock_open()) as mock_file:
        mock_file.side_effect = IOError()

        r = await ota_p.FileImage.fetch_image(file_image)
        assert r is None
        assert mock_file.call_count == 1
        assert mock_file.call_args[0][0] == file_image.file_name

    with mock.patch("builtins.open", mock.mock_open()) as mock_file:
        mock_file.side_effect = ValueError()

        r = await ota_p.FileImage.fetch_image(file_image)
        assert r is None
        assert mock_file.call_count == 1
        assert mock_file.call_args[0][0] == file_image.file_name


async def test_filestore_fetch_uncaught_exc(file_image):
    with pytest.raises(RuntimeError):
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            mock_file.side_effect = RuntimeError()

            await ota_p.FileImage.fetch_image(file_image)
    assert mock_file.call_count == 1
    assert mock_file.call_args[0][0] == file_image.file_name


def test_filestore_validate_ota_dir(tmpdir):
    file_prov = ota_p.FileStore()

    assert file_prov.validate_ota_dir(None) is None

    tmpdir = str(tmpdir)
    assert file_prov.validate_ota_dir(tmpdir) == tmpdir

    # non existing dir
    non_existing = os.path.join(tmpdir, "non_existing")
    assert file_prov.validate_ota_dir(non_existing) is None

    # file instead of dir
    file_path = os.path.join(tmpdir, "file")
    with open(file_path, mode="w+"):
        pass
    assert file_prov.validate_ota_dir(file_path) is None


async def test_filestore_init_provider_success(file_prov):
    file_prov.enable = mock.MagicMock()
    file_prov.refresh_firmware_list = AsyncMock()
    file_prov.validate_ota_dir = mock.MagicMock(return_value=mock.sentinel.ota_dir)

    r = await file_prov.initialize_provider({CONF_OTA_DIR: mock.sentinel.ota_dir})
    assert r is None
    assert file_prov.validate_ota_dir.call_count == 1
    assert file_prov.validate_ota_dir.call_args[0][0] == mock.sentinel.ota_dir
    assert file_prov.enable.call_count == 1
    assert file_prov.refresh_firmware_list.call_count == 1


async def test_filestore_init_provider_failure(file_prov):
    file_prov.enable = mock.MagicMock()
    file_prov.refresh_firmware_list = AsyncMock()
    file_prov.validate_ota_dir = mock.MagicMock(return_value=None)

    r = await file_prov.initialize_provider({CONF_OTA_DIR: mock.sentinel.ota_dir})
    assert r is None
    assert file_prov.validate_ota_dir.call_count == 1
    assert file_prov.validate_ota_dir.call_args[0][0] == mock.sentinel.ota_dir
    assert file_prov.enable.call_count == 0
    assert file_prov.refresh_firmware_list.call_count == 0


async def test_filestore_refresh_firmware_list(
    file_prov, file_image_with_version, monkeypatch
):
    image_1 = file_image_with_version(image_type=mock.sentinel.image_1)
    image_2 = file_image_with_version(image_type=mock.sentinel.image_2)
    _ = file_image_with_version(image_type=mock.sentinel.image_3)
    images = (image_1, None, image_2)
    ota_dir = os.path.dirname(image_1.file_name)

    file_image_mock = mock.MagicMock()
    file_image_mock.scan_image.side_effect = images
    monkeypatch.setattr(ota_p, "FileImage", file_image_mock)
    file_prov.update_expiration = mock.MagicMock()

    r = await file_prov.refresh_firmware_list()
    assert r is None
    assert file_image_mock.scan_image.call_count == 0
    assert file_prov.update_expiration.call_count == 0
    assert len(file_prov._cache) == 0

    # check with an ota_dir this time
    file_prov._ota_dir = ota_dir
    for file in ota_p.SKIP_OTA_FILES:
        with open(os.path.join(ota_dir, file), mode="w+"):
            pass
    r = await file_prov.refresh_firmware_list()
    assert r is None
    assert file_image_mock.scan_image.call_count == len(images)
    assert file_prov.update_expiration.call_count == 1
    assert len(file_prov._cache) == len([img for img in images if img])


async def test_filestore_refresh_firmware_list_2(
    file_prov, file_image_with_version, monkeypatch
):
    """Test two files with same key and the same version."""
    ver = 100
    image_1 = file_image_with_version(version=ver)
    image_2 = file_image_with_version(version=ver)

    ota_dir = os.path.dirname(image_1.file_name)

    file_image_mock = mock.MagicMock()
    file_image_mock.scan_image.side_effect = [image_1, image_2]
    monkeypatch.setattr(ota_p, "FileImage", file_image_mock)
    file_prov.update_expiration = mock.MagicMock()

    file_prov._ota_dir = ota_dir
    r = await file_prov.refresh_firmware_list()
    assert r is None
    assert file_image_mock.scan_image.call_count == 2
    assert file_prov.update_expiration.call_count == 1
    assert len(file_prov._cache) == 1
    assert file_prov._cache[image_1.key].version == ver


async def test_filestore_refresh_firmware_list_3(
    file_prov, file_image_with_version, monkeypatch
):
    """Test two files with the same key, older, then newer versions."""
    ver = 100
    image_1 = file_image_with_version(version=(ver - 1))
    image_2 = file_image_with_version(version=ver)

    ota_dir = os.path.dirname(image_1.file_name)

    file_image_mock = mock.MagicMock()
    file_image_mock.scan_image.side_effect = [image_1, image_2]
    monkeypatch.setattr(ota_p, "FileImage", file_image_mock)
    file_prov.update_expiration = mock.MagicMock()

    file_prov._ota_dir = ota_dir
    r = await file_prov.refresh_firmware_list()
    assert r is None
    assert file_image_mock.scan_image.call_count == 2
    assert file_prov.update_expiration.call_count == 1
    assert len(file_prov._cache) == 1
    assert file_prov._cache[image_1.key].version == ver


async def test_filestore_refresh_firmware_list_4(
    file_prov, file_image_with_version, monkeypatch
):
    """Test two files with the same key, newer, then older versions."""
    ver = 100
    image_1 = file_image_with_version(version=ver)
    image_2 = file_image_with_version(version=(ver - 1))

    ota_dir = os.path.dirname(image_1.file_name)

    file_image_mock = mock.MagicMock()
    file_image_mock.scan_image.side_effect = [image_1, image_2]
    monkeypatch.setattr(ota_p, "FileImage", file_image_mock)
    file_prov.update_expiration = mock.MagicMock()

    file_prov._ota_dir = ota_dir
    r = await file_prov.refresh_firmware_list()
    assert r is None
    assert file_image_mock.scan_image.call_count == 2
    assert file_prov.update_expiration.call_count == 1
    assert len(file_prov._cache) == 1
    assert file_prov._cache[image_1.key].version == ver


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
