from __future__ import annotations

import enum
import functools
import logging
from typing import Any, Sequence
import warnings

from zigpy import util
import zigpy.types as t
from zigpy.typing import AddressingMode, EndpointType
from zigpy.zcl import foundation

LOGGER = logging.getLogger(__name__)


def convert_list_schema(
    schema: Sequence[type], command_id: int, is_reply: bool
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
        direction=foundation.Direction._from_is_reply(is_reply),
        id=command_id,
        name="schema",
    )

    return temp.with_compiled_schema().schema


class ClusterType(enum.IntEnum):
    Server = 0
    Client = 1


class Cluster(util.ListenableMixin, util.CatchingTaskMixin):
    """A cluster on an endpoint"""

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

    # Clusters contain attributes and both client and server commands
    attributes: dict[int, foundation.ZCLAttributeDef] = {}
    client_commands: dict[int, foundation.ZCLCommandDef] = {}
    server_commands: dict[int, foundation.ZCLCommandDef] = {}

    # Internal caches and indices
    _registry: dict = {}
    _registry_range: dict = {}

    _server_commands_idx: dict[str, int] = {}
    _client_commands_idx: dict[str, int] = {}

    attributes_by_name: dict[str, foundation.ZCLAttributeDef] = {}
    commands_by_name: dict[str, foundation.ZCLCommandDef] = {}

    def __init_subclass__(cls):
        # Fail on deprecated attribute presence
        for a in ("attributes", "client_commands", "server_commands"):
            if not hasattr(cls, f"manufacturer_{a}"):
                continue

            raise TypeError(
                f"`manufacturer_{a}` is deprecated. Copy the parent class's `{a}`"
                f" dictionary and update it with your manufacturer-specific `{a}`. Make"
                f" sure to specify that it is manufacturer-specific through the "
                f" appropriate constructor or tuple!"
            )

        if cls.cluster_id is not None:
            cls.cluster_id = t.ClusterId(cls.cluster_id)

        # Clear the caches and lookup tables. Their contents should correspond exactly
        # to what's in their respective command/attribute dictionaries.
        cls.attributes_by_name = {}
        cls.commands_by_name = {}
        cls._server_commands_idx = {}
        cls._client_commands_idx = {}

        # Compile command definitions
        for commands, index in [
            (cls.server_commands, cls._server_commands_idx),
            (cls.client_commands, cls._client_commands_idx),
        ]:
            for command_id, command in list(commands.items()):
                if isinstance(command, tuple):
                    # Backwards compatibility with old command tuples
                    name, schema, is_reply = command
                    command = foundation.ZCLCommandDef(
                        id=command_id,
                        name=name,
                        schema=convert_list_schema(schema, command_id, is_reply),
                        is_reply=is_reply,
                    )
                else:
                    command = command.replace(id=command_id)

                if command.name in cls.commands_by_name:
                    raise TypeError(
                        f"Command name {command} is not unique in {cls}: {cls.commands_by_name}"
                    )

                index[command.name] = command.id

                command = command.with_compiled_schema()
                commands[command.id] = command
                cls.commands_by_name[command.name] = command

        # Compile attributes
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

            cls.attributes[attr.id] = attr
            cls.attributes_by_name[attr.name] = attr

        if cls._skip_registry:
            return

        if cls.cluster_id is not None:
            cls._registry[cls.cluster_id] = cls

        if cls.cluster_id_range is not None:
            cls._registry_range[cls.cluster_id_range] = cls

    def __init__(self, endpoint: EndpointType, is_server: bool = True):
        self._endpoint: EndpointType = endpoint
        self._attr_cache: dict[int, Any] = {}
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
            raise ValueError(
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
            if hdr.direction == foundation.Direction.Client_to_Server:
                commands = self.client_commands
            else:
                commands = self.server_commands

            if hdr.command_id not in commands:
                self.warning("Unknown cluster command %s %s", hdr.command_id, data)
                return hdr, data

            command = commands[hdr.command_id]
        else:
            # General command
            if hdr.command_id not in foundation.GENERAL_COMMANDS:
                self.warning("Unknown foundation command %s %s", hdr.command_id, data)
                return hdr, data

            command = foundation.GENERAL_COMMANDS[hdr.command_id]

        hdr.frame_control.direction = command.direction
        response, data = command.schema.deserialize(data)

        self.debug("Decoded ZCL frame: %s:%r", type(self).__name__, response)

        if data:
            self.warning("Data remains after deserializing ZCL frame: %r", data)

        return hdr, response

    def _create_request(
        self,
        *,
        general: bool,
        command_id: foundation.GeneralCommand | int,
        schema: dict | t.Struct,
        manufacturer: int | None = None,
        tsn: int | None = None,
        disable_default_response: bool,
        direction: foundation.Direction,
        # Schema args and kwargs
        args: tuple[Any, ...],
        kwargs: Any,
    ) -> tuple[foundation.ZCLHeader, bytes]:
        # Convert out-of-band dict schemas to struct schemas
        if isinstance(schema, (tuple, list)):
            schema = convert_list_schema(
                command_id=command_id, schema=schema, is_reply=False
            )

        request = schema(*args, **kwargs)  # type:ignore[operator]
        request.serialize()  # Throw an error before generating a new TSN

        if tsn is None:
            tsn = self._endpoint.device.application.get_sequence()

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

    @util.retryable_request
    async def request(
        self,
        general: bool,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        schema: dict | t.Struct,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
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
                foundation.Direction.Client_to_Server
                if self.is_client
                else foundation.Direction.Server_to_Client
            ),
            args=args,
            kwargs=kwargs,
        )

        self.debug("Sending request header: %r", hdr)
        self.debug("Sending request: %r", request)
        data = hdr.serialize() + request.serialize()

        return await self._endpoint.request(
            self.cluster_id,
            hdr.tsn,
            data,
            expect_reply=expect_reply,
            command_id=hdr.command_id,
        )

    async def reply(
        self,
        general: bool,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        schema: dict | t.Struct,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        tsn: int | t.uint8_t | None = None,
        **kwargs,
    ):
        hdr, request = self._create_request(
            general=general,
            command_id=command_id,
            schema=schema,
            manufacturer=manufacturer,
            tsn=tsn,
            disable_default_response=True,
            direction=foundation.Direction.Client_to_Server,
            args=args,
            kwargs=kwargs,
        )

        self.debug("Sending reply header: %r", hdr)
        self.debug("Sending reply: %r", request)
        data = hdr.serialize() + request.serialize()

        return await self._endpoint.reply(
            self.cluster_id, hdr.tsn, data, command_id=hdr.command_id
        )

    def handle_message(
        self,
        hdr: foundation.ZCLHeader,
        args: list[Any],
        *,
        dst_addressing: AddressingMode | None = None,
    ):
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

    def read_attributes_raw(self, attributes, manufacturer=None):
        attributes = [t.uint16_t(a) for a in attributes]
        return self._read_attributes(attributes, manufacturer=manufacturer)

    async def read_attributes(
        self,
        attributes: list[int | str],
        allow_cache: bool = False,
        only_cache: bool = False,
        manufacturer: int | t.uint16_t | None = None,
    ):
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

        result = await self.read_attributes_raw(to_read, manufacturer=manufacturer)
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

    def read_attributes_rsp(self, attributes, manufacturer=None, *, tsn=None):
        args = []
        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attributes_by_name[attrid].id

            a = foundation.ReadAttributeRecord(
                attrid, foundation.Status.UNSUPPORTED_ATTRIBUTE, foundation.TypeValue()
            )
            args.append(a)

            if value is None:
                continue

            try:
                a.status = foundation.Status.SUCCESS
                python_type = self.attributes[attrid].type
                a.value.type = foundation.DATA_TYPES.pytype_to_datatype_id(python_type)
                a.value.value = python_type(value)
            except ValueError as e:
                a.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
                self.error(str(e))

        return self._read_attributes_rsp(args, manufacturer=manufacturer, tsn=tsn)

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
            attr.value.type = foundation.DATA_TYPES.pytype_to_datatype_id(attr_def.type)

            try:
                attr.value.value = attr_def.type(value)
            except ValueError as e:
                self.error(
                    "Failed to convert attribute 0x%04X from %s (%s) to type %s: %s",
                    attrid,
                    value,
                    type(value),
                    attr_def.type,
                    e,
                )
            else:
                args.append(attr)

        return args

    async def write_attributes(
        self, attributes: dict[str | int, Any], manufacturer: int | None = None
    ) -> list:
        """Write attributes to device with internal 'attributes' validation"""
        attrs = self._write_attr_records(attributes)
        return await self.write_attributes_raw(attrs, manufacturer)

    async def write_attributes_raw(
        self, attrs: list[foundation.Attribute], manufacturer: int | None = None
    ) -> list:
        """Write attributes to device without internal 'attributes' validation"""
        result = await self._write_attributes(attrs, manufacturer=manufacturer)
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

    def bind(self):
        return self._endpoint.device.zdo.bind(cluster=self)

    def unbind(self):
        return self._endpoint.device.zdo.unbind(cluster=self)

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
        except KeyError:
            raise ValueError(f"Unknown attribute {attribute!r} of {self} cluster")

        cfg = foundation.AttributeReportingConfig()
        cfg.direction = direction
        cfg.attrid = attr_def.id
        cfg.datatype = foundation.DATA_TYPES.pytype_to_datatype_id(attr_def.type)
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
        response = await self.configure_reporting_multiple(
            {attribute: (min_interval, max_interval, reportable_change)},
            manufacturer=manufacturer,
        )
        return response

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
            for attr in attributes.keys():
                self.remove_unsupported_attribute(attr)
        return res

    def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tries: int = 1,
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
            tries=tries,
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
    def is_client(self) -> bool:
        """Return True if this is a client cluster."""
        return self._type == ClusterType.Client

    @property
    def is_server(self) -> bool:
        """Return True if this is a server cluster."""
        return self._type == ClusterType.Server

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def endpoint(self):
        return self._endpoint

    @property
    def commands(self):
        return list(self._server_commands_idx.keys())

    def update_attribute(self, attrid, value):
        """Update specified attribute with specified value"""
        self._update_attribute(attrid, value)

    def _update_attribute(self, attrid, value):
        self._attr_cache[attrid] = value
        self.listener_event("attribute_updated", attrid, value)

    def log(self, lvl, msg, *args, **kwargs):
        msg = "[%s:%s:0x%04x] " + msg
        args = (
            self._endpoint.device.name,
            self._endpoint.endpoint_id,
            self.cluster_id,
        ) + args
        return LOGGER.log(lvl, msg, *args, **kwargs)

    def __getattr__(self, name):
        if name in self._client_commands_idx:
            return functools.partial(
                self.client_command, self._client_commands_idx[name]
            )
        elif name in self._server_commands_idx:
            return functools.partial(self.command, self._server_commands_idx[name])
        else:
            raise AttributeError(f"No such command name: {name}")

    def get(self, key: int | str, default: Any | None = None) -> Any:
        """Get cached attribute."""
        try:
            attr_def = self.find_attribute(key)
        except KeyError:
            return default

        return self._attr_cache.get(attr_def.id, default)

    def __getitem__(self, key: int | str) -> Any:
        """Return cached value of the attr."""
        return self._attr_cache[self.find_attribute(key).id]

    def __setitem__(self, key: int | str, value: Any) -> None:
        """Set cached value through attribute write."""
        if not isinstance(key, (int, str)):
            raise ValueError("attr_name or attr_id are accepted only")
        self.create_catching_task(self.write_attributes({key: value}))

    def general_command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tries: int = 1,
        tsn: int | t.uint8_t | None = None,
        **kwargs,
    ):
        command = foundation.GENERAL_COMMANDS[command_id]

        if command.direction == foundation.Direction.Client_to_Server:
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
            tries=tries,
            tsn=tsn,
            **kwargs,
        )

    _configure_reporting = functools.partialmethod(
        general_command, foundation.GeneralCommand.Configure_Reporting
    )
    _read_attributes = functools.partialmethod(
        general_command, foundation.GeneralCommand.Read_Attributes
    )
    _read_attributes_rsp = functools.partialmethod(
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
    def __init__(self, applistener, cluster):
        self._applistener = applistener
        self._cluster = cluster

    def attribute_updated(self, attrid, value):
        self._applistener.attribute_updated(self._cluster, attrid, value)

    def cluster_command(self, *args, **kwargs):
        pass

    def general_command(self, *args, **kwargs):
        pass

    def unsupported_attribute_added(self, attrid: int) -> None:
        """An unsupported attribute was added."""
        self._applistener.unsupported_attribute_added(self._cluster, attrid)

    def unsupported_attribute_removed(self, attrid: int) -> None:
        """Remove an unsupported attribute."""
        self._applistener.unsupported_attribute_removed(self._cluster, attrid)


# Import to populate the registry
from . import clusters  # noqa: F401, E402, isort:skip
