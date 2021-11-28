"""Classes to implement status of the application controller."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import InitVar, dataclass, field
import functools
from typing import Any

import zigpy.config as conf
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
        if self.partner_ieee is None:
            self.partner_ieee = t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff")


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
class NetworkInfo:
    """Network information."""

    extended_pan_id: t.ExtendedPanId | None = None
    pan_id: t.PanId | None = 0xFFFE
    nwk_update_id: t.uint8_t | None = 0x00
    nwk_manager_id: t.NWK | None = t.NWK(0x0000)
    channel: t.uint8_t | None = None
    channel_mask: t.Channels | None = None
    security_level: t.uint8_t | None = None
    network_key: t.KeyData | None = None
    network_key_seq: t.uint8_t | None = None
    network_key_counter: t.uint32_t | None = None
    tc_link_key: t.KeyData | None = None
    tc_address: t.EUI64 | None = None
    key_table: list[Key] | None = None
    children: list[t.EUI64] | None = None

    # If exposed by the stack, NWK addresses of other connected devices on the network
    nwk_addresses: dict[t.EUI64, t.NWK] | None = None

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
        if self.children is None:
            self.children = []
        if self.nwk_addresses is None:
            self.nwk_addresses = {}


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
    node_info: NodeInfo = field(default_factory=NodeInfo)
    network_info: NetworkInfo = field(default_factory=NetworkInfo)
    counters: CounterGroups | None = field(init=False, default=None)
    broadcast_counters: CounterGroups | None = field(init=False, default=None)
    device_counters: CounterGroups | None = field(init=False, default=None)
    group_counters: CounterGroups | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Initialize default counters."""
        for col_name in ("", "broadcast_", "device_", "group_"):
            setattr(self, f"{col_name}counters", CounterGroups())


LOGICAL_TYPE_TO_JSON = {
    zdo_t.LogicalType.Coordinator: "coordinator",
    zdo_t.LogicalType.Router: "router",
    zdo_t.LogicalType.EndDevice: "end_device",
}


JSON_TO_LOGICAL_TYPE = {v: k for k, v in LOGICAL_TYPE_TO_JSON.items()}


def network_state_to_json(
    *, network_info: NetworkInfo, node_info: NodeInfo, source: str = None
) -> dict[str, Any]:
    devices = {}

    for ieee, nwk in network_info.nwk_addresses.items():
        devices[ieee] = {
            "ieee_address": ieee.serialize()[::-1].hex(),
            "nwk_address": nwk.serialize()[::-1].hex(),
            "is_child": False,
        }

    for ieee in network_info.children:
        if ieee not in devices:
            devices[ieee] = {
                "ieee_address": ieee.serialize()[::-1].hex(),
                "nwk_address": None,
                "is_child": True,
            }
        else:
            devices[ieee]["is_child"] = True

    for key in network_info.key_table:
        if key.partner_ieee not in devices:
            devices[key.partner_ieee] = {
                "ieee_address": key.partner_ieee.serialize()[::-1].hex(),
                "nwk_address": None,
                "is_child": False,
            }

        devices[key.partner_ieee]["link_key"] = {
            "key": key.key.serialize().hex(),
            "tx_counter": key.tx_counter,
            "rx_counter": key.rx_counter,
        }

    return {
        "metadata": {
            "version": 1,
            "format": "zigpy/open-coordinator-backup",
            "source": source,
            "internal": {
                "node": {
                    "ieee": node_info.ieee.serialize()[::-1].hex(),
                    "nwk": node_info.nwk.serialize()[::-1].hex(),
                    "type": LOGICAL_TYPE_TO_JSON[node_info.logical_type],
                },
                "network": {
                    "tc_link_key": network_info.tc_link_key.serialize().hex(),
                    "tc_address": network_info.tc_address.serialize()[::-1].hex(),
                    "nwk_manager": network_info.nwk_manager_id.serialize()[::-1].hex(),
                },
                "link_key_seqs": {
                    key.partner_ieee.serialize()[::-1].hex(): key.seq
                    for key in network_info.key_table
                },
            },
        },
        "stack_specific": network_info.stack_specific,
        "coordinator_ieee": node_info.ieee.serialize()[::-1].hex(),
        "pan_id": network_info.pan_id.serialize()[::-1].hex(),
        "extended_pan_id": network_info.extended_pan_id.serialize()[::-1].hex(),
        "nwk_update_id": network_info.nwk_update_id,
        "security_level": network_info.security_level,
        "channel": network_info.channel,
        "channel_mask": list(network_info.channel_mask),
        "network_key": {
            "key": network_info.network_key.serialize().hex(),
            "sequence_number": network_info.network_key_seq or 0,
            "frame_counter": network_info.network_key_counter,
        },
        "devices": sorted(devices.values(), key=lambda d: d["ieee_address"]),
    }


