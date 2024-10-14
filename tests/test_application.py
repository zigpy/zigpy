import asyncio
import errno
import logging
from unittest import mock
from unittest.mock import ANY, PropertyMock, call

import pytest

import zigpy.application
import zigpy.config as conf
from zigpy.exceptions import (
    DeliveryError,
    NetworkNotFormed,
    NetworkSettingsInconsistent,
    TransientConnectionError,
)
import zigpy.ota
import zigpy.quirks
import zigpy.types as t
from zigpy.zcl import clusters, foundation
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock, patch, sentinel
from .conftest import (
    NCP_IEEE,
    App,
    make_app,
    make_ieee,
    make_neighbor,
    make_neighbor_from_device,
    make_node_desc,
)


@pytest.fixture
def ieee():
    return make_ieee()


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
    node_desc = make_node_desc()

    app.handle_join(1, ieee, None)
    app.get_device(ieee).node_desc = node_desc

    app.handle_join(1, ieee, None)
    assert app.get_device(ieee).node_desc == node_desc


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
    for _i in range(1, 20):
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
        for _i in range(1, 20):
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


async def test_handle_message_shim(app):
    dev = MagicMock()
    dev.nwk = 0x1234

    app.packet_received = MagicMock(spec_set=app.packet_received)
    app.handle_message(dev, 260, 1, 2, 3, b"data")

    assert app.packet_received.mock_calls == [
        call(
            t.ZigbeePacket(
                profile_id=260,
                cluster_id=1,
                src_ep=2,
                dst_ep=3,
                data=t.SerializableBytes(b"data"),
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=0x1234,
                ),
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=0x0000,
                ),
            )
        )
    ]


@patch("zigpy.device.Device.is_initialized", new_callable=PropertyMock)
@patch("zigpy.quirks.handle_message_from_uninitialized_sender", new=MagicMock())
async def test_handle_message_uninitialized_dev(is_init_mock, app, ieee):
    dev = app.add_device(ieee, 0x1234)
    dev.packet_received = MagicMock()
    is_init_mock.return_value = False

    assert not dev.initializing

    def make_packet(
        profile_id: int, cluster_id: int, src_ep: int, dst_ep: int, data: bytes
    ) -> t.ZigbeePacket:
        return t.ZigbeePacket(
            profile_id=profile_id,
            cluster_id=cluster_id,
            src_ep=src_ep,
            dst_ep=dst_ep,
            data=t.SerializableBytes(data),
            src=t.AddrModeAddress(
                addr_mode=t.AddrMode.NWK,
                address=dev.nwk,
            ),
            dst=t.AddrModeAddress(
                addr_mode=t.AddrMode.NWK,
                address=0x0000,
            ),
        )

    # Power Configuration cluster not allowed, no endpoints
    app.packet_received(
        make_packet(profile_id=260, cluster_id=0x0001, src_ep=1, dst_ep=1, data=b"test")
    )
    assert dev.packet_received.call_count == 0
    assert zigpy.quirks.handle_message_from_uninitialized_sender.call_count == 1

    # Device should be completing initialization
    assert dev.initializing

    # ZDO is allowed
    app.packet_received(
        make_packet(profile_id=260, cluster_id=0x0000, src_ep=0, dst_ep=0, data=b"test")
    )
    assert dev.packet_received.call_count == 1

    # Endpoint is uninitialized but Basic attribute read responses still work
    ep = dev.add_endpoint(1)
    app.packet_received(
        make_packet(profile_id=260, cluster_id=0x0000, src_ep=1, dst_ep=1, data=b"test")
    )
    assert dev.packet_received.call_count == 2

    # Others still do not
    app.packet_received(
        make_packet(profile_id=260, cluster_id=0x0001, src_ep=1, dst_ep=1, data=b"test")
    )
    assert dev.packet_received.call_count == 2
    assert zigpy.quirks.handle_message_from_uninitialized_sender.call_count == 2

    # They work after the endpoint is initialized
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    app.packet_received(
        make_packet(profile_id=260, cluster_id=0x0001, src_ep=1, dst_ep=1, data=b"test")
    )
    assert dev.packet_received.call_count == 3
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


