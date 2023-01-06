import asyncio
import logging
from unittest import mock

import pytest

from zigpy import listeners
import zigpy.device
from zigpy.zcl import foundation
import zigpy.zcl.clusters.general


def make_hdr(cmd, **kwargs):
    return foundation.ZCLHeader.cluster(tsn=0x12, command_id=cmd.command.id, **kwargs)


query_next_image = zigpy.zcl.clusters.general.Ota.commands_by_name[
    "query_next_image"
].schema
on = zigpy.zcl.clusters.general.OnOff.commands_by_name["on"].schema
off = zigpy.zcl.clusters.general.OnOff.commands_by_name["off"].schema
toggle = zigpy.zcl.clusters.general.OnOff.commands_by_name["toggle"].schema


async def test_future_listener():
    listener = listeners.FutureListener(
        device=mock.Mock(spec_set=zigpy.device.Device),
        matchers=[
            query_next_image(manufacturer_code=0x1234),
            on(),
            lambda hdr, cmd: hdr.command_id == 0x02,
        ],
        future=asyncio.get_running_loop().create_future(),
    )

    assert not listener.resolve(make_hdr(off()), off())
    assert not listener.resolve(
        make_hdr(query_next_image()),
        query_next_image(
            field_control=0,
            manufacturer_code=0x5678,  # wrong `manufacturer_code`
            image_type=0x0000,
            current_file_version=0x00000000,
        ),
    )

    # Only `on()` matches
    assert listener.resolve(make_hdr(on()), on())
    assert listener.future.result() == (make_hdr(on()), on())

    # Subsequent matches will not work
    assert not listener.resolve(make_hdr(on()), on())

    # Reset the future
    object.__setattr__(listener, "future", asyncio.get_running_loop().create_future())
    valid_query = query_next_image(
        field_control=0,
        manufacturer_code=0x1234,  # correct `manufacturer_code`
        image_type=0x0000,
        current_file_version=0x00000000,
    )
    assert listener.resolve(make_hdr(valid_query), valid_query)
    assert listener.future.result() == (make_hdr(valid_query), valid_query)

    # Reset the future
    object.__setattr__(listener, "future", asyncio.get_running_loop().create_future())

    # Function matcher works
    assert listener.resolve(make_hdr(toggle()), toggle())
    assert listener.future.result() == (make_hdr(toggle()), toggle())


async def test_future_listener_cancellation():
    listener = listeners.FutureListener(
        device=mock.Mock(spec_set=zigpy.device.Device),
        matchers=[],
        future=asyncio.get_running_loop().create_future(),
    )

    assert listener.cancel()
    assert listener.cancel()
    assert listener.cancel()

    with pytest.raises(asyncio.CancelledError):
        await listener.future


async def test_callback_listener():
    listener = listeners.CallbackListener(
        device=mock.Mock(spec_set=zigpy.device.Device),
        matchers=[
            query_next_image(manufacturer_code=0x1234),
            on(),
        ],
        callback=mock.Mock(),
    )

    assert not listener.resolve(make_hdr(off()), off())
    assert not listener.resolve(
        make_hdr(query_next_image()),
        query_next_image(
            field_control=0,
            manufacturer_code=0x5678,  # wrong `manufacturer_code`
            image_type=0x0000,
            current_file_version=0x00000000,
        ),
    )

    # Only `on()` matches
    assert listener.resolve(make_hdr(on()), on())
    assert listener.callback.mock_calls == [mock.call(make_hdr(on()), on())]

    # Subsequent matches still work
    assert not listener.cancel()  # cancellation is not supported
    assert listener.resolve(make_hdr(on()), on())
    assert listener.callback.mock_calls == [
        mock.call(make_hdr(on()), on()),
        mock.call(make_hdr(on()), on()),
    ]


async def test_callback_listener_async():
    listener = listeners.CallbackListener(
        device=mock.Mock(spec_set=zigpy.device.Device),
        matchers=[
            on(),
        ],
        callback=mock.AsyncMock(),
    )

    assert not listener.resolve(make_hdr(off()), off())
    assert listener.resolve(make_hdr(on()), on())

    await asyncio.sleep(0.1)

    assert listener.callback.mock_calls == [mock.call(make_hdr(on()), on())]
    assert listener.callback.await_count == 1


async def test_callback_listener_error(caplog):
    listener = listeners.CallbackListener(
        device=mock.Mock(spec_set=zigpy.device.Device),
        matchers=[
            on(),
        ],
        callback=mock.Mock(side_effect=RuntimeError("Uh oh")),
    )

    with caplog.at_level(logging.WARNING):
        assert listener.resolve(make_hdr(on()), on())

    assert "Caught an exception while executing callback" in caplog.text
    assert "RuntimeError: Uh oh" in caplog.text
