from unittest import mock

import pytest

import zigpy.types as t
from zigpy import device, endpoint


@pytest.fixture
def dev():
    app_mock = mock.MagicMock()
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    return device.Device(app_mock, ieee, 65535)


@pytest.mark.asyncio
async def test_initialize(monkeypatch, dev):
    async def mockrequest(req, nwk, tries=None, delay=None):
        return [0, None, [1, 2]]

    async def mockepinit(self):
        return

    monkeypatch.setattr(endpoint.Endpoint, 'initialize', mockepinit)

    dev.zdo.request = mockrequest
    await dev._initialize()

    assert dev.status > device.Status.NEW
    assert 1 in dev.endpoints
    assert 2 in dev.endpoints


@pytest.mark.asyncio
async def test_initialize_fail(dev):
    async def mockrequest(req, nwk, tries=None, delay=None):
        return [1]

    dev.zdo.request = mockrequest
    await dev._initialize()

    assert dev.status == device.Status.NEW


def test_request(dev):
    dev.request(1, 2, 3, 3, 4, b'')
    app_mock = dev._application
    assert app_mock.request.call_count == 1
    assert app_mock.get_sequence.call_count == 0


def test_radio_details(dev):
    dev.radio_details(1, 2)
    assert dev.lqi == 1
    assert dev.rssi == 2


def test_handle_request_no_endpoint(dev):
    dev.handle_message(False, 99, 98, 97, 97, 1, 0, [])


def test_handle_request(dev):
    ep = dev.add_endpoint(3)
    ep.handle_message = mock.MagicMock()
    dev.handle_message(False, 99, 98, 3, 3, 1, 0, [])
    assert ep.handle_message.call_count == 1


def test_endpoint_getitem(dev):
    ep = dev.add_endpoint(3)
    assert dev[3] is ep

    with pytest.raises(KeyError):
        dev[1]