async def test_remove_parent_devices(app, make_initialized_device):
    """Test removing an end device with parents."""

    end_device = make_initialized_device(app)
    end_device.node_desc.logical_type = zdo_t.LogicalType.EndDevice

    router_1 = make_initialized_device(app)
    router_1.node_desc.logical_type = zdo_t.LogicalType.Router

    router_2 = make_initialized_device(app)
    router_2.node_desc.logical_type = zdo_t.LogicalType.Router

    parent = make_initialized_device(app)

    app.topology.neighbors[router_1.ieee] = [
        make_neighbor_from_device(router_2),
        make_neighbor_from_device(parent),
    ]
    app.topology.neighbors[router_2.ieee] = [
        make_neighbor_from_device(parent),
        make_neighbor_from_device(router_1),
    ]
    app.topology.neighbors[parent.ieee] = [
        make_neighbor_from_device(router_2),
        make_neighbor_from_device(router_1),
        make_neighbor_from_device(end_device),
        make_neighbor(ieee=make_ieee(123), nwk=0x9876),
    ]

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
        for _i in range(1, 60):
            await asyncio.sleep(0)

        assert end_device.zdo.leave.await_count == 1
        assert end_device.zdo.request.await_count == 0
        assert router_1.zdo.leave.await_count == 0
        assert router_1.zdo.request.await_count == 0
        assert router_2.zdo.leave.await_count == 0
        assert router_2.zdo.request.await_count == 0
        assert parent.zdo.leave.await_count == 0
        assert parent.zdo.request.await_count == 1


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

    with (
        patch.object(App, "connect") as connect,
        patch.object(App, "disconnect") as disconnect,
    ):
        result = await App.probe(config)

    assert set(config.items()) <= set(result.items())

    assert connect.await_count == 1
    assert disconnect.await_count == 1


async def test_probe_failure():
    config = {"path": "/dev/test"}

    with (
        patch.object(App, "connect", side_effect=asyncio.TimeoutError) as connect,
        patch.object(App, "disconnect") as disconnect,
    ):
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

    assert nwk_info1.channel in (11, 15, 20, 25)


@mock.patch("zigpy.util.pick_optimal_channel", mock.Mock(return_value=22))
async def test_form_network_find_best_channel(app):
    orig_start_network = app.start_network

    async def start_network(*args, **kwargs):
        start_network.await_count += 1

        if start_network.await_count == 1:
            raise NetworkNotFormed

        return await orig_start_network(*args, **kwargs)

    start_network.await_count = 0
    app.start_network = start_network

    with patch.object(app, "write_network_info") as write:
        with patch.object(
            app.backups, "create_backup", wraps=app.backups.create_backup
        ) as create_backup:
            await app.form_network()

    assert start_network.await_count == 2

    # A temporary network will be formed first
    nwk_info1 = write.mock_calls[0].kwargs["network_info"]
    assert nwk_info1.channel == 11

    # Then, after the scan, a better channel is chosen
    nwk_info2 = write.mock_calls[1].kwargs["network_info"]
    assert nwk_info2.channel == 22

    # Only a single backup will be present
    assert create_backup.await_count == 1


async def test_startup_formed():
    app = make_app({conf.CONF_STARTUP_ENERGY_SCAN: False})
    app.start_network = AsyncMock(wraps=app.start_network)
    app.form_network = AsyncMock()
    app.permit = AsyncMock()

    await app.startup(auto_form=False)

    assert app.start_network.await_count == 1
    assert app.form_network.await_count == 0
    assert app.permit.await_count == 1


async def test_startup_not_formed():
    app = make_app({conf.CONF_STARTUP_ENERGY_SCAN: False})
    app.start_network = AsyncMock(wraps=app.start_network)
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


async def test_startup_not_formed_with_backup():
    app = make_app({conf.CONF_STARTUP_ENERGY_SCAN: False})
    app.start_network = AsyncMock(wraps=app.start_network)
    app.load_network_info = AsyncMock(side_effect=[NetworkNotFormed(), None])
    app.permit = AsyncMock()

    app.backups.restore_backup = AsyncMock()
    app.backups.backups = [sentinel.OLD_BACKUP, sentinel.NEW_BACKUP]

    await app.startup(auto_form=True)

    assert app.start_network.await_count == 1
    app.backups.restore_backup.assert_called_once_with(sentinel.NEW_BACKUP)


async def test_startup_backup():
    app = make_app({conf.CONF_NWK_BACKUP_ENABLED: True})

    with patch("zigpy.backups.BackupManager.start_periodic_backups") as p:
        await app.startup()

    p.assert_called_once()


async def test_startup_no_backup():
    app = make_app({conf.CONF_NWK_BACKUP_ENABLED: False})

    with patch("zigpy.backups.BackupManager.start_periodic_backups") as p:
        await app.startup()

    p.assert_not_called()


