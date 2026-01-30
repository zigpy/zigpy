from __future__ import annotations

import collections
from collections import defaultdict
from collections.abc import Generator, Iterable, Sequence
import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
import enum
import functools
import itertools
import logging
import types
from typing import TYPE_CHECKING, Any, Final
import warnings

from zigpy import util
from zigpy.const import APS_REPLY_TIMEOUT
from zigpy.event import EventBase
import zigpy.types as t
from zigpy.typing import UNDEFINED, UndefinedType
from zigpy.zcl import foundation
from zigpy.zcl.foundation import BaseAttributeDefs, BaseCommandDefs, CommandSchema

from .helpers import AttributeCache, ReportingConfig, UnsupportedAttribute

if TYPE_CHECKING:
    from zigpy.endpoint import Endpoint


LOGGER = logging.getLogger(__name__)

# Tracks (cluster_id, attrid) pairs for which AttributeUpdatedEvent should be suppressed.
# Used during Report_Attributes handling to allow quirks that update other clusters or
# other attributes to emit their own events while suppressing the direct report's event.
_suppressed_attribute_updates: ContextVar[frozenset[tuple[int, int]]] = ContextVar(
    "_suppressed_attribute_updates", default=frozenset()
)


@contextlib.contextmanager
def _suppress_attribute_update_event(
    cluster_id: int, attrid: int
) -> Generator[None, None, None]:
    """Suppress AttributeUpdatedEvent for a specific (cluster, attribute) pair."""
    current = _suppressed_attribute_updates.get()
    token = _suppressed_attribute_updates.set(current | {(cluster_id, attrid)})

    try:
        yield
    finally:
        _suppressed_attribute_updates.reset(token)


class ClusterType(enum.IntEnum):
    Server = 0
    Client = 1


@dataclass(kw_only=True, frozen=True)
class AttributeReadEvent:
    """Event generated when an attribute has been read."""

    event_type: Final[str] = "attribute_read"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str
    attribute_id: int
    manufacturer_code: int
    raw_value: Any | None
    value: Any | None


@dataclass(kw_only=True, frozen=True)
class AttributeReportedEvent:
    """Event generated when an attribute has been reported."""

    event_type: Final[str] = "attribute_report"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str | None
    attribute_id: int
    manufacturer_code: int
    raw_value: Any | None
    value: Any


@dataclass(kw_only=True, frozen=True)
class AttributeWrittenEvent:
    """Event generated when an attribute is written."""

    event_type: Final[str] = "attribute_written"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str
    attribute_id: int
    manufacturer_code: int | None
    value: Any | None
    status: foundation.Status


@dataclass(kw_only=True, frozen=True)
class AttributeUpdatedEvent:
    """Event generated when an attribute has been updated externally (deprecated)."""

    event_type: Final[str] = "attribute_updated"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str | None
    attribute_id: int
    manufacturer_code: int
    value: Any


@dataclass(kw_only=True, frozen=True)
class AttributeUnsupportedEvent:
    """Event generated when an attribute is found to be unsupported."""

    event_type: Final[str] = "attribute_unsupported"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str
    attribute_id: int
    manufacturer_code: int | None


@dataclass(kw_only=True, frozen=True)
class AttributeReportingConfiguredEvent:
    """Event generated when attribute reporting is configured."""

    event_type: Final[str] = "attribute_reporting_configured"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str
    attribute_id: int
    manufacturer_code: int | None
    min_interval: int
    max_interval: int
    reportable_change: Any | None


@dataclass(kw_only=True, frozen=True)
class AttributeClearedEvent:
    """Event generated when an attribute is cleared."""

    event_type: Final[str] = "attribute_cleared"

    device_ieee: str
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    attribute_name: str
    attribute_id: int
    manufacturer_code: int | None


def convert_list_schema(
    schema: Sequence[type], command_id: int, direction: foundation.Direction
) -> type[t.Struct]:
    schema_dict = {}

    for i, param_type in enumerate(schema, start=1):
        name = f"param{i}"
        real_type = next(c for c in param_type.__mro__ if c.__name__ != "Optional")

        if real_type is not param_type:
            name += "?"

        schema_dict[name] = real_type

    temp = foundation.ZCLCommandDef(
        schema=schema_dict,
        direction=direction,
        id=command_id,
        name="schema",
    )

    return temp.with_compiled_schema().schema


