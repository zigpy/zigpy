import hashlib
import os.path
from unittest import mock
import uuid

import pytest

from zigpy.config import CONF_OTA_DIR, CONF_OTA_IKEA
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider as ota_p

from .async_mock import AsyncMock, patch
from .test_ota_image import image  # noqa: F401

MANUFACTURER_ID = 4476
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def file_image_name(tmp_path, image):  # noqa: F811
    def ota_img_filename(name="ota-image"):
        image_file = tmp_path / (name + "-" + str(uuid.uuid4()))
        image_file.write_bytes(image.serialize())

        return str(image_file)

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
    def img(image_type=IMAGE_TYPE):
        img = zigpy.ota.provider.IKEAImage(
            image_type=image_type,
            binary_url=mock.sentinel.url,
            sha3_256_sum=mock.sentinel.sha3_256_sum,
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


async def test_ikea_init_ota_dir(ikea_prov):
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

    non_ikea = zigpy.ota.image.ImageKey(
        ota_p.Trådfri.MANUFACTURER_ID + 1,
        IMAGE_TYPE,
    )

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
async def test_ikea_refresh_list(mock_get, ikea_prov):
    mock_get.return_value.__aenter__.return_value.json = AsyncMock(
        side_effect=[
            [
                {
                    "fw_image_type": 4557,
                    "fw_type": 2,
                    "fw_sha3_256": "896edfb0a9d8314fb49d44fb11dc91fb5bb55e2ee1f793d53189cb13f884e13c",
                    "fw_binary_url": "https://fw.ota.homesmart.ikea.com/files/rodret-dimmer-soc_release_prod_v16777287_9812b73c-b02e-4678-b737-d21251a34fd2.ota",
                },
                {
                    "fw_update_prio": 5,
                    "fw_filesize": 242071587,
                    "fw_type": 3,
                    "fw_hotfix_version": 1,
                    "fw_major_version": 2,
                    "fw_binary_checksum": "8c17b203bede63ea53e36d345b628cc7f2faecc18d4406458a12f8f25e54718a24495d30a03fe3244799bfaa50de72d99e6c0d2f7553a8465e37c10c22ba75fc",
                    "fw_minor_version": 453,
                    "fw_sha3_256": "657ed8fd0f6e5e6700acdc6afd64829cebacb1dd03b3f5453258b4bd77b674ed",
                    "fw_binary_url": "https://fw.ota.homesmart.ikea.com/files/DIRIGERA_release_prod_v2.453.1_348f0dce-3c34-49a2-b64c-a1caa202104c.raucb",
                },
                {
                    "fw_image_type": 4552,
                    "fw_type": 2,
                    "fw_sha3_256": "1b5fbea79c5b41864352a938a90ad25d9a0118054bf1cdc0314ef9636a60143a",
                    "fw_binary_url": "https://fw.ota.homesmart.ikea.com/files/tradfri-motion-sensor2_release_prod_v604241925_8afa2f7c-19c3-4ddf-a96c-233714179022.ota",
                },
            ]
        ]
    )
    mock_get.return_value.__aenter__.return_value.status = 200
    mock_get.return_value.__aenter__.return_value.reason = "OK"

    await ikea_prov.refresh_firmware_list()
    assert mock_get.call_count == 1
    assert len(ikea_prov._cache) == 2

    image1 = ikea_prov._cache[
        zigpy.ota.image.ImageKey(ota_p.Trådfri.MANUFACTURER_ID, 4557)
    ]
    image2 = ikea_prov._cache[
        zigpy.ota.image.ImageKey(ota_p.Trådfri.MANUFACTURER_ID, 4552)
    ]

    assert image1 == ota_p.IKEAImage(
        image_type=4557,
        binary_url="https://fw.ota.homesmart.ikea.com/files/rodret-dimmer-soc_release_prod_v16777287_9812b73c-b02e-4678-b737-d21251a34fd2.ota",
        sha3_256_sum="896edfb0a9d8314fb49d44fb11dc91fb5bb55e2ee1f793d53189cb13f884e13c",
    )

    assert image1.version == 16777287

    assert image2 == ota_p.IKEAImage(
        image_type=4552,
        binary_url="https://fw.ota.homesmart.ikea.com/files/tradfri-motion-sensor2_release_prod_v604241925_8afa2f7c-19c3-4ddf-a96c-233714179022.ota",
        sha3_256_sum="1b5fbea79c5b41864352a938a90ad25d9a0118054bf1cdc0314ef9636a60143a",
    )
    assert image2.version == 604241925

    assert not ikea_prov.expired


def test_ikea_bad_version():
    image = ota_p.IKEAImage(
        image_type=4552,
        binary_url="https://fw.ota.homesmart.ikea.com/files/DIRIGERA_release_prod_v2.453.1_348f0dce-3c34-49a2-b64c-a1caa202104c.raucb",
        sha3_256_sum="1b5fbea79c5b41864352a938a90ad25d9a0118054bf1cdc0314ef9636a60143a",
    )

    with pytest.raises(ValueError):
        image.version


@patch("aiohttp.ClientSession.get")
async def test_ikea_refresh_list_locked(mock_get, ikea_prov):
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
    img.sha3_256_sum = hashlib.sha3_256(container).hexdigest()

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
        mock_file.side_effect = OSError()

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
        mock_file.side_effect = OSError()

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


def test_filestore_validate_ota_dir(tmp_path):
    file_prov = ota_p.FileStore()

    assert file_prov.validate_ota_dir(None) is None
    assert file_prov.validate_ota_dir(str(tmp_path)) == str(tmp_path)

    # non existing dir
    non_existing = tmp_path / "non_existing"
    assert file_prov.validate_ota_dir(str(non_existing)) is None

    # file instead of dir
    file_path = tmp_path / "file"
    file_path.touch()

    assert file_prov.validate_ota_dir(str(file_path)) is None


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