def with_attributes(obj, **attrs):
    for k, v in attrs.items():
        setattr(obj, k, v)

    return obj


@pytest.mark.parametrize(
    "error",
    [
        with_attributes(OSError("Network is unreachable"), errno=errno.ENETUNREACH),
        ConnectionRefusedError(),
    ],
)
async def test_startup_failure_transient_error(error):
    app = make_app({conf.CONF_NWK_BACKUP_ENABLED: False})

    with patch.object(app, "connect", side_effect=[error]):
        with pytest.raises(TransientConnectionError):
            await app.startup()


@patch("zigpy.backups.BackupManager.from_network_state")
@patch("zigpy.backups.BackupManager.most_recent_backup")
async def test_initialize_compatible_backup(
    mock_most_recent_backup, mock_backup_from_state
):
    app = make_app({conf.CONF_NWK_VALIDATE_SETTINGS: True})
    mock_backup_from_state.return_value.is_compatible_with.return_value = True

    await app.initialize()

    mock_backup_from_state.return_value.is_compatible_with.assert_called_once()
    mock_most_recent_backup.assert_called_once()


@patch("zigpy.backups.BackupManager.from_network_state")
@patch("zigpy.backups.BackupManager.most_recent_backup")
async def test_initialize_incompatible_backup(
    mock_most_recent_backup, mock_backup_from_state
):
    app = make_app({conf.CONF_NWK_VALIDATE_SETTINGS: True})
    mock_backup_from_state.return_value.is_compatible_with.return_value = False

    with pytest.raises(NetworkSettingsInconsistent) as exc:
        await app.initialize()

    mock_backup_from_state.return_value.is_compatible_with.assert_called_once()
    mock_most_recent_backup.assert_called_once()

    assert exc.value.old_state is mock_most_recent_backup()
    assert exc.value.new_state is mock_backup_from_state.return_value


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


async def test_request_concurrency():
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
                    raise asyncio.DeliveryError

    app = make_app({conf.CONF_MAX_CONCURRENT_REQUESTS: 16}, app_base=SlowApp)

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

    app.send_packet.assert_called_once_with(packet)
    app.send_packet.reset_mock()

    # Test sending with IEEE
    await send_request(app, use_ieee=True)
    app.send_packet.assert_called_once_with(
        packet.replace(
            src=t.AddrModeAddress(
                addr_mode=t.AddrMode.IEEE,
                address=app.state.node_info.ieee,
            ),
            dst=t.AddrModeAddress(
                addr_mode=t.AddrMode.IEEE,
                address=device.ieee,
            ),
        )
    )
    app.send_packet.reset_mock()

    # Test sending with source route
    app.build_source_route_to.return_value = [0x000A, 0x000B]

    with patch.dict(app.config, {conf.CONF_SOURCE_ROUTING: True}):
        await send_request(app)

    app.build_source_route_to.assert_called_once_with(dest=device)
    app.send_packet.assert_called_once_with(
        packet.replace(source_route=[0x000A, 0x000B])
    )
    app.send_packet.reset_mock()

    # Test sending without waiting for a reply
    status, msg = await send_request(app, expect_reply=False)

    app.send_packet.assert_called_once_with(
        packet.replace(tx_options=t.TransmitOptions.ACK)
    )
    app.send_packet.reset_mock()

    # Test explicit ACK control (enabled)
    status, msg = await send_request(app, ask_for_ack=True)

    app.send_packet.assert_called_once_with(
        packet.replace(tx_options=t.TransmitOptions.ACK)
    )
    app.send_packet.reset_mock()

    # Test explicit ACK control (disabled)
    status, msg = await send_request(app, ask_for_ack=False)

    app.send_packet.assert_called_once_with(
        packet.replace(tx_options=t.TransmitOptions(0))
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
        packet.replace(
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.Group, address=0xABCD),
            dst_ep=None,
            radius=12,
            non_member_radius=34,
            tx_options=t.TransmitOptions.NONE,
        )
    )


async def test_send_broadcast(app, packet):
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
        packet.replace(
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
        *{
            "NWKAddr": device.nwk,
            "IEEEAddr": device.ieee,
            "Capability": 0x00,
        }.values(),
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
            {
                "NWKAddrOfInterest": device.nwk,
                "RequestType": zdo_t.AddrRequestType.Single,
                "StartIndex": 0,
            }.values()
        )

        zdo_data = zigpy.zdo.ZDO(None)._serialize(
            zdo_t.ZDOCmd.IEEE_addr_rsp,
            *{
                "Status": zdo_t.Status.SUCCESS,
                "IEEEAddr": device.ieee,
                "NWKAddr": device.nwk,
                "NumAssocDev": 0,
                "StartIndex": 0,
                "NWKAddrAssocDevList": [],
            }.values(),
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
        nwk=device.nwk, ieee=device.ieee, parent_nwk=None, handle_rejoin=False
    )

    zigpy_device = app.get_device(ieee=device.ieee)
    assert zigpy_device.lqi == zdo_packet.lqi
    assert zigpy_device.rssi == zdo_packet.rssi


