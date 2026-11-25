"""Key/value stores for state that is not a ZCL attribute.

Quirks and applications keep device state here that has no ZCL attribute to live in,
such as Tuya datapoint values or locally stored settings. Values are plain JSON and the
store never interprets them. A `StoredValue` declaration gives a key its type, the way a
`ZCLAttributeDef` does for an attribute, and is the intended way to read and write.

There are two scopes with the same API: a `DeviceStore` per device, whose values follow
the device and are deleted when it is removed, and the application's `NetworkStore`, for
state that belongs to the network rather than to one device. Each scope has its own
events, emitted by `DeviceStores` and by the `NetworkStore` itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from typing import Any, Final, Generic, TypeAlias, TypeVar, overload

from zigpy.event import EventBase
import zigpy.types as t

LOGGER = logging.getLogger(__name__)

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)

T = TypeVar("T")
D = TypeVar("D")
E = TypeVar("E")

DEFAULT_VERSION: Final = 1


@dataclass(kw_only=True, frozen=True)
class StoreValueUpdatedEvent:
    """Event generated when a store value is set."""

    event_type: Final[str] = "store_value_updated"

    device_ieee: str
    namespace: str
    key: str
    value: JSONValue
    version: int
    last_updated: datetime


@dataclass(kw_only=True, frozen=True)
class StoreValueDeletedEvent:
    """Event generated when a store value is deleted."""

    event_type: Final[str] = "store_value_deleted"

    device_ieee: str
    namespace: str
    key: str


@dataclass(kw_only=True, frozen=True)
class NetworkStoreValueUpdatedEvent:
    """Event generated when a network store value is set."""

    event_type: Final[str] = "network_store_value_updated"

    namespace: str
    key: str
    value: JSONValue
    version: int
    last_updated: datetime


@dataclass(kw_only=True, frozen=True)
class NetworkStoreValueDeletedEvent:
    """Event generated when a network store value is deleted."""

    event_type: Final[str] = "network_store_value_deleted"

    namespace: str
    key: str


DeviceStoreEvent: TypeAlias = StoreValueUpdatedEvent | StoreValueDeletedEvent
NetworkStoreEvent: TypeAlias = (
    NetworkStoreValueUpdatedEvent | NetworkStoreValueDeletedEvent
)


@dataclass(kw_only=True, frozen=True)
class StoreItem:
    """A stored value with its row metadata."""

    value: JSONValue
    version: int
    last_updated: datetime


def normalize_json(value: Any) -> JSONValue:
    """Return `value` as it will read back after a JSON round trip.

    Raises `TypeError` for values JSON cannot encode and `ValueError` for NaN and
    infinity, so a caller storing a non-JSON value fails at the write site.
    """
    return json.loads(json.dumps(value, allow_nan=False))


def _identity(value: Any) -> Any:
    return value


@dataclass(frozen=True, kw_only=True)
class StoredValue(Generic[T]):
    """Typed declaration of a store key.

    `type` decodes the stored JSON into `T` and `encode` converts a `T` back to JSON.
    For ints, floats, strings and int enums, `type` is the class itself and `encode`
    can be left as the identity, since JSON encodes int subclasses as plain ints.

    A row whose `version` differs from the declaration is stale. It is passed to
    `migrate(old_version, value)` when provided, which returns the value in the
    current layout or `None` to drop it. Without `migrate`, the row is deleted.
    """

    namespace: str
    key: str
    type: Callable[[JSONValue], T]
    encode: Callable[[T], JSONValue] = _identity
    version: int = DEFAULT_VERSION
    migrate: Callable[[int, JSONValue], JSONValue | None] | None = None


class StoreNamespace:
    """Untyped key/value map within a store."""

    def __init__(self, store: Store[Any], name: str) -> None:
        self._store = store
        self.name = name
        self._items: dict[str, StoreItem] = {}

    def item(self, key: str) -> StoreItem:
        return self._items[key]

    def __getitem__(self, key: str) -> JSONValue:
        return self._items[key].value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def set(
        self,
        key: str,
        value: Any,
        *,
        version: int = DEFAULT_VERSION,
        last_updated: datetime | None = None,
    ) -> None:
        """Store a JSON value and emit `StoreValueUpdatedEvent`.

        `last_updated` defaults to now; a value carried over from elsewhere, such as a
        migrated attribute, can keep the time it was last updated there. It must be
        timezone-aware, like every stored time.

        A closed store (only a removed device's is) ignores the write, so code still
        holding a reference to a removed device cannot write rows for it.
        """
        value = normalize_json(value)

        if last_updated is not None and last_updated.utcoffset() is None:
            raise ValueError(f"`last_updated` must be timezone-aware: {last_updated!r}")

        if self._store.closed:
            LOGGER.debug(
                "[%s] Ignoring write of %s/%s to a closed store",
                self._store.log_name,
                self.name,
                key,
            )
            return

        item = StoreItem(
            value=value,
            version=version,
            last_updated=datetime.now(UTC) if last_updated is None else last_updated,
        )
        self._items[key] = item
        self._store._emit(
            self.name, key, self._store._updated_event(self.name, key, item)
        )

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        self.delete(key)

    def delete(self, key: str) -> None:
        """Delete a key and emit `StoreValueDeletedEvent`.

        Raises `KeyError` if the key is absent. A closed store ignores the delete.
        """
        if key not in self._items:
            raise KeyError(key)

        if self._store.closed:
            LOGGER.debug(
                "[%s] Ignoring delete of %s/%s from a closed store",
                self._store.log_name,
                self.name,
                key,
            )
            return

        del self._items[key]
        self._store._emit(self.name, key, self._store._deleted_event(self.name, key))

    def restore(
        self, key: str, value: JSONValue, *, version: int, last_updated: datetime
    ) -> None:
        """Load a persisted row without emitting an event."""
        self._items[key] = StoreItem(
            value=value, version=version, last_updated=last_updated
        )

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> Iterator[tuple[str, StoreItem]]:
        return iter(self._items.items())


class Store(Generic[E]):
    """Values of one scope, addressed by `StoredValue` declarations.

    `store[DECL]` reads, `store[DECL] = value` writes and `del store[DECL]` deletes.
    `namespace()` exposes the untyped map for keys that are only known at runtime.

    Reads return the stored JSON object itself: changing a list or dict in place
    neither emits an event nor persists it, so set the changed value again instead.

    Subclasses define the scope: the name used in log messages, the events emitted
    for a change, and where they are emitted.
    """

    log_name: str

    def __init__(self) -> None:
        super().__init__()
        self._namespaces: dict[str, StoreNamespace] = {}
        self._closed = False
        self._change_callbacks: dict[tuple[str, str], list[Callable[[E], None]]] = {}

    @property
    def closed(self) -> bool:
        """Whether the store ignores writes and deletes. Only a removed device's is."""
        return self._closed

    def _updated_event(self, namespace: str, key: str, item: StoreItem) -> E:
        raise NotImplementedError

    def _deleted_event(self, namespace: str, key: str) -> E:
        raise NotImplementedError

    def _emit_event(self, event: E) -> None:
        raise NotImplementedError

    def namespace(self, name: str) -> StoreNamespace:
        if name not in self._namespaces:
            self._namespaces[name] = StoreNamespace(self, name)

        return self._namespaces[name]

    def namespaces(self) -> Iterator[StoreNamespace]:
        return iter(self._namespaces.values())

    def _emit(self, namespace: str, key: str, event: E) -> None:
        self._emit_event(event)

        for callback in list(self._change_callbacks.get((namespace, key), ())):
            try:
                callback(event)
            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "[%s] Error calling store change callback %r for %s/%s",
                    self.log_name,
                    callback,
                    namespace,
                    key,
                )

    def _current_item(self, decl: StoredValue[T]) -> StoreItem:
        """Return the row for `decl` at its declared version, migrating a stale row."""
        namespace = self.namespace(decl.namespace)
        item = namespace.item(decl.key)

        if item.version == decl.version:
            return item

        if item.version > decl.version:
            # Written by newer code, e.g. before a downgrade. It reads as absent and is
            # kept, so upgrading again finds it unchanged.
            LOGGER.debug(
                "[%s] Ignoring %s/%s store value from a newer version (%d > %d)",
                self.log_name,
                decl.namespace,
                decl.key,
                item.version,
                decl.version,
            )
            raise KeyError(decl.key)

        if decl.migrate is None:
            LOGGER.warning(
                "[%s] Dropping stale %s/%s store value (version %d, expected %d): %r",
                self.log_name,
                decl.namespace,
                decl.key,
                item.version,
                decl.version,
                item.value,
            )
            del namespace[decl.key]
            raise KeyError(decl.key)

        migrated = decl.migrate(item.version, item.value)

        if migrated is None:
            del namespace[decl.key]
            raise KeyError(decl.key)

        if self.closed:
            # Nothing can be written back, but the caller still gets the current layout
            return StoreItem(
                value=normalize_json(migrated),
                version=decl.version,
                last_updated=item.last_updated,
            )

        namespace.set(decl.key, migrated, version=decl.version)
        return namespace.item(decl.key)

    def __getitem__(self, decl: StoredValue[T]) -> T:
        return decl.type(self._current_item(decl).value)

    @overload
    def get(self, decl: StoredValue[T]) -> T | None: ...

    @overload
    def get(self, decl: StoredValue[T], default: D) -> T | D: ...

    def get(self, decl: StoredValue[T], default: Any = None) -> Any:
        """Return the value, or `default` if it is absent or cannot be decoded.

        A value that cannot be decoded (a removed enum member, an unexpected type) is
        logged and kept, so that a single bad value cannot stop a device from loading.
        """
        try:
            return self[decl]
        except KeyError:
            return default
        except (TypeError, ValueError):
            LOGGER.warning(
                "[%s] Failed to decode %s/%s store value",
                self.log_name,
                decl.namespace,
                decl.key,
                exc_info=True,
            )
            return default

    def __setitem__(self, decl: StoredValue[T], value: T) -> None:
        self.set(decl, value)

    def set(
        self,
        decl: StoredValue[T],
        value: T,
        *,
        last_updated: datetime | None = None,
    ) -> None:
        """Set a value, like `store[decl] = value`, optionally with its update time."""
        self.namespace(decl.namespace).set(
            decl.key,
            decl.encode(value),
            version=decl.version,
            last_updated=last_updated,
        )

    def __delitem__(self, decl: StoredValue[Any]) -> None:
        del self.namespace(decl.namespace)[decl.key]

    def __contains__(self, decl: object) -> bool:
        if not isinstance(decl, StoredValue):
            return False

        try:
            self._current_item(decl)
        except KeyError:
            return False

        return True

    def last_updated(self, decl: StoredValue[Any]) -> datetime:
        return self._current_item(decl).last_updated

    def on_change(
        self, decl: StoredValue[Any], callback: Callable[[E], None]
    ) -> Callable[[], None]:
        """Call `callback` whenever the value for `decl` is set or deleted.

        Callbacks are held by this store. For a device store, they only fire for this
        device and stop with it: a device added again under the same IEEE gets a new
        store.
        """
        key = (decl.namespace, decl.key)
        callbacks = self._change_callbacks.setdefault(key, [])
        callbacks.append(callback)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                callbacks.remove(callback)

            if not callbacks and self._change_callbacks.get(key) is callbacks:
                del self._change_callbacks[key]

        return unsubscribe


