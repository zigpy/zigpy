import binascii
import os.path
from unittest import mock
import uuid

import pytest

from zigpy.config import CONF_OTA_DIR, CONF_OTA_IKEA, CONF_OTA_LEDVANCE
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from .async_mock import AsyncMock, patch

MANUFACTURER_ID = 4476
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def file_image_name(tmpdir):
    def ota_img_filename(name="ota-image"):
        prefix = b"\x00This is extra data\x00\x55\xaa"
        data = (
            "1ef1ee0b0001380000007c11012178563412020054657374204f54412049"
            "6d61676500000000000000000000000000000000000042000000"
        )
        data = binascii.unhexlify(data)
        sub_el = b"\x00\x00\x04\x00\x00\x00abcd"

        file_name = os.path.join(str(tmpdir), name + "-" + str(uuid.uuid4()))
        with open(os.path.join(file_name), mode="bw+") as file:
            file.write(prefix + data + sub_el)
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
    image = mock.MagicMock()
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
    image = mock.MagicMock()
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
                            "version": {"major": 1, "minor": 2, "build": 428},
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
                            "version": {"major": 1, "minor": 2, "build": 428},
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
    assert cached_1.url == base + "?Company=4489&Product=25&Version=1.2.428"

    cached_2 = ledvance_prov._cache[img2.key]
    assert cached_2.image_type == img2.image_type
    assert cached_2.url == base + "?Company=4489&Product=13&Version=1.2.428"

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
