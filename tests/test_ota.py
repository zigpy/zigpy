import asyncio
from unittest import mock

import pytest

import zigpy.application
import zigpy.ota
import zigpy.ota.firmware
import zigpy.ota.provider

MANUFACTURER_ID = mock.sentinel.manufacturer_id
IMAGE_TYPE = mock.sentinel.image_type


@pytest.fixture
def firmware(key):
    data = b'abcdef'
    return zigpy.ota.firmware.Firmware(key, 100, len(data), '', data)


@pytest.fixture
def key():
    return zigpy.ota.firmware.FirmwareKey(MANUFACTURER_ID, IMAGE_TYPE)


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


def test_get_firmware_empty(ota, firmware, key):
    handler_mock = mock.MagicMock(return_value=[None])
    ota.listener_event = mock.MagicMock(side_effect=handler_mock)

    assert len(ota._firmwares) == 0
    res = ota.get_firmware(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._firmwares) == 0
    assert res is None
    assert ota.listener_event.call_count == 1
    assert ota.listener_event.call_args[0][0] == 'get_firmware'
    assert ota.listener_event.call_args[0][1] == key


def test_get_firmware_new(ota, firmware, key):
    new_data = b'new_firmware_2'
    newer = zigpy.ota.firmware.Firmware(key, firmware.version + 1,
                                        len(new_data), '', new_data)

    handler_mock = mock.MagicMock(return_value=[None, firmware, newer])
    ota.listener_event = mock.MagicMock(side_effect=handler_mock)

    assert len(ota._firmwares) == 0
    res = ota.get_firmware(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._firmwares) == 1
    assert res is newer
    assert ota.listener_event.call_count == 1
    assert ota.listener_event.call_args[0][0] == 'get_firmware'
    assert ota.listener_event.call_args[0][1] == key

    ota.listener_event.reset_mock()
    assert len(ota._firmwares) == 1
    res = ota.get_firmware(MANUFACTURER_ID, IMAGE_TYPE)

    assert len(ota._firmwares) == 1
    assert res is newer
    assert ota.listener_event.call_count == 0
