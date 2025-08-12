import pytest
import zigpy.types as t
from .async_mock import MagicMock
from .conftest import make_ieee


def make_packet(src_address=None, **overrides):
    """Build a packet."""
    defaults = {
        "src": src_address
        or t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
        "src_ep": 1,
        "dst": t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        "dst_ep": 1,
        "tsn": 123,
        "profile_id": 0x0104,
        "cluster_id": 0x0006,
        "data": t.SerializableBytes(b"test"),
        "lqi": 255,
        "rssi": -30,
    }
    defaults.update(overrides)
    return t.ZigbeePacket(**defaults)


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
async def test_packet_callback_address_filter(app, src_address, should_trigger):
    """Source address match."""
    filt = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234)
    cb = MagicMock()
    app.register_packet_callback(filt, cb)
    pkt = make_packet(src_address=src_address)
    app.notify_packet_callbacks(pkt)
    if should_trigger:
        cb.assert_called_once_with(pkt)
    else:
        cb.assert_not_called()


async def test_packet_callback_addr_mode_mismatch(app):
    """Address mode mismatch."""
    ieee = make_ieee()
    filt = t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=ieee)
    cb = MagicMock()
    app.register_packet_callback(filt, cb)
    pkt = make_packet(
        src_address=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234)
    )
    app.notify_packet_callbacks(pkt)
    cb.assert_not_called()


async def test_packet_callback_multiple_same_filter(app):
    """Multiple callbacks, cancel one."""
    addr = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x9ABC)
    cb1 = MagicMock()
    cb2 = MagicMock()
    cancel1 = app.register_packet_callback(addr, cb1)
    app.register_packet_callback(addr, cb2)
    pkt1 = make_packet(src_address=addr)
    app.notify_packet_callbacks(pkt1)
    cb1.assert_called_once_with(pkt1)
    cb2.assert_called_once_with(pkt1)
    cancel1()
    pkt2 = make_packet(src_address=addr, tsn=124)
    app.notify_packet_callbacks(pkt2)
    cb1.assert_called_once()
    assert cb2.call_count == 2
    cb2.assert_called_with(pkt2)


async def test_packet_callback_exception_global(app, caplog):
    """Exception isolation."""
    failing = MagicMock(side_effect=ValueError("boom"))
    ok = MagicMock()
    app.register_packet_callback(None, failing)
    app.register_packet_callback(None, ok)
    pkt = make_packet()
    app.notify_packet_callbacks(pkt)
    ok.assert_called_once_with(pkt)
    assert any("packet callback" in r.message.lower() for r in caplog.records)
