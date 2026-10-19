import logging

import pytest

from zigpy.listeners import Matcher, RawFrame
import zigpy.types as t

from .async_mock import MagicMock, call
from .conftest import make_ieee


@pytest.fixture
def base_packet():
    """Base ZigbeePacket to clone with .replace()."""
    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=1,
        tsn=123,
        profile_id=0x0104,
        cluster_id=0x0006,
        data=t.SerializableBytes(b"test"),
        lqi=255,
        rssi=-30,
    )


async def test_raw_frame_before_device_lookup(app, base_packet):
    """Raw frames are dispatched even for packets from unknown devices."""
    callback = MagicMock(return_value=None)
    unsubscribe = app.frame_listeners.subscribe(RawFrame, callback)

    with app.frame_listeners.wait_for(
        Matcher(RawFrame, lambda frame: frame.packet.tsn == base_packet.tsn)
    ) as future:
        app.packet_received(base_packet)

        assert (await future).packet == base_packet

    unsubscribe()

    # The callback was registered before the future, which only consumes the frame for
    # listeners after it
    assert callback.mock_calls == [call(RawFrame(packet=base_packet))]


@pytest.mark.parametrize(
    ("filter_address", "src_address", "should_trigger"),
    [
        (None, t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234), True),
        (
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
            True,
        ),
        (
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x5678),
            False,
        ),
        # Address mode mismatch
        (
            t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=make_ieee()),
            t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
            False,
        ),
    ],
)
async def test_register_packet_callback(
    app, base_packet, filter_address, src_address, should_trigger
):
    """The deprecated packet callback filters on the source address."""
    cb = MagicMock(return_value=None)

    with pytest.warns(DeprecationWarning, match="register_packet_callback"):
        cancel = app.register_packet_callback(filter_address, cb)

    pkt = base_packet.replace(src=src_address)
    app.frame_listeners.dispatch(RawFrame(packet=pkt))
    cancel()
    app.frame_listeners.dispatch(RawFrame(packet=pkt))

    assert cb.mock_calls == ([call(pkt)] if should_trigger else [])


async def test_packet_callback_multiple_same_filter(app, base_packet):
    """Multiple callbacks, cancel one."""
    addr = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x9ABC)
    cb1 = MagicMock(return_value=None)
    cb2 = MagicMock(return_value=None)

    with pytest.warns(DeprecationWarning, match="register_packet_callback"):
        cancel1 = app.register_packet_callback(addr, cb1)

    with pytest.warns(DeprecationWarning, match="register_packet_callback"):
        app.register_packet_callback(addr, cb2)

    pkt1 = base_packet.replace(src=addr, tsn=200)
    app.frame_listeners.dispatch(RawFrame(packet=pkt1))
    assert cb1.mock_calls == [call(pkt1)]
    assert cb2.mock_calls == [call(pkt1)]

    cancel1()
    pkt2 = base_packet.replace(src=addr, tsn=201)
    app.frame_listeners.dispatch(RawFrame(packet=pkt2))
    assert cb1.mock_calls == [call(pkt1)]
    assert cb2.mock_calls == [call(pkt1), call(pkt2)]


@pytest.mark.parametrize(
    "filter_address",
    [None, t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234)],
)
async def test_packet_callback_exception(app, base_packet, caplog, filter_address):
    """A failing callback does not stop the others."""
    failing = MagicMock(side_effect=ValueError("boom"))
    ok = MagicMock(return_value=None)

    with pytest.warns(DeprecationWarning, match="register_packet_callback"):
        app.register_packet_callback(filter_address, failing)

    with pytest.warns(DeprecationWarning, match="register_packet_callback"):
        app.register_packet_callback(filter_address, ok)

    with caplog.at_level(logging.WARNING):
        app.frame_listeners.dispatch(RawFrame(packet=base_packet))

    assert ok.mock_calls == [call(base_packet)]
    assert "boom" in caplog.text


async def test_notify_packet_callbacks(app, base_packet):
    """The deprecated notification dispatches a raw frame."""
    callback = MagicMock(return_value=None)
    app.frame_listeners.subscribe(RawFrame, callback)

    with pytest.warns(DeprecationWarning, match="notify_packet_callbacks"):
        app.notify_packet_callbacks(base_packet)

    assert callback.mock_calls == [call(RawFrame(packet=base_packet))]