@patch("zigpy.device.Device.initialize", AsyncMock())
async def test_packet_received_ieee_no_rejoin(app, device, zdo_packet, caplog):
    device.is_initialized = True
    app.devices[device.ieee] = device

    app.handle_join = MagicMock(wraps=app.handle_join)

    zdo_data = zigpy.zdo.ZDO(None)._serialize(
        zdo_t.ZDOCmd.IEEE_addr_rsp,
        *{
            "Status": zdo_t.Status.SUCCESS,
            "IEEEAddr": device.ieee,
            "NWKAddr": device.nwk,
        }.values(),
    )

    zdo_packet.cluster_id = zdo_t.ZDOCmd.IEEE_addr_rsp
    zdo_packet.data = t.SerializableBytes(
        t.uint8_t(zdo_packet.tsn).serialize() + zdo_data
    )
    app.packet_received(zdo_packet)

    assert "joined the network" not in caplog.text

    app.handle_join.assert_called_once_with(
        nwk=device.nwk, ieee=device.ieee, parent_nwk=None, handle_rejoin=False
    )

    assert len(device.schedule_group_membership_scan.mock_calls) == 0
    assert len(device.schedule_initialize.mock_calls) == 0


@patch("zigpy.device.Device.initialize", AsyncMock())
async def test_packet_received_ieee_rejoin(app, device, zdo_packet, caplog):
    device.is_initialized = True
    app.devices[device.ieee] = device

    app.handle_join = MagicMock(wraps=app.handle_join)

    zdo_data = zigpy.zdo.ZDO(None)._serialize(
        zdo_t.ZDOCmd.IEEE_addr_rsp,
        *{
            "Status": zdo_t.Status.SUCCESS,
            "IEEEAddr": device.ieee,
            "NWKAddr": device.nwk + 1,  # NWK has changed
        }.values(),
    )

    zdo_packet.cluster_id = zdo_t.ZDOCmd.IEEE_addr_rsp
    zdo_packet.data = t.SerializableBytes(
        t.uint8_t(zdo_packet.tsn).serialize() + zdo_data
    )
    app.packet_received(zdo_packet)

    assert "joined the network" not in caplog.text

    app.handle_join.assert_called_once_with(
        nwk=device.nwk, ieee=device.ieee, parent_nwk=None, handle_rejoin=False
    )

    assert len(device.schedule_initialize.mock_calls) == 1


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

    assert len(device.packet_received.mock_calls) == 1


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


async def test_request_future_matching(app, make_initialized_device):
    device = make_initialized_device(app)
    device._packet_debouncer.filter = MagicMock(return_value=False)

    ota = device.endpoints[1].add_output_cluster(clusters.general.Ota.cluster_id)

    req_hdr, req_cmd = ota._create_request(
        general=False,
        command_id=ota.commands_by_name["query_next_image"].id,
        schema=ota.commands_by_name["query_next_image"].schema,
        disable_default_response=False,
        direction=foundation.Direction.Client_to_Server,
        args=(),
        kwargs={
            "field_control": 0,
            "manufacturer_code": 0x1234,
            "image_type": 0x5678,
            "current_file_version": 0x11112222,
        },
    )

    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=1,
        tsn=req_hdr.tsn,
        profile_id=260,
        cluster_id=ota.cluster_id,
        data=t.SerializableBytes(req_hdr.serialize() + req_cmd.serialize()),
        lqi=255,
        rssi=-30,
    )

    assert not app._req_listeners[device]

    with app.wait_for_response(
        device, [ota.commands_by_name["query_next_image"].schema()]
    ) as rsp_fut:
        # Attach two listeners
        with app.wait_for_response(
            device, [ota.commands_by_name["query_next_image"].schema()]
        ) as rsp_fut2:
            assert app._req_listeners[device]

            # Listeners are resolved FIFO
            app.packet_received(packet)
            assert rsp_fut.done()
            assert not rsp_fut2.done()

            app.packet_received(packet)
            assert rsp_fut.done()
            assert rsp_fut2.done()

            # Unhandled packets are ignored
            app.packet_received(packet)

            rsp_hdr, rsp_cmd = await rsp_fut
            assert rsp_hdr == req_hdr
            assert rsp_cmd == req_cmd
            assert rsp_cmd.current_file_version == 0x11112222

    assert not app._req_listeners[device]


