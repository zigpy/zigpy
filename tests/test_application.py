import asyncio

import pytest
import voluptuous as vol

from zigpy import device
import zigpy.application
import zigpy.application.state as app_state
from zigpy.config import (
    CONF_DATABASE,
    CONF_DEVICE,
    CONF_DEVICE_PATH,
    CONF_OTA,
    CONF_OTA_IKEA,
    ZIGPY_SCHEMA,
)
from zigpy.exceptions import DeliveryError
import zigpy.ota
import zigpy.quirks
import zigpy.types as t
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock, patch, sentinel

NCP_IEEE = t.EUI64.convert("aa:11:22:bb:33:44:be:ef")


@pytest.fixture
@patch("zigpy.ota.OTA", MagicMock(spec_set=zigpy.ota.OTA))
@patch("zigpy.device.Device._initialize", AsyncMock())
def app():
    class App(zigpy.application.ControllerApplication):
        async def shutdown(self):
            pass

        async def startup(self, auto_form=False):
            pass

        async def request(
            self,
            device,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=True,
            use_ieee=False,
        ):
            pass

        async def permit_ncp(self, time_s=60):
            pass

        async def probe(self, config):
            return True

    config = App.SCHEMA(
        {CONF_DATABASE: None, CONF_DEVICE: {CONF_DEVICE_PATH: "/dev/null"}}
    )
    app = App(config)
    app.state.node_information = app_state.NodeInfo(
        t.NWK(0x0000), ieee=NCP_IEEE, logical_type=zdo_t.LogicalType.Coordinator
    )
    return app


@pytest.fixture
def ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


async def test_startup():
    class App(zigpy.application.ControllerApplication):
        async def shutdown(self):
            pass

        async def request(
            self,
            device,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=True,
            use_ieee=False,
        ):
            pass

        async def permit_ncp(self, time_s=60):
            pass

    with pytest.raises(TypeError):
        await App({}).startup()


@patch("zigpy.ota.OTA", spec_set=zigpy.ota.OTA)
async def test_new_exception(ota_mock):
    class App(zigpy.application.ControllerApplication):
        async def shutdown(self):
            pass

        async def startup(self, auto_form=False):
            pass

        async def request(
            self,
            device,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=True,
            use_ieee=False,
        ):
            pass

        async def permit_ncp(self, time_s=60):
            pass

        async def probe(self, config):
            return True

    p1 = patch.object(App, "_load_db", AsyncMock())
    p2 = patch.object(App, "startup", AsyncMock())
    p3 = patch.object(App, "shutdown", AsyncMock())
    ota_mock.return_value.initialize = AsyncMock()

    with p1 as db_mck, p2 as start_mck, p3 as shut_mck:
        await App.new(ZIGPY_SCHEMA({CONF_DATABASE: "/dev/null"}))
    assert db_mck.call_count == 1
    assert db_mck.await_count == 1
    assert ota_mock.return_value.initialize.call_count == 1
    assert start_mck.call_count == 1
    assert start_mck.await_count == 1
    assert shut_mck.call_count == 0
    assert shut_mck.await_count == 0

    with p1 as db_mck, p2 as start_mck, p3 as shut_mck:
        start_mck.side_effect = asyncio.TimeoutError()
        with pytest.raises(asyncio.TimeoutError):
            await App.new(ZIGPY_SCHEMA({CONF_DATABASE: "/dev/null"}))
    assert db_mck.call_count == 2
    assert db_mck.await_count == 2
    assert ota_mock.return_value.initialize.call_count == 2
    assert start_mck.call_count == 2
    assert start_mck.await_count == 2
    assert shut_mck.call_count == 1
    assert shut_mck.await_count == 1


async def test_form_network(app):
    with pytest.raises(NotImplementedError):
        await app.form_network()


async def test_force_remove(app):
    with pytest.raises(NotImplementedError):
        await app.force_remove(None)


async def test_request():
    class App(zigpy.application.ControllerApplication):
        async def shutdown(self):
            pass

        async def startup(self, auto_form=False):
            pass

        async def permit_ncp(self, time_s=60):
            pass

    with pytest.raises(TypeError):
        await App({}).request(None, None, None, None, None, None, None)


