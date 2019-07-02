import asyncio
import datetime
from unittest import mock

import pytest

import zigpy.application
import zigpy.ota
import zigpy.ota.image
import zigpy.ota.provider

MANUFACTURER_ID = mock.sentinel.manufacturer_id
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def image_with_version():
    def img(version=100):
        img = zigpy.ota.image.OTAImage()
        img.header.manufacturer_id = MANUFACTURER_ID
        img.header.image_type = IMAGE_TYPE
        img.header.file_version = version
        img.subelements.append(
            zigpy.ota.image.SubElement.deserialize(
                b'\x00\x00\x04\x00\x00\x00abcdef')[0])
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
    app = mock.MagicMock(spec_set=zigpy.application.ControllerApplication)
    tradfri = mock.MagicMock(spec_set=zigpy.ota.provider.Trådfri)
    with mock.patch('zigpy.ota.provider.Trådfri', tradfri):
        return zigpy.ota.OTA(app)


@pytest.mark.asyncio
async def test_ota_initialize(ota):
    init_mock = mock.MagicMock()
    init_mock.side_effect = asyncio.coroutine(mock.MagicMock())
    ota.listener_event = mock.MagicMock(return_value=[init_mock()])
    await ota._initialize()

    assert ota.listener_event.call_count == 1
    assert ota.listener_event.call_args[0][0] == 'initialize_provider'
    assert init_mock.call_count == 1


@pytest.mark.asyncio
async def test_refresh_firmware(ota):
    handler_mock = mock.MagicMock()
    handler_mock.side_effect = asyncio.coroutine(mock.MagicMock())
    ota.listener_event = mock.MagicMock(return_value=[handler_mock()])
    await ota.refresh_firmwares()

    assert ota.listener_event.call_count == 1
    assert ota.listener_event.call_args[0][0] == 'refresh_firmwares'
    assert handler_mock.call_count == 1


def test_initialize(ota):
    ota._initialize = mock.MagicMock()
    ota._initialize.side_effect = asyncio.coroutine(mock.MagicMock())

    assert ota.not_initialized
    ota.initialize()
    assert not ota.not_initialized
    assert ota._initialize.call_count == 1


@pytest.mark.asyncio
async def test_get_image_empty(ota, image, key):
    def handler_mock(*args, **kwargs):
        result = [None, None, None]

        async def get_image(idx):
            return result[idx]

        return [get_image(0), get_image(1), get_image(2)]

    ota.listener_event = mock.MagicMock(side_effect=handler_mock)

    assert len(ota._image_cache) == 0
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._image_cache) == 0
    assert res is None
    assert ota.listener_event.call_count == 1
    assert ota.listener_event.call_args[0][0] == 'get_image'
    assert ota.listener_event.call_args[0][1] == key


@pytest.mark.asyncio
async def test_get_image_new(ota,
                             image,
                             key,
                             image_with_version,
                             monkeypatch):
    newer = image_with_version(image.version + 1)

    def handler_mock(*args, **kwargs):
        result = [None, image, newer]

        async def get_image(idx):
            return result[idx]

        return [get_image(0), get_image(1), get_image(2)]

    ota.listener_event = mock.MagicMock(side_effect=handler_mock)

    assert len(ota._image_cache) == 0
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    # got new image in the cache
    assert len(ota._image_cache) == 1
    assert res.header == newer.header
    assert res.subelements == newer.subelements
    assert ota.listener_event.call_count == 1
    assert ota.listener_event.call_args[0][0] == 'get_image'
    assert ota.listener_event.call_args[0][1] == key

    ota.listener_event.reset_mock()
    assert len(ota._image_cache) == 1
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    # should get just the cached image
    assert len(ota._image_cache) == 1
    assert res.header == newer.header
    assert res.subelements == newer.subelements
    assert ota.listener_event.call_count == 0

    # on cache expiration, ping listeners
    ota.listener_event.reset_mock()
    delta = datetime.timedelta(seconds=-1)
    monkeypatch.setattr(ota._image_cache[key], 'DEFAULT_EXPIRATION', delta)
    assert len(ota._image_cache) == 1
    res = await ota.get_ota_image(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._image_cache) == 1
    assert res.header == newer.header
    assert res.subelements == newer.subelements
    assert ota.listener_event.call_count == 1


def test_cached_image_expiration(image, monkeypatch):
    delta = datetime.timedelta(seconds=-1)

    cached = zigpy.ota.CachedImage.new(image)
    monkeypatch.setattr(cached, 'DEFAULT_EXPIRATION', delta)
    assert cached.expired is True

    cached = zigpy.ota.CachedImage()
    monkeypatch.setattr(cached, 'DEFAULT_EXPIRATION', delta)
    assert cached.expired is False

    cached = zigpy.ota.CachedImage.new(image)
    assert cached.expired is False


def test_cached_image_expiration_delay():
    d = b'\x1e\xf1\xee\x0b\x00\x018\x00'
    d += b'\x00\x00'
    d += b'|\x11\x01!rE!\x12\x02\x00EBL tradfri_light_basic\x00\x00\x00' \
         b'\x00\x00\x00\x00\x00\x00\x38\x00\x00\x00'

    img = zigpy.ota.image.OTAImage.deserialize(d)[0]
    cached = zigpy.ota.CachedImage.new(img)
    orig_expiration = cached.expires_on

    cached.get_image_block(0, 40)
    assert cached.expires_on > orig_expiration