async def test_request_callback_matching(app, make_initialized_device):
    device = make_initialized_device(app)
    device._packet_debouncer.filter = MagicMock(return_value=False)
    ota = device.endpoints[1].add_output_cluster(clusters.general.Ota.cluster_id)

    req_hdr, req_cmd = ota._create_request(
        general=False,
        command_id=ota.commands_by_name["query_next_image"].id,
        schema=ota.commands_by_name["query_next_image"].schema,
        disable_default_response=False,
        direction=foundation.Direction.Client_to_Server,
        args=(),
        kwargs={
            "field_control": 0,
            "manufacturer_code": 0x1234,
            "image_type": 0x5678,
            "current_file_version": 0x11112222,
        },
    )

    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=1,
        tsn=req_hdr.tsn,
        profile_id=260,
        cluster_id=ota.cluster_id,
        data=t.SerializableBytes(req_hdr.serialize() + req_cmd.serialize()),
        lqi=255,
        rssi=-30,
    )

    mock_callback = mock.Mock()

    assert not app._req_listeners[device]

    with app.callback_for_response(
        device, [ota.commands_by_name["query_next_image"].schema()], mock_callback
    ):
        assert app._req_listeners[device]

        asyncio.get_running_loop().call_soon(app.packet_received, packet)
        asyncio.get_running_loop().call_soon(app.packet_received, packet)
        asyncio.get_running_loop().call_soon(app.packet_received, packet)

        await asyncio.sleep(0.1)

        assert len(mock_callback.mock_calls) == 3
        assert mock_callback.mock_calls == [mock.call(req_hdr, req_cmd)] * 3

    assert not app._req_listeners[device]


async def test_energy_scan_default(app):
    await app.startup()

    raw_scan_results = [
        170,
        191,
        181,
        165,
        179,
        169,
        196,
        163,
        174,
        162,
        190,
        186,
        191,
        178,
        204,
        187,
    ]
    coordinator = app._device
    coordinator.zdo.Mgmt_NWK_Update_req = AsyncMock(
        return_value=[
            zdo_t.Status.SUCCESS,
            t.Channels.ALL_CHANNELS,
            29,
            10,
            raw_scan_results,
        ]
    )

    results = await app.energy_scan(
        channels=t.Channels.ALL_CHANNELS, duration_exp=2, count=1
    )

    assert len(results) == 16
    assert results == dict(zip(range(11, 26 + 1), raw_scan_results))


async def test_energy_scan_not_implemented(app):
    """Energy scanning still "works" even when the radio doesn't implement it."""
    await app.startup()
    app._device.zdo.Mgmt_NWK_Update_req.side_effect = asyncio.TimeoutError()

    results = await app.energy_scan(
        channels=t.Channels.ALL_CHANNELS, duration_exp=2, count=1
    )
    assert results == {c: 0 for c in range(11, 26 + 1)}


@pytest.mark.parametrize(
    ("scan", "message_present"),
    [
        ({c: 0 for c in t.Channels.ALL_CHANNELS}, False),
        ({c: 255 for c in t.Channels.ALL_CHANNELS}, True),
    ],
)
async def test_startup_energy_scan(app, caplog, scan, message_present):
    with mock.patch.object(app, "energy_scan", return_value=scan):
        with caplog.at_level(logging.WARNING):
            await app.startup()

    if message_present:
        assert "Zigbee channel 15 utilization is 100.00%" in caplog.text
    else:
        assert "Zigbee channel" not in caplog.text


async def test_startup_broadcast_failure_due_to_interference(app, caplog):
    err = DeliveryError(
        "Failed to deliver packet: <TXStatus.MAC_CHANNEL_ACCESS_FAILURE: 225>", 225
    )

    with mock.patch.object(app, "permit", side_effect=err):
        with caplog.at_level(logging.WARNING):
            await app.startup()

    # The application will still start up, however
    assert "Failed to send startup broadcast" in caplog.text
    assert "interference" in caplog.text


async def test_startup_broadcast_failure_other(app, caplog):
    with mock.patch.object(app, "permit", side_effect=DeliveryError("Error", 123)):
        with pytest.raises(DeliveryError, match="^Error$"):
            await app.startup()