def json_to_network_state(obj: dict[str, Any]) -> tuple[NetworkInfo, NodeInfo]:
    node_meta = obj["metadata"].get("internal", {}).get("node", {})

    node_info = NodeInfo()

    if "nwk" in node_meta:
        node_info.nwk, _ = t.NWK.deserialize(bytes.fromhex(node_meta["nwk"])[::-1])
    else:
        node_info.nwk = t.NWK(0x0000)

    node_info.logical_type = JSON_TO_LOGICAL_TYPE[node_meta.get("type", "coordinator")]

    # Should be identical to `metadata.internal.node.ieee`
    node_info.ieee, _ = t.EUI64.deserialize(
        bytes.fromhex(obj["coordinator_ieee"])[::-1]
    )

    network_meta = obj["metadata"].get("internal", {}).get("network", {})
    network_info = NetworkInfo()
    network_info.pan_id, _ = t.NWK.deserialize(bytes.fromhex(obj["pan_id"])[::-1])
    network_info.extended_pan_id, _ = t.EUI64.deserialize(
        bytes.fromhex(obj["extended_pan_id"])[::-1]
    )
    network_info.nwk_update_id = obj["nwk_update_id"]

    if "nwk_manager" in network_meta:
        network_info.nwk_manager_id, _ = t.NWK.deserialize(
            bytes.fromhex(network_meta["nwk_manager"])
        )
    else:
        network_info.nwk_manager_id = t.NWK(0x0000)

    network_info.channel = obj["channel"]
    network_info.channel_mask = t.Channels.from_channel_list(obj["channel_mask"])
    network_info.security_level = obj["security_level"]

    if obj.get("stack_specific"):
        network_info.stack_specific = obj.get("stack_specific")

    if "tc_link_key" in network_meta:
        network_info.tc_link_key, _ = t.KeyData.deserialize(
            bytes.fromhex(network_meta["tc_link_key"])
        )
    else:
        network_info.tc_link_key = conf.CONF_NWK_TC_LINK_KEY_DEFAULT

    if "tc_address" in network_meta:
        network_info.tc_address, _ = t.EUI64.deserialize(
            bytes.fromhex(network_meta["tc_address"])[::-1]
        )
    else:
        network_info.tc_address = node_info.ieee

    network_info.network_key, _ = t.KeyData.deserialize(
        bytes.fromhex(obj["network_key"]["key"])
    )
    network_info.network_key_counter = obj["network_key"]["frame_counter"]
    network_info.network_key_seq = obj["network_key"]["sequence_number"]

    network_info.children = []
    network_info.nwk_addresses = {}

    for device in obj["devices"]:
        if device["nwk_address"] is not None:
            nwk, _ = t.NWK.deserialize(bytes.fromhex(device["nwk_address"])[::-1])
        else:
            nwk = None

        ieee, _ = t.EUI64.deserialize(bytes.fromhex(device["ieee_address"])[::-1])

        # The `is_child` key is currently optional
        if device.get("is_child", True):
            network_info.children.append(ieee)

        if nwk is not None:
            network_info.nwk_addresses[ieee] = nwk

        if "link_key" in device:
            key = Key()
            key.key, _ = t.KeyData.deserialize(bytes.fromhex(device["link_key"]["key"]))
            key.tx_counter = device["link_key"]["tx_counter"]
            key.rx_counter = device["link_key"]["rx_counter"]
            key.partner_ieee = ieee

            try:
                key.seq = obj["metadata"]["internal"]["link_key_seqs"][
                    device["ieee_address"]
                ]
            except KeyError:
                key.seq = 0

            network_info.key_table.append(key)

        # XXX: Devices that are not children, have no NWK address, and have no link key
        #      are effectively ignored, since there is no place to write them

    return network_info, node_info
