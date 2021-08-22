"""Classes to implement status of the application controller."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import InitVar, dataclass, field
import functools
from typing import Any

import zigpy.types as t
import zigpy.zdo.types as zdo_t


@dataclass
class Key:
    """APS/TC Link key."""

    key: t.KeyData | None = None
    tx_counter: t.uint32_t | None = 0
    rx_counter: t.uin32_t | None = 0
    seq: t.uint8_t | None = 0
    partner_ieee: t.EUI64 | None = None

    def __post_init__(self) -> None:
        """Initialize instance."""
        if self.ieee is None:
            self.ieee = t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff")


@dataclass
class NodeInfo:
    """Controller Application network Node information."""

    nwk: t.NWK = t.NWK(0xFFFE)
    ieee: t.EUI64 | None = None
    logical_type: zdo_t.LogicalType | None = None

    def __post_init__(self) -> None:
        """Initialize instance."""
        if self.ieee is None:
            self.ieee = t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff")
        if self.logical_type is None:
            self.logical_type = zdo_t.LogicalType.Coordinator


@dataclass
class NetworkInformation:
    """Network information."""

    extended_pan_id: t.ExtendedPanId | None = None
    pan_id: t.PanId | None = 0xFFFE
    nwk_update_id: t.uint8_t | None = 0x00
    nwk_manager_id: t.NWK | None = t.NWK(0xFFFE)
    channel: t.uint8_t | None = None
    channel_mask: t.Channels | None = None
    security_level: t.uint8_t | None = None
    network_key: Key | None = None
    tc_link_key: Key | None = None
    key_table: list[Key] | None = None

    # Dict to keep track of stack-specific network stuff.
    # Z-Stack, for example, has a TCLK_SEED that should be backed up.
    stack_specific: dict[int | str, Any] | None = None

    def __post_init__(self) -> None:
        """Initialize instance."""
        if self.extended_pan_id is None:
            self.extended_pan_id = t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff")
        if self.key_table is None:
            self.key_table = []
        if self.stack_specific is None:
            self.stack_specific = {}


@dataclass
class Counter:
    """Ever increasing Counter."""

    name: str
    initial_value: InitVar[int] = 0
    _raw_value: int = field(init=False, default=0)
    reset_count: int = field(init=False, default=0)
    _last_reset_value: int = field(init=False, default=0)

    def __eq__(self, other) -> bool:
        """Compare two counters."""
        if isinstance(other, self.__class__):
            return self.value == other.value

        return self.value == other

    def __int__(self) -> int:
        """Return int of the current value."""
        return self.value

    def __post_init__(self, initial_value) -> None:
        """Initialize instance."""
        self._raw_value = initial_value

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name} = {self.value}"

    @property
    def value(self) -> int:
        """Current value of the counter."""

        return self._last_reset_value + self._raw_value

    def update(self, new_value: int) -> None:
        """Update counter value."""

        if new_value == self._raw_value:
            return

        diff = new_value - self._raw_value
        if diff < 0:  # Roll over or reset
            self.reset_and_update(new_value)
            return

        self._raw_value = new_value

    def increment(self, increment: int = 1) -> None:
        """Increment current value by increment."""

        assert increment >= 0
        self._raw_value += increment

    def reset_and_update(self, value: int) -> None:
        """Clear (rollover event) and optionally update."""

        self._last_reset_value = self.value
        self._raw_value = value
        self.reset_count += 1

    reset = functools.partialmethod(reset_and_update, 0)


class CounterGroup(dict):
    """Named collection of related counters."""

    def __init__(
        self,
        collection_name: str | None = None,
    ) -> None:
        """Initialize instance."""

        self._name: str | None = collection_name
        super().__init__()

    def counters(self) -> Iterable[Counter]:
        """Return an iterable of the counters"""
        return (counter for counter in self.values() if isinstance(counter, Counter))

    def groups(self) -> Iterable[CounterGroup]:
        """Return an iterable of the counter groups"""
        return (group for group in self.values() if isinstance(group, CounterGroup))

    def tags(self) -> Iterable[int | str]:
        """Return an iterable if tags"""
        return (group.name for group in self.groups())

    def __missing__(self, counter_id: Any) -> Counter:
        """Default counter factory."""

        counter = Counter(counter_id)
        self[counter_id] = counter
        return counter

    def __repr__(self) -> str:
        """Representation magic method."""
        counters = (
            f"{counter.__class__.__name__}('{counter.name}', {int(counter)})"
            for counter in self.counters()
        )
        counters = ", ".join(counters)
        return f"{self.__class__.__name__}('{self.name}', {{{counters}}})"

    def __str__(self) -> str:
        """String magic method."""
        counters = [str(counter) for counter in self.counters()]
        return f"{self.name}: [{', '.join(counters)}]"

    @property
    def name(self) -> str:
        """Return counter collection name."""
        return self._name

    def increment(self, name: int | str, *tags: int | str) -> None:
        """Create and Update all counters recursively."""

        if tags:
            tag, *rest = tags
            self.setdefault(tag, CounterGroup(tag))
            self[tag][name].increment()
            self[tag].increment(name, *rest)
            return

    def reset(self) -> None:
        """Clear and rollover counters."""

        for counter in self.values():
            counter.reset()


class CounterGroups(dict):
    """A collection of unrelated counter groups in a dict."""

    def __iter__(self) -> Iterable[CounterGroup]:
        """Return an iterable of the counters"""
        return (counter_group for counter_group in self.values())

    def __missing__(self, counter_group_name: Any) -> CounterGroup:
        """Default counter factory."""

        counter_group = CounterGroup(counter_group_name)
        super().__setitem__(counter_group_name, counter_group)
        return counter_group


@dataclass
class State:
    node_information: NodeInfo = field(default_factory=NodeInfo)
    network_information: NetworkInformation = field(default_factory=NetworkInformation)
    counters: CounterGroups | None = field(init=False, default=None)
    broadcast_counters: CounterGroups | None = field(init=False, default=None)
    device_counters: CounterGroups | None = field(init=False, default=None)
    group_counters: CounterGroups | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Initialize default counters."""
        for col_name in ("", "broadcast_", "device_", "group_"):
            setattr(self, f"{col_name}counters", CounterGroups())