@patch("zigpy.application.CHANNEL_CHANGE_SETTINGS_RELOAD_DELAY_S", 0.1)
@patch("zigpy.application.CHANNEL_CHANGE_BROADCAST_DELAY_S", 0.01)
async def test_move_network_to_new_channel(app):
    async def nwk_update(*args, **kwargs):
        async def inner():
            await asyncio.sleep(
                zigpy.application.CHANNEL_CHANGE_SETTINGS_RELOAD_DELAY_S * 5
            )
            NwkUpdate = args[0]
            app.state.network_info.channel = list(NwkUpdate.ScanChannels)[0]
            app.state.network_info.nwk_update_id = NwkUpdate.nwkUpdateId

        asyncio.create_task(inner())  # noqa: RUF006

    await app.startup()

    assert app.state.network_info.channel != 26

    with patch.object(
        app._device.zdo, "Mgmt_NWK_Update_req", side_effect=nwk_update
    ) as mock_update:
        await app.move_network_to_channel(new_channel=26, num_broadcasts=10)

    assert app.state.network_info.channel == 26
    assert len(mock_update.mock_calls) == 1


async def test_move_network_to_new_channel_noop(app):
    await app.startup()

    old_channel = app.state.network_info.channel

    with patch("zigpy.zdo.broadcast") as mock_broadcast:
        await app.move_network_to_channel(new_channel=old_channel)

    assert app.state.network_info.channel == old_channel
    assert len(mock_broadcast.mock_calls) == 0


async def test_startup_multiple_dblistener(app):
    app._dblistener = AsyncMock()
    app.connect = AsyncMock(side_effect=RuntimeError())

    with pytest.raises(RuntimeError):
        await app.startup()

    with pytest.raises(RuntimeError):
        await app.startup()

    # The database listener will not be shut down automatically
    assert len(app._dblistener.shutdown.mock_calls) == 0


async def test_connection_lost(app):
    exc = RuntimeError()
    listener = MagicMock()

    app.add_listener(listener)
    app.connection_lost(exc)

    listener.connection_lost.assert_called_with(exc)


async def test_watchdog(app):
    error = RuntimeError()

    app = make_app({})
    app._watchdog_period = 0.1
    app._watchdog_feed = AsyncMock(side_effect=[None, None, error])
    app.connection_lost = MagicMock()

    assert app._watchdog_task is None
    await app.startup()
    assert app._watchdog_task is not None

    # We call it once during startup synchronously
    assert app._watchdog_feed.mock_calls == [call()]
    assert app.connection_lost.mock_calls == []

    await asyncio.sleep(0.5)

    assert app._watchdog_feed.mock_calls == [call(), call(), call()]
    assert app.connection_lost.mock_calls == [call(error)]
    assert app._watchdog_task.done()


async def test_permit_with_key(app):
    app = make_app({})

    app.permit_with_link_key = AsyncMock()

    with pytest.raises(ValueError):
        await app.permit_with_key(
            node=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
            code=b"invalid code that is far too long and of the wrong parity",
            time_s=60,
        )

    assert app.permit_with_link_key.mock_calls == []

    await app.permit_with_key(
        node=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
        code=bytes.fromhex("11223344556677884AF7"),
        time_s=60,
    )

    assert app.permit_with_link_key.mock_calls == [
        call(
            node=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
            link_key=t.KeyData.convert("41618FC0C83B0E14A589954B16E31466"),
            time_s=60,
        )
    ]


async def test_probe(app):
    class BaudSpecificApp(App):
        _probe_configs = [
            {conf.CONF_DEVICE_BAUDRATE: 57600},
            {conf.CONF_DEVICE_BAUDRATE: 115200},
        ]

        async def connect(self):
            if self._config[conf.CONF_DEVICE][conf.CONF_DEVICE_BAUDRATE] != 115200:
                raise asyncio.TimeoutError

    # Only one baudrate is valid
    assert (await BaudSpecificApp.probe({conf.CONF_DEVICE_PATH: "/dev/null"})) == {
        conf.CONF_DEVICE_PATH: "/dev/null",
        conf.CONF_DEVICE_BAUDRATE: 115200,
        conf.CONF_DEVICE_FLOW_CONTROL: None,
    }

    class NeverConnectsApp(App):
        async def connect(self):
            raise asyncio.TimeoutError

    # No settings will work
    assert (await NeverConnectsApp.probe({conf.CONF_DEVICE_PATH: "/dev/null"})) is False
