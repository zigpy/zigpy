import asyncio
import logging
from unittest.mock import ANY, PropertyMock

import pytest
import voluptuous as vol

import zigpy.application
import zigpy.config as conf
from zigpy.exceptions import (
    DeliveryError,
    NetworkNotFormed,
    NetworkSettingsInconsistent,
)
import zigpy.ota
import zigpy.quirks
import zigpy.state as app_state
import zigpy.types as t
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock, patch, sentinel
from .conftest import App

NCP_IEEE = t.EUI64.convert("aa:11:22:bb:33:44:be:ef")


@pytest.fixture
@patch("zigpy.ota.OTA", MagicMock(spec_set=zigpy.ota.OTA))
@patch("zigpy.device.Device._initialize", AsyncMock())
def app_factory():
    def app(extra_config={}, app_base=App):
        config = {
            conf.CONF_DATABASE: None,
            conf.CONF_DEVICE: {conf.CONF_DEVICE_PATH: "/dev/null"},
        }
        config.update(extra_config)

        app = app_base(config)
        app.state.node_info = app_state.NodeInfo(
            nwk=t.NWK(0x0000), ieee=NCP_IEEE, logical_type=zdo_t.LogicalType.Coordinator
        )
        return app

    return app


@pytest.fixture
def app(app_factory):
    return app_factory({})


@pytest.fixture
def ieee(init=0):
    return t.EUI64(map(t.uint8_t, range(init, init + 8)))


@patch("zigpy.ota.OTA", spec_set=zigpy.ota.OTA)
async def test_new_exception(ota_mock):
    p1 = patch.object(App, "_load_db", AsyncMock())
    p2 = patch.object(App, "load_network_info", AsyncMock())
    p3 = patch.object(App, "shutdown", AsyncMock())
    ota_mock.return_value.initialize = AsyncMock()

    with p1 as db_mck, p2 as load_nwk_info_mck, p3 as shut_mck:
        await App.new(
            {
                conf.CONF_DATABASE: "/dev/null",
                conf.CONF_DEVICE: {conf.CONF_DEVICE_PATH: "/dev/null"},
            }
        )
    assert db_mck.call_count == 1
    assert db_mck.await_count == 1
    assert ota_mock.return_value.initialize.call_count == 1
    assert load_nwk_info_mck.call_count == 1
    assert load_nwk_info_mck.await_count == 1
    assert shut_mck.call_count == 0
    assert shut_mck.await_count == 0

    with p1 as db_mck, p2 as load_nwk_info_mck, p3 as shut_mck:
        load_nwk_info_mck.side_effect = asyncio.TimeoutError()
        with pytest.raises(asyncio.TimeoutError):
            await App.new(
                {
                    conf.CONF_DATABASE: "/dev/null",
                    conf.CONF_DEVICE: {conf.CONF_DEVICE_PATH: "/dev/null"},
                }
            )
    assert db_mck.call_count == 2
    assert db_mck.await_count == 2
    assert ota_mock.return_value.initialize.call_count == 2
    assert load_nwk_info_mck.call_count == 2
    assert load_nwk_info_mck.await_count == 2
    assert shut_mck.call_count == 1
    assert shut_mck.await_count == 1


async def test_permit(app, ieee):
    app.devices[ieee] = MagicMock()
    app.devices[ieee].zdo.permit = AsyncMock()
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
    def zdo_permit(*args, **kwargs):
        raise DeliveryError("Failed")

    app.devices[ieee] = MagicMock()
    app.devices[ieee].zdo.permit = zdo_permit
    app.permit_ncp = AsyncMock()
    await app.permit(node=ieee)
    assert app.permit_ncp.call_count == 0


async def test_permit_broadcast(app):
    app.permit_ncp = AsyncMock()
    app.send_packet = AsyncMock()
    await app.permit(time_s=30)
    assert app.send_packet.call_count == 1
    assert app.permit_ncp.call_count == 1

    assert app.send_packet.mock_calls[0].args[0].dst.addr_mode == t.AddrMode.Broadcast


