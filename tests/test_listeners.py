import asyncio
import logging
from unittest import mock

import pytest

from tests.conftest import make_ieee
from zigpy.listeners import (
    ANY_DEVICE,
    RawFrame,
    ZCLFrame,
    ZDOFrame,
    legacy_subscribe,
    legacy_wait_for,
    zcl_command,
)
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import OnOff, Ota
import zigpy.zdo.types as zdo_t

PACKET = t.ZigbeePacket(
    src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
    src_ep=1,
    dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
    dst_ep=1,
    tsn=0x12,
    profile_id=260,
    cluster_id=OnOff.cluster_id,
    data=t.SerializableBytes(b""),
)


def zcl_frame(device, command_def: foundation.ZCLCommandDef, **kwargs) -> ZCLFrame:
    return ZCLFrame(
        device=device,
        packet=PACKET,
        header=foundation.ZCLHeader.cluster(tsn=0x12, command_id=command_def.id),
        command=command_def.schema(**kwargs),
    )


def zdo_frame(device) -> ZDOFrame:
    return ZDOFrame(
        device=device,
        packet=PACKET,
        header=zdo_t.ZDOHeader(command_id=zdo_t.ZDOCmd.NWK_addr_req, tsn=0x01),
        command=[0x0000],
    )


@pytest.fixture
def dev(app):
    return app.add_device(nwk=0x1234, ieee=make_ieee(1))


@pytest.mark.parametrize(
    ("ieee", "called"),
    [
        # Any device
        (None, True),
        # This device
        (make_ieee(1), True),
        # Another device
        (make_ieee(2), False),
    ],
)
async def test_subscribe_device(app, dev, ieee, called):
    callback = mock.Mock(return_value=None)
    app.frame_listeners.subscribe(ZCLFrame, callback, ieee=ieee)

    frame = zcl_frame(dev, OnOff.ServerCommandDefs.on)
    app.frame_listeners.dispatch(frame)

    assert callback.mock_calls == ([mock.call(frame)] if called else [])


async def test_subscribe_follows_ieee(app, dev):
    """A listener matches every object with the device's IEEE address."""
    callback = mock.Mock(return_value=None)
    app.frame_listeners.subscribe(ZCLFrame, callback, ieee=dev.ieee)

    # For example the shadow device of a re-interview
    shadow = type(dev)(app, dev.ieee, dev.nwk)
    frame = zcl_frame(shadow, OnOff.ServerCommandDefs.on)
    app.frame_listeners.dispatch(frame)

    assert callback.mock_calls == [mock.call(frame)]


async def test_subscribe_frame_type(app, dev):
    """Listeners only receive frames of the type they subscribed to."""
    callback = mock.Mock(return_value=None)
    app.frame_listeners.subscribe(ZDOFrame, callback)

    app.frame_listeners.dispatch(zcl_frame(dev, OnOff.ServerCommandDefs.on))
    app.frame_listeners.dispatch(RawFrame(packet=PACKET))

    assert callback.mock_calls == []


@pytest.mark.parametrize(
    ("command_def", "called"),
    [
        (OnOff.ServerCommandDefs.on, True),
        (OnOff.ServerCommandDefs.off, False),
    ],
)
async def test_subscribe_zcl_command(app, dev, command_def, called):
    callback = mock.Mock(return_value=None)
    app.frame_listeners.subscribe(zcl_command(OnOff.ServerCommandDefs.on), callback)

    frame = zcl_frame(dev, command_def)
    app.frame_listeners.dispatch(frame)

    assert callback.mock_calls == ([mock.call(frame)] if called else [])


async def test_unsubscribe(app, dev):
    callback = mock.Mock(return_value=None)
    unsubscribe = app.frame_listeners.subscribe(ZCLFrame, callback)
    unsubscribe()

    app.frame_listeners.dispatch(zcl_frame(dev, OnOff.ServerCommandDefs.on))

    assert callback.mock_calls == []


async def test_callback_unsubscribes_itself(app, dev):
    """A callback can remove its own listener while frames are dispatched."""
    calls = []

    def callback(frame):
        calls.append(frame)
        unsubscribe()

    unsubscribe = app.frame_listeners.subscribe(ZCLFrame, callback)
    app.frame_listeners.subscribe(ZCLFrame, calls.append)

    frame = zcl_frame(dev, OnOff.ServerCommandDefs.on)
    app.frame_listeners.dispatch(frame)
    app.frame_listeners.dispatch(frame)

    assert calls == [frame, frame, frame]


async def test_wait_for(app, dev):
    with app.frame_listeners.wait_for(
        zcl_command(OnOff.ServerCommandDefs.on), ieee=dev.ieee
    ) as future:
        app.frame_listeners.dispatch(zcl_frame(dev, OnOff.ServerCommandDefs.off))
        assert not future.done()

        frame = zcl_frame(dev, OnOff.ServerCommandDefs.on)
        app.frame_listeners.dispatch(frame)

        assert await future == frame

    # The listener is gone, with nothing left to resolve
    app.frame_listeners.dispatch(frame)


