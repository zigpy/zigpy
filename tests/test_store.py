"""Tests for the device and network key/value stores."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from tests.conftest import make_ieee
from zigpy.store import (
    DEFAULT_VERSION,
    DeviceStores,
    NetworkStore,
    NetworkStoreValueDeletedEvent,
    NetworkStoreValueUpdatedEvent,
    Store,
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


@pytest.fixture(params=["device", "network"])
def store(request: pytest.FixtureRequest, stores: DeviceStores) -> Store[Any]:
    """A store of either scope, for behaviour both share."""
    if request.param == "device":
        return stores[make_ieee(1)]

    return NetworkStore()


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

    ns.delete("k2")

    assert "k2" not in ns
    assert len(ns) == 0

    with pytest.raises(KeyError):
        ns.delete("k2")


def test_namespace_delete_event(stores: DeviceStores, listener: MagicMock) -> None:
    ieee = make_ieee(1)
    ns = stores[ieee].namespace("ns")
    ns["k"] = 1
    listener.reset_mock()

    ns.delete("k")

    assert listener.mock_calls == [
        call(StoreValueDeletedEvent(device_ieee=str(ieee), namespace="ns", key="k"))
    ]


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


def test_typed_access(store: Store[Any]) -> None:
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


def test_typed_encode(store: Store[Any]) -> None:
    timestamp = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)

    store[TIMESTAMP] = timestamp

    assert store.namespace("quirk:test")["timestamp"] == timestamp.isoformat()
    assert store[TIMESTAMP] == timestamp


def test_version_mismatch_without_migrate(
    stores: DeviceStores, listener: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]
    store.namespace("quirk:test").set("mode", 1, version=0)
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
        (lambda old_version, value: value * (old_version + 9), 40),
        (lambda old_version, value: None, None),
    ],
)
def test_version_mismatch_with_migrate(store: Store[Any], migrate, expected) -> None:
    decl = StoredValue(
        namespace="quirk:test", key="count", type=int, version=2, migrate=migrate
    )
    ns = store.namespace("quirk:test")
    ns.set("count", 4, version=1)

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


def test_closed_store_ignores_writes(stores: DeviceStores, listener: MagicMock) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]
    store[COUNT] = 1
    listener.reset_mock()

    stores.close(ieee)
    assert store.closed
    assert stores[ieee] is store

    store[COUNT] = 2
    del store[COUNT]
    store.namespace("other")["k"] = 1

    assert store[COUNT] == 1
    assert "k" not in store.namespace("other")
    assert listener.mock_calls == []

    # Values that cannot be stored are still rejected
    with pytest.raises(TypeError):
        store[COUNT] = object()


def test_pop_closes_store(stores: DeviceStores) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]

    assert stores.get(ieee) is store
    assert stores.get(make_ieee(2)) is None
    assert make_ieee(2) not in stores

    stores.pop(ieee)

    assert store.closed
    assert stores.get(ieee) is None
    assert stores[ieee] is store


def test_closed_store_migrates_without_writing(stores: DeviceStores) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]
    store.namespace("quirk:test").restore(
        "count", {"old": 5}, version=1, last_updated=datetime.now(UTC)
    )
    decl = StoredValue(
        namespace="quirk:test",
        key="count",
        type=int,
        version=2,
        migrate=lambda version, value: value["old"],
    )
    stores.close(ieee)

    assert store[decl] == 5
    assert decl in store
    assert store.namespace("quirk:test").item("count").version == 1


def test_closed_store_delete_missing_key(stores: DeviceStores) -> None:
    ieee = make_ieee(1)
    stores.close(ieee)
    assert stores[ieee].closed

    with pytest.raises(KeyError):
        del stores[ieee].namespace("ns")["missing"]


def test_reopen(stores: DeviceStores) -> None:
    ieee = make_ieee(1)
    store = stores[ieee]

    # An open store is kept
    stores.reopen(ieee)
    assert stores[ieee] is store

    # A store closed for a pending removal is replaced
    stores.close(ieee)
    stores.reopen(ieee)
    assert stores[ieee] is not store
    assert not stores[ieee].closed

    # A removed store stays reachable, closed and empty, until the IEEE is added again
    store = stores[ieee]
    store[COUNT] = 1
    namespace = store.namespace(COUNT.namespace)
    callback = MagicMock()
    store.on_change(COUNT, callback)
    stores.pop(ieee)
    assert stores[ieee] is store
    assert store.closed
    assert COUNT not in store
    assert COUNT.key not in namespace
    assert store._change_callbacks == {}

    stores.reopen(ieee)
    assert stores[ieee] is not store
    assert not stores[ieee].closed


def test_newer_version_kept(stores: DeviceStores, listener: MagicMock) -> None:
    """A value written by newer code reads as absent and is not deleted."""
    store = stores[make_ieee(1)]
    ns = store.namespace("quirk:test")
    ns.set("mode", 1, version=2)
    listener.reset_mock()

    migrate = MagicMock()
    decl = StoredValue(namespace="quirk:test", key="mode", type=Mode, migrate=migrate)

    assert decl not in store
    assert store.get(decl) is None

    with pytest.raises(KeyError):
        store[decl]

    assert ns.item("mode").version == 2
    assert migrate.mock_calls == []
    assert listener.mock_calls == []


@pytest.mark.parametrize("value", [None, "x", [1]])
def test_get_undecodable(
    store: Store[Any], caplog: pytest.LogCaptureFixture, value
) -> None:
    """A value that cannot be decoded is logged and kept, `get` returns the default."""
    store.namespace("quirk:test")["count"] = value

    with caplog.at_level(logging.WARNING):
        assert store.get(COUNT, 5) == 5

    assert "Failed to decode quirk:test/count store value" in caplog.text
    assert store.namespace("quirk:test")["count"] == value

    with pytest.raises((TypeError, ValueError)):
        store[COUNT]


def test_on_change_callback_error(
    stores: DeviceStores, listener: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing change callback does not stop other callbacks or persistence."""
    store = stores[make_ieee(1)]
    failing = MagicMock(side_effect=RuntimeError)
    callback = MagicMock()
    store.on_change(COUNT, failing)
    store.on_change(COUNT, callback)

    store[COUNT] = 1

    assert "Error calling store change callback" in caplog.text
    assert len(callback.mock_calls) == 1
    assert len(listener.mock_calls) == 1


