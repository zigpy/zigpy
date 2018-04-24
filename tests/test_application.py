import asyncio
from unittest import mock

import pytest

from zigpy.application import ControllerApplication
from zigpy import device
import zigpy.types as t


@pytest.fixture
def app():
    return ControllerApplication()


@pytest.fixture
def ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


def test_startup(app):
    with pytest.raises(NotImplementedError):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.startup())


def test_form_network(app):
    with pytest.raises(NotImplementedError):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.form_network())


def test_force_remove(app):
    with pytest.raises(NotImplementedError):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.force_remove(None))


def test_request(app):
    with pytest.raises(NotImplementedError):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.request(None, None, None, None, None, None, None))


def test_permit(app):
    with pytest.raises(NotImplementedError):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.permit())


def test_permit_with_key(app):
    with pytest.raises(NotImplementedError):
        app.permit_with_key(None, None)


def test_join_handler_skip(app, ieee):
    app.handle_join(1, ieee, None)
    app.devices[ieee].status = device.Status.ZDO_INIT
    app.handle_join(1, ieee, None)
    assert app.devices[ieee].status == device.Status.ZDO_INIT


def test_join_handler_change_id(app, ieee):
    app.handle_join(1, ieee, None)
    app.handle_join(2, ieee, None)
    assert app.devices[ieee].nwk == 2


def _remove(app, ieee, retval):
    app.devices[ieee] = mock.MagicMock()

    async def leave():
        return retval

    app.devices[ieee].zdo.leave.side_effect = leave
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.remove(ieee))
    assert ieee not in app.devices


def test_remove(app, ieee):
    app.force_remove = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    _remove(app, ieee, [0])
    assert app.force_remove.call_count == 0


def test_remove_with_failed_zdo(app, ieee):
    app.force_remove = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    _remove(app, ieee, 1)
    assert app.force_remove.call_count == 1


def test_remove_nonexistent(app, ieee):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.remove(ieee))
    assert ieee not in app.devices


def test_add_device(app, ieee):
    app.add_device(ieee, 8)
    app.add_device(ieee, 9)
    assert app.get_device(ieee).nwk == 9


def test_get_device_nwk(app, ieee):
    dev = app.add_device(ieee, 8)
    assert app.get_device(nwk=8) is dev


def test_get_device_ieee(app, ieee):
    dev = app.add_device(ieee, 8)
    assert app.get_device(ieee=ieee) is dev


def test_get_device_both(app, ieee):
    dev = app.add_device(ieee, 8)
    assert app.get_device(ieee=ieee, nwk=8) is dev


def test_get_device_missing(app, ieee):
    with pytest.raises(KeyError):
        app.get_device(nwk=8)


def test_ieee(app):
    assert app.ieee == app._ieee


def test_nwk(app):
    assert app.nwk == app._nwk


def test_handle_message(app, ieee):
    dev = app.devices[ieee] = mock.MagicMock()
    dev.nwk = 8
    app.handle_message(False, 8, 260, 1, 1, 1, 1, 1, [])
    assert dev.handle_message.call_count == 1


def test_handle_message_unknown(app, ieee):
    app.handle_message(False, 8, 260, 1, 1, 1, 1, 1, [])
