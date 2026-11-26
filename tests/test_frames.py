import asyncio
import logging

import pytest

import zigpy.frames
import zigpy.types as t
from zigpy.zcl import foundation
import zigpy.zdo.commands as zdo_c
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock, call, patch
from .conftest import add_initialized_device, make_ieee

NWK = t.NWK(0x1234)
OTHER_NWK = t.NWK(0x5678)

DEVICE_ANNCE = zdo_c.ZDOCommand(
    command_id=zdo_t.ZDOCmd.Device_annce,
    tsn=0x10,
    command=zdo_c.DeviceAnnce(
        nwk_addr=NWK,
        ieee_addr=make_ieee(),
        capability=zdo_t.MACCapabilityFlags.NONE,
    ),
)

# Read Attributes Response: manufacturer name (0x0004) is the string "abc"
READ_ATTRIBUTES_RSP = bytes.fromhex("18 01 01 0400 00 42 03 616263")


def make_packet(
    *,
    src: t.NWK = NWK,
    endpoint: int = 1,
    profile_id: int = 0x0104,
    cluster_id: int = 0x0000,
    data: bytes = b"",
) -> t.ZigbeePacket:
    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=src),
        src_ep=endpoint,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=endpoint,
        profile_id=profile_id,
        cluster_id=cluster_id,
        data=t.SerializableBytes(data),
    )


def make_zdo_packet(frame: zdo_c.ZDOCommand, *, src: t.NWK = NWK) -> t.ZigbeePacket:
    return make_packet(
        src=src,
        endpoint=0,
        profile_id=0x0000,
        cluster_id=frame.command_id,
        data=frame.serialize(),
    )


def any_frame(frame: zigpy.frames.Frame) -> bool:
    return True


@pytest.mark.parametrize(
    ("packet", "expected"),
    [
        (
            make_zdo_packet(DEVICE_ANNCE),
            lambda p: zigpy.frames.ZDOFrame(packet=p, command=DEVICE_ANNCE),
        ),
        # Truncated ZDO payload
        (
            make_packet(endpoint=0, profile_id=0x0000, cluster_id=0x0013, data=b"\x10"),
            lambda p: zigpy.frames.RawFrame(packet=p),
        ),
        # Neither ZDO nor ZCL
        (
            make_packet(profile_id=0xC0C0, data=b"\x01\x02"),
            lambda p: zigpy.frames.RawFrame(packet=p),
        ),
        # Truncated ZCL header
        (
            make_packet(data=b"\x18"),
            lambda p: zigpy.frames.RawFrame(packet=p),
        ),
        (
            make_packet(data=READ_ATTRIBUTES_RSP),
            lambda p: zigpy.frames.ZCLFrame(
                packet=p,
                header=foundation.ZCLHeader.deserialize(READ_ATTRIBUTES_RSP)[0],
                command=foundation.GENERAL_COMMANDS[
                    foundation.GeneralCommand.Read_Attributes_rsp
                ].schema(
                    status_records=[
                        foundation.ReadAttributeRecord(
                            attrid=0x0004,
                            status=foundation.Status.SUCCESS,
                            value=foundation.TypeValue(
                                type=foundation.DataTypeId.string,
                                value=t.CharacterString("abc"),
                            ),
                        )
                    ]
                ),
            ),
        ),
        # Cluster-specific commands need the device's clusters, they stay raw
        (
            make_packet(cluster_id=0x0006, data=b"\x01\x05\x01\xaa"),
            lambda p: zigpy.frames.ZCLFrame(
                packet=p,
                header=foundation.ZCLHeader.deserialize(b"\x01\x05\x01")[0],
                command=b"\xaa",
            ),
        ),
        # Unknown general command
        (
            make_packet(data=b"\x18\x01\x1f\xaa"),
            lambda p: zigpy.frames.ZCLFrame(
                packet=p,
                header=foundation.ZCLHeader.deserialize(b"\x18\x01\x1f")[0],
                command=b"\xaa",
            ),
        ),
        # Malformed general command
        (
            make_packet(data=b"\x18\x01\x01\x04"),
            lambda p: zigpy.frames.ZCLFrame(
                packet=p,
                header=foundation.ZCLHeader.deserialize(b"\x18\x01\x01")[0],
                command=b"\x04",
            ),
        ),
    ],
)
def test_parse_frame(packet, expected):
    assert zigpy.frames.parse_frame(packet) == expected(packet)


async def test_subscribe_by_nwk(app):
    by_nwk = MagicMock()
    any_source = MagicMock()

    unsubscribe = app.frame_listeners.subscribe(NWK, any_frame, by_nwk)
    app.frame_listeners.subscribe(None, any_frame, any_source)

    packet = make_packet(src=NWK, data=READ_ATTRIBUTES_RSP)
    other_packet = make_packet(src=OTHER_NWK, data=READ_ATTRIBUTES_RSP)

    app.packet_received(packet)
    app.packet_received(other_packet)
    unsubscribe()
    app.packet_received(packet)

    frame = zigpy.frames.parse_frame(packet)
    other_frame = zigpy.frames.parse_frame(other_packet)

    assert by_nwk.mock_calls == [call(frame)]
    assert any_source.mock_calls == [call(frame), call(other_frame), call(frame)]