@patch("zigpy.device.Device.initialize", new_callable=AsyncMock)
async def test_join_handler_skip(init_mock, app, ieee):
    app.handle_join(1, ieee, None)
    app.get_device(ieee).node_desc = _devices(1).node_desc

    app.handle_join(1, ieee, None)
    assert app.get_device(ieee).node_desc == _devices(1).node_desc


async def test_join_handler_change_id(app, ieee):
    app.handle_join(1, ieee, None)
    app.handle_join(2, ieee, None)
    assert app.devices[ieee].nwk == 2


async def test_unknown_device_left(app, ieee):
    with patch.object(app, "listener_event", wraps=app.listener_event):
        app.handle_leave(0x1234, ieee)
        app.listener_event.assert_not_called()


async def test_known_device_left(app, ieee):
    dev = app.add_device(ieee, 0x1234)

    with patch.object(app, "listener_event", wraps=app.listener_event):
        app.handle_leave(0x1234, ieee)
        app.listener_event.assert_called_once_with("device_left", dev)


async def _remove(
    app, ieee, retval, zdo_reply=True, delivery_failure=True, has_node_desc=True
):
    async def leave(*args, **kwargs):
        if zdo_reply:
            return retval
        elif delivery_failure:
            raise DeliveryError("Error")
        else:
            raise asyncio.TimeoutError

    device = MagicMock()
    device.ieee = ieee
    device.zdo.leave.side_effect = leave

    if has_node_desc:
        device.node_desc = zdo_t.NodeDescriptor(1, 64, 142, 4388, 82, 255, 0, 255, 0)
    else:
        device.node_desc = None

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


async def test_remove_without_node_desc(app, ieee):
    with patch.object(app, "_remove_device", wraps=app._remove_device) as remove_device:
        await _remove(app, ieee, [0], has_node_desc=False)
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


def test_device_property(app):
    app.add_device(nwk=0x0000, ieee=NCP_IEEE)
    assert app._device is app.get_device(ieee=NCP_IEEE)


def test_ieee(app):
    assert app.state.node_info.ieee


def test_nwk(app):
    assert app.state.node_info.nwk is not None


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


@patch("zigpy.device.Device.is_initialized", new_callable=PropertyMock)
@patch("zigpy.quirks.handle_message_from_uninitialized_sender", new=MagicMock())
async def test_handle_message_uninitialized_dev(is_init_mock, app, ieee):
    dev = app.add_device(ieee, 0x1234)
    dev.handle_message = MagicMock()
    is_init_mock.return_value = False

    assert not dev.initializing

    # Power Configuration cluster not allowed, no endpoints
    app.handle_message(dev, 260, cluster=0x0001, src_ep=1, dst_ep=1, message=b"")
    assert dev.handle_message.call_count == 0
    assert zigpy.quirks.handle_message_from_uninitialized_sender.call_count == 1

    # Device should be completing initialization
    assert dev.initializing

    # ZDO is allowed
    app.handle_message(dev, 260, cluster=0x0000, src_ep=0, dst_ep=0, message=b"")
    assert dev.handle_message.call_count == 1

    # Endpoint is uninitialized but Basic attribute read responses still work
    ep = dev.add_endpoint(1)
    app.handle_message(dev, 260, cluster=0x0000, src_ep=1, dst_ep=1, message=b"")
    assert dev.handle_message.call_count == 2

    # Others still do not
    app.handle_message(dev, 260, cluster=0x0001, src_ep=1, dst_ep=1, message=b"")
    assert dev.handle_message.call_count == 2
    assert zigpy.quirks.handle_message_from_uninitialized_sender.call_count == 2

    # They work after the endpoint is initialized
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    app.handle_message(dev, 260, cluster=0x0001, src_ep=1, dst_ep=1, message=b"")
    assert dev.handle_message.call_count == 3
    assert zigpy.quirks.handle_message_from_uninitialized_sender.call_count == 2


def test_get_dst_address(app):
    r = app.get_dst_address(MagicMock())
    assert r.addrmode == 3
    assert r.endpoint == 1


def test_props(app):
    assert app.state.network_info.channel is not None
    assert app.state.network_info.channel_mask is not None
    assert app.state.network_info.extended_pan_id is not None
    assert app.state.network_info.pan_id is not None
    assert app.state.network_info.nwk_update_id is not None