class DeviceStore(Store[DeviceStoreEvent]):
    """The store of one device.

    `device.store[DECL]` reads, `device.store[DECL] = value` writes and
    `del device.store[DECL]` deletes. Values follow the device: they survive a
    re-interview and quirk replacement, and are deleted when the device is removed.
    """

    def __init__(self, stores: DeviceStores, ieee: t.EUI64) -> None:
        super().__init__()
        self._stores = stores
        self.ieee = ieee
        self.log_name = str(ieee)

    def close(self) -> None:
        """Stop accepting writes and deletes, for a device that is being removed."""
        self._closed = True

    def clear(self) -> None:
        """Drop all values and change callbacks from memory, without emitting events.

        Used once a removed device's rows are deleted. The network store has no
        equivalent: its values are only removed by deleting them.
        """
        # Namespaces handed out earlier must not keep reading the values either
        for namespace in self._namespaces.values():
            namespace._items.clear()

        self._namespaces.clear()
        self._change_callbacks.clear()

    def _updated_event(
        self, namespace: str, key: str, item: StoreItem
    ) -> StoreValueUpdatedEvent:
        return StoreValueUpdatedEvent(
            device_ieee=str(self.ieee),
            namespace=namespace,
            key=key,
            value=item.value,
            version=item.version,
            last_updated=item.last_updated,
        )

    def _deleted_event(self, namespace: str, key: str) -> StoreValueDeletedEvent:
        return StoreValueDeletedEvent(
            device_ieee=str(self.ieee), namespace=namespace, key=key
        )

    def _emit_event(self, event: DeviceStoreEvent) -> None:
        self._stores.emit(event.event_type, event)


