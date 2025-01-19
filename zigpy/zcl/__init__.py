from __future__ import annotations

import collections
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
import enum
import functools
import itertools
import logging
import types
from typing import TYPE_CHECKING, Any
import warnings

from zigpy import util
from zigpy.const import APS_REPLY_TIMEOUT
import zigpy.types as t
from zigpy.typing import AddressingMode, EndpointType
from zigpy.zcl import foundation
from zigpy.zcl.foundation import BaseAttributeDefs, BaseCommandDefs

if TYPE_CHECKING:
    from zigpy.appdb import PersistingListener
    from zigpy.endpoint import Endpoint


LOGGER = logging.getLogger(__name__)


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


class ClusterType(enum.IntEnum):
    Server = 0
    Client = 1


class Cluster(util.ListenableMixin, util.CatchingTaskMixin):
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

    # Clusters are accessible by name from their endpoint as an attribute
    ep_attribute: str = None

    # Manufacturer specific clusters exist between 0xFC00 and 0xFFFF. This exists solely
    # to remove the need to create 1024 "ManufacturerSpecificCluster" instances.
    cluster_id_range: tuple[t.uint16_t, t.uint16_t] = None

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

        # Populate the `name` attribute of every definition
        for defs in (cls.ServerCommandDefs, cls.ClientCommandDefs, cls.AttributeDefs):
            for name in dir(defs):
                definition = getattr(defs, name)

                if isinstance(
                    definition,
                    (foundation.ZCLCommandDef, foundation.ZCLAttributeDef),
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

    def __init__(self, endpoint: EndpointType, is_server: bool = True) -> None:
        self._endpoint: EndpointType = endpoint
        self._attr_cache: dict[int, Any] = {}
        self._attr_last_updated: dict[int, datetime] = {}
        self.unsupported_attributes: set[int | str] = set()
        self._listeners = {}
        self._type: ClusterType = (
            ClusterType.Server if is_server else ClusterType.Client
        )

    @property
    def attridx(self):
        warnings.warn(
            "`attridx` has been replaced by `attributes_by_name`", DeprecationWarning
        )

        return self.attributes_by_name

    def find_attribute(self, name_or_id: int | str) -> foundation.ZCLAttributeDef:
        if isinstance(name_or_id, str):
            return self.attributes_by_name[name_or_id]
        elif isinstance(name_or_id, int):
            return self.attributes[name_or_id]
        else:
            raise ValueError(  # noqa: TRY004
                f"Attribute must be either a string or an integer,"
                f" not {name_or_id!r} ({type(name_or_id)!r}"
            )

    @classmethod
    def from_id(
        cls, endpoint: EndpointType, cluster_id: int, is_server: bool = True
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

    def deserialize(self, data: bytes) -> tuple[foundation.ZCLHeader, ...]:
        self.debug("Received ZCL frame: %r", data)

        hdr, data = foundation.ZCLHeader.deserialize(data)
        self.debug("Decoded ZCL frame header: %r", hdr)

        if hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND:
            # Cluster command
            if hdr.direction == foundation.Direction.Server_to_Client:
                commands = self.client_commands
            else:
                commands = self.server_commands

            if hdr.command_id not in commands:
                self.debug("Unknown cluster command %s %s", hdr.command_id, data)
                return hdr, data

            command = commands[hdr.command_id]
        else:
            # General command
            if hdr.command_id not in foundation.GENERAL_COMMANDS:
                self.debug("Unknown foundation command %s %s", hdr.command_id, data)
                return hdr, data

            command = foundation.GENERAL_COMMANDS[hdr.command_id]

        hdr.frame_control.direction = command.direction
        response, data = command.schema.deserialize(data)

        self.debug("Decoded ZCL frame: %s:%r", type(self).__name__, response)

        if data:
            self.debug("Data remains after deserializing ZCL frame: %r", data)

        return hdr, response

    def _create_request(
        self,
        *,
        general: bool,
        command_id: foundation.GeneralCommand | int,
        schema: type[t.Struct],
        manufacturer: int | None = None,
        tsn: int | None = None,
        disable_default_response: bool,
        direction: foundation.Direction,
        # Schema args and kwargs
        args: tuple[Any, ...],
        kwargs: Any,
    ) -> tuple[foundation.ZCLHeader, bytes]:
        request = schema(*args, **kwargs)  # type:ignore[operator]
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
        priority: int = t.PacketPriority.NORMAL,
        tsn: int | t.uint8_t | None = None,
        timeout=APS_REPLY_TIMEOUT,
        **kwargs,
    ):
        hdr, request = self._create_request(
            general=general,
            command_id=command_id,
            schema=schema,
            manufacturer=manufacturer,
            tsn=tsn,
            disable_default_response=self.is_client,
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
        priority: int = t.PacketPriority.NORMAL,
        **kwargs,
    ) -> None:
        hdr, request = self._create_request(
            general=general,
            command_id=command_id,
            schema=schema,
            manufacturer=manufacturer,
            tsn=tsn,
            disable_default_response=True,
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
        *,
        dst_addressing: AddressingMode | None = None,
    ) -> None:
        self.debug(
            "Received command 0x%02X (TSN %d): %s", hdr.command_id, hdr.tsn, args
        )
        if hdr.frame_control.is_cluster:
            self.handle_cluster_request(hdr, args, dst_addressing=dst_addressing)
            self.listener_event("cluster_command", hdr.tsn, hdr.command_id, args)
            return
        self.listener_event("general_command", hdr, args)
        self.handle_cluster_general_request(hdr, args, dst_addressing=dst_addressing)

    def handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: list[Any],
        *,
        dst_addressing: AddressingMode | None = None,
    ):
        self.debug(
            "No explicit handler for cluster command 0x%02x: %s",
            hdr.command_id,
            args,
        )

    def handle_cluster_general_request(
        self,
        hdr: foundation.ZCLHeader,
        args: list,
        *,
        dst_addressing: AddressingMode | None = None,
    ) -> None:
        if hdr.command_id == foundation.GeneralCommand.Report_Attributes:
            values = []

            for a in args.attribute_reports:
                if a.attrid in self.attributes:
                    values.append(f"{self.attributes[a.attrid].name}={a.value.value!r}")
                else:
                    values.append(f"0x{a.attrid:04X}={a.value.value!r}")

            self.debug("Attribute report received: %s", ", ".join(values))

            for attr in args.attribute_reports:
                try:
                    value = self.attributes[attr.attrid].type(attr.value.value)
                except KeyError:
                    value = attr.value.value
                except ValueError:
                    self.debug(
                        "Couldn't normalize %a attribute with %s value",
                        attr.attrid,
                        attr.value.value,
                        exc_info=True,
                    )
                    value = attr.value.value
                self._update_attribute(attr.attrid, value)

            if not hdr.frame_control.disable_default_response:
                self.send_default_rsp(
                    hdr,
                    foundation.Status.SUCCESS,
                )

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

            self.create_catching_task(self.read_attributes_rsp(records, tsn=hdr.tsn))

    def read_attributes_raw(self, attributes, manufacturer=None, **kwargs):
        attributes = [t.uint16_t(a) for a in attributes]
        return self._read_attributes(attributes, manufacturer=manufacturer, **kwargs)

    async def read_attributes(
        self,
        attributes: list[int | str],
        allow_cache: bool = False,
        only_cache: bool = False,
        manufacturer: int | t.uint16_t | None = None,
        **kwargs,
    ) -> Any:
        success, failure = {}, {}
        attribute_ids: list[int] = []
        orig_attributes: dict[int, int | str] = {}

        for attribute in attributes:
            if isinstance(attribute, str):
                attrid = self.attributes_by_name[attribute].id
            else:
                # Allow reading attributes that aren't defined
                attrid = attribute

            attribute_ids.append(attrid)
            orig_attributes[attrid] = attribute

        to_read = []
        if allow_cache or only_cache:
            for idx, attribute in enumerate(attribute_ids):
                if attribute in self._attr_cache:
                    success[attributes[idx]] = self._attr_cache[attribute]
                elif attribute in self.unsupported_attributes:
                    failure[attributes[idx]] = foundation.Status.UNSUPPORTED_ATTRIBUTE
                else:
                    to_read.append(attribute)
        else:
            to_read = attribute_ids

        if not to_read or only_cache:
            return success, failure

        result = await self.read_attributes_raw(
            to_read, manufacturer=manufacturer, **kwargs
        )
        if not isinstance(result[0], list):
            for attrid in to_read:
                orig_attribute = orig_attributes[attrid]
                failure[orig_attribute] = result[0]  # Assume default response
        else:
            for record in result[0]:
                orig_attribute = orig_attributes[record.attrid]
                if record.status == foundation.Status.SUCCESS:
                    try:
                        value = self.attributes[record.attrid].type(record.value.value)
                    except KeyError:
                        value = record.value.value
                    except ValueError:
                        value = record.value.value
                        self.debug(
                            "Couldn't normalize %a attribute with %s value",
                            record.attrid,
                            value,
                            exc_info=True,
                        )
                    self._update_attribute(record.attrid, value)
                    success[orig_attribute] = value
                    self.remove_unsupported_attribute(record.attrid)
                else:
                    if record.status == foundation.Status.UNSUPPORTED_ATTRIBUTE:
                        self.add_unsupported_attribute(record.attrid)
                    failure[orig_attribute] = record.status

        return success, failure

    def _write_attr_records(
        self, attributes: dict[str | int, Any]
    ) -> list[foundation.Attribute]:
        args = []
        for attrid, value in attributes.items():
            try:
                attr_def = self.find_attribute(attrid)
            except KeyError:
                self.error("%s is not a valid attribute id", attrid)

                # Throw an error if it's an unknown attribute name, without an ID
                if isinstance(attrid, str):
                    raise

                continue

            attr = foundation.Attribute(attr_def.id, foundation.TypeValue())
            attr.value.type = attr_def.zcl_type

            try:
                attr.value.value = attr_def.type(value)
            except ValueError as e:
                if isinstance(attrid, int):
                    attrid = f"0x{attrid:04X}"

                raise ValueError(
                    f"Failed to convert attribute {attrid} from {value!r}"
                    f" ({type(value)}) to type {attr_def.type}"
                ) from e
            else:
                args.append(attr)

        return args

    async def write_attributes(
        self,
        attributes: dict[str | int, Any],
        manufacturer: int | None = None,
        **kwargs,
    ) -> list:
        """Write attributes to device with internal 'attributes' validation"""
        attrs = self._write_attr_records(attributes)
        return await self.write_attributes_raw(attrs, manufacturer, **kwargs)

    async def write_attributes_raw(
        self,
        attrs: list[foundation.Attribute],
        manufacturer: int | None = None,
        **kwargs,
    ) -> list:
        """Write attributes to device without internal 'attributes' validation"""
        result = await self._write_attributes(
            attrs, manufacturer=manufacturer, **kwargs
        )
        if not isinstance(result[0], list):
            return result

        records = result[0]
        if len(records) == 1 and records[0].status == foundation.Status.SUCCESS:
            for attr_rec in attrs:
                self._update_attribute(attr_rec.attrid, attr_rec.value.value)
        else:
            failed = [rec.attrid for rec in records]
            for attr_rec in attrs:
                if attr_rec.attrid not in failed:
                    self._update_attribute(attr_rec.attrid, attr_rec.value.value)

        return result

    def write_attributes_undivided(
        self, attributes: dict[str | int, Any], manufacturer: int | None = None
    ) -> list:
        """Either all or none of the attributes are written by the device."""
        args = self._write_attr_records(attributes)
        return self._write_attributes_undivided(args, manufacturer=manufacturer)

    async def bind(self):
        return await self._endpoint.device.zdo.bind(cluster=self)

    async def unbind(self):
        return await self._endpoint.device.zdo.unbind(cluster=self)

    def _attr_reporting_rec(
        self,
        attribute: int | str,
        min_interval: int,
        max_interval: int,
        reportable_change: int = 1,
        direction: int = 0x00,
    ) -> foundation.AttributeReportingConfig:
        try:
            attr_def = self.find_attribute(attribute)
        except KeyError as exc:
            raise ValueError(
                f"Unknown attribute {attribute!r} of {self} cluster"
            ) from exc

        cfg = foundation.AttributeReportingConfig()
        cfg.direction = direction
        cfg.attrid = attr_def.id
        cfg.datatype = foundation.DataType.from_python_type(attr_def.type).type_id
        cfg.min_interval = min_interval
        cfg.max_interval = max_interval
        cfg.reportable_change = reportable_change

        return cfg

    async def configure_reporting(
        self,
        attribute: int | str,
        min_interval: int,
        max_interval: int,
        reportable_change: int,
        manufacturer: int | None = None,
    ) -> list[foundation.ConfigureReportingResponseRecord]:
        """Configure attribute reporting for a single attribute."""
        return await self.configure_reporting_multiple(
            {attribute: (min_interval, max_interval, reportable_change)},
            manufacturer=manufacturer,
        )

    async def configure_reporting_multiple(
        self,
        attributes: dict[int | str, tuple[int, int, int]],
        manufacturer: int | None = None,
    ) -> list[foundation.ConfigureReportingResponseRecord]:
        """Configure attribute reporting for multiple attributes in the same request.

        :param attributes: dict of attributes to configure attribute reporting.
        Key is either int or str for attribute id or attribute name.
        Value is a tuple of:
        - minimum reporting interval
        - maximum reporting interval
        - reportable change
        :param manufacturer: optional manufacturer id to use with the command
        """

        cfg = [
            self._attr_reporting_rec(attr, rep[0], rep[1], rep[2])
            for attr, rep in attributes.items()
        ]
        res = await self._configure_reporting(cfg, manufacturer=manufacturer)

        # Parse configure reporting result for unsupported attributes
        records = res[0]
        if (
            isinstance(records, list)
            and not (
                len(records) == 1 and records[0].status == foundation.Status.SUCCESS
            )
            and len(records) >= 0
        ):
            failed = [
                r.attrid
                for r in records
                if r.status == foundation.Status.UNSUPPORTED_ATTRIBUTE
            ]
            for attr in failed:
                self.add_unsupported_attribute(attr)

            success = [
                r.attrid for r in records if r.status == foundation.Status.SUCCESS
            ]
            for attr in success:
                self.remove_unsupported_attribute(attr)
        elif isinstance(records, list) and (
            len(records) == 1 and records[0].status == foundation.Status.SUCCESS
        ):
            # we get a single success when all are supported
            for attr in attributes:
                self.remove_unsupported_attribute(attr)
        return res

    def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs,
    ):
        command = self.server_commands[command_id]

        return self.request(
            False,
            command_id,
            command.schema,
            *args,
            manufacturer=manufacturer,
            expect_reply=expect_reply,
            tsn=tsn,
            **kwargs,
        )

    def client_command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        tsn: int | t.uint8_t | None = None,
        **kwargs,
    ):
        command = self.client_commands[command_id]

        return self.reply(
            False,
            command_id,
            command.schema,
            *args,
            manufacturer=manufacturer,
            tsn=tsn,
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

    def update_attribute(self, attrid: int | t.uint16_t, value: Any) -> None:
        """Update specified attribute with specified value"""
        self._update_attribute(attrid, value)

    def _update_attribute(self, attrid: int | t.uint16_t, value: Any) -> None:
        if value is None:
            if attrid not in self._attr_cache:
                return

            self._attr_cache.pop(attrid)
            self._attr_last_updated.pop(attrid)
            self.listener_event("attribute_cleared", attrid)
        else:
            now = datetime.now(timezone.utc)
            self._attr_cache[attrid] = value
            self._attr_last_updated[attrid] = now
            self.listener_event("attribute_updated", attrid, value, now)

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

    def get(self, key: int | str, default: Any | None = None) -> Any:
        """Get cached attribute."""
        attr_def = self.find_attribute(key)
        return self._attr_cache.get(attr_def.id, default)

    def __getitem__(self, key: int | str) -> Any:
        """Return cached value of the attr."""
        return self._attr_cache[self.find_attribute(key).id]

    def __setitem__(self, key: int | str, value: Any) -> None:
        """Set cached value through attribute write."""
        if not isinstance(key, (int, str)):
            raise ValueError("attr_name or attr_id are accepted only")  # noqa: TRY004
        self.create_catching_task(self.write_attributes({key: value}))

    def general_command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
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
    _write_attributes_undivided = functools.partialmethod(
        general_command, foundation.GeneralCommand.Write_Attributes_Undivided
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
        self, attr: int | str, inhibit_events: bool = False
    ) -> None:
        """Adds unsupported attribute."""

        if attr in self.unsupported_attributes:
            return

        self.unsupported_attributes.add(attr)

        if isinstance(attr, int) and not inhibit_events:
            self.listener_event("unsupported_attribute_added", attr)

        try:
            attrdef = self.find_attribute(attr)
        except KeyError:
            pass
        else:
            if isinstance(attr, int):
                self.add_unsupported_attribute(attrdef.name, inhibit_events)
            else:
                self.add_unsupported_attribute(attrdef.id, inhibit_events)

    def remove_unsupported_attribute(
        self, attr: int | str, inhibit_events: bool = False
    ) -> None:
        """Removes an unsupported attribute."""

        if attr not in self.unsupported_attributes:
            return

        self.unsupported_attributes.remove(attr)

        if isinstance(attr, int) and not inhibit_events:
            self.listener_event("unsupported_attribute_removed", attr)

        try:
            attrdef = self.find_attribute(attr)
        except KeyError:
            pass
        else:
            if isinstance(attr, int):
                self.remove_unsupported_attribute(attrdef.name, inhibit_events)
            else:
                self.remove_unsupported_attribute(attrdef.id, inhibit_events)


class ClusterPersistingListener:
    def __init__(self, applistener: PersistingListener, cluster: Cluster) -> None:
        self._applistener = applistener
        self._cluster = cluster

    def attribute_updated(
        self, attrid: int | t.uint16_t, value: Any, timestamp: datetime
    ) -> None:
        self._applistener.attribute_updated(self._cluster, attrid, value, timestamp)

    def attribute_cleared(self, attrid: int | t.uint16_t) -> None:
        self._applistener.attribute_cleared(self._cluster, attrid)

    def cluster_command(self, *args, **kwargs) -> None:
        pass

    def general_command(self, *args, **kwargs) -> None:
        pass

    def unsupported_attribute_added(self, attrid: int) -> None:
        """An unsupported attribute was added."""
        self._applistener.unsupported_attribute_added(self._cluster, attrid)

    def unsupported_attribute_removed(self, attrid: int) -> None:
        """Remove an unsupported attribute."""
        self._applistener.unsupported_attribute_removed(self._cluster, attrid)


# Import to populate the registry
from . import clusters  # noqa: F401, E402, isort:skip