def test_app_config_setter(app):
    """Test configuration setter."""

    cfg_copy = app.config.copy()
    assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is False
    with pytest.raises(vol.Invalid):
        cfg_copy[conf.CONF_OTA][conf.CONF_OTA_IKEA] = "invalid bool"
        app.config = cfg_copy
        assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is False

    cfg_copy[conf.CONF_OTA][conf.CONF_OTA_IKEA] = True
    app.config = cfg_copy
    assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is True

    with pytest.raises(vol.Invalid):
        cfg_copy[conf.CONF_OTA][conf.CONF_OTA_IKEA] = "invalid bool"
        app.config = cfg_copy
        assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is True


def test_app_update_config(app):
    """Test configuration partial update."""

    assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is False
    with pytest.raises(vol.Invalid):
        app.update_config({conf.CONF_OTA: {conf.CONF_OTA_IKEA: "invalid bool"}})
        assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is False

    app.update_config({conf.CONF_OTA: {conf.CONF_OTA_IKEA: "yes"}})
    assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is True

    with pytest.raises(vol.Invalid):
        app.update_config({conf.CONF_OTA: {conf.CONF_OTA_IKEA: "invalid bool"}})
        assert app.config[conf.CONF_OTA][conf.CONF_OTA_IKEA] is True


async def test_uninitialized_message_handlers(app, ieee):
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
    end_device.node_desc.logical_type = zdo_t.LogicalType.EndDevice
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


async def test_startup_log_on_uninitialized_device(ieee, caplog):
    class TestApp(App):
        async def _load_db(self):
            dev = self.add_device(ieee, 1)
            assert not dev.is_initialized

    caplog.set_level(logging.WARNING)

    await TestApp.new(
        {
            conf.CONF_DATABASE: "/dev/null",
            conf.CONF_DEVICE: {conf.CONF_DEVICE_PATH: "/dev/null"},
        }
    )
    assert "Device is partially initialized" in caplog.text


@patch("zigpy.device.Device.schedule_initialize", new_callable=MagicMock)
@patch("zigpy.device.Device.schedule_group_membership_scan", new_callable=MagicMock)
@patch("zigpy.device.Device.is_initialized", new_callable=PropertyMock)
async def test_device_join_rejoin(is_init_mock, group_scan_mock, init_mock, app, ieee):
    app.listener_event = MagicMock()
    is_init_mock.return_value = False

    # First join is treated as a new join
    app.handle_join(0x0001, ieee, None)
    app.listener_event.assert_called_once_with("device_joined", ANY)
    app.listener_event.reset_mock()
    init_mock.assert_called_once()
    init_mock.reset_mock()

    # Second join with the same NWK is just a reset, not a join
    app.handle_join(0x0001, ieee, None)
    app.listener_event.assert_not_called()
    group_scan_mock.assert_not_called()

    # Since the device is still partially initialized, re-initialize it
    init_mock.assert_called_once()
    init_mock.reset_mock()

    # Another join with the same NWK but initialized will trigger a group re-scan
    is_init_mock.return_value = True

    app.handle_join(0x0001, ieee, None)
    is_init_mock.return_value = True
    app.listener_event.assert_not_called()
    group_scan_mock.assert_called_once()
    group_scan_mock.reset_mock()
    init_mock.assert_not_called()

    # Join with a different NWK but the same IEEE is a re-join
    app.handle_join(0x0002, ieee, None)
    app.listener_event.assert_called_once_with("device_joined", ANY)
    group_scan_mock.assert_not_called()
    init_mock.assert_called_once()


async def test_get_device(app):
    """Test get_device."""

    await app.startup()

    app.add_device(t.EUI64.convert("11:11:11:11:22:22:22:22"), 0x0000)
    dev_2 = app.add_device(app.state.node_info.ieee, 0x0000)
    app.add_device(t.EUI64.convert("11:11:11:11:22:22:22:33"), 0x0000)

    assert app.get_device(nwk=0x0000) is dev_2


async def test_probe_success():
    config = {"path": "/dev/test"}

    with patch.object(App, "connect") as connect, patch.object(
        App, "disconnect"
    ) as disconnect:
        result = await App.probe(config)

    assert result == config

    assert connect.await_count == 1
    assert disconnect.await_count == 1