def test_on_change_not_inherited(stores: DeviceStores) -> None:
    """Callbacks stay with the removed device's store."""
    ieee = make_ieee(1)
    callback = MagicMock()
    stores[ieee].on_change(COUNT, callback)

    stores.pop(ieee)
    stores.reopen(ieee)
    stores[ieee][COUNT] = 1

    assert callback.mock_calls == []


def test_on_change_unsubscribe_cleans_up(store: Store[Any]) -> None:
    unsub1 = store.on_change(COUNT, MagicMock())
    unsub2 = store.on_change(COUNT, MagicMock())

    unsub1()
    assert store._change_callbacks
    unsub2()
    unsub2()
    assert store._change_callbacks == {}


@pytest.fixture
def network_listener() -> tuple[NetworkStore, MagicMock]:
    network_store = NetworkStore()
    mock = MagicMock()
    network_store.on_event(NetworkStoreValueUpdatedEvent.event_type, mock)
    network_store.on_event(NetworkStoreValueDeletedEvent.event_type, mock)
    return network_store, mock


def test_network_store_events(
    stores: DeviceStores,
    listener: MagicMock,
    network_listener: tuple[NetworkStore, MagicMock],
) -> None:
    """Network values emit their own events on the network store only."""
    network_store, network_mock = network_listener
    ns = network_store.namespace("zigpy.groups")

    ns.set("next_id", 5, version=2)

    assert network_mock.mock_calls == [
        call(
            NetworkStoreValueUpdatedEvent(
                namespace="zigpy.groups",
                key="next_id",
                value=5,
                version=2,
                last_updated=ns.item("next_id").last_updated,
            )
        )
    ]

    network_mock.reset_mock()
    network_store[COUNT] = 1
    del network_store[COUNT]

    assert network_mock.mock_calls[1:] == [
        call(NetworkStoreValueDeletedEvent(namespace="quirk:test", key="count"))
    ]

    # Device store listeners see nothing of the network scope, and the reverse
    network_mock.reset_mock()
    stores[make_ieee(1)][COUNT] = 1

    assert listener.mock_calls[0].args[0].event_type == "store_value_updated"
    assert len(listener.mock_calls) == 1
    assert network_mock.mock_calls == []
    assert NetworkStoreValueUpdatedEvent.event_type != StoreValueUpdatedEvent.event_type
    assert NetworkStoreValueDeletedEvent.event_type != StoreValueDeletedEvent.event_type


