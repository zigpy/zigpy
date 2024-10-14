import asyncio

import pytest

from zigpy import zdo
import zigpy.device
import zigpy.types as t
import zigpy.zdo.types as zdo_types

from .async_mock import AsyncMock, MagicMock, patch, sentinel


def test_commands():
    for cmdid, cmdspec in zdo.types.CLUSTERS.items():
        assert 0 <= cmdid <= 0xFFFF
        assert isinstance(cmdspec, tuple)
        for paramname, paramtype in zip(cmdspec[0], cmdspec[1]):
            assert isinstance(paramname, str)
            assert hasattr(paramtype, "serialize")
            assert hasattr(paramtype, "deserialize")


@pytest.fixture
def zdo_f(app):
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    dev = zigpy.device.Device(app, ieee, 65535)
    dev.request = AsyncMock()

    app.devices[dev.ieee] = dev

    return zdo.ZDO(dev)


def test_deserialize(zdo_f):
    hdr, args = zdo_f.deserialize(2, b"\x01\x02\x03xx")
    assert hdr.tsn == 1
    assert hdr.is_reply is False
    assert args == [0x0302]


def test_deserialize_unknown(zdo_f):
    with pytest.raises(ValueError):
        hdr, args = zdo_f.deserialize(0x0100, b"\x01")


async def test_request(zdo_f):
    with patch.object(
        zdo_f._device, "get_sequence", wraps=zdo_f._device.get_sequence
    ) as get_sequence:
        await zdo_f.request(2, 65535)
        assert zdo_f.device.request.call_count == 1
        assert zdo_f.device.request.mock_calls[0].kwargs["expect_reply"] is True
        assert get_sequence.call_count == 1


async def test_bind(zdo_f):
    cluster = MagicMock()
    cluster.endpoint.endpoint_id = 1
    cluster.cluster_id = 1026
    await zdo_f.bind(cluster)
    assert zdo_f.device.request.call_count == 1
    assert zdo_f.device.request.mock_calls[0].kwargs["cluster"] == 0x0021


async def test_unbind(zdo_f):
    cluster = MagicMock()
    cluster.endpoint.endpoint_id = 1
    cluster.cluster_id = 1026
    await zdo_f.unbind(cluster)
    assert zdo_f.device.request.call_count == 1
    assert zdo_f.device.request.mock_calls[0].kwargs["cluster"] == 0x0022


@pytest.mark.parametrize(
    ("remove_children", "rejoin", "flags"),
    [
        (False, False, 0),
        (False, True, 0x80),
        (True, False, 0x40),
        (True, True, 0xC0),
    ],
)
async def test_leave(zdo_f, remove_children, rejoin, flags):
    """Test ZDO leave request options."""
    with patch.object(zdo_f, "request", AsyncMock()) as req_mock:
        await zdo_f.leave(remove_children, rejoin)
    assert req_mock.await_count == 1
    assert req_mock.await_args[0][0] == 0x0034
    assert req_mock.await_args[0][1] == t.EUI64.convert("07:06:05:04:03:02:01:00")
    assert req_mock.await_args[0][2] == flags


async def test_permit(zdo_f):
    await zdo_f.permit()
    assert zdo_f.device.request.call_count == 1
    assert zdo_f.device.request.mock_calls[0].kwargs["cluster"] == 0x0036


async def test_broadcast(app):
    await zigpy.zdo.broadcast(app, 0x0036, 0, 0, 60, 0)

    assert app.send_packet.call_count == 1

    packet = app.send_packet.mock_calls[0].args[0]
    assert packet.dst.addr_mode == t.AddrMode.Broadcast
    assert packet.cluster_id == 0x0036


def _handle_match_desc(zdo_f, profile):
    zdo_f.reply = AsyncMock()
    hdr = MagicMock()
    hdr.command_id = zdo_types.ZDOCmd.Match_Desc_req
    zdo_f.handle_message(5, 0x0006, hdr, [None, profile, [], []])
    assert zdo_f.reply.call_count == 1


async def test_handle_match_desc_zha(zdo_f):
    _handle_match_desc(zdo_f, 260)
    await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.FIRST_COMPLETED)
    assert zdo_f.reply.await_count == 1
    assert zdo_f.reply.call_args[0][3]


async def test_handle_match_desc_generic(zdo_f):
    _handle_match_desc(zdo_f, 0)
    await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.FIRST_COMPLETED)
    assert zdo_f.reply.await_count == 1
    assert not zdo_f.reply.call_args[0][3]