class NetworkStore(Store[NetworkStoreEvent], EventBase):
    """The application's store for state that belongs to the network.

    `app.network_store[DECL]` reads and writes like a device store. Values have no
    lifecycle of their own: they stay until they are deleted, whatever happens to the
    devices. A value about one device keeps that device's IEEE in its key.

    Changes emit `NetworkStoreValueUpdatedEvent` and `NetworkStoreValueDeletedEvent` on
    this object, never on `DeviceStores`, so a device store listener sees no network
    values and the network events need no device field.

    The database subscribes to these events when it is loaded, at application start-up.
    A value set before that is not persisted, and is replaced by a persisted value of
    the same key.
    """

    log_name = "network"

    def _updated_event(
        self, namespace: str, key: str, item: StoreItem
    ) -> NetworkStoreValueUpdatedEvent:
        return NetworkStoreValueUpdatedEvent(
            namespace=namespace,
            key=key,
            value=item.value,
            version=item.version,
            last_updated=item.last_updated,
        )

    def _deleted_event(self, namespace: str, key: str) -> NetworkStoreValueDeletedEvent:
        return NetworkStoreValueDeletedEvent(namespace=namespace, key=key)

    def _emit_event(self, event: NetworkStoreEvent) -> None:
        self.emit(event.event_type, event)


