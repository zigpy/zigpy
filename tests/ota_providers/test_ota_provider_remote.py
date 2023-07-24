import hashlib
import logging
from unittest import mock

import pytest

import zigpy.ota
import zigpy.ota.image
from zigpy.ota.provider import RemoteImage, RemoteProvider

from tests.async_mock import AsyncMock
from tests.conftest import make_app

MANUFACTURER_ID_1 = 0x1234
MANUFACTURER_ID_2 = 0x5678
IMAGE_TYPE = 0xABCD


@pytest.fixture
def provider():
    p = RemoteProvider(
        url="https://example.org/ota/",
        manufacturer_ids=[MANUFACTURER_ID_1, MANUFACTURER_ID_2],
    )
    p.enable()
    return p


@pytest.fixture
def ota_image():
    img = zigpy.ota.image.OTAImage()
    img.header = zigpy.ota.image.OTAImageHeader(
        upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
        header_version=256,
        header_length=56 + 2 + 2,
        field_control=zigpy.ota.image.FieldControl.HARDWARE_VERSIONS_PRESENT,
        manufacturer_id=MANUFACTURER_ID_2,
        image_type=IMAGE_TYPE,
        file_version=100,
        stack_version=2,
        header_string="This is a test header!",
        image_size=56 + 2 + 4 + 4 + 2 + 2,
        minimum_hardware_version=1,
        maximum_hardware_version=3,
    )
    img.subelements = [zigpy.ota.image.SubElement(tag_id=0x0000, data=b"data")]

    return img


@pytest.fixture
def image_json(ota_image):
    return {
        "binary_url": "https://example.org/ota/image1.ota",
        "file_version": ota_image.header.file_version,
        "image_type": ota_image.header.image_type,
        "manufacturer_id": ota_image.header.manufacturer_id,
        "changelog": "A changelog would go here.",
        "checksum": f"sha3-256:{hashlib.sha3_256(ota_image.serialize()).hexdigest()}",
        "min_hardware_version": ota_image.header.minimum_hardware_version,
        "max_hardware_version": ota_image.header.maximum_hardware_version,
        "min_current_file_version": 1,
        "max_current_file_version": 99,
    }


@mock.patch("aiohttp.ClientSession.get")
async def test_remote_image(mock_get, image_json, ota_image, provider, caplog):
    image = RemoteImage.from_json(image_json)

    assert image.key == zigpy.ota.image.ImageKey(
        image.manufacturer_id,
        image.image_type,
    )

    # Test unsuccessful download
    rsp = mock_get.return_value.__aenter__.return_value
    rsp.status = 404

    with caplog.at_level(logging.WARNING):
        await provider.initialize_provider({})

    assert "Couldn't download" in caplog.text
    caplog.clear()

    # Test successful download
    rsp.status = 200
    rsp.json = AsyncMock(return_value=[image_json])
    rsp.read = AsyncMock(return_value=ota_image.serialize())
    await provider.initialize_provider({})

    new_image = await provider.get_image(image.key)
    assert new_image == ota_image


@mock.patch("aiohttp.ClientSession.get")
async def test_remote_image_bad_checksum(mock_get, image_json, ota_image, provider):
    image = RemoteImage.from_json(image_json)

    # Corrupt the checksum
    image_json["checksum"] = f"sha3-256:{hashlib.sha3_256(b'').hexdigest()}"

    # Test "successful" download
    rsp = mock_get.return_value.__aenter__.return_value
    rsp.status = 200
    rsp.json = AsyncMock(return_value=[image_json])
    rsp.read = AsyncMock(return_value=ota_image.serialize())
    await provider.initialize_provider({})

    # The image will fail to download
    with pytest.raises(ValueError) as exc:
        await provider.get_image(image.key)

    assert "Image checksum is invalid" in str(exc.value)


async def test_get_image_with_no_manufacturer_ids(ota_image, provider):
    provider.manufacturer_ids = None

    missing_key = zigpy.ota.image.ImageKey(
        ota_image.header.manufacturer_id + 1,
        ota_image.header.image_type + 1,
    )

    assert await provider.filter_get_image(missing_key) is False


async def test_provider_initialization():
    app = make_app(
        {
            "ota": {
                "remote_providers": [
                    {
                        "url": "https://fw.zigbee.example.org/ota.json",
                        "manufacturer_ids": [4660, 22136],
                    },
                    {
                        "url": "https://fw.zigbee.example.org/ota-beta.json",
                    },
                ]
            }
        }
    )

    listeners, _ = zip(*app._ota._listeners.values())

    assert listeners[0].url == "https://fw.zigbee.example.org/ota.json"
    assert listeners[0].manufacturer_ids == [4660, 22136]

    assert listeners[1].url == "https://fw.zigbee.example.org/ota-beta.json"
    assert listeners[1].manufacturer_ids == []