async def test_probe_failure():
    config = {"path": "/dev/test"}

    with patch.object(
        App, "connect", side_effect=asyncio.TimeoutError
    ) as connect, patch.object(App, "disconnect") as disconnect:
        result = await App.probe(config)

    assert result is False

    assert connect.await_count == 1
    assert disconnect.await_count == 1


async def test_form_network(app):
    with patch.object(app, "write_network_info") as write1:
        await app.form_network()

    with patch.object(app, "write_network_info") as write2:
        await app.form_network()

    nwk_info1 = write1.mock_calls[0].kwargs["network_info"]
    node_info1 = write1.mock_calls[0].kwargs["node_info"]

    nwk_info2 = write2.mock_calls[0].kwargs["network_info"]
    node_info2 = write2.mock_calls[0].kwargs["node_info"]

    assert node_info1 == node_info2

    # Critical network settings are randomized
    assert nwk_info1.extended_pan_id != nwk_info2.extended_pan_id
    assert nwk_info1.pan_id != nwk_info2.pan_id
    assert nwk_info1.network_key != nwk_info2.network_key

    # The well-known TCLK is used
    assert (
        nwk_info1.tc_link_key.key
        == nwk_info2.tc_link_key.key
        == t.KeyData(b"ZigBeeAlliance09")
    )

    assert nwk_info1.channel == 15


async def test_startup_formed(app):
    app.start_network = AsyncMock()
    app.form_network = AsyncMock()
    app.permit = AsyncMock()

    await app.startup(auto_form=False)

    assert app.start_network.await_count == 1
    assert app.form_network.await_count == 0
    assert app.permit.await_count == 1


async def test_startup_not_formed(app):
    app.start_network = AsyncMock()
    app.form_network = AsyncMock()
    app.load_network_info = AsyncMock(
        side_effect=[NetworkNotFormed(), NetworkNotFormed(), None]
    )
    app.permit = AsyncMock()

    app.backups.backups = []
    app.backups.restore_backup = AsyncMock()

    with pytest.raises(NetworkNotFormed):
        await app.startup(auto_form=False)

    assert app.start_network.await_count == 0
    assert app.form_network.await_count == 0
    assert app.permit.await_count == 0

    await app.startup(auto_form=True)

    assert app.start_network.await_count == 1
    assert app.form_network.await_count == 1
    assert app.permit.await_count == 1
    assert app.backups.restore_backup.await_count == 0


async def test_startup_not_formed_with_backup(app):
    app.start_network = AsyncMock()
    app.load_network_info = AsyncMock(side_effect=[NetworkNotFormed(), None])
    app.permit = AsyncMock()

    app.backups.restore_backup = AsyncMock()
    app.backups.backups = [sentinel.OLD_BACKUP, sentinel.NEW_BACKUP]

    await app.startup(auto_form=True)

    assert app.start_network.await_count == 1
    app.backups.restore_backup.assert_called_once_with(sentinel.NEW_BACKUP)


async def test_deprecated_properties_and_methods(app):
    with pytest.deprecated_call():
        assert app.state.network_information is app.state.network_info

    with pytest.deprecated_call():
        assert app.state.node_information is app.state.node_info

    app.shutdown = AsyncMock()
    app.state = MagicMock()

    with pytest.deprecated_call():
        await app.pre_shutdown()

    assert app.shutdown.await_count == 1

    with pytest.deprecated_call():
        assert app.nwk is app.state.node_info.nwk

    with pytest.deprecated_call():
        assert app.ieee is app.state.node_info.ieee

    with pytest.deprecated_call():
        assert app.pan_id is app.state.network_info.pan_id

    with pytest.deprecated_call():
        assert app.extended_pan_id is app.state.network_info.extended_pan_id

    with pytest.deprecated_call():
        assert app.network_key is app.state.network_info.network_key

    with pytest.deprecated_call():
        assert app.channel is app.state.network_info.channel

    with pytest.deprecated_call():
        assert app.channels is app.state.network_info.channel_mask

    with pytest.deprecated_call():
        assert app.nwk_update_id is app.state.network_info.nwk_update_id