class DeviceStores(EventBase):
    """All device stores of an application, keyed by IEEE address.

    Owned by the application rather than the device so the store survives a device
    object being replaced by a quirk. Store events are emitted here.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stores: dict[t.EUI64, DeviceStore] = {}
        # Closed stores of removed devices, until a device with that IEEE is added
        self._removed: dict[t.EUI64, DeviceStore] = {}

    def __getitem__(self, ieee: t.EUI64) -> DeviceStore:
        # Code still holding a removed device must not create an open store that a
        # device added again under the same IEEE would then inherit
        if ieee in self._removed:
            return self._removed[ieee]

        if ieee not in self._stores:
            self._stores[ieee] = DeviceStore(self, ieee)

        return self._stores[ieee]

    def get(self, ieee: t.EUI64) -> DeviceStore | None:
        """Return the store of `ieee` if it exists, without creating one."""
        return self._stores.get(ieee)

    def close(self, ieee: t.EUI64) -> None:
        """Stop accepting writes for a device that is being removed.

        A store is created if the device never used one, so that a first write while
        the removal is pending cannot create an open one.
        """
        self[ieee].close()

    def pop(self, ieee: t.EUI64) -> None:
        """Forget a removed device's store. References still held to it stay closed."""
        store = self._stores.pop(ieee, None) or DeviceStore(self, ieee)
        store.close()
        store.clear()
        self._removed[ieee] = store

    def discard(self, ieee: t.EUI64) -> None:
        """Forget the store of an IEEE that is not a device, like a blocked one."""
        self._stores.pop(ieee, None)

    def reopen(self, ieee: t.EUI64) -> None:
        """Give a device added under `ieee` a new store if the last one was closed."""
        self._removed.pop(ieee, None)

        if ieee in self._stores and self._stores[ieee].closed:
            del self._stores[ieee]

    def __contains__(self, ieee: object) -> bool:
        return ieee in self._stores

    def __iter__(self) -> Iterator[t.EUI64]:
        return iter(self._stores)

    def __len__(self) -> int:
        return len(self._stores)
