import pytest

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


@pytest.mark.parametrize(
    "filter_address",
    [
        None,
        t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
        t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=make_ieee()),
    ],
)
async def test_packet_callback_register_cancel(app, filter_address):
    """Register and cancel packet callback."""
    cb = MagicMock()
    cancel = app.register_packet_callback(filter_address, cb)
    assert cb in app._packet_callbacks[filter_address]
    cancel()
    assert cb not in app._packet_callbacks[filter_address]
    cancel()


@pytest.mark.parametrize(
    ("src_address", "should_trigger"),
    [
        (t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234), True),
        (t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x5678), False),
    ],
)
async def test_packet_callback_address_filter(
    app, base_packet, src_address, should_trigger
):
    """Source address match."""
    filt = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234)
    cb = MagicMock()
    app.register_packet_callback(filt, cb)
    pkt = base_packet.replace(src=src_address)
    app.notify_packet_callbacks(pkt)
    if should_trigger:
        assert cb.mock_calls == [call(pkt)]
    else:
        assert cb.mock_calls == []


async def test_packet_callback_addr_mode_mismatch(app, base_packet):
    """Address mode mismatch."""
    ieee = make_ieee()
    filt = t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=ieee)
    cb = MagicMock()
    app.register_packet_callback(filt, cb)
    app.notify_packet_callbacks(base_packet)
    assert cb.mock_calls == []


async def test_packet_callback_multiple_same_filter(app, base_packet):
    """Multiple callbacks, cancel one."""
    addr = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x9ABC)
    cb1 = MagicMock()
    cb2 = MagicMock()
    cancel1 = app.register_packet_callback(addr, cb1)
    app.register_packet_callback(addr, cb2)
    pkt1 = base_packet.replace(src=addr, tsn=200)
    app.notify_packet_callbacks(pkt1)
    assert cb1.mock_calls == [call(pkt1)]
    assert cb2.mock_calls == [call(pkt1)]
    cancel1()
    pkt2 = base_packet.replace(src=addr, tsn=201)
    app.notify_packet_callbacks(pkt2)
    assert cb1.mock_calls == [call(pkt1)]
    assert cb2.mock_calls == [call(pkt1), call(pkt2)]


async def test_packet_callback_exception_global(app, base_packet, caplog):
    """Exception isolation for global callbacks."""
    failing = MagicMock(side_effect=ValueError("boom"))
    ok = MagicMock()
    app.register_packet_callback(None, failing)
    app.register_packet_callback(None, ok)
    app.notify_packet_callbacks(base_packet)
    assert ok.mock_calls == [call(base_packet)]
    assert any("global packet callback" in r.message.lower() for r in caplog.records)


async def test_packet_callback_exception_address(app, base_packet, caplog):
    """Exception isolation for address-specific callbacks."""
    addr = base_packet.src
    failing = MagicMock(side_effect=ValueError("boom"))
    ok = MagicMock()
    app.register_packet_callback(addr, failing)
    app.register_packet_callback(addr, ok)
    app.notify_packet_callbacks(base_packet)
    assert ok.mock_calls == [call(base_packet)]
    assert any(
        "packet callback for address" in r.message.lower() for r in caplog.records
    )