async def test_subscribe_predicate(app):
    callback = MagicMock()
    app.frame_listeners.subscribe(
        None, zigpy.frames.zdo_command(zdo_c.DeviceAnnce, tsn=0x11), callback
    )

    app.packet_received(make_zdo_packet(DEVICE_ANNCE))
    assert callback.mock_calls == []

    frame = zdo_c.ZDOCommand(
        command_id=DEVICE_ANNCE.command_id, tsn=0x11, command=DEVICE_ANNCE.command
    )
    app.packet_received(make_zdo_packet(frame))
    assert len(callback.mock_calls) == 1


async def test_async_callback(app):
    callback = AsyncMock()
    app.frame_listeners.subscribe(None, any_frame, callback)

    packet = make_packet(data=READ_ATTRIBUTES_RSP)
    app.packet_received(packet)
    await asyncio.sleep(0)

    assert callback.await_args_list == [call(zigpy.frames.parse_frame(packet))]


async def test_callback_exception(app, caplog):
    failing = MagicMock(side_effect=RuntimeError("boom"))
    ok = MagicMock()
    app.frame_listeners.subscribe(None, any_frame, failing)
    app.frame_listeners.subscribe(None, any_frame, ok)

    with caplog.at_level(logging.ERROR):
        app.packet_received(make_packet(data=READ_ATTRIBUTES_RSP))

    assert len(ok.mock_calls) == 1
    assert "Frame callback" in caplog.text


async def test_wait_for_consumes(app):
    """The first matching future takes the frame, the device never sees it."""
    dev = add_initialized_device(app, nwk=NWK, ieee=make_ieee(1))
    callback = MagicMock()
    app.frame_listeners.subscribe(NWK, any_frame, callback)

    packet = make_packet(data=READ_ATTRIBUTES_RSP)

    with (
        patch.object(dev, "packet_received") as device_packet_received,
        app.frame_listeners.wait_for(NWK, any_frame) as first,
        app.frame_listeners.wait_for(NWK, any_frame) as second,
    ):
        app.packet_received(packet)

        assert first.result() == zigpy.frames.parse_frame(packet)
        assert not second.done()

    assert len(callback.mock_calls) == 1
    assert device_packet_received.mock_calls == []

    # The listeners are gone, the next frame reaches the device
    with patch.object(dev, "packet_received") as device_packet_received:
        app.packet_received(packet)

    assert device_packet_received.mock_calls == [call(packet)]


async def test_wait_for_skips_done_future(app):
    packet = make_packet(data=READ_ATTRIBUTES_RSP)

    with (
        app.frame_listeners.wait_for(NWK, any_frame) as cancelled,
        app.frame_listeners.wait_for(NWK, any_frame) as waiting,
    ):
        cancelled.cancel()
        app.packet_received(packet)

        assert waiting.result() == zigpy.frames.parse_frame(packet)


async def test_wait_for_unknown_device(app):
    """Frames from an unknown NWK can be consumed before device discovery."""
    with (
        patch.object(app, "_discover_unknown_device") as discover,
        app.frame_listeners.wait_for(NWK, any_frame) as future,
    ):
        app.packet_received(make_packet(data=READ_ATTRIBUTES_RSP))

    assert future.done()
    assert discover.mock_calls == []


async def test_consumed_zdo_notification(app):
    """A consumed Device_annce is still handled as a join."""
    with (
        patch.object(app, "handle_join") as handle_join,
        app.frame_listeners.wait_for(None, any_frame) as future,
    ):
        app.packet_received(make_zdo_packet(DEVICE_ANNCE))

    assert future.done()
    assert handle_join.mock_calls == [
        call(nwk=NWK, ieee=DEVICE_ANNCE.command.ieee_addr, parent_nwk=None)
    ]


@pytest.mark.parametrize(
    ("filter_address", "triggered"),
    [
        (None, True),
        (t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=NWK), True),
        (t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=OTHER_NWK), False),
        (t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=make_ieee()), False),
    ],
)
async def test_register_packet_callback_deprecated(app, filter_address, triggered):
    callback = MagicMock()

    with pytest.warns(DeprecationWarning, match="frame_listeners.subscribe"):
        cancel = app.register_packet_callback(filter_address, callback)

    packet = make_packet(data=READ_ATTRIBUTES_RSP)
    app.packet_received(packet)
    cancel()
    app.packet_received(packet)

    assert callback.mock_calls == ([call(packet)] if triggered else [])