async def test_startup_backup(app_factory):
    app = app_factory({conf.CONF_NWK_BACKUP_ENABLED: True})

    with patch("zigpy.backups.BackupManager.start_periodic_backups") as p:
        await app.startup()

    p.assert_called_once()


async def test_startup_no_backup(app_factory):
    app = app_factory({conf.CONF_NWK_BACKUP_ENABLED: False})

    with patch("zigpy.backups.BackupManager.start_periodic_backups") as p:
        await app.startup()

    p.assert_not_called()


@patch("zigpy.backups.BackupManager.from_network_state")
@patch("zigpy.backups.BackupManager.most_recent_backup")
async def test_initialize_compatible_backup(
    mock_most_recent_backup, mock_backup_from_state, app_factory
):
    app = app_factory({conf.CONF_NWK_VALIDATE_SETTINGS: True})
    mock_backup_from_state.return_value.is_compatible_with.return_value = True

    await app.initialize()

    mock_backup_from_state.return_value.is_compatible_with.assert_called_once()
    mock_most_recent_backup.assert_called_once()


@patch("zigpy.backups.BackupManager.from_network_state")
@patch("zigpy.backups.BackupManager.most_recent_backup")
async def test_initialize_incompatible_backup(
    mock_most_recent_backup, mock_backup_from_state, app_factory
):
    app = app_factory({conf.CONF_NWK_VALIDATE_SETTINGS: True})
    mock_backup_from_state.return_value.is_compatible_with.return_value = False

    with pytest.raises(NetworkSettingsInconsistent):
        await app.initialize()

    mock_backup_from_state.return_value.is_compatible_with.assert_called_once()
    mock_most_recent_backup.assert_called_once()


async def test_relays_received_device_exists(app):
    device = MagicMock()

    app._discover_unknown_device = AsyncMock(spec_set=app._discover_unknown_device)
    app.get_device = MagicMock(spec_set=app.get_device, return_value=device)
    app.handle_relays(nwk=0x1234, relays=[0x5678, 0xABCD])

    app.get_device.assert_called_once_with(nwk=0x1234)
    assert device.relays == [0x5678, 0xABCD]
    assert app._discover_unknown_device.call_count == 0


async def test_relays_received_device_does_not_exist(app):
    app._discover_unknown_device = AsyncMock(spec_set=app._discover_unknown_device)
    app.get_device = MagicMock(wraps=app.get_device)
    app.handle_relays(nwk=0x1234, relays=[0x5678, 0xABCD])

    app.get_device.assert_called_once_with(nwk=0x1234)
    app._discover_unknown_device.assert_called_once_with(nwk=0x1234)


async def test_request_concurrency(app_factory):
    current_concurrency = 0
    peak_concurrency = 0

    class SlowApp(App):
        async def send_packet(self, packet):
            nonlocal current_concurrency, peak_concurrency

            async with self._limit_concurrency():
                current_concurrency += 1
                peak_concurrency = max(peak_concurrency, current_concurrency)

                await asyncio.sleep(0.1)
                current_concurrency -= 1

                if packet % 10 == 7:
                    # Fail randomly
                    raise asyncio.DeliveryError()

    app = app_factory({conf.CONF_MAX_CONCURRENT_REQUESTS: 16}, app_base=SlowApp)

    assert current_concurrency == 0
    assert peak_concurrency == 0

    await asyncio.gather(
        *[app.send_packet(i) for i in range(100)], return_exceptions=True
    )

    assert current_concurrency == 0
    assert peak_concurrency == 16


@pytest.fixture
def device():
    device = MagicMock()
    device.nwk = 0xABCD
    device.ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")

    return device


@pytest.fixture
def packet(app, device):
    return t.ZigbeePacket(
        src=t.AddrModeAddress(
            addr_mode=t.AddrMode.NWK, address=app.state.node_info.nwk
        ),
        src_ep=0x9A,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk),
        dst_ep=0xBC,
        tsn=0xDE,
        profile_id=0x1234,
        cluster_id=0x0006,
        data=t.SerializableBytes(b"test data"),
        source_route=None,
        extended_timeout=False,
        tx_options=t.TransmitOptions.NONE,
    )