async def test_handle_nwk_addr(zdo_f):
    ieee = zdo_f._device.application.state.node_info.ieee
    zdo_f.reply = MagicMock()
    hdr = MagicMock()
    hdr.command_id = zdo_types.ZDOCmd.NWK_addr_req
    zdo_f.handle_message(5, 0x0000, hdr, [ieee, 0x00])
    assert zdo_f.reply.call_count == 1


async def test_handle_ieee_addr(zdo_f):
    nwk = zdo_f._device.application.state.node_info.nwk
    zdo_f.reply = MagicMock()
    hdr = MagicMock()
    hdr.command_id = zdo_types.ZDOCmd.IEEE_addr_req
    zdo_f.handle_message(5, 0x0001, hdr, [nwk, 0x00])
    assert zdo_f.reply.call_count == 1


def test_handle_announce(zdo_f):
    dev = zdo_f._device
    listener = MagicMock()
    zdo_f.add_listener(listener)

    dev._application.devices.pop(dev.ieee)
    hdr = MagicMock()
    hdr.command_id = zdo_types.ZDOCmd.Device_annce
    zdo_f.handle_message(
        5, 0x0013, hdr, [dev.nwk, dev.ieee, 0], dst_addressing=sentinel.dst_addr
    )

    assert listener.device_announce.call_count == 1
    assert listener.device_announce.call_args[0][0] is dev

    assert listener.zdo_device_annce.call_count == 1
    assert listener.zdo_device_annce.call_args[0][0] is dev
    assert listener.zdo_device_annce.call_args[0][1] is sentinel.dst_addr
    assert listener.zdo_device_annce.call_args[0][2] is hdr
    assert listener.zdo_device_annce.call_args[0][3] == [dev.nwk, dev.ieee, 0]


def test_handle_permit_join(zdo_f):
    listener = MagicMock()
    zdo_f.add_listener(listener)
    hdr = MagicMock()
    hdr.command_id = zdo_types.ZDOCmd.Mgmt_Permit_Joining_req
    zdo_f.handle_message(5, 0x0036, hdr, [100, 1])
    assert listener.permit_duration.call_count == 1


def test_handle_unsupported(zdo_f):
    listener = MagicMock()
    zdo_f.add_listener(listener)
    hdr = MagicMock()
    hdr.command_id = zdo_types.ZDOCmd(0xFFFF)
    assert hdr.command_id not in list(zdo_types.ZDOCmd)
    zdo_f.request = MagicMock()
    zdo_f.reply = MagicMock()
    zdo_f.handle_message(5, 0xFFFF, hdr, [])

    assert listener.zdo_undefined_0xffff.call_count == 1
    assert zdo_f.request.call_count == 0
    assert zdo_f.reply.call_count == 0


def test_device_accessor(zdo_f):
    assert zdo_f.device.nwk == 65535


async def test_reply(zdo_f):
    zdo_f.device.request = AsyncMock()
    await zdo_f.reply(0x0005)
    assert zdo_f.device.request.call_count == 1


def test_get_attr_error(zdo_f):
    with pytest.raises(AttributeError):
        zdo_f.no_such_attribute()


async def test_reply_tsn_override(zdo_f, monkeypatch):
    clusters = MagicMock()
    clusters.__getitem__.return_value = (
        sentinel.param_names,
        sentinel.scheam,
    )
    monkeypatch.setattr(zdo_types, "CLUSTERS", clusters)
    mock_ser = MagicMock()
    mock_ser.return_value = b"\xaa\x55"
    monkeypatch.setattr(t, "serialize", mock_ser)
    await zdo_f.reply(sentinel.cmd, sentinel.arg1, sentinel.arg2)
    seq = zdo_f.device.request.mock_calls[0].kwargs["sequence"]
    data = zdo_f.device.request.mock_calls[0].kwargs["data"]
    assert seq == 1
    assert data[0] == 1
    assert data[1:3] == b"\xaa\x55"

    # override tsn
    tsn = 0x23
    await zdo_f.reply(sentinel.cmd, sentinel.arg1, sentinel.arg2, tsn=tsn)
    seq = zdo_f.device.request.mock_calls[1].kwargs["sequence"]
    data = zdo_f.device.request.mock_calls[1].kwargs["data"]
    assert seq == tsn
    assert data[0] == tsn
    assert data[1:3] == b"\xaa\x55"