async def test_permit_ncp():
    class App(zigpy.application.ControllerApplication):
        async def shutdown(self):
            pass

        async def startup(self, auto_form=False):
            pass

        async def request(
            self,
            device,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=True,
            use_ieee=False,
        ):
            pass

    with pytest.raises(TypeError):
        await App({}).permit_ncp()


async def test_permit(app, ieee):
    app.devices[ieee] = MagicMock()
    app.devices[ieee].zdo.permit = MagicMock(side_effect=asyncio.coroutine(MagicMock()))
    app.permit_ncp = AsyncMock()
    await app.permit(node=(1, 1, 1, 1, 1, 1, 1, 1))
    assert app.devices[ieee].zdo.permit.call_count == 0
    assert app.permit_ncp.call_count == 0
    await app.permit(node=ieee)
    assert app.devices[ieee].zdo.permit.call_count == 1
    assert app.permit_ncp.call_count == 0
    await app.permit(node=NCP_IEEE)
    assert app.devices[ieee].zdo.permit.call_count == 1
    assert app.permit_ncp.call_count == 1


async def test_permit_delivery_failure(app, ieee):
    from zigpy.exceptions import DeliveryError

    def zdo_permit(*args, **kwargs):
        raise DeliveryError

    app.devices[ieee] = MagicMock()
    app.devices[ieee].zdo.permit = zdo_permit
    app.permit_ncp = AsyncMock()
    await app.permit(node=ieee)
    assert app.permit_ncp.call_count == 0


async def test_permit_broadcast(app):
    app.broadcast = AsyncMock()
    app.permit_ncp = AsyncMock()
    await app.permit(time_s=30)
    assert app.broadcast.call_count == 1
    assert app.permit_ncp.call_count == 1


def test_permit_with_key(app):
    with pytest.raises(NotImplementedError):
        app.permit_with_key(None, None)


async def test_join_handler_skip(app, ieee):
    app.handle_join(1, ieee, None)
    app.devices[ieee].status = device.Status.ZDO_INIT
    app.handle_join(1, ieee, None)
    assert app.devices[ieee].status == device.Status.ZDO_INIT


async def test_join_handler_change_id(app, ieee):
    app.handle_join(1, ieee, None)
    app.handle_join(2, ieee, None)
    assert app.devices[ieee].nwk == 2


async def _remove(app, ieee, retval, zdo_reply=True, delivery_failure=True):
    async def leave():
        if zdo_reply:
            return retval
        elif delivery_failure:
            raise DeliveryError
        else:
            raise asyncio.TimeoutError

    device = MagicMock()
    device.ieee = ieee
    device.node_desc = zdo_t.NodeDescriptor(1, 64, 142, 4388, 82, 255, 0, 255, 0)
    device.zdo.leave.side_effect = leave

    app.devices[ieee] = device
    await app.remove(ieee)
    for i in range(1, 20):
        await asyncio.sleep(0)
    assert ieee not in app.devices


async def test_remove(app, ieee):
    """Test remove with successful zdo status."""

    with patch.object(app, "_remove_device", wraps=app._remove_device) as remove_device:
        await _remove(app, ieee, [0])
        assert remove_device.await_count == 1


async def test_remove_with_failed_zdo(app, ieee):
    """Test remove with unsuccessful zdo status."""

    with patch.object(app, "_remove_device", wraps=app._remove_device) as remove_device:
        await _remove(app, ieee, [1])
        assert remove_device.await_count == 1


async def test_remove_nonexistent(app, ieee):
    with patch.object(app, "_remove_device", AsyncMock()) as remove_device:
        await app.remove(ieee)
        for i in range(1, 20):
            await asyncio.sleep(0)
        assert ieee not in app.devices
        assert remove_device.await_count == 0


async def test_remove_with_unreachable_device(app, ieee):
    with patch.object(app, "_remove_device", wraps=app._remove_device) as remove_device:
        await _remove(app, ieee, [0], zdo_reply=False)
        assert remove_device.await_count == 1