async def test_request(app, device, packet):
    app.send_packet = AsyncMock(spec_set=app.send_packet)
    app.build_source_route_to = MagicMock(spec_set=app.build_source_route_to)

    async def send_request(app, **kwargs):
        kwargs = {
            "device": device,
            "profile": 0x1234,
            "cluster": 0x0006,
            "src_ep": 0x9A,
            "dst_ep": 0xBC,
            "sequence": 0xDE,
            "data": b"test data",
            "expect_reply": True,
            "use_ieee": False,
            "extended_timeout": False,
            **kwargs,
        }

        return await app.request(**kwargs)

    # Test sending with NWK
    status, msg = await send_request(app)
    assert status == zigpy.zcl.foundation.Status.SUCCESS
    assert isinstance(msg, str)

    app.send_packet.assert_called_once_with(packet=packet)
    app.send_packet.reset_mock()

    # Test sending with IEEE
    await send_request(app, use_ieee=True)
    app.send_packet.assert_called_once_with(
        packet=packet.replace(
            src=t.AddrModeAddress(
                addr_mode=t.AddrMode.IEEE, address=app.state.node_info.ieee
            ),
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=device.ieee),
        )
    )
    app.send_packet.reset_mock()

    # Test sending with source route
    app.build_source_route_to.return_value = [0x000A, 0x000B]

    with patch.dict(app.config, {conf.CONF_SOURCE_ROUTING: True}):
        await send_request(app)

    app.build_source_route_to.assert_called_once_with(dest=device)
    app.send_packet.assert_called_once_with(
        packet=packet.replace(source_route=[0x000A, 0x000B])
    )
    app.send_packet.reset_mock()

    # Test sending without waiting for a reply
    status, msg = await send_request(app, expect_reply=False)

    app.send_packet.assert_called_once_with(
        packet=packet.replace(tx_options=t.TransmitOptions.ACK)
    )
    app.send_packet.reset_mock()


def test_build_source_route_has_relays(app):
    device = MagicMock()
    device.relays = [0x1234, 0x5678]

    assert app.build_source_route_to(device) == [0x5678, 0x1234]


def test_build_source_route_no_relays(app):
    device = MagicMock()
    device.relays = None

    assert app.build_source_route_to(device) is None


async def test_send_mrequest(app, packet):
    app.send_packet = AsyncMock(spec_set=app.send_packet)

    status, msg = await app.mrequest(
        group_id=0xABCD,
        profile=0x1234,
        cluster=0x0006,
        src_ep=0x9A,
        sequence=0xDE,
        data=b"test data",
        hops=12,
        non_member_radius=34,
    )
    assert status == zigpy.zcl.foundation.Status.SUCCESS
    assert isinstance(msg, str)

    app.send_packet.assert_called_once_with(
        packet=packet.replace(
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.Group, address=0xABCD),
            dst_ep=None,
            radius=12,
            non_member_radius=34,
            tx_options=t.TransmitOptions.NONE,
        )
    )


async def test_send_broadcast(app, packet):
    app.send_packet = AsyncMock(spec_set=app.send_packet)

    status, msg = await app.broadcast(
        profile=0x1234,
        cluster=0x0006,
        src_ep=0x9A,
        dst_ep=0xBC,
        grpid=0x0000,  # unused
        radius=12,
        sequence=0xDE,
        data=b"test data",
        broadcast_address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
    )
    assert status == zigpy.zcl.foundation.Status.SUCCESS
    assert isinstance(msg, str)

    app.send_packet.assert_called_once_with(
        packet=packet.replace(
            dst=t.AddrModeAddress(
                addr_mode=t.AddrMode.Broadcast,
                address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
            ),
            radius=12,
            tx_options=t.TransmitOptions.NONE,
        )
    )


@pytest.fixture
def zdo_packet(app, device):
    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk),
        dst=t.AddrModeAddress(
            addr_mode=t.AddrMode.NWK, address=app.state.node_info.nwk
        ),
        src_ep=0x00,  # ZDO
        dst_ep=0x00,
        tsn=0xDE,
        profile_id=0x0000,
        cluster_id=0x0000,
        data=t.SerializableBytes(b""),
        source_route=None,
        extended_timeout=False,
        tx_options=t.TransmitOptions.ACK,
        lqi=123,
        rssi=-80,
    )


