"""Tests for Green Power Proxy Table management."""

from __future__ import annotations

from zigpy.zgp.proxy import GPProxyTable, GPProxyTableEntry
from zigpy.zgp.types import CommunicationMode, SecurityLevel


def test_creation():
    entry = GPProxyTableEntry(source_id=0x12345678, proxy_nwk=0x1234)
    assert entry.source_id == 0x12345678
    assert entry.proxy_nwk == 0x1234
    assert entry.communication_mode == CommunicationMode.UnicastLightweight
    assert entry.security_level == SecurityLevel.NoSecurity
    assert entry.frame_counter == 0


def test_touch_updates_last_seen():
    entry = GPProxyTableEntry(source_id=0x12345678, proxy_nwk=0x1234)
    first_seen = entry.last_seen
    entry.touch()
    # last_seen should be >= first_seen (same or later)
    assert entry.last_seen >= first_seen


def test_empty_table():
    table = GPProxyTable()
    assert len(table) == 0
    assert table.entries == []


def test_add_entry():
    table = GPProxyTable()
    entry = table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x1234)

    assert len(table) == 1
    assert entry.source_id == 0xAABBCCDD
    assert entry.proxy_nwk == 0x1234


def test_update_existing_entry():
    table = GPProxyTable()
    entry1 = table.add_or_update(
        source_id=0xAABBCCDD, proxy_nwk=0x1234, frame_counter=10
    )
    entry2 = table.add_or_update(
        source_id=0xAABBCCDD, proxy_nwk=0x1234, frame_counter=20
    )

    # Should be same entry, not a new one
    assert len(table) == 1
    assert entry1 is entry2
    assert entry2.frame_counter == 20


def test_update_doesnt_decrease_counter():
    table = GPProxyTable()
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x1234, frame_counter=20)
    entry = table.add_or_update(
        source_id=0xAABBCCDD, proxy_nwk=0x1234, frame_counter=10
    )

    assert entry.frame_counter == 20  # Should not decrease


def test_multiple_proxies_for_one_device():
    table = GPProxyTable()
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x1111)
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x2222)
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x3333)

    assert len(table) == 3
    proxies = table.get_proxies_for_device(0xAABBCCDD)
    assert set(proxies) == {0x1111, 0x2222, 0x3333}


def test_one_proxy_multiple_devices():
    table = GPProxyTable()
    table.add_or_update(source_id=0x11111111, proxy_nwk=0x1234)
    table.add_or_update(source_id=0x22222222, proxy_nwk=0x1234)

    assert len(table) == 2
    devices = table.get_devices_for_proxy(0x1234)
    assert set(devices) == {0x11111111, 0x22222222}


def test_remove_by_source_id():
    table = GPProxyTable()
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x1111)
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x2222)
    table.add_or_update(source_id=0x11111111, proxy_nwk=0x1111)

    removed = table.remove_by_source_id(0xAABBCCDD)

    assert removed == 2
    assert len(table) == 1
    assert table.get_proxies_for_device(0xAABBCCDD) == []
    assert table.get_proxies_for_device(0x11111111) == [0x1111]


def test_remove_by_source_id_nonexistent():
    table = GPProxyTable()
    removed = table.remove_by_source_id(0xDEADBEEF)
    assert removed == 0


def test_remove_by_proxy():
    table = GPProxyTable()
    table.add_or_update(source_id=0x11111111, proxy_nwk=0x1234)
    table.add_or_update(source_id=0x22222222, proxy_nwk=0x1234)
    table.add_or_update(source_id=0x11111111, proxy_nwk=0x5678)

    removed = table.remove_by_proxy(0x1234)

    assert removed == 2
    assert len(table) == 1
    assert table.get_devices_for_proxy(0x1234) == []


def test_remove_by_proxy_nonexistent():
    table = GPProxyTable()
    removed = table.remove_by_proxy(0x9999)
    assert removed == 0


def test_get_entry():
    table = GPProxyTable()
    table.add_or_update(source_id=0xAABBCCDD, proxy_nwk=0x1234)

    entry = table.get_entry(0xAABBCCDD, 0x1234)
    assert entry is not None
    assert entry.source_id == 0xAABBCCDD

    assert table.get_entry(0xDEADBEEF, 0x1234) is None
    assert table.get_entry(0xAABBCCDD, 0x9999) is None


def test_clear():
    table = GPProxyTable()
    table.add_or_update(source_id=0x11111111, proxy_nwk=0x1111)
    table.add_or_update(source_id=0x22222222, proxy_nwk=0x2222)

    table.clear()
    assert len(table) == 0


def test_repr():
    table = GPProxyTable()
    r = repr(table)
    assert r.startswith("<GPProxyTable")
    assert "0 entries" in r

    table.add_or_update(source_id=0x11111111, proxy_nwk=0x1111)
    assert "1 entry>" in repr(table)

    table.add_or_update(source_id=0x22222222, proxy_nwk=0x2222)
    assert "2 entries>" in repr(table)


def test_get_proxies_for_nonexistent_device():
    table = GPProxyTable()
    assert table.get_proxies_for_device(0xDEADBEEF) == []


def test_get_devices_for_nonexistent_proxy():
    table = GPProxyTable()
    assert table.get_devices_for_proxy(0x9999) == []
