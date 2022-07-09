"""Classes to implement status of the application controller."""

from __future__ import annotations

from collections.abc import Iterable
import dataclasses
from dataclasses import InitVar, field
import functools
from typing import (  # `Dict as Dict` so pyupgrade doesn't try to upgrade it
    Any,
    Dict as Dict,
    Iterator,
    List as List,
    Optional as Optional,
)

from pydantic.dataclasses import dataclass

import zigpy.config as conf
import zigpy.types as t
import zigpy.util
import zigpy.zdo.types as zdo_t


@dataclass
class Key:
    """APS/TC Link key."""

    key: t.KeyData = field(default_factory=lambda: t.KeyData.UNKNOWN)
    tx_counter: t.uint32_t = 0
    rx_counter: t.uint32_t = 0
    seq: t.uint8_t = 0
    partner_ieee: t.EUI64 = field(default_factory=lambda: t.EUI64.UNKNOWN)

    def replace(self, **kwargs) -> Key:
        return dataclasses.replace(self, **kwargs)


@dataclass
class NodeInfo:
    """Controller Application network Node information."""

    nwk: t.NWK = t.NWK(0xFFFE)
    ieee: t.EUI64 = field(default_factory=lambda: t.EUI64.UNKNOWN)
    logical_type: zdo_t.LogicalType = zdo_t.LogicalType.EndDevice

    def replace(self, **kwargs) -> NodeInfo:
        return dataclasses.replace(self, **kwargs)


@dataclass
class NetworkInfo:
    """Network information."""

    extended_pan_id: t.ExtendedPanId = field(
        default_factory=lambda: t.ExtendedPanId.UNKNOWN
    )
    pan_id: t.PanId = t.PanId(0xFFFE)
    nwk_update_id: t.uint8_t = t.uint8_t(0x00)
    nwk_manager_id: t.NWK = t.NWK(0x0000)
    channel: t.uint8_t = 0
    channel_mask: t.Channels = t.Channels.NO_CHANNELS
    security_level: t.uint8_t = 0
    network_key: Key = field(default_factory=Key)
    tc_link_key: Key = field(
        default_factory=lambda: Key(
            key=conf.CONF_NWK_TC_LINK_KEY_DEFAULT,
            tx_counter=0,
            rx_counter=0,
            seq=0,
            partner_ieee=t.EUI64.UNKNOWN,
        )
    )
    key_table: List[Key] = field(default_factory=list)
    children: List[t.EUI64] = field(default_factory=list)

    # If exposed by the stack, NWK addresses of other connected devices on the network
    nwk_addresses: Dict[t.EUI64, t.NWK] = field(default_factory=dict)

    # Dict to keep track of stack-specific network information.
    # Z-Stack, for example, has a TCLK_SEED that should be backed up.
    stack_specific: Dict[str, Any] = field(default_factory=dict)

    # Internal metadata not directly used for network restoration
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Package generating the network information
    source: Optional[str] = None  # pyupgrade: noqa

    def replace(self, **kwargs) -> NetworkInfo:
        return dataclasses.replace(self, **kwargs)


@dataclass
class Counter:
    """Ever increasing Counter."""

    name: str
    initial_value: InitVar[int] = 0
    raw_value: int = field(init=False, default=0)
    reset_count: int = field(init=False, default=0)
    last_reset_value: int = field(init=False, default=0)

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
        self.raw_value = initial_value

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name} = {self.value}"

    @property
    def value(self) -> int:
        """Current value of the counter."""

        return self.last_reset_value + self.raw_value

    def update(self, new_value: int) -> None:
        """Update counter value."""

        if new_value == self.raw_value:
            return

        diff = new_value - self.raw_value
        if diff < 0:  # Roll over or reset
            self.reset_and_update(new_value)
            return

        self.raw_value = new_value

    def increment(self, increment: int = 1) -> None:
        """Increment current value by increment."""

        assert increment >= 0
        self.raw_value += increment

    def reset_and_update(self, value: int) -> None:
        """Clear (rollover event) and optionally update."""

        self.last_reset_value = self.value
        self.raw_value = value
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
        return self._name if self._name is not None else "No Name"

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

    def __iter__(self) -> Iterator[CounterGroup]:
        """Return an iterable of the counters"""
        return iter(self.values())

    def __missing__(self, counter_group_name: Any) -> CounterGroup:
        """Default counter factory."""

        counter_group = CounterGroup(counter_group_name)
        super().__setitem__(counter_group_name, counter_group)
        return counter_group


@dataclass
class State:
    node_info: NodeInfo = field(default_factory=NodeInfo)
    network_info: NetworkInfo = field(default_factory=NetworkInfo)
    counters: CounterGroups = field(init=False, default=None)
    broadcast_counters: CounterGroups = field(init=False, default=None)
    device_counters: CounterGroups = field(init=False, default=None)
    group_counters: CounterGroups = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Initialize default counters."""
        for col_name in ("", "broadcast_", "device_", "group_"):
            setattr(self, f"{col_name}counters", CounterGroups())

    @property
    @zigpy.util.deprecated("`network_information` has been renamed to `network_info`")
    def network_information(self) -> NetworkInfo:
        return self.network_info

    @property
    @zigpy.util.deprecated("`node_information` has been renamed to `node_info`")
    def node_information(self) -> NodeInfo:
        return self.node_info