@patch("zigpy.device.Device.initialize", AsyncMock())
async def test_packet_received_new_device_zdo_announce(app, device, zdo_packet):
    app.handle_join = MagicMock(wraps=app.handle_join)

    zdo_data = zigpy.zdo.ZDO(None)._serialize(
        zdo_t.ZDOCmd.Device_annce,
        *dict(
            NWKAddr=device.nwk,
            IEEEAddr=device.ieee,
            Capability=0x00,
        ).values()
    )

    zdo_packet.cluster_id = zdo_t.ZDOCmd.Device_annce
    zdo_packet.data = t.SerializableBytes(
        t.uint8_t(zdo_packet.tsn).serialize() + zdo_data
    )
    app.packet_received(zdo_packet)

    app.handle_join.assert_called_once_with(
        nwk=device.nwk, ieee=device.ieee, parent_nwk=None
    )

    zigpy_device = app.get_device(ieee=device.ieee)
    assert zigpy_device.lqi == zdo_packet.lqi
    assert zigpy_device.rssi == zdo_packet.rssi


@patch("zigpy.device.Device.initialize", AsyncMock())
async def test_packet_received_new_device_discovery(app, device, zdo_packet):
    app.handle_join = MagicMock(wraps=app.handle_join)

    async def send_packet(packet):
        if packet.dst_ep != 0x00 or packet.cluster_id != zdo_t.ZDOCmd.IEEE_addr_req:
            return

        hdr, args = zigpy.zdo.ZDO(None).deserialize(
            packet.cluster_id, packet.data.serialize()
        )
        assert args == list(
            dict(
                NWKAddrOfInterest=device.nwk,
                RequestType=zdo_t.AddrRequestType.Single,
                StartIndex=0,
            ).values()
        )

        zdo_data = zigpy.zdo.ZDO(None)._serialize(
            zdo_t.ZDOCmd.IEEE_addr_rsp,
            *dict(
                Status=zdo_t.Status.SUCCESS,
                IEEEAddr=device.ieee,
                NWKAddr=device.nwk,
                NumAssocDev=0,
                StartIndex=0,
                NWKAddrAssocDevList=[],
            ).values()
        )

        # Receive the IEEE address reply
        zdo_packet.data = t.SerializableBytes(
            t.uint8_t(zdo_packet.tsn).serialize() + zdo_data
        )
        zdo_packet.cluster_id = zdo_t.ZDOCmd.IEEE_addr_rsp
        app.packet_received(zdo_packet)

    app.send_packet = AsyncMock(side_effect=send_packet)

    # Receive a bogus packet first, to trigger device discovery
    bogus_packet = zdo_packet.replace(dst_ep=0x01, src_ep=0x01)
    app.packet_received(bogus_packet)

    await asyncio.sleep(0.1)

    app.handle_join.assert_called_once_with(
        nwk=device.nwk, ieee=device.ieee, parent_nwk=None
    )

    zigpy_device = app.get_device(ieee=device.ieee)
    assert zigpy_device.lqi == zdo_packet.lqi
    assert zigpy_device.rssi == zdo_packet.rssi


async def test_bad_zdo_packet_received(app, device):
    device.is_initialized = True
    app.devices[device.ieee] = device

    bogus_zdo_packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=0,  # bad destination endpoint
        tsn=180,
        profile_id=260,
        cluster_id=6,
        data=t.SerializableBytes(b"\x08n\n\x00\x00\x10\x00"),
        lqi=255,
        rssi=-30,
    )

    app.packet_received(bogus_zdo_packet)

    assert len(device.handle_message.mock_calls) == 1


def test_get_device_with_address_nwk(app, device):
    app.devices[device.ieee] = device

    assert (
        app.get_device_with_address(
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk)
        )
        is device
    )
    assert (
        app.get_device_with_address(
            t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=device.ieee)
        )
        is device
    )

    with pytest.raises(ValueError):
        app.get_device_with_address(
            t.AddrModeAddress(addr_mode=t.AddrMode.Group, address=device.nwk)
        )

    with pytest.raises(KeyError):
        app.get_device_with_address(
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk + 1)
        )