async def test_remove_with_reply_timeout(app, ieee):
    with patch.object(app, "_remove_device", wraps=app._remove_device) as remove_device:
        await _remove(app, ieee, [0], zdo_reply=False, delivery_failure=False)
        assert remove_device.await_count == 1


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
    assert app.ieee


def test_nwk(app):
    assert app.nwk is not None


def test_config(app):
    assert app.config == app._config


def test_deserialize(app, ieee):
    dev = MagicMock()
    app.deserialize(dev, 1, 1, b"")
    assert dev.deserialize.call_count == 1


def test_handle_message(app, ieee):
    dev = MagicMock()
    app.handle_message(dev, 260, 1, 1, 1, [])
    assert dev.handle_message.call_count == 1


def test_handle_message_uninitialized_dev(app, ieee):
    dev = device.Device(app, ieee, 0x1234)
    dev.handle_message = MagicMock()
    app.handle_message(dev, 260, 1, 1, 1, [])
    assert dev.handle_message.call_count == 0

    dev.status = device.Status.ZDO_INIT
    app.handle_message(dev, 260, 1, 1, 1, [])
    assert dev.handle_message.call_count == 0

    app.handle_message(dev, 260, 0, 1, 1, [])
    assert dev.handle_message.call_count == 1


async def test_broadcast(app):
    from zigpy.profiles import zha

    with pytest.raises(NotImplementedError):
        (profile, cluster, src_ep, dst_ep, grp, radius, tsn, data) = (
            zha.PROFILE_ID,
            1,
            2,
            3,
            0,
            4,
            212,
            b"\x02\x01\x00",
        )
        await app.broadcast(
            app, profile, cluster, src_ep, dst_ep, grp, radius, tsn, data
        )


async def test_shutdown():
    class App(zigpy.application.ControllerApplication):
        async def startup(self, auto_form=False):
            pass

        async def request(
            self,
            device,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=True,
            use_ieee=False,
        ):
            pass

        async def permit_ncp(self, time_s=60):
            pass

    with pytest.raises(TypeError):
        await App({}).shutdown()


def test_get_dst_address(app):
    r = app.get_dst_address(MagicMock())
    assert r.addrmode == 3
    assert r.endpoint == 1


async def test_update_network(app):
    with pytest.raises(NotImplementedError):
        await app.update_network()


def test_props(app):
    assert app.channel is None
    assert app.channels is None
    assert app.extended_pan_id
    assert app.pan_id
    assert app.nwk_update_id is not None

    new_ieee = t.EUI64.convert("aa:22:11:22:11:22:33:44")
    app._ieee = new_ieee
    assert app.state.node_information.ieee == new_ieee

    app._nwk = 0x4321
    assert app.state.node_information.nwk == 0x4321


async def test_mrequest(app):
    s = sentinel
    with pytest.raises(NotImplementedError):
        await app.mrequest(
            s.group_id, s.profile_id, s.cluster, s.src_ep, s.sequence, s.data
        )


def test_app_config_setter(app):
    """Test configuration setter."""

    cfg_copy = app.config.copy()
    assert app.config[CONF_OTA][CONF_OTA_IKEA] is False
    with pytest.raises(vol.Invalid):
        cfg_copy[CONF_OTA][CONF_OTA_IKEA] = "invalid bool"
        app.config = cfg_copy
        assert app.config[CONF_OTA][CONF_OTA_IKEA] is False

    cfg_copy[CONF_OTA][CONF_OTA_IKEA] = True
    app.config = cfg_copy
    assert app.config[CONF_OTA][CONF_OTA_IKEA] is True

    with pytest.raises(vol.Invalid):
        cfg_copy[CONF_OTA][CONF_OTA_IKEA] = "invalid bool"
        app.config = cfg_copy
        assert app.config[CONF_OTA][CONF_OTA_IKEA] is True


