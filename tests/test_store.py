"""Tests for the per-device key/value store."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from unittest.mock import MagicMock, call

import pytest

from tests.conftest import make_ieee
from zigpy.store import (
    DEFAULT_VERSION,
    DeviceStores,
    StoredValue,
    StoreValueDeletedEvent,
    StoreValueUpdatedEvent,
    normalize_json,
)
import zigpy.types as t


class Mode(t.enum8):
    Off = 0
    Heat = 1


MODE = StoredValue(namespace="quirk:test", key="mode", type=Mode)
COUNT = StoredValue(namespace="quirk:test", key="count", type=int)
TIMESTAMP = StoredValue(
    namespace="quirk:test",
    key="timestamp",
    type=datetime.fromisoformat,
    encode=datetime.isoformat,
)


@pytest.fixture
def stores() -> DeviceStores:
    return DeviceStores()


@pytest.fixture
def listener(stores: DeviceStores) -> MagicMock:
    mock = MagicMock()
    stores.on_event(StoreValueUpdatedEvent.event_type, mock)
    stores.on_event(StoreValueDeletedEvent.event_type, mock)
    return mock


def test_namespace_mapping(stores: DeviceStores) -> None:
    ns = stores[make_ieee(1)].namespace("ns")

    assert len(ns) == 0
    assert "k" not in ns
    assert ns.get("k") is None
    assert ns.get("k", 5) == 5

    ns["k"] = 1
    ns.set("k2", 2, version=3)

    assert ns["k"] == 1
    assert ns.item("k").version == DEFAULT_VERSION
    assert ns.item("k2").version == 3
    assert isinstance(ns.item("k").last_updated, datetime)
    assert "k" in ns
    assert list(ns) == ["k", "k2"]
    assert len(ns) == 2
    assert [key for key, _ in ns.items()] == ["k", "k2"]

    del ns["k"]

    assert "k" not in ns

    with pytest.raises(KeyError):
        ns["k"]

    with pytest.raises(KeyError):
        del ns["k"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ((1, 2), [1, 2]),
        (Mode.Heat, 1),
        (t.uint8_t(5), 5),
        (t.Bool.true, 1),
        ({1: "a"}, {"1": "a"}),
        ({"a": [None, True, 1.5, "x"]}, {"a": [None, True, 1.5, "x"]}),
        ("x", "x"),
        (None, None),
    ],
)
def test_normalize_json(value, expected) -> None:
    result = normalize_json(value)

    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    ("value", "exception"),
    [
        (b"\x00", TypeError),
        (object(), TypeError),
        (datetime.now(UTC), TypeError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        ({"a": b"x"}, TypeError),
    ],
)
def test_normalize_json_rejects(value, exception) -> None:
    with pytest.raises(exception):
        normalize_json(value)


def test_events(stores: DeviceStores, listener: MagicMock) -> None:
    ieee = make_ieee(1)
    ns = stores[ieee].namespace("ns")

    ns.set("k", {"a": 1}, version=2)

    assert listener.mock_calls == [
        call(
            StoreValueUpdatedEvent(
                device_ieee=str(ieee),
                namespace="ns",
                key="k",
                value={"a": 1},
                version=2,
                last_updated=ns.item("k").last_updated,
            )
        )
    ]

    listener.reset_mock()
    del ns["k"]

    assert listener.mock_calls == [
        call(StoreValueDeletedEvent(device_ieee=str(ieee), namespace="ns", key="k"))
    ]


def test_restore_emits_nothing(stores: DeviceStores, listener: MagicMock) -> None:
    ns = stores[make_ieee(1)].namespace("ns")
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)

    ns.restore("k", [1, 2], version=4, last_updated=timestamp)

    assert len(listener.mock_calls) == 0
    assert ns["k"] == [1, 2]
    assert ns.item("k").version == 4
    assert ns.item("k").last_updated == timestamp


def test_typed_access(stores: DeviceStores) -> None:
    store = stores[make_ieee(1)]

    assert MODE not in store
    assert "not a declaration" not in store
    assert store.get(MODE) is None
    assert store.get(MODE, Mode.Off) == Mode.Off

    with pytest.raises(KeyError):
        store[MODE]

    with pytest.raises(KeyError):
        store.last_updated(MODE)

    store[MODE] = Mode.Heat

    raw = store.namespace("quirk:test")["mode"]
    assert raw == 1
    assert type(raw) is int

    assert MODE in store
    assert store[MODE] == Mode.Heat
    assert isinstance(store[MODE], Mode)
    assert isinstance(store.last_updated(MODE), datetime)
    assert COUNT not in store

    del store[MODE]

    assert MODE not in store


def test_typed_encode(stores: DeviceStores) -> None:
    store = stores[make_ieee(1)]
    timestamp = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)

    store[TIMESTAMP] = timestamp

    assert store.namespace("quirk:test")["timestamp"] == timestamp.isoformat()
    assert store[TIMESTAMP] == timestamp


def test_version_mismatch_without_migrate(
    stores: DeviceStores, listener: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]
    store.namespace("quirk:test").set("mode", 1, version=99)
    listener.reset_mock()

    with caplog.at_level(logging.WARNING):
        assert store.get(MODE) is None

    assert "Dropping stale quirk:test/mode store value" in caplog.text
    assert "mode" not in store.namespace("quirk:test")
    assert listener.mock_calls == [
        call(
            StoreValueDeletedEvent(
                device_ieee=str(ieee), namespace="quirk:test", key="mode"
            )
        )
    ]


@pytest.mark.parametrize(
    ("migrate", "expected"),
    [
        (lambda old_version, value: value * old_version, 40),
        (lambda old_version, value: None, None),
    ],
)
def test_version_mismatch_with_migrate(stores: DeviceStores, migrate, expected) -> None:
    decl = StoredValue(
        namespace="quirk:test", key="count", type=int, version=2, migrate=migrate
    )
    store = stores[make_ieee(1)]
    ns = store.namespace("quirk:test")
    ns.set("count", 4, version=10)

    assert store.get(decl) == expected

    if expected is None:
        assert "count" not in ns
    else:
        assert ns["count"] == expected
        assert ns.item("count").version == 2


def test_on_change(stores: DeviceStores) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]
    other_store = stores[make_ieee(2)]
    callback = MagicMock()

    unsubscribe = store.on_change(MODE, callback)

    other_store[MODE] = Mode.Heat
    store[COUNT] = 1
    store.namespace("other")["mode"] = 1

    assert len(callback.mock_calls) == 0

    store[MODE] = Mode.Off
    del store[MODE]

    assert callback.mock_calls == [
        call(
            StoreValueUpdatedEvent(
                device_ieee=str(ieee),
                namespace="quirk:test",
                key="mode",
                value=0,
                version=DEFAULT_VERSION,
                last_updated=callback.mock_calls[0].args[0].last_updated,
            )
        ),
        call(
            StoreValueDeletedEvent(
                device_ieee=str(ieee), namespace="quirk:test", key="mode"
            )
        ),
    ]

    callback.reset_mock()
    unsubscribe()
    store[MODE] = Mode.Heat

    assert len(callback.mock_calls) == 0


def test_stores_registry(stores: DeviceStores) -> None:
    ieee = make_ieee(1)

    assert ieee not in stores
    assert len(stores) == 0

    store = stores[ieee]

    assert stores[ieee] is store
    assert store.ieee == ieee
    assert ieee in stores
    assert list(stores) == [ieee]

    store[COUNT] = 1
    assert [ns.name for ns in store.namespaces()] == ["quirk:test"]

    stores.pop(ieee)
    stores.pop(ieee)

    assert ieee not in stores
    assert stores[ieee] is not store
