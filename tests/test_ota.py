import datetime

import pytest

import zigpy.application
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider
import zigpy.ota.validators

from .async_mock import AsyncMock, MagicMock, patch, sentinel

MANUFACTURER_ID = sentinel.manufacturer_id
IMAGE_TYPE = sentinel.image_type


@pytest.fixture
def image_with_version():
    def img(version=100):
        img = zigpy.ota.image.OTAImage()
        img.header = zigpy.ota.image.OTAImageHeader()
        img.header.manufacturer_id = MANUFACTURER_ID
        img.header.image_type = IMAGE_TYPE
        img.header.file_version = version
        img.subelements = [
            zigpy.ota.image.SubElement.deserialize(b"\x00\x00\x04\x00\x00\x00abcdef")[0]
        ]
        return img

    return img


@pytest.fixture
def image(image_with_version):
    return image_with_version()


@pytest.fixture
def key():
    return zigpy.ota.image.ImageKey(MANUFACTURER_ID, IMAGE_TYPE)


@pytest.fixture
def ota():
    app = MagicMock(spec_set=zigpy.application.ControllerApplication)
    tradfri = MagicMock(spec_set=zigpy.ota.provider.Trådfri)
    check_invalid = MagicMock(
        spec_set=zigpy.ota.validators.check_invalid,
        return_value=False,
    )

    with patch("zigpy.ota.provider.Trådfri", tradfri):
        with patch("zigpy.ota.check_invalid", check_invalid):
            yield zigpy.ota.OTA(app)


async def test_ota_initialize(ota):
    ota.async_event = AsyncMock()
    await ota.initialize()

    assert ota.async_event.call_count == 1
    assert ota.async_event.call_args[0][0] == "initialize_provider"
    assert ota.not_initialized is False


async def test_get_image_empty(ota, image, key):
    ota.async_event = AsyncMock(return_value=[None, None])

    assert len(ota._image_cache) == 0
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._image_cache) == 0
    assert res is None
    assert ota.async_event.call_count == 1
    assert ota.async_event.call_args[0][0] == "get_image"
    assert ota.async_event.call_args[0][1] == key


async def test_get_image_new(ota, image, key, image_with_version, monkeypatch):
    newer = image_with_version(image.header.file_version + 1)

    ota.async_event = AsyncMock(return_value=[None, image, newer])

    assert len(ota._image_cache) == 0
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    # got new image in the cache
    assert len(ota._image_cache) == 1
    assert res.image.header == newer.header
    assert res.image.subelements == newer.subelements
    assert ota.async_event.call_count == 1
    assert ota.async_event.call_args[0][0] == "get_image"
    assert ota.async_event.call_args[0][1] == key

    ota.async_event.reset_mock()
    assert len(ota._image_cache) == 1
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    # should get just the cached image
    assert len(ota._image_cache) == 1
    assert res.image.header == newer.header
    assert res.image.subelements == newer.subelements
    assert ota.async_event.call_count == 0

    # on cache expiration, ping listeners
    ota.async_event.reset_mock()
    assert len(ota._image_cache) == 1

    monkeypatch.setattr(
        zigpy.ota,
        "TIMEDELTA_0",
        zigpy.ota.CachedImage.DEFAULT_EXPIRATION + datetime.timedelta(seconds=1),
    )
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._image_cache) == 1
    assert res.image.header == newer.header
    assert res.image.subelements == newer.subelements
    assert ota.async_event.call_count == 1


async def test_get_image_invalid(ota, image, image_with_version):
    corrupted = image_with_version(image.header.file_version)

    zigpy.ota.check_invalid.side_effect = [True]
    ota.async_event = AsyncMock(return_value=[None, corrupted])

    assert len(ota._image_cache) == 0
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)
    assert len(ota._image_cache) == 0

    assert res is None


@pytest.mark.parametrize("v1", [0, 1])
@pytest.mark.parametrize("v2", [0, 1])
async def test_get_image_invalid_then_valid_versions(v1, v2, ota, image_with_version):
    image = image_with_version(100 + v1)
    image.header.header_string = b"\x12" * 32

    corrupted = image_with_version(100 + v2)
    corrupted.header.header_string = b"\x11" * 32

    ota.async_event = AsyncMock(return_value=[corrupted, image])
    zigpy.ota.check_invalid.side_effect = [True, False]

    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    # The valid image is always picked, even if the versions match
    assert res.image.header.header_string == image.header.header_string


def test_cached_image_expiration(image, monkeypatch):
    cached = zigpy.ota.CachedImage.new(image)
    assert cached.expired is False

    monkeypatch.setattr(
        zigpy.ota,
        "TIMEDELTA_0",
        zigpy.ota.CachedImage.DEFAULT_EXPIRATION + datetime.timedelta(seconds=1),
    )
    assert cached.expired is True


def test_cached_image_no_expiration(image, monkeypatch):
    cached = zigpy.ota.CachedImage()
    monkeypatch.setattr(
        zigpy.ota,
        "TIMEDELTA_0",
        zigpy.ota.CachedImage.DEFAULT_EXPIRATION + datetime.timedelta(seconds=1),
    )
    assert cached.expired is False


def test_cached_image_expiration_delay():
    d = b"\x1e\xf1\xee\x0b\x00\x018\x00"
    d += b"\x00\x00"
    d += (
        b"|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x38\x00\x00\x00"
    )

    img = zigpy.ota.image.OTAImage.deserialize(d)[0]
    cached = zigpy.ota.CachedImage.new(img)
    orig_expiration = cached.expires_on

    cached.get_image_block(0, 40)
    assert cached.expires_on == orig_expiration

    new_expiration = (
        cached.expires_on
        - zigpy.ota.CachedImage.DEFAULT_EXPIRATION
        + zigpy.ota.DELAY_EXPIRATION
        - datetime.timedelta(seconds=10)
    )

    cached.expires_on = new_expiration
    cached.get_image_block(0, 40)
    assert cached.expires_on > new_expiration


def test_cached_image_serialization_cache(image):
    image = MagicMock(image)
    image.serialize.side_effect = [b"data"]

    cached = zigpy.ota.CachedImage.new(image)
    assert cached.cached_data is None
    assert image.serialize.call_count == 0

    assert cached.get_image_block(0, 1) == b"d"
    assert cached.get_image_block(1, 1) == b"a"
    assert cached.get_image_block(2, 1) == b"t"

    assert image.serialize.call_count == 1


async def test_get_image_salus(ota, image, image_with_version):
    SALUS_ID = 4216
    newer = image_with_version(image.header.file_version + 1)

    ota.async_event = AsyncMock(return_value=[None, image, newer])

    assert len(ota._image_cache) == 0
    await ota.get_ota_image(SALUS_ID, "model123")

    # got new image in the cache
    assert len(ota._image_cache) == 1
