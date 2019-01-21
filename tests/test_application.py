import asyncio
from unittest import mock

import pytest

from zigpy.application import ControllerApplication
from zigpy.exceptions import DeliveryError
from zigpy import device
import zigpy.types as t


@pytest.fixture
def app():
    return ControllerApplication()


@pytest.fixture
def ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


@pytest.mark.asyncio
async def test_startup(app):
    with pytest.raises(NotImplementedError):
        await app.startup()


@pytest.mark.asyncio
async def test_form_network(app):
    with pytest.raises(NotImplementedError):
        await app.form_network()


@pytest.mark.asyncio
async def test_force_remove(app):
    with pytest.raises(NotImplementedError):
        await app.force_remove(None)


@pytest.mark.asyncio
async def test_request(app):
    with pytest.raises(NotImplementedError):
        await app.request(None, None, None, None, None, None, None)


@pytest.mark.asyncio
async def test_permit_ncp(app):
    with pytest.raises(NotImplementedError):
        await app.permit_ncp()


@pytest.mark.asyncio
async def test_permit(app, ieee):
    ncp_ieee = t.EUI64(map(t.uint8_t, range(8, 16)))
    app._ieee = ncp_ieee
    app.devices[ieee] = mock.MagicMock()
    app.devices[ieee].zdo.permit = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    app.permit_ncp = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    await app.permit(node=(1, 1, 1, 1, 1, 1, 1, 1))
    assert app.devices[ieee].zdo.permit.call_count == 0
    assert app.permit_ncp.call_count == 0
    await app.permit(node=ieee)
    assert app.devices[ieee].zdo.permit.call_count == 1
    assert app.permit_ncp.call_count == 0
    await app.permit(node=ncp_ieee)
    assert app.devices[ieee].zdo.permit.call_count == 1
    assert app.permit_ncp.call_count == 1


@pytest.mark.asyncio
async def test_permit_delivery_failure(app, ieee):
    from zigpy.exceptions import DeliveryError

    def zdo_permit(*args, **kwargs):
        raise DeliveryError

    app.devices[ieee] = mock.MagicMock()
    app.devices[ieee].zdo.permit = zdo_permit
    app.permit_ncp = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    await app.permit(node=ieee)
    assert app.permit_ncp.call_count == 0


@pytest.mark.asyncio
async def test_permit_broadcast(app):
    app.broadcast = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    app.permit_ncp = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    await app.permit(time_s=30)
    assert app.broadcast.call_count == 1
    assert app.permit_ncp.call_count == 1


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


async def _remove(app, ieee, retval, zdo_reply=True):
    app.devices[ieee] = mock.MagicMock()

    async def leave():
        if zdo_reply:
            return retval
        else:
            raise DeliveryError

    app.devices[ieee].zdo.leave.side_effect = leave
    await app.remove(ieee)
    assert ieee not in app.devices


@pytest.mark.asyncio
async def test_remove(app, ieee):
    app.force_remove = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    await _remove(app, ieee, [0])
    assert app.force_remove.call_count == 0


@pytest.mark.asyncio
async def test_remove_with_failed_zdo(app, ieee):
    app.force_remove = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    await _remove(app, ieee, [1])
    assert app.force_remove.call_count == 1


@pytest.mark.asyncio
async def test_remove_nonexistent(app, ieee):
    await app.remove(ieee)
    assert ieee not in app.devices


@pytest.mark.asyncio
async def test_remove_with_unreachable_device(app, ieee):
    app.force_remove = mock.MagicMock(side_effect=asyncio.coroutine(mock.MagicMock()))
    await _remove(app, ieee, [0], zdo_reply=False)
    assert app.force_remove.call_count == 1


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


def test_deserialize(app, ieee):
    dev = mock.MagicMock()
    app.deserialize(dev, 1, 1, b'')
    assert dev.deserialize.call_count == 1


def test_handle_message(app, ieee):
    dev = mock.MagicMock()
    app.handle_message(dev, False, 260, 1, 1, 1, 1, 1, [])
    assert dev.handle_message.call_count == 1


@pytest.mark.asyncio
async def test_broadcast(app):
    from zigpy.profiles import zha
    with pytest.raises(NotImplementedError):
        (profile, cluster, src_ep, dst_ep, grp, radius, tsn, data) = (
            zha.PROFILE_ID, 1, 2, 3, 0, 4, 212, b'\x02\x01\x00'
        )
        await app.broadcast(app, profile, cluster, src_ep, dst_ep,
                            grp, radius, tsn, data)
