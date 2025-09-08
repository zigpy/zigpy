"""Classes to implement status of the application controller."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
import dataclasses
from dataclasses import InitVar
import functools
from typing import Any

import zigpy.config as conf
import zigpy.types as t
import zigpy.util
import zigpy.zdo.types as zdo_t

LOGICAL_TYPE_TO_JSON = {
    zdo_t.LogicalType.Coordinator: "coordinator",
    zdo_t.LogicalType.Router: "router",
    zdo_t.LogicalType.EndDevice: "end_device",
}


JSON_TO_LOGICAL_TYPE = {v: k for k, v in LOGICAL_TYPE_TO_JSON.items()}


@dataclasses.dataclass
class Key(t.BaseDataclassMixin):
    """APS/TC Link key."""

    key: t.KeyData = dataclasses.field(default_factory=lambda: t.KeyData.UNKNOWN)
    tx_counter: t.uint32_t = 0
    rx_counter: t.uint32_t = 0
    seq: t.uint8_t = 0
    partner_ieee: t.EUI64 = dataclasses.field(default_factory=lambda: t.EUI64.UNKNOWN)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": str(t.KeyData(self.key)),
            "tx_counter": self.tx_counter,
            "rx_counter": self.rx_counter,
            "seq": self.seq,
            "partner_ieee": str(self.partner_ieee),
        }

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> Key:
        return cls(
            key=t.KeyData.convert(obj["key"]),
            tx_counter=obj["tx_counter"],
            rx_counter=obj["rx_counter"],
            seq=obj["seq"],
            partner_ieee=t.EUI64.convert(obj["partner_ieee"]),
        )


@dataclasses.dataclass
class NodeInfo(t.BaseDataclassMixin):
    """Controller Application network Node information."""

    nwk: t.NWK = t.NWK(0xFFFE)
    ieee: t.EUI64 = dataclasses.field(default_factory=lambda: t.EUI64.UNKNOWN)
    logical_type: zdo_t.LogicalType = zdo_t.LogicalType.EndDevice

    # Device information
    model: str | None = None
    manufacturer: str | None = None
    version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "nwk": str(self.nwk)[2:],
            "ieee": str(self.ieee),
            "logical_type": LOGICAL_TYPE_TO_JSON[self.logical_type],
            "model": self.model,
            "manufacturer": self.manufacturer,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> NodeInfo:
        return cls(
            nwk=t.NWK.convert(obj["nwk"]),
            ieee=t.EUI64.convert(obj["ieee"]),
            logical_type=JSON_TO_LOGICAL_TYPE[obj["logical_type"]],
            model=obj["model"],
            manufacturer=obj["manufacturer"],
            version=obj["version"],
        )


@dataclasses.dataclass
class NetworkInfo(t.BaseDataclassMixin):
    """Network information."""

    extended_pan_id: t.ExtendedPanId = dataclasses.field(
        default_factory=lambda: t.ExtendedPanId.UNKNOWN
    )
    pan_id: t.PanId = t.PanId(0xFFFE)
    nwk_update_id: t.uint8_t = t.uint8_t(0x00)
    nwk_manager_id: t.NWK = t.NWK(0x0000)
    channel: t.uint8_t = 0
    channel_mask: t.Channels = t.Channels.NO_CHANNELS
    security_level: t.uint8_t = 0
    network_key: Key = dataclasses.field(default_factory=Key)
    tc_link_key: Key = dataclasses.field(
        default_factory=lambda: Key(
            key=conf.CONF_NWK_TC_LINK_KEY_DEFAULT,
            tx_counter=0,
            rx_counter=0,
            seq=0,
            partner_ieee=t.EUI64.UNKNOWN,
        )
    )
    key_table: list[Key] = dataclasses.field(default_factory=list)
    children: list[t.EUI64] = dataclasses.field(default_factory=list)

    # If exposed by the stack, NWK addresses of other connected devices on the network
    nwk_addresses: dict[t.EUI64, t.NWK] = dataclasses.field(default_factory=dict)

    # dict to keep track of stack-specific network information.
    # Z-Stack, for example, has a TCLK_SEED that should be backed up.
    stack_specific: dict[str, Any] = dataclasses.field(default_factory=dict)

    # Internal metadata not directly used for network restoration
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    # Package generating the network information
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "extended_pan_id": str(self.extended_pan_id),
            "pan_id": str(t.PanId(self.pan_id))[2:],
            "nwk_update_id": self.nwk_update_id,
            "nwk_manager_id": str(t.NWK(self.nwk_manager_id))[2:],
            "channel": self.channel,
            "channel_mask": list(self.channel_mask),
            "security_level": self.security_level,
            "network_key": self.network_key.as_dict(),
            "tc_link_key": self.tc_link_key.as_dict(),
            "key_table": [key.as_dict() for key in self.key_table],
            "children": sorted(str(ieee) for ieee in self.children),
            "nwk_addresses": {
                str(ieee): str(t.NWK(nwk))[2:]
                for ieee, nwk in sorted(self.nwk_addresses.items())
            },
            "stack_specific": self.stack_specific,
            "metadata": self.metadata,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> NetworkInfo:
        return cls(
            extended_pan_id=t.ExtendedPanId.convert(obj["extended_pan_id"]),
            pan_id=t.PanId.convert(obj["pan_id"]),
            nwk_update_id=obj["nwk_update_id"],
            nwk_manager_id=t.NWK.convert(obj["nwk_manager_id"]),
            channel=obj["channel"],
            channel_mask=t.Channels.from_channel_list(obj["channel_mask"]),
            security_level=obj["security_level"],
            network_key=Key.from_dict(obj["network_key"]),
            tc_link_key=Key.from_dict(obj["tc_link_key"]),
            key_table=sorted(
                (Key.from_dict(o) for o in obj["key_table"]),
                key=lambda k: k.partner_ieee,
            ),
            children=[t.EUI64.convert(ieee) for ieee in obj["children"]],
            nwk_addresses={
                t.EUI64.convert(ieee): t.NWK.convert(nwk)
                for ieee, nwk in obj["nwk_addresses"].items()
            },
            stack_specific=obj["stack_specific"],
            metadata=obj["metadata"],
            source=obj["source"],
        )


@dataclasses.dataclass
class Counter(t.BaseDataclassMixin):
    """Ever increasing Counter."""

    name: str
    initial_value: InitVar[int] = 0
    _raw_value: int = dataclasses.field(init=False, default=0)
    reset_count: int = dataclasses.field(init=False, default=0)
    _last_reset_value: int = dataclasses.field(init=False, default=0)

    def __eq__(self, other) -> bool:
        """Compare two counters."""
        if isinstance(other, self.__class__):
            return self.value == other.value

        return self.value == other

    def __int__(self) -> int:
        """Return int of the current value."""
        return self.value

    def __post_init__(self, initial_value: int) -> None:
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


@dataclasses.dataclass
class State:
    node_info: NodeInfo = dataclasses.field(default_factory=NodeInfo)
    network_info: NetworkInfo = dataclasses.field(default_factory=NetworkInfo)
    counters: CounterGroups = dataclasses.field(init=False, default=None)
    broadcast_counters: CounterGroups = dataclasses.field(init=False, default=None)
    device_counters: CounterGroups = dataclasses.field(init=False, default=None)
    group_counters: CounterGroups = dataclasses.field(init=False, default=None)

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