def test_network_store_restore_emits_nothing(
    network_listener: tuple[NetworkStore, MagicMock],
) -> None:
    network_store, network_mock = network_listener
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)

    network_store.namespace("ns").restore("k", [1], version=3, last_updated=timestamp)

    assert network_mock.mock_calls == []
    assert network_store.namespace("ns").item("k").version == 3


def test_network_store_version_rules(
    network_listener: tuple[NetworkStore, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stale values are dropped with an event, newer ones are kept and read as absent."""
    network_store, network_mock = network_listener
    ns = network_store.namespace("quirk:test")
    ns.set("mode", 1, version=0)
    ns.set("count", 1, version=2)
    network_mock.reset_mock()

    with caplog.at_level(logging.WARNING):
        assert network_store.get(MODE) is None
        assert network_store.get(COUNT) is None

    assert "[network] Dropping stale quirk:test/mode store value" in caplog.text
    assert "mode" not in ns
    assert ns.item("count").version == 2
    assert COUNT not in network_store
    assert network_mock.mock_calls == [
        call(NetworkStoreValueDeletedEvent(namespace="quirk:test", key="mode"))
    ]


def test_network_store_on_change(stores: DeviceStores) -> None:
    network_store = NetworkStore()
    callback = MagicMock()
    unsubscribe = network_store.on_change(MODE, callback)

    # The same declaration in a device store is a different value
    stores[make_ieee(1)][MODE] = Mode.Heat
    network_store[COUNT] = 1

    assert callback.mock_calls == []

    network_store[MODE] = Mode.Heat

    assert callback.mock_calls == [
        call(
            NetworkStoreValueUpdatedEvent(
                namespace="quirk:test",
                key="mode",
                value=1,
                version=DEFAULT_VERSION,
                last_updated=network_store.last_updated(MODE),
            )
        )
    ]

    unsubscribe()
    del network_store[MODE]

    assert len(callback.mock_calls) == 1


def test_network_store_never_closed() -> None:
    network_store = NetworkStore()

    assert not network_store.closed
    assert not hasattr(network_store, "close")
    assert not hasattr(network_store, "clear")


def test_set_with_last_updated(store: Store[Any]) -> None:
    """A value carried over from elsewhere can keep its update time."""
    when = datetime(2026, 1, 2, tzinfo=UTC)

    store.set(COUNT, 3, last_updated=when)
    assert store[COUNT] == 3
    assert store.last_updated(COUNT) == when

    store.namespace("other").set("key", 1, last_updated=when)
    assert store.namespace("other").item("key").last_updated == when

    store.set(COUNT, 4)
    assert store.last_updated(COUNT) > when

    with pytest.raises(ValueError, match="timezone-aware"):
        store.set(COUNT, 5, last_updated=datetime(2026, 1, 2))

    assert store[COUNT] == 4


def test_set_with_last_updated_event(stores: DeviceStores, listener: MagicMock) -> None:
    when = datetime(2026, 1, 2, tzinfo=UTC)
    stores[make_ieee(1)].set(COUNT, 3, last_updated=when)

    (event,) = [c.args[0] for c in listener.mock_calls]
    assert event.last_updated == when