async def test_wait_for_consumes(app, dev):
    """Futures resolve in order, and a resolved one consumes the frame."""
    callback = mock.Mock(return_value=None)

    # Listeners for any device come first
    with (
        app.frame_listeners.wait_for(ZCLFrame, ieee=dev.ieee) as device_future,
        app.frame_listeners.wait_for(ZCLFrame) as any_future1,
        app.frame_listeners.wait_for(ZCLFrame) as any_future2,
    ):
        app.frame_listeners.subscribe(ZCLFrame, callback, ieee=dev.ieee)

        frames = [zcl_frame(dev, OnOff.ServerCommandDefs.on) for _ in range(4)]

        for frame in frames:
            app.frame_listeners.dispatch(frame)

        assert any_future1.result() is frames[0]
        assert any_future2.result() is frames[1]
        assert device_future.result() is frames[2]

    # The callback after the device future only sees what the futures did not consume
    assert callback.mock_calls == [mock.call(frames[3])]


async def test_callback_exception_logged(app, dev, caplog):
    def failing(frame):
        raise ValueError("Boom!")

    callback = mock.Mock(return_value=None)
    app.frame_listeners.subscribe(ZCLFrame, failing)
    app.frame_listeners.subscribe(ZCLFrame, callback)

    frame = zcl_frame(dev, OnOff.ServerCommandDefs.on)

    with caplog.at_level(logging.WARNING):
        app.frame_listeners.dispatch(frame)

    assert callback.mock_calls == [mock.call(frame)]
    assert "Frame callback" in caplog.text
    assert "Boom!" in caplog.text


@pytest.mark.parametrize("fail", [False, True])
async def test_async_callback(app, dev, caplog, fail):
    """A coroutine returned by a callback runs as a task, its exception is logged."""
    calls = []

    async def callback(frame):
        await asyncio.sleep(0)
        calls.append(frame)

        if fail:
            raise ValueError("Boom!")

    app.frame_listeners.subscribe(ZCLFrame, callback)

    frame = zcl_frame(dev, OnOff.ServerCommandDefs.on)

    with caplog.at_level(logging.WARNING):
        app.frame_listeners.dispatch(frame)
        assert calls == []

        await asyncio.gather(
            *(
                task
                for task in asyncio.all_tasks()
                if task.get_name().startswith("frame_callback")
            )
        )

    assert calls == [frame]
    assert ("Boom!" in caplog.text) is fail


@pytest.mark.parametrize(
    ("frame_factory", "called"),
    [
        # Field values do not matter, only the command
        (
            lambda dev: zcl_frame(
                dev,
                Ota.ServerCommandDefs.query_next_image,
                field_control=0,
                manufacturer_code=0x5678,
                image_type=0x0000,
                current_file_version=0x00000000,
            ),
            True,
        ),
        (lambda dev: zcl_frame(dev, OnOff.ServerCommandDefs.on), True),
        (lambda dev: zcl_frame(dev, OnOff.ServerCommandDefs.toggle), True),
        (lambda dev: zcl_frame(dev, OnOff.ServerCommandDefs.off), False),
        # A command schema never matches ZDO
        (zdo_frame, False),
    ],
)
async def test_legacy_matchers(app, dev, frame_factory, called):
    callback = mock.Mock(return_value=None)
    legacy_subscribe(
        app.frame_listeners,
        ANY_DEVICE,
        [
            Ota.ServerCommandDefs.query_next_image.schema(manufacturer_code=0x1234),
            OnOff.ServerCommandDefs.on.schema(),
            lambda hdr, cmd: hdr.command_id == OnOff.ServerCommandDefs.toggle.id,
        ],
        callback,
    )

    frame = frame_factory(dev)
    app.frame_listeners.dispatch(frame)

    assert callback.mock_calls == (
        [mock.call(frame.header, frame.command)] if called else []
    )


async def test_legacy_zdo(app, dev):
    """Legacy listeners receive ZDO frames, as a header and an argument list."""
    callback = mock.Mock(return_value=None)
    remove = legacy_subscribe(
        app.frame_listeners, dev, [lambda hdr, cmd: True], callback
    )

    frame = zdo_frame(dev)
    app.frame_listeners.dispatch(frame)
    remove()
    app.frame_listeners.dispatch(frame)

    assert callback.mock_calls == [mock.call(frame.header, [0x0000])]


async def test_legacy_wait_for(app, dev):
    with legacy_wait_for(
        app.frame_listeners, dev, [OnOff.ServerCommandDefs.on.schema()]
    ) as future:
        frame = zcl_frame(dev, OnOff.ServerCommandDefs.on)
        app.frame_listeners.dispatch(frame)

        assert await future == (frame.header, frame.command)