def test_app_update_config(app):
    """Test configuration partial update."""

    assert app.config[CONF_OTA][CONF_OTA_IKEA] is False
    with pytest.raises(vol.Invalid):
        app.update_config({CONF_OTA: {CONF_OTA_IKEA: "invalid bool"}})
        assert app.config[CONF_OTA][CONF_OTA_IKEA] is False

    app.update_config({CONF_OTA: {CONF_OTA_IKEA: "yes"}})
    assert app.config[CONF_OTA][CONF_OTA_IKEA] is True

    with pytest.raises(vol.Invalid):
        app.update_config({CONF_OTA: {CONF_OTA_IKEA: "invalid bool"}})
        assert app.config[CONF_OTA][CONF_OTA_IKEA] is True


def test_uninitialized_message_handlers(app, ieee):
    """Test uninitialized message handlers."""
    handler_1 = MagicMock(return_value=None)
    handler_2 = MagicMock(return_value=True)

    zigpy.quirks.register_uninitialized_device_message_handler(handler_1)
    zigpy.quirks.register_uninitialized_device_message_handler(handler_2)

    device = app.add_device(ieee, 0x1234)

    app.handle_message(device, 0x0260, 0x0000, 0, 0, b"123abcd23")
    assert handler_1.call_count == 0
    assert handler_2.call_count == 0

    app.handle_message(device, 0x0260, 0x0000, 1, 1, b"123abcd23")
    assert handler_1.call_count == 1
    assert handler_2.call_count == 1

    handler_1.return_value = True
    app.handle_message(device, 0x0260, 0x0000, 1, 1, b"123abcd23")
    assert handler_1.call_count == 2
    assert handler_2.call_count == 1


def _devices(index):
    """Device factory."""

    start_ieee = 0xFEAB000000
    start_nwk = 0x1000

    dev = MagicMock()
    dev.ieee = zigpy.types.EUI64(zigpy.types.uint64_t(start_ieee + index).serialize())
    dev.nwk = zigpy.types.NWK(start_nwk + index)
    dev.neighbors = []
    dev.node_desc = zdo_t.NodeDescriptor(1, 64, 142, 4388, 82, 255, 0, 255, 0)
    dev.zdo = zigpy.zdo.ZDO(dev)
    return dev


async def test_remove_parent_devices(app):
    """Test removing an end device with parents."""

    end_device = _devices(1)
    end_device.node_desc.byte1 = 2
    nei_end_device = MagicMock()
    nei_end_device.device = end_device

    router_1 = _devices(2)
    nei_router_1 = MagicMock()
    nei_router_1.device = router_1

    router_2 = _devices(3)
    nei_router_2 = MagicMock()
    nei_router_2.device = router_2

    parent = _devices(4)
    nei_parent = MagicMock()
    nei_parent.device = router_1

    router_1.neighbors = [nei_router_2, nei_parent]
    router_2.neighbors = [nei_parent, nei_router_1]
    parent.neighbors = [nei_router_2, nei_router_1, nei_end_device]

    app.devices[end_device.ieee] = end_device
    app.devices[parent.ieee] = parent
    app.devices[router_1.ieee] = router_1
    app.devices[router_2.ieee] = router_2

    p1 = patch.object(end_device.zdo, "leave", AsyncMock())
    p2 = patch.object(end_device.zdo, "request", AsyncMock())
    p3 = patch.object(parent.zdo, "leave", AsyncMock())
    p4 = patch.object(parent.zdo, "request", AsyncMock())
    p5 = patch.object(router_1.zdo, "leave", AsyncMock())
    p6 = patch.object(router_1.zdo, "request", AsyncMock())
    p7 = patch.object(router_2.zdo, "leave", AsyncMock())
    p8 = patch.object(router_2.zdo, "request", AsyncMock())

    with p1, p2, p3, p4, p5, p6, p7, p8:
        await app.remove(end_device.ieee)
        for i in range(1, 60):
            await asyncio.sleep(0)

        assert end_device.zdo.leave.await_count == 1
        assert end_device.zdo.request.await_count == 0
        assert router_1.zdo.leave.await_count == 0
        assert router_1.zdo.request.await_count == 0
        assert router_2.zdo.leave.await_count == 0
        assert router_2.zdo.request.await_count == 0
        assert parent.zdo.leave.await_count == 0
        assert parent.zdo.request.await_count == 1