class Cluster(util.ListenableMixin, util.CatchingTaskMixin, EventBase):
    """A cluster on an endpoint"""

    class AttributeDefs(BaseAttributeDefs):
        pass

    class ServerCommandDefs(BaseCommandDefs):
        pass

    class ClientCommandDefs(BaseCommandDefs):
        pass

    # Custom clusters for quirks subclass Cluster but should not be stored in any global
    # registries, since they're device-specific and collide with existing clusters.
    _skip_registry: bool = False

    # Most clusters are identified by a single cluster ID
    cluster_id: t.uint16_t = None

    # If set, this manufacturer code will be used for all manufacturer-specific
    # attributes and commands in this cluster.
    manufacturer_id_override: t.uint16_t | UndefinedType | None = UNDEFINED

    # Clusters are accessible by name from their endpoint as an attribute
    ep_attribute: str = None

    # Manufacturer specific clusters exist between 0xFC00 and 0xFFFF. This exists solely
    # to remove the need to create 1024 "ManufacturerSpecificCluster" instances.
    cluster_id_range: tuple[t.uint16_t, t.uint16_t] = None

    # Internal cache to speed up attribute finding. Nested layering, keyed by:
    # attr_id, is_manufacturer_specific, manufacturer_code
    _attributes_by_id: dict[
        int,
        dict[
            bool | None,
            dict[int | UndefinedType | None, foundation.ZCLAttributeDef],
        ],
    ] = {}

    # Deprecated: clusters contain attributes and both client and server commands
    attributes: dict[int, foundation.ZCLAttributeDef] = {}
    client_commands: dict[int, foundation.ZCLCommandDef] = {}
    server_commands: dict[int, foundation.ZCLCommandDef] = {}
    attributes_by_name: dict[str, foundation.ZCLAttributeDef] = {}
    commands_by_name: dict[str, foundation.ZCLCommandDef] = {}

    # Internal caches and indices
    _registry: dict = {}
    _registry_range: dict = {}

    def __init_subclass__(cls) -> None:
        if cls.cluster_id is not None:
            cls.cluster_id = t.ClusterId(cls.cluster_id)

        # Compile the old command definitions
        for commands in [cls.server_commands, cls.client_commands]:
            for command_id, command in list(commands.items()):
                if isinstance(command, tuple):
                    # Backwards compatibility with old command tuples
                    name, schema, direction = command
                    command = foundation.ZCLCommandDef(
                        id=command_id,
                        name=name,
                        schema=convert_list_schema(schema, command_id, direction),
                        direction=direction,
                    )

                command = command.replace(id=command_id).with_compiled_schema()
                commands[command.id] = command

        # Compile the old attribute definitions
        for attr_id, attr in list(cls.attributes.items()):
            if isinstance(attr, tuple):
                if len(attr) == 2:
                    attr_name, attr_type = attr
                    attr_manuf_specific = False
                else:
                    attr_name, attr_type, attr_manuf_specific = attr

                attr = foundation.ZCLAttributeDef(
                    id=attr_id,
                    name=attr_name,
                    type=attr_type,
                    is_manufacturer_specific=attr_manuf_specific,
                )
            else:
                attr = attr.replace(id=attr_id)

            cls.attributes[attr.id] = attr.replace(id=attr_id)

        # Create new definitions from the old-style definitions
        if cls.attributes and "AttributeDefs" not in cls.__dict__:
            cls.AttributeDefs = types.new_class(
                name="AttributeDefs",
                bases=(BaseAttributeDefs,),
            )

            for attr in cls.attributes.values():
                setattr(cls.AttributeDefs, attr.name, attr)

        if cls.server_commands and "ServerCommandDefs" not in cls.__dict__:
            cls.ServerCommandDefs = types.new_class(
                name="ServerCommandDefs",
                bases=(BaseCommandDefs,),
            )

            for command in cls.server_commands.values():
                setattr(cls.ServerCommandDefs, command.name, command)

        if cls.client_commands and "ClientCommandDefs" not in cls.__dict__:
            cls.ClientCommandDefs = types.new_class(
                name="ClientCommandDefs",
                bases=(BaseCommandDefs,),
            )

            for command in cls.client_commands.values():
                setattr(cls.ClientCommandDefs, command.name, command)

        # Check the old definitions for duplicates
        for old_defs in [cls.attributes, cls.server_commands, cls.client_commands]:
            counts = collections.Counter(d.name for d in old_defs.values())

            if len(counts) != sum(counts.values()):
                duplicates = [n for n, c in counts.items() if c > 1]
                raise TypeError(f"Duplicate definitions exist for {duplicates}")

        # Populate the `name` and `manufacturer_code` attribute of every definition
        for defs in (cls.ServerCommandDefs, cls.ClientCommandDefs, cls.AttributeDefs):
            for name in dir(defs):
                if name.startswith("_") or name.endswith("_"):
                    continue

                definition = getattr(defs, name)

                if isinstance(definition, foundation.ZCLCommandDef):
                    direction = (
                        foundation.Direction.Client_to_Server
                        if defs is cls.ClientCommandDefs
                        else foundation.Direction.Server_to_Client
                    )

                    if (
                        definition.direction is not None
                        and definition.direction != direction
                    ):
                        warnings.warn(
                            f"Command {definition.name!r} has an incorrect direction, please remove the `direction` kwarg",
                            DeprecationWarning,
                            stacklevel=2,
                        )
                        LOGGER.warning(
                            "Command %r has an incorrect direction, please remove the `direction` kwarg",
                            definition.name,
                            stacklevel=2,
                        )

                    object.__setattr__(definition, "direction", direction)

                if isinstance(
                    definition,
                    foundation.ZCLCommandDef | foundation.ZCLAttributeDef,
                ):
                    if definition.name is None:
                        object.__setattr__(definition, "name", name)
                    elif definition.name != name:
                        raise TypeError(
                            f"Definition name {definition.name!r} does not match"
                            f" attribute name {name!r}"
                        )

        # Compile the schemas
        for defs in (cls.ServerCommandDefs, cls.ClientCommandDefs):
            for name in dir(defs):
                definition = getattr(defs, name)

                if isinstance(definition, foundation.ZCLCommandDef):
                    setattr(defs, definition.name, definition.with_compiled_schema())

        # Create a way to look up attributes (with manufacturer_code) internally
        cls._attributes_by_id = {}

        for attr_def in cls.AttributeDefs:
            if attr_def.id not in cls._attributes_by_id:
                cls._attributes_by_id[attr_def.id] = {True: {}, False: {}, None: {}}

            is_manuf = attr_def.is_manufacturer_specific
            cls._attributes_by_id[attr_def.id][is_manuf][attr_def.manufacturer_code] = (
                attr_def
            )

        # Recreate the old structures using the new-style definitions
        cls.attributes = {attr.id: attr for attr in cls.AttributeDefs}
        cls.client_commands = {cmd.id: cmd for cmd in cls.ClientCommandDefs}
        cls.server_commands = {cmd.id: cmd for cmd in cls.ServerCommandDefs}
        cls.attributes_by_name = {attr.name: attr for attr in cls.AttributeDefs}

        all_cmds: Iterable[foundation.ZCLCommandDef] = itertools.chain(
            cls.ClientCommandDefs, cls.ServerCommandDefs
        )
        cls.commands_by_name = {cmd.name: cmd for cmd in all_cmds}

        if cls._skip_registry:
            return

        if cls.cluster_id is not None:
            cls._registry[cls.cluster_id] = cls

        if cls.cluster_id_range is not None:
            cls._registry_range[cls.cluster_id_range] = cls

    def __init__(self, endpoint: Endpoint, is_server: bool = True) -> None:
        super().__init__()
        self._endpoint: Endpoint = endpoint
        self._type: ClusterType = (
            ClusterType.Server if is_server else ClusterType.Client
        )

        # We proxy `_attr_cache` because custom quirks can overwrite it with a dict
        self._attr_cache_internal: AttributeCache = AttributeCache(self)

    @property
    def _attr_cache(self) -> AttributeCache:
        """Attribute cache accessor."""
        return self._attr_cache_internal

    @_attr_cache.setter
    def _attr_cache(self, new_value: dict[str, Any]) -> None:
        """Deprecated accessor to update the attribute cache directly."""
        LOGGER.warning(
            "Updating the attribute cache directly is deprecated and will stop working"
            " in the near future. Please contribute your custom quirk to"
            " https://github.com/zigpy/zha-device-handlers/ or update your code.",
            stacklevel=2,
        )

        for key, value in new_value.items():
            self._update_attribute(key, value)

    def _legacy_apply_quirk_attribute_update(
        self, attr_def: foundation.ZCLAttributeDef, value: Any
    ) -> Any | None:
        """Update an attribute and return the cached value (possibly transformed).

        Returns None if the quirk swallowed the attribute (no super() call).
        """
        with _suppress_attribute_update_event(self.cluster_id, attr_def.id):
            self._update_attribute(attr_def.id, value)

        try:
            return self._attr_cache.get_value(attr_def)
        except KeyError:
            pass

        # When multiple attrs share an ID (different manufacturer codes),
        # `_update_attribute` stores in legacy cache. Move it to typed cache.
        if attr_def.id in self._attr_cache._legacy_cache:
            cached_value = self._attr_cache._legacy_cache.pop(attr_def.id).value
            self._attr_cache.set_value(attr_def, cached_value)
            return cached_value

        # Quirk swallowed the attribute
        return None

    @classmethod
    def find_attribute(
        cls,
        name_or_id: int | str | foundation.ZCLAttributeDef,
        *,
        manufacturer_code: int | UndefinedType | None = UNDEFINED,
    ) -> foundation.ZCLAttributeDef:
        if isinstance(name_or_id, foundation.ZCLAttributeDef):
            return cls.attributes_by_name[name_or_id.name]
        elif isinstance(name_or_id, str):
            return cls.attributes_by_name[name_or_id]
        elif isinstance(name_or_id, int):
            # Integer lookups are the most complicated, since we know the ID of an
            # attribute but there may be multiple candidates sharing it
            candidates = cls._attributes_by_id[name_or_id]
            manuf_specific = candidates[True]
            non_manuf_specific = candidates[False]
            maybe_manuf_specific = candidates[None]

            # If a manufacturer code is explicitly provided, we can narrow things down
            if manufacturer_code is not UNDEFINED:
                if manufacturer_code is None:
                    # Explicitly no manufacturer code
                    if None in non_manuf_specific:
                        return non_manuf_specific[None]

                    # Fall back to unspecified
                    if UNDEFINED in non_manuf_specific:
                        return non_manuf_specific[UNDEFINED]

                    if UNDEFINED in maybe_manuf_specific:
                        return maybe_manuf_specific[UNDEFINED]
                else:
                    # Try exact manufacturer-specific match
                    if manufacturer_code in manuf_specific:
                        return manuf_specific[manufacturer_code]

                    # Try manufacturer-specific without explicit code (deprecation)
                    if UNDEFINED in manuf_specific:
                        attr_def = manuf_specific[UNDEFINED]
                        warnings.warn(
                            f"Attribute {attr_def.name!r} has `is_manufacturer_specific`"
                            f" without an explicit `manufacturer_code`. Please set"
                            f" `manufacturer_code=0x{manufacturer_code:04X}`.",
                            DeprecationWarning,
                            stacklevel=3,
                        )
                        return attr_def

                raise KeyError(manufacturer_code)

            # Otherwise, we pick the first one and hope there is only a single choice
            all_candidates = (
                list(manuf_specific.values())
                + list(non_manuf_specific.values())
                + list(maybe_manuf_specific.values())
            )

            if len(all_candidates) > 1:
                raise KeyError(
                    f"Multiple definitions exist for attribute ID {name_or_id:#06x},"
                    f" please specify a manufacturer code: {candidates!r}"
                )

            # Pick the only one
            return all_candidates[0]
        else:
            raise TypeError(  # noqa: TRY004
                f"Attribute must be a definition, string, or integer,"
                f" not {name_or_id!r} ({type(name_or_id)!r})"
            )

    def is_attribute_unsupported(
        self, attr: int | str | foundation.ZCLAttributeDef
    ) -> bool:
        """Return whether an attribute is unsupported."""
        attr_def = self.find_attribute(attr)
        return self._attr_cache.is_unsupported(attr_def)

    @classmethod
    def from_id(
        cls, endpoint: Endpoint, cluster_id: int, is_server: bool = True
    ) -> Cluster:
        cluster_id = t.ClusterId(cluster_id)

        if cluster_id in cls._registry:
            return cls._registry[cluster_id](endpoint, is_server)

        for (start, end), cluster in cls._registry_range.items():
            if start <= cluster_id <= end:
                cluster = cluster(endpoint, is_server)
                cluster.cluster_id = cluster_id
                return cluster

        LOGGER.debug("Unknown cluster 0x%04X", cluster_id)

        cluster = cls(endpoint, is_server)
        cluster.cluster_id = cluster_id
        return cluster

    def deserialize(
        self, data: bytes
    ) -> tuple[foundation.ZCLHeader, CommandSchema | bytes]:
        self.debug("Received ZCL frame: %r", data.hex(" "))

        hdr, data = foundation.ZCLHeader.deserialize(data)
        self.debug("Decoded ZCL frame header: %r", hdr)

        if hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND:
            # Cluster command
            if hdr.direction == foundation.Direction.Server_to_Client:
                commands = self.client_commands
            else:
                commands = self.server_commands

            if hdr.command_id not in commands:
                self.debug(
                    "Unknown cluster command %s %r", hdr.command_id, data.hex(" ")
                )
                return hdr, data

            command = commands[hdr.command_id]
        else:
            # General command
            if hdr.command_id not in foundation.GENERAL_COMMANDS:
                self.debug(
                    "Unknown foundation command %s %r", hdr.command_id, data.hex(" ")
                )
                return hdr, data

            command_id = foundation.GeneralCommand(hdr.command_id)
            command = foundation.GENERAL_COMMANDS[command_id]

        response, data = command.schema.deserialize(data)

        self.debug("Decoded ZCL frame: %s:%r", type(self).__name__, response)

        if data:
            self.debug("Data remains after deserializing ZCL frame: %r", data.hex(" "))

        return hdr, response

    def _create_request(
        self,
        *,
        general: bool,
        command_id: foundation.GeneralCommand | int,
        schema: type[CommandSchema],
        manufacturer: int | None = None,
        tsn: int | None = None,
        disable_default_response: bool,
        direction: foundation.Direction,
        # Schema args and kwargs
        args: tuple[Any, ...],
        kwargs: Any,
    ) -> tuple[foundation.ZCLHeader, CommandSchema]:
        request = schema(*args, **kwargs)
        request.serialize()  # Throw an error before generating a new TSN

        if tsn is None:
            tsn = self._endpoint.device.get_sequence()

        frame_control = foundation.FrameControl(
            frame_type=(
                foundation.FrameType.GLOBAL_COMMAND
                if general
                else foundation.FrameType.CLUSTER_COMMAND
            ),
            is_manufacturer_specific=(manufacturer is not None),
            direction=direction,
            disable_default_response=disable_default_response,
            reserved=0b000,
        )

        hdr = foundation.ZCLHeader(
            frame_control=frame_control,
            manufacturer=manufacturer,
            tsn=tsn,
            command_id=command_id,
        )

        return hdr, request

    async def request(
        self,
        general: bool,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        schema: type[t.Struct],
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        use_ieee: bool = False,
        ask_for_ack: bool | None = None,
        disable_default_response: bool | None = None,
        priority: int | None = None,
        tsn: int | t.uint8_t | None = None,
        timeout=APS_REPLY_TIMEOUT,
        **kwargs,
    ):
        if disable_default_response is None:
            disable_default_response = self.is_client

        hdr, request = self._create_request(
            general=general,
            command_id=command_id,
            schema=schema,
            manufacturer=manufacturer,
            tsn=tsn,
            disable_default_response=disable_default_response,
            direction=(
                foundation.Direction.Server_to_Client
                if self.is_client
                else foundation.Direction.Client_to_Server
            ),
            args=args,
            kwargs=kwargs,
        )

        self.debug("Sending request header: %r", hdr)
        self.debug("Sending request: %r", request)
        data = hdr.serialize() + request.serialize()

        return await self._endpoint.request(
            cluster=self.cluster_id,
            sequence=hdr.tsn,
            data=data,
            command_id=hdr.command_id,
            timeout=timeout,
            expect_reply=expect_reply,
            use_ieee=use_ieee,
            ask_for_ack=ask_for_ack,
            priority=priority,
        )

    async def reply(
        self,
        general: bool,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        schema: type[t.Struct],
        *args,
        manufacturer: int | t.uint16_t | None = None,
        tsn: int | t.uint8_t | None = None,
        timeout=APS_REPLY_TIMEOUT,
        expect_reply: bool = False,
        use_ieee: bool = False,
        ask_for_ack: bool | None = None,
        disable_default_response: bool | None = None,
        priority: int | None = None,
        **kwargs,
    ) -> None:
        if disable_default_response is None:
            disable_default_response = True

        hdr, request = self._create_request(
            general=general,
            command_id=command_id,
            schema=schema,
            manufacturer=manufacturer,
            tsn=tsn,
            disable_default_response=disable_default_response,
            direction=(
                foundation.Direction.Server_to_Client
                if self.is_client
                else foundation.Direction.Client_to_Server
            ),
            args=args,
            kwargs=kwargs,
        )

        self.debug("Sending reply header: %r", hdr)
        self.debug("Sending reply: %r", request)
        data = hdr.serialize() + request.serialize()

        return await self._endpoint.reply(
            cluster=self.cluster_id,
            sequence=hdr.tsn,
            data=data,
            command_id=hdr.command_id,
            timeout=timeout,
            expect_reply=expect_reply,
            use_ieee=use_ieee,
            ask_for_ack=ask_for_ack,
            priority=priority,
        )

    def handle_message(
        self,
        hdr: foundation.ZCLHeader,
        args: list[Any],
    ) -> None:
        self.debug(
            "Received command 0x%02X (TSN %d): %s", hdr.command_id, hdr.tsn, args
        )
        if hdr.frame_control.is_cluster:
            self.handle_cluster_request(hdr, args)
            self.listener_event("cluster_command", hdr.tsn, hdr.command_id, args)
            return
        self.listener_event("general_command", hdr, args)
        self.handle_cluster_general_request(hdr, args)

    def handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: list[Any],
        *,
        # This parameter is unused and kept only for backwards compatibility
        dst_addressing: t.AddrMode | None = None,
    ):
        self.debug(
            "No explicit handler for cluster command 0x%02x: %s",
            hdr.command_id,
            args,
        )

        if not hdr.frame_control.disable_default_response:
            self.send_default_rsp(
                hdr,
                foundation.Status.SUCCESS,
            )

    def handle_cluster_general_request(
        self,
        hdr: foundation.ZCLHeader,
        args: list,
        *,
        # This parameter is unused and kept only for backwards compatibility
        dst_addressing: t.AddrMode | None = None,
    ) -> None:
        if hdr.command_id == foundation.GeneralCommand.Read_Attributes:
            records = []

            for attrid in args.attribute_ids:
                record = foundation.ReadAttributeRecord(attrid=attrid)
                records.append(record)

                try:
                    attr_def = self.find_attribute(attrid)
                except KeyError:
                    record.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
                    continue

                attr_read_func = getattr(
                    self, f"handle_read_attribute_{attr_def.name}", None
                )

                if attr_read_func is None:
                    record.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
                    continue

                record.status = foundation.Status.SUCCESS
                record.value = foundation.TypeValue(
                    type=attr_def.zcl_type,
                    value=attr_read_func(),
                )

            # We do not emit a default response here because a ReadAttributesResponse is
            # sent instead
            self.create_catching_task(self.read_attributes_rsp(records, tsn=hdr.tsn))
            return

        if hdr.command_id == foundation.GeneralCommand.Report_Attributes:
            for attr in args.attribute_reports:
                try:
                    attr_def = self.find_attribute(
                        attr.attrid, manufacturer_code=hdr.manufacturer
                    )
                except KeyError:
                    attr_def = None
                    value = attr.value.value
                else:
                    value = attr_def.type(attr.value.value)

                if attr_def is None:
                    # Unknown attribute, update and emit reported event
                    with _suppress_attribute_update_event(self.cluster_id, attr.attrid):
                        self._update_attribute(attr.attrid, value)

                    self.emit(
                        AttributeReportedEvent.event_type,
                        AttributeReportedEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=None,
                            attribute_id=attr.attrid,
                            manufacturer_code=hdr.manufacturer,
                            raw_value=attr.value.value,
                            value=value,
                        ),
                    )
                    continue

                cached_value = self._legacy_apply_quirk_attribute_update(
                    attr_def, value
                )

                if cached_value is None:
                    # Quirk swallowed the attribute
                    continue
                elif cached_value != value:
                    # Quirk transformed the value, emit AttributeUpdatedEvent
                    self.emit(
                        AttributeUpdatedEvent.event_type,
                        AttributeUpdatedEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=attr_def.name,
                            attribute_id=attr_def.id,
                            manufacturer_code=hdr.manufacturer,
                            value=cached_value,
                        ),
                    )
                else:
                    # Value unchanged, emit AttributeReportedEvent
                    self.emit(
                        AttributeReportedEvent.event_type,
                        AttributeReportedEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=attr_def.name,
                            attribute_id=attr.attrid,
                            manufacturer_code=hdr.manufacturer,
                            raw_value=attr.value.value,
                            value=value,
                        ),
                    )

        if not hdr.frame_control.disable_default_response:
            self.send_default_rsp(
                hdr,
                foundation.Status.SUCCESS,
            )

    def read_attributes_raw(
        self, attributes: list[int], manufacturer: int | None = None, **kwargs
    ):
        return self._read_attributes(
            [t.uint16_t(a) for a in attributes], manufacturer=manufacturer, **kwargs
        )

    def _get_effective_manufacturer_code(
        self,
        definition: foundation.ZCLAttributeDef | foundation.ZCLCommandDef,
        manufacturer: int | UndefinedType | None = UNDEFINED,
    ) -> int | None:
        """Get the effective manufacturer code for an attribute or command."""

        # If a command overrides the manufacturer code, it takes priority
        if manufacturer is not UNDEFINED:
            return manufacturer

        # Otherwise, use what the definition has set explicitly
        if definition.manufacturer_code is not UNDEFINED:
            return definition.manufacturer_code

        # Or implicitly
        if definition.is_manufacturer_specific is not None:
            if not definition.is_manufacturer_specific:
                return None

            return (
                self.manufacturer_id_override
                if self.manufacturer_id_override is not UNDEFINED
                else self.endpoint.device.manufacturer_id
            )

        # Finally, fall back to spec-compliant behavior and use a manufacturer code for
        # any commands destined for a manufacturer-specific cluster
        if 0xFC00 <= self.cluster_id <= 0xFFFF:
            return (
                self.manufacturer_id_override
                if self.manufacturer_id_override is not UNDEFINED
                else self.endpoint.device.manufacturer_id
            )

        return None

    async def read_attributes(
        self,
        attributes: list[int | str | foundation.ZCLAttributeDef],
        allow_cache: bool = False,
        only_cache: bool = False,
        manufacturer: int | UndefinedType | None = UNDEFINED,
        **kwargs,
    ) -> Any:
        # Find definition objects for every attribute
        attribute_defs: list[foundation.ZCLAttributeDef] = []

        # And keep track of the original object, for return values
        attribute_map: dict[
            foundation.ZCLAttributeDef, int | str | foundation.ZCLAttributeDef
        ] = {}

        for attribute in attributes:
            # This lookup can fail if we pass an integer attribute ID and two attributes
            # sharing an ID exist
            attr_def = self.find_attribute(attribute, manufacturer_code=manufacturer)
            attribute_defs.append(attr_def)

            if attr_def in attribute_map:
                raise ValueError(
                    f"Cannot read the same attribute twice in the same call: {attr_def}"
                )

            attribute_map[attr_def] = attribute

        # Attribute read commands share a manufacturer code (or lack of one), we need to
        # group heterogeneous reads into separate requests
        reads_by_manuf_code: defaultdict[
            int | None, list[foundation.ZCLAttributeDef]
        ] = defaultdict(list)

        # Pre-fill the success and failure dicts with cached information, if necessary
        success = {}
        failure = {}

        for attr_def in attribute_defs:
            if allow_cache or only_cache:
                try:
                    cached_value = self._attr_cache.get_value(attr_def)
                except KeyError:
                    pass
                except UnsupportedAttribute:
                    failure[attribute_map[attr_def]] = (
                        foundation.Status.UNSUPPORTED_ATTRIBUTE
                    )
                    continue
                else:
                    # If an attribute was in the cache, we do not read it
                    success[attribute_map[attr_def]] = cached_value
                    continue

            # Otherwise, populate the groups of attributes to read
            effective_manuf = self._get_effective_manufacturer_code(attr_def)
            reads_by_manuf_code[effective_manuf].append(attr_def)

        if only_cache:
            LOGGER.debug(
                "Reading only from cache, skipping reads: %s", reads_by_manuf_code
            )
            return success, failure

        # Now, we can perform the reads for each manufacturer code group
        for manufacturer_code, attribute_group in reads_by_manuf_code.items():
            result = await self.read_attributes_raw(
                [attr_def.id for attr_def in attribute_group],
                manufacturer=manufacturer_code,
                **kwargs,
            )

            # The read response should contain only these attributes
            potential_attributes = {
                attr_def.id: attr_def for attr_def in attribute_group
            }

            if not isinstance(result[0], list):
                # If we get back a single response status, all reads failed
                for attr_def in attribute_group:
                    failure[attribute_map[attr_def]] = result[0]
            else:
                for record in result[0]:
                    attr_def = potential_attributes[record.attrid]

                    if record.status == foundation.Status.SUCCESS:
                        if record.value.value is None:
                            # TODO: remove this workaround when `LocalDataCluster` and
                            # `_VALID_ATTRIBUTES` are removed from quirks. There is no
                            # way for `value` to actually be `None` when read from a
                            # real device.
                            value = None
                        else:
                            value = attr_def.type(record.value.value)

                        success[attribute_map[attr_def]] = value

                        cached_value = self._legacy_apply_quirk_attribute_update(
                            attr_def, value
                        )

                        if cached_value is None:
                            # Quirk swallowed the attribute
                            continue
                        elif cached_value != value:
                            # Quirk transformed the value, emit AttributeUpdatedEvent
                            self.emit(
                                AttributeUpdatedEvent.event_type,
                                AttributeUpdatedEvent(
                                    device_ieee=str(self.endpoint.device.ieee),
                                    endpoint_id=self.endpoint.endpoint_id,
                                    cluster_type=self._type,
                                    cluster_id=self.cluster_id,
                                    attribute_name=attr_def.name,
                                    attribute_id=attr_def.id,
                                    manufacturer_code=manufacturer_code,
                                    value=cached_value,
                                ),
                            )
                        else:
                            # Value unchanged, emit AttributeReadEvent
                            self.emit(
                                AttributeReadEvent.event_type,
                                AttributeReadEvent(
                                    device_ieee=str(self.endpoint.device.ieee),
                                    endpoint_id=self.endpoint.endpoint_id,
                                    cluster_type=self._type,
                                    cluster_id=self.cluster_id,
                                    attribute_name=attr_def.name,
                                    attribute_id=attr_def.id,
                                    manufacturer_code=manufacturer_code,
                                    raw_value=record.value.value,
                                    value=value,
                                ),
                            )
                    else:
                        if record.status == foundation.Status.UNSUPPORTED_ATTRIBUTE:
                            self._attr_cache.mark_unsupported(attr_def)
                            self.emit(
                                AttributeUnsupportedEvent.event_type,
                                AttributeUnsupportedEvent(
                                    device_ieee=str(self.endpoint.device.ieee),
                                    endpoint_id=self.endpoint.endpoint_id,
                                    cluster_type=self._type,
                                    cluster_id=self.cluster_id,
                                    attribute_name=attr_def.name,
                                    attribute_id=attr_def.id,
                                    manufacturer_code=manufacturer_code,
                                ),
                            )

                        failure[attribute_map[attr_def]] = record.status

        return success, failure

    def update_attribute(
        self, attrid: int | t.uint16_t | foundation.ZCLAttributeDef, value: Any
    ) -> None:
        """Update specified attribute with specified value"""
        self._update_attribute(attrid, value)

    def _update_attribute(
        self, attrid: int | t.uint16_t | foundation.ZCLAttributeDef, value: Any
    ) -> None:
        # Check if AttributeUpdatedEvent should be suppressed for this attribute.
        # This is used during Report_Attributes handling to allow quirks that update
        # other clusters or attributes to emit their own events.
        suppressed = (self.cluster_id, attrid) in _suppressed_attribute_updates.get()

        try:
            attr_def = self.find_attribute(attrid)
        except KeyError:
            if value is not None:
                self._attr_cache.set_legacy_value(attrid, value)

                if not suppressed:
                    self.emit(
                        AttributeUpdatedEvent.event_type,
                        AttributeUpdatedEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=None,
                            attribute_id=attrid,
                            manufacturer_code=None,
                            value=value,
                        ),
                    )

                    # Legacy `listener_event`, will be removed in the near future
                    self.listener_event(
                        "attribute_updated", attrid, value, datetime.now(UTC)
                    )

            return

        if value is None:
            self._attr_cache.remove(attr_def)
            self.emit(
                AttributeClearedEvent.event_type,
                AttributeClearedEvent(
                    device_ieee=str(self.endpoint.device.ieee),
                    endpoint_id=self.endpoint.endpoint_id,
                    cluster_type=self._type,
                    cluster_id=self.cluster_id,
                    attribute_name=attr_def.name,
                    attribute_id=attr_def.id,
                    manufacturer_code=self._get_effective_manufacturer_code(attr_def),
                ),
            )
        else:
            self._attr_cache.set_value(attr_def, value)

            if not suppressed:
                self.emit(
                    AttributeUpdatedEvent.event_type,
                    AttributeUpdatedEvent(
                        device_ieee=str(self.endpoint.device.ieee),
                        endpoint_id=self.endpoint.endpoint_id,
                        cluster_type=self._type,
                        cluster_id=self.cluster_id,
                        attribute_name=attr_def.name,
                        attribute_id=attr_def.id,
                        manufacturer_code=self._get_effective_manufacturer_code(
                            attr_def
                        ),
                        value=value,
                    ),
                )

                # Legacy `listener_event`, will be removed in the near future
                self.listener_event(
                    "attribute_updated", attrid, value, datetime.now(UTC)
                )

    async def write_attributes(
        self,
        attributes: dict[str | int | foundation.ZCLAttributeDef, Any],
        manufacturer: int | UndefinedType | None = UNDEFINED,
        *,
        update_cache: bool = True,
        **kwargs,
    ) -> list[list[foundation.WriteAttributesStatusRecord]]:
        """Write attributes to device with internal 'attributes' validation."""

        # Group attributes by effective manufacturer code
        writes_by_manuf_code: defaultdict[
            int | None, list[tuple[foundation.ZCLAttributeDef, Any]]
        ] = defaultdict(list)

        for attr, value in attributes.items():
            attr_def = self.find_attribute(attr, manufacturer_code=manufacturer)
            effective_manuf = self._get_effective_manufacturer_code(attr_def)
            writes_by_manuf_code[effective_manuf].append((attr_def, value))

        # Write each group separately and merge results
        results: list[foundation.WriteAttributesStatusRecord] = []

        for manufacturer_code, attribute_list in writes_by_manuf_code.items():
            zcl_attrs: list[foundation.Attribute] = []
            attr_defs: dict[int, foundation.ZCLAttributeDef] = {}
            attribute_values: dict[int, Any] = {}

            for attr_def, value in attribute_list:
                attr_defs[attr_def.id] = attr_def
                attribute_values[attr_def.id] = value

                zcl_attr = foundation.Attribute(attr_def.id, foundation.TypeValue())
                zcl_attr.value.type = attr_def.zcl_type
                zcl_attr.value.value = attr_def.type(value)
                zcl_attrs.append(zcl_attr)

            result = await self._write_attributes(
                zcl_attrs, manufacturer=manufacturer_code, **kwargs
            )

            records_group: list[foundation.WriteAttributesStatusRecord] = []

            if isinstance(result[0], list):
                # Check for global success (status=SUCCESS, attrid=None)
                if (
                    len(result[0]) == 1
                    and result[0][0].status == foundation.Status.SUCCESS
                    and result[0][0].attrid is None
                ):
                    # Global success: all attributes succeeded
                    records_group.extend(
                        foundation.WriteAttributesStatusRecord(
                            status=foundation.Status.SUCCESS, attrid=zcl_attr.attrid
                        )
                        for zcl_attr in zcl_attrs
                    )
                else:
                    # Only failed writes are in the response. Attributes not
                    # present implicitly succeeded.
                    failed_attrids = {r.attrid for r in result[0]}
                    for zcl_attr in zcl_attrs:
                        if zcl_attr.attrid in failed_attrids:
                            records_group.extend(
                                r for r in result[0] if r.attrid == zcl_attr.attrid
                            )
                        else:
                            records_group.append(
                                foundation.WriteAttributesStatusRecord(
                                    status=foundation.Status.SUCCESS,
                                    attrid=zcl_attr.attrid,
                                )
                            )
            else:
                # Default response: apply status to all attributes in this group
                status = result[0]
                records_group.extend(
                    foundation.WriteAttributesStatusRecord(
                        status=status, attrid=zcl_attr.attrid
                    )
                    for zcl_attr in zcl_attrs
                )

            results.extend(records_group)

            if not update_cache:
                continue

            # Finally, emit events for the group
            for record in records_group:
                attr_def = attr_defs[record.attrid]

                if record.status == foundation.Status.SUCCESS:
                    self._attr_cache.set_value(
                        attr_def, attribute_values[record.attrid]
                    )
                elif record.status == foundation.Status.UNSUPPORTED_ATTRIBUTE:
                    self._attr_cache.mark_unsupported(attr_def)
                    self.emit(
                        AttributeUnsupportedEvent.event_type,
                        AttributeUnsupportedEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=attr_def.name,
                            attribute_id=attr_def.id,
                            manufacturer_code=manufacturer_code,
                        ),
                    )

                self.emit(
                    AttributeWrittenEvent.event_type,
                    AttributeWrittenEvent(
                        device_ieee=str(self.endpoint.device.ieee),
                        endpoint_id=self.endpoint.endpoint_id,
                        cluster_type=self._type,
                        cluster_id=self.cluster_id,
                        attribute_name=attr_def.name,
                        attribute_id=attr_def.id,
                        manufacturer_code=manufacturer_code,
                        value=attribute_values[record.attrid],
                        status=record.status,
                    ),
                )

        # TODO: ditch the low-level return type
        return [results]

    async def bind(self, **kwargs):
        return await self._endpoint.device.zdo.bind(cluster=self, **kwargs)

    async def unbind(self):
        return await self._endpoint.device.zdo.unbind(cluster=self)

    async def configure_reporting(
        self,
        attribute: foundation.ZCLAttributeDef | int | str,
        min_interval: int,
        max_interval: int,
        reportable_change: int,
    ) -> list[foundation.ConfigureReportingResponseRecord]:
        """Configure attribute reporting for a single attribute."""
        attr_def = self.find_attribute(attribute)
        return await self.configure_reporting_multiple(
            {
                attr_def: ReportingConfig(
                    min_interval=min_interval,
                    max_interval=max_interval,
                    reportable_change=reportable_change,
                ),
            }
        )

    async def configure_reporting_multiple(
        self, config: dict[foundation.ZCLAttributeDef, ReportingConfig]
    ) -> list[foundation.ConfigureReportingResponseRecord]:
        """Configure attribute reporting for multiple attributes in the same request."""

        # Group attributes by effective manufacturer code
        reporting_by_manuf_code: defaultdict[
            int | None,
            list[
                tuple[foundation.ZCLAttributeDef, foundation.AttributeReportingConfig]
            ],
        ] = defaultdict(list)

        for attr_def, reporting_config in config.items():
            cfg = foundation.AttributeReportingConfig()
            cfg.direction = foundation.ReportingDirection.SendReports
            cfg.attrid = attr_def.id
            cfg.datatype = (
                attr_def.zcl_type
                if attr_def.zcl_type is not None
                else foundation.DataType.from_python_type(attr_def.type).type_id
            )
            cfg.min_interval = reporting_config.min_interval
            cfg.max_interval = reporting_config.max_interval
            cfg.reportable_change = reporting_config.reportable_change

            effective_manuf = self._get_effective_manufacturer_code(attr_def)
            reporting_by_manuf_code[effective_manuf].append((attr_def, cfg))

        results: list[foundation.ConfigureReportingResponseRecord] = []

        for manufacturer_code, reporting_configs in reporting_by_manuf_code.items():
            configs = [cfg for _attr_def, cfg in reporting_configs]
            attr_defs_by_id = {
                attr_def.id: attr_def for attr_def, _cfg in reporting_configs
            }

            rsp = await self._configure_reporting(
                configs, manufacturer=manufacturer_code
            )

            reporting_results = []

            if isinstance(rsp[0], list):
                records = rsp[0]

                # Single status report for all attributes
                if len(records) == 1:
                    for attr_def, _cfg in reporting_configs:
                        reporting_results.append(
                            foundation.ConfigureReportingResponseRecord(
                                status=records[0].status,
                                attrid=attr_def.id,
                            )
                        )
                else:
                    reporting_results = records
            else:
                # Default response: apply status to all attributes in this group
                status = rsp[1]
                for attr_def, _cfg in reporting_configs:
                    reporting_results.append(
                        foundation.ConfigureReportingResponseRecord(
                            status=status,
                            attrid=attr_def.id,
                        )
                    )

            for result in reporting_results:
                attr_def = attr_defs_by_id[result.attrid]

                if result.status == foundation.Status.SUCCESS:
                    self._attr_cache.remove_unsupported(attr_def)
                    self.emit(
                        AttributeReportingConfiguredEvent.event_type,
                        AttributeReportingConfiguredEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=attr_def.name,
                            attribute_id=attr_def.id,
                            manufacturer_code=manufacturer_code,
                            min_interval=config[attr_def].min_interval,
                            max_interval=config[attr_def].max_interval,
                            reportable_change=config[attr_def].reportable_change,
                        ),
                    )
                elif result.status == foundation.Status.UNSUPPORTED_ATTRIBUTE:
                    self._attr_cache.mark_unsupported(attr_def)
                    self.emit(
                        AttributeUnsupportedEvent.event_type,
                        AttributeUnsupportedEvent(
                            device_ieee=str(self.endpoint.device.ieee),
                            endpoint_id=self.endpoint.endpoint_id,
                            cluster_type=self._type,
                            cluster_id=self.cluster_id,
                            attribute_name=attr_def.name,
                            attribute_id=attr_def.id,
                            manufacturer_code=manufacturer_code,
                        ),
                    )
                else:
                    # Is this even possible?
                    pass

        return results

    def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | UndefinedType | None = None,
        expect_reply: bool = True,
        **kwargs,
    ):
        command = self.server_commands[command_id]

        # Quirks override `def command` but provide their own signature that has
        # `manufacturer` default to `None`. We treat this as UNDEFINED.
        if manufacturer is None:
            manufacturer = UNDEFINED

        return self.request(
            False,
            command_id,
            command.schema,
            *args,
            manufacturer=self._get_effective_manufacturer_code(command, manufacturer),
            expect_reply=expect_reply,
            **kwargs,
        )

    def client_command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | UndefinedType | None = UNDEFINED,
        **kwargs,
    ):
        command = self.client_commands[command_id]

        return self.reply(
            False,
            command_id,
            command.schema,
            *args,
            # No quirks override or touch `client_command` so we can keep this simple
            manufacturer=self._get_effective_manufacturer_code(command, manufacturer),
            **kwargs,
        )

    @property
    def cluster_type(self) -> ClusterType:
        """Return the type of this cluster."""
        return self._type

    @property
    def is_client(self) -> bool:
        """Return True if this is a client cluster."""
        return self._type == ClusterType.Client

    @property
    def is_server(self) -> bool:
        """Return True if this is a server cluster."""
        return self._type == ClusterType.Server

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def endpoint(self) -> Endpoint:
        return self._endpoint

    @property
    def commands(self):
        return list(self.ServerCommandDefs)

    def log(self, lvl: int, msg: str, *args, **kwargs) -> None:
        msg = "[%s:%s:0x%04x] " + msg
        args = (
            self._endpoint.device.name,
            self._endpoint.endpoint_id,
            self.cluster_id,
            *args,
        )
        return LOGGER.log(lvl, msg, *args, **kwargs)

    def __getattr__(self, name: str) -> functools.partial:
        try:
            cmd = getattr(self.ClientCommandDefs, name)
        except AttributeError:
            pass
        else:
            return functools.partial(self.client_command, cmd.id)

        try:
            cmd = getattr(self.ServerCommandDefs, name)
        except AttributeError:
            pass
        else:
            return functools.partial(self.command, cmd.id)

        raise AttributeError(f"No such command name: {name}")

    def get_cached_value(self, key: int | str | foundation.ZCLAttributeDef) -> Any:
        """Get cached attribute."""
        attr_def = self.find_attribute(key)
        return self._attr_cache.get_value(attr_def)

    def get(self, key: int | str, default: Any | None = None) -> Any:
        """Get cached attribute."""
        attr_def = self.find_attribute(key)
        try:
            return self._attr_cache.get_value(attr_def)
        except (KeyError, UnsupportedAttribute):
            return default

    def __getitem__(self, key: int | str) -> Any:
        """Return cached value of the attr."""
        attr_def = self.find_attribute(key)
        return self._attr_cache.get_value(attr_def)

    def general_command(
        self,
        command_id: foundation.GeneralCommand,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs,
    ):
        command = foundation.GENERAL_COMMANDS[command_id]

        if command.direction == foundation.Direction.Server_to_Client:
            # should reply be retryable?
            return self.reply(
                True,
                command.id,
                command.schema,
                *args,
                manufacturer=manufacturer,
                tsn=tsn,
                **kwargs,
            )

        return self.request(
            True,
            command.id,
            command.schema,
            *args,
            manufacturer=manufacturer,
            expect_reply=expect_reply,
            tsn=tsn,
            **kwargs,
        )

    _configure_reporting = functools.partialmethod(
        general_command, foundation.GeneralCommand.Configure_Reporting
    )
    _read_attributes = functools.partialmethod(
        general_command, foundation.GeneralCommand.Read_Attributes
    )
    read_attributes_rsp = functools.partialmethod(
        general_command, foundation.GeneralCommand.Read_Attributes_rsp
    )
    _write_attributes = functools.partialmethod(
        general_command, foundation.GeneralCommand.Write_Attributes
    )
    discover_attributes = functools.partialmethod(
        general_command, foundation.GeneralCommand.Discover_Attributes
    )
    discover_attributes_extended = functools.partialmethod(
        general_command, foundation.GeneralCommand.Discover_Attribute_Extended
    )
    discover_commands_received = functools.partialmethod(
        general_command, foundation.GeneralCommand.Discover_Commands_Received
    )
    discover_commands_generated = functools.partialmethod(
        general_command, foundation.GeneralCommand.Discover_Commands_Generated
    )

    def send_default_rsp(
        self,
        hdr: foundation.ZCLHeader,
        status: foundation.Status = foundation.Status.SUCCESS,
    ) -> None:
        """Send default response unconditionally."""
        self.create_catching_task(
            self.general_command(
                foundation.GeneralCommand.Default_Response,
                hdr.command_id,
                status,
                tsn=hdr.tsn,
                priority=t.PacketPriority.LOW,
            )
        )

    def add_unsupported_attribute(
        self,
        attr: int | str | foundation.ZCLAttributeDef,
        *,
        manufacturer_code: int | UndefinedType | None = UNDEFINED,
    ) -> None:
        """Adds unsupported attribute."""
        attr_def = self.find_attribute(attr, manufacturer_code=manufacturer_code)
        self._attr_cache.mark_unsupported(attr_def)

        self.emit(
            AttributeUnsupportedEvent.event_type,
            AttributeUnsupportedEvent(
                device_ieee=str(self.endpoint.device.ieee),
                endpoint_id=self.endpoint.endpoint_id,
                cluster_type=self._type,
                cluster_id=self.cluster_id,
                attribute_name=attr_def.name,
                attribute_id=attr_def.id,
                manufacturer_code=self._get_effective_manufacturer_code(attr_def),
            ),
        )


# Import to populate the registry
from . import clusters  # noqa: F401, E402, isort:skip
