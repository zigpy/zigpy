import asyncio
from unittest import mock

import pytest

import zigpy.types as t
import zigpy.device
import zigpy.zdo as zdo


def test_commands():
    for cmdid, cmdspec in zdo.types.CLUSTERS.items():
        assert 0 <= cmdid <= 0xffff
        assert isinstance(cmdspec, tuple)
        assert isinstance(cmdspec[0], str)
        for paramname, paramtype in zip(cmdspec[1], cmdspec[2]):
            assert isinstance(paramname, str)
            assert hasattr(paramtype, 'serialize')
            assert hasattr(paramtype, 'deserialize')


@pytest.fixture
def app():
    app = mock.MagicMock()
    app.ieee = t.EUI64(map(t.uint8_t, [8, 9, 10, 11, 12, 13, 14, 15]))
    app.get_sequence.return_value = 123
    app.request.side_effect = asyncio.coroutine(mock.MagicMock())
    return app


@pytest.fixture
def zdo_f(app):
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    dev = zigpy.device.Device(app, ieee, 65535)
    return zdo.ZDO(dev)


def test_deserialize(zdo_f):
    tsn, command_id, is_reply, args = zdo_f.deserialize(2, b'\x01\x02\x03xx')
    assert tsn == 1
    assert is_reply is False
    assert args == [0x0302]


def test_deserialize_unknown(zdo_f):
    tsn, command_id, is_reply, args = zdo_f.deserialize(0x0100, b'\x01')
    assert tsn == 1
    assert is_reply is False


@pytest.mark.asyncio
async def test_request(zdo_f):
    await zdo_f.request(2, 65535)
    app_mock = zdo_f._device._application
    assert app_mock.request.call_count == 1
    assert app_mock.get_sequence.call_count == 1


@pytest.mark.asyncio
async def test_bind(zdo_f):
    await zdo_f.bind(1, 1026)
    app_mock = zdo_f._device._application
    assert app_mock.request.call_count == 1
    assert app_mock.request.call_args[0][2] == 0x0021


@pytest.mark.asyncio
async def test_unbind(zdo_f):
    await zdo_f.unbind(1, 1026)
    app_mock = zdo_f._device._application
    assert app_mock.request.call_count == 1
    assert app_mock.request.call_args[0][2] == 0x0022


@pytest.mark.asyncio
async def test_leave(zdo_f):
    await zdo_f.leave()
    app_mock = zdo_f._device._application
    assert app_mock.request.call_count == 1
    assert app_mock.request.call_args[0][2] == 0x0034


@pytest.mark.asyncio
async def test_permit(zdo_f):
    await zdo_f.permit()
    app_mock = zdo_f._device._application
    assert app_mock.request.call_count == 1
    assert app_mock.request.call_args[0][2] == 0x0036


def test_broadcast(app):
    zigpy.device.broadcast = mock.MagicMock()
    zigpy.zdo.broadcast(app, 0x0036, 0, 0, 60, 0)

    assert zigpy.device.broadcast.call_count == 1
    assert zigpy.device.broadcast.call_args[0][2] == 0x0036


def _handle_match_desc(zdo_f, profile):
    zdo_f.reply = mock.MagicMock()
    zdo_f.handle_message(False, 5, 0x0006, 123, 0x0006, [None, profile, [], []])
    assert zdo_f.reply.call_count == 1


def test_handle_match_desc_zha(zdo_f):
    return _handle_match_desc(zdo_f, 260)


def test_handle_match_desc_generic(zdo_f):
    return _handle_match_desc(zdo_f, 0)


def test_unexpected_reply(zdo_f):
    zdo_f.handle_message(True, 5, 4, 3, 2, [])


def test_handle_nwk_addr(zdo_f):
    ieee = zdo_f._device.application.ieee
    zdo_f.reply = mock.MagicMock()
    zdo_f.handle_message(False, 5, 0x0000, 234, 0x0000, [ieee])
    assert zdo_f.reply.call_count == 1


def test_handle_ieee_addr(zdo_f):
    nwk = zdo_f._device.application.nwk
    zdo_f.reply = mock.MagicMock()
    zdo_f.handle_message(False, 5, 0x0001, 234, 0x0001, [nwk])
    assert zdo_f.reply.call_count == 1


def test_handle_announce(zdo_f):
    dev = zdo_f._device
    zdo_f.listener_event = mock.MagicMock()
    dev._application.devices.pop(dev.ieee)
    zdo_f.handle_message(False, 5, 0x0013, 111, 0x0013, [0, dev.ieee, dev.nwk])
    assert zdo_f.listener_event.call_count == 1


def test_handle_permit_join(zdo_f):
    zdo_f.listener_event = mock.MagicMock()
    zdo_f.handle_message(False, 5, 0x0036, 111, 0x0036, [100, 1])
    assert zdo_f.listener_event.call_count == 1


def test_handle_unsupported(zdo_f):
    zdo_f.handle_message(False, 5, 0xffff, 321, 0xffff, [])


def test_device_accessor(zdo_f):
    assert zdo_f.device.nwk == 65535


@pytest.mark.asyncio
async def test_reply(zdo_f):
    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1

    zdo_f.device._application.request = mock_request
    zdo_f.reply(0x0005)
    await asyncio.sleep(0)
    assert call_count == 1
