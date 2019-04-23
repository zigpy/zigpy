import asyncio
from unittest import mock

import pytest

import zigpy.types as t
from zigpy.application import ControllerApplication
from zigpy import device, endpoint
from zigpy.zdo import types as zdo_t


@pytest.fixture
def dev():
    app_mock = mock.MagicMock(spec_set=ControllerApplication)
    app_mock.remove.side_effect = asyncio.coroutine(mock.MagicMock())
    app_mock.request.side_effect = asyncio.coroutine(mock.MagicMock())
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    return device.Device(app_mock, ieee, 65535)


@pytest.mark.asyncio
async def test_initialize(monkeypatch, dev):
    async def mockrequest(nwk, tries=None, delay=None):
        return [0, None, [1, 2]]

    async def mockepinit(self):
        self.status = endpoint.Status.ZDO_INIT
        return

    monkeypatch.setattr(endpoint.Endpoint, 'initialize', mockepinit)
    gnd = asyncio.coroutine(mock.MagicMock())
    dev.get_node_descriptor = mock.MagicMock(side_effect=gnd)

    dev.zdo.Active_EP_req = mockrequest
    await dev._initialize()

    assert dev.status > device.Status.NEW
    assert 1 in dev.endpoints
    assert 2 in dev.endpoints
    assert dev._application.device_initialized.call_count == 1


@pytest.mark.asyncio
async def test_initialize_fail(dev):
    async def mockrequest(nwk, tries=None, delay=None):
        return [1]

    dev.zdo.Active_EP_req = mockrequest
    gnd = asyncio.coroutine(mock.MagicMock())
    dev.get_node_descriptor = mock.MagicMock(side_effect=gnd)
    await dev._initialize()

    assert dev.status == device.Status.NEW


@pytest.mark.asyncio
async def test_initialize_ep_failed(monkeypatch, dev):
    async def mockrequest(req, nwk, tries=None, delay=None):
        return [0, None, [1, 2]]

    async def mockepinit(self):
        raise AttributeError

    monkeypatch.setattr(endpoint.Endpoint, 'initialize', mockepinit)

    dev.zdo.request = mockrequest
    await dev._initialize()

    assert dev.status == device.Status.ZDO_INIT
    assert dev.application.listener_event.call_count == 1
    assert dev.application.listener_event.call_args[0][0] == 'device_init_failure'
    assert dev.application.remove.call_count == 1


@pytest.mark.asyncio
async def test_request(dev):
    assert dev.last_seen is None
    await dev.request(1, 2, 3, 3, 4, b'')
    assert dev._application.request.call_count == 1
    assert dev._application.get_sequence.call_count == 0
    assert dev.last_seen is not None


@pytest.mark.asyncio
async def test_failed_request(dev):
    assert dev.last_seen is None
    dev._application.request.side_effect = Exception
    with pytest.raises(Exception):
        await dev.request(1, 2, 3, 4, b'')
    assert dev.last_seen is None


def test_radio_details(dev):
    dev.radio_details(1, 2)
    assert dev.lqi == 1
    assert dev.rssi == 2


def test_deserialize(dev):
    ep = dev.add_endpoint(3)
    ep.deserialize = mock.MagicMock()
    dev.deserialize(3, 1, b'')
    assert ep.deserialize.call_count == 1


def test_handle_message_no_endpoint(dev):
    dev.handle_message(False, 99, 98, 97, 97, 1, 0, [])


def test_handle_message(dev):
    ep = dev.add_endpoint(3)
    ep.handle_message = mock.MagicMock()
    dev.handle_message(False, 99, 98, 3, 3, 1, 0, [])
    assert ep.handle_message.call_count == 1


def test_endpoint_getitem(dev):
    ep = dev.add_endpoint(3)
    assert dev[3] is ep

    with pytest.raises(KeyError):
        dev[1]


@pytest.mark.asyncio
async def test_broadcast():
    from zigpy.profiles import zha

    app = mock.MagicMock()
    app.broadcast.side_effect = asyncio.coroutine(mock.MagicMock())
    app.ieee = t.EUI64(map(t.uint8_t, [8, 9, 10, 11, 12, 13, 14, 15]))

    (profile, cluster, src_ep, dst_ep, data) = (
        zha.PROFILE_ID, 1, 2, 3, b'\x02\x01\x00'
    )
    await device.broadcast(app, profile, cluster, src_ep, dst_ep, 0, 0, 123, data)

    assert app.broadcast.call_count == 1
    assert app.broadcast.call_args[0][0] == profile
    assert app.broadcast.call_args[0][1] == cluster
    assert app.broadcast.call_args[0][2] == src_ep
    assert app.broadcast.call_args[0][3] == dst_ep
    assert app.broadcast.call_args[0][7] == data


async def _get_node_descriptor(dev, zdo_success=True, request_success=True):
    async def mockrequest(nwk, tries=None, delay=None):
        if not request_success:
            raise asyncio.TimeoutError

        status = 0 if zdo_success else 1
        return [status, nwk,
                zdo_t.NodeDescriptor.deserialize(b'abcdefghijklm')[0]]

    dev.zdo.Node_Desc_req = mock.MagicMock(side_effect=mockrequest)
    return await dev.get_node_descriptor()


@pytest.mark.asyncio
async def test_get_node_descriptor(dev):
    nd = await _get_node_descriptor(dev, zdo_success=True,
                                    request_success=True)

    assert nd is not None
    assert isinstance(nd, zdo_t.NodeDescriptor)
    assert dev.zdo.Node_Desc_req.call_count == 1


@pytest.mark.asyncio
async def test_get_node_descriptor_no_reply(dev):
    nd = await _get_node_descriptor(dev, zdo_success=True,
                                    request_success=False)

    assert nd is None
    assert dev.zdo.Node_Desc_req.call_count == 1


@pytest.mark.asyncio
async def test_get_node_descriptor_fail(dev):
    nd = await _get_node_descriptor(dev, zdo_success=False,
                                    request_success=True)

    assert nd is None
    assert dev.zdo.Node_Desc_req.call_count == 1
