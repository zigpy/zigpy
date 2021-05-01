from __future__ import annotations

import asyncio
import enum
import functools
import logging
from typing import Any, Callable, Coroutine, List, Optional, Sequence, Union

from zigpy import util
import zigpy.types as t
from zigpy.typing import EndpointType
from zigpy.zcl import foundation

LOGGER = logging.getLogger(__name__)

AddressingMode = Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]


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
        schema=schema_dict, is_reply=is_reply, id=command_id, name="schema"
    )
    temp.compile_schema()

    return temp.schema


def future_exception(e):
    future = asyncio.Future()
    future.set_exception(e)

    return future


class ClusterType(enum.IntEnum):
    Server = 0
    Client = 1


class Cluster(util.ListenableMixin, util.CatchingTaskMixin):
    """A cluster on an endpoint"""

    _skip_registry: bool = False

    cluster_id: t.uint16_t = None
    cluster_id_range: tuple[t.uint16_t, t.uint16_t] = None

    attributes: dict[int, tuple[str, Callable]] = {}
    client_commands: dict[int, foundation.ZCLCommandDef] = {}
    server_commands: dict[int, foundation.ZCLCommandDef] = {}

    manufacturer_attributes: dict[int, tuple[str, Callable]] = {}
    manufacturer_client_commands: dict[int, foundation.ZCLCommandDef] = {}
    manufacturer_server_commands: dict[int, foundation.ZCLCommandDef] = {}

    # Internal caches and indices
    _registry: dict = {}
    _registry_custom_clusters: set = set()
    _registry_range: dict = {}

    _server_commands_idx: dict[str, int] = {}
    _client_commands_idx: dict[str, int] = {}

    attridx: dict[str, int] = {}

    def __init_subclass__(cls):
        if cls.cluster_id is not None:
            cls.cluster_id = t.ClusterId(cls.cluster_id)

        if cls.manufacturer_attributes:
            # A new dictionary is made. Otherwise, the update affects the parent class.
            cls.attributes = {**cls.attributes, **cls.manufacturer_attributes}

        cls.attridx = {
            attr_name: attr_id for attr_id, (attr_name, _) in cls.attributes.items()
        }

        for commands_type in ("server_commands", "client_commands"):
            commands = getattr(cls, commands_type)

            manufacturer_specific = getattr(cls, f"manufacturer_{commands_type}", {})

            # Only change the attribute if manufacturer-specific commands exist
            if manufacturer_specific:
                commands = {**commands, **manufacturer_specific}

            commands_idx = {}

            for command_id, command in list(commands.items()):
                if isinstance(command, tuple):
                    # Backwards compatibility with old command tuples
                    name, schema, is_reply = command
                    commands[command_id] = command = foundation.ZCLCommandDef(
                        id=command_id,
                        name=name,
                        schema=convert_list_schema(schema, command_id, is_reply),
                        is_reply=is_reply,
                    )
                else:
                    command.id = command_id

                command.compile_schema()

                commands_idx[command.name] = command.id

            setattr(cls, f"_{commands_type}_idx", commands_idx)

            if manufacturer_specific:
                setattr(cls, commands_type, commands)

        if cls._skip_registry:
            if cls.__name__ != "CustomCluster":
                cls._registry_custom_clusters.add(cls)

            return

        if cls.cluster_id is not None:
            cls._registry[cls.cluster_id] = cls

        if cls.cluster_id_range is not None:
            cls._registry_range[cls.cluster_id_range] = cls

    def __init__(self, endpoint: EndpointType, is_server: bool = True):
        self._endpoint: EndpointType = endpoint
        self._attr_cache: dict[int, Any] = {}
        self._listeners = {}

        if is_server:
            self._type: ClusterType = ClusterType.Server
        else:
            self._type: ClusterType = ClusterType.Client

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

        LOGGER.warning("Unknown cluster 0x%04X", cluster_id)

        cluster = cls(endpoint, is_server)
        cluster.cluster_id = cluster_id
        return cluster

    def deserialize(self, data: bytes) -> tuple[foundation.ZCLHeader, ...]:
        orig_data = data
        hdr, data = foundation.ZCLHeader.deserialize(data)
        self.debug("ZCL header: %s", hdr)

        if hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND:
            # Cluster command
            if hdr.is_reply:
                commands = self.client_commands
            else:
                commands = self.server_commands

            if hdr.command_id not in commands:
                self.warning("Unknown cluster command %s %s", hdr.command_id, data)
                return hdr, data

            command = commands[hdr.command_id]
        else:
            # General command
            if hdr.command_id not in foundation.COMMANDS:
                self.warning("Unknown foundation command %s %s", hdr.command_id, data)
                return hdr, data

            command = foundation.COMMANDS[hdr.command_id]

        response, data = command.schema.deserialize(data)

        if data:
            self.warning(
                "Data remains after deserializing ZCL frame %s: %s", orig_data, data
            )

        hdr.frame_control.is_reply = command.is_reply

        return hdr, list(response.as_tuple())

    @util.retryable_request
    def request(
        self,
        general: bool,
        command_id: Union[foundation.Command, int, t.uint8_t],
        schema: dict | t.Struct,
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        expect_reply: bool = True,
        tsn: Optional[Union[int, t.uint8_t]] = None,
        **kwargs,
    ):
        # Convert out-of-band dict schemas to struct schemas
        if isinstance(schema, (tuple, list)):
            schema = convert_list_schema(
                command_id=command_id, schema=schema, is_reply=False
            )

        try:
            payload = schema(*args, **kwargs).serialize()
        except (ValueError, TypeError) as e:
            return future_exception(e)

        if tsn is None:
            tsn = self._endpoint.device.application.get_sequence()

        if general:
            hdr = foundation.ZCLHeader.general(tsn, command_id, manufacturer)
        else:
            hdr = foundation.ZCLHeader.cluster(tsn, command_id, manufacturer)

        data = hdr.serialize() + payload

        return self._endpoint.request(
            self.cluster_id, tsn, data, expect_reply=expect_reply, command_id=command_id
        )

    def reply(
        self,
        general: bool,
        command_id: Union[foundation.Command, int, t.uint8_t],
        schema: dict | t.Struct,
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        tsn: Optional[Union[int, t.uint8_t]] = None,
        **kwargs,
    ):
        # Convert out-of-band dict schemas to struct schemas
        if isinstance(schema, (tuple, list)):
            schema = convert_list_schema(
                command_id=command_id, schema=schema, is_reply=True
            )

        try:
            payload = schema(*args, **kwargs).serialize()
        except (ValueError, TypeError) as e:
            return future_exception(e)

        if tsn is None:
            tsn = self._endpoint.device.application.get_sequence()

        if general:
            hdr = foundation.ZCLHeader.general(
                tsn, command_id, manufacturer, is_reply=True
            )
        else:
            hdr = foundation.ZCLHeader.cluster(
                tsn, command_id, manufacturer, is_reply=True
            )

        data = hdr.serialize() + payload

        return self._endpoint.reply(self.cluster_id, tsn, data, command_id=command_id)

    def handle_message(
        self,
        hdr: foundation.ZCLHeader,
        args: List[Any],
        *,
        dst_addressing: Optional[AddressingMode] = None,
    ):
        self.debug("ZCL request 0x%04x: %s", hdr.command_id, args)
        if hdr.frame_control.is_cluster:
            self.handle_cluster_request(hdr, args, dst_addressing=dst_addressing)
            self.listener_event("cluster_command", hdr.tsn, hdr.command_id, args)
            return
        self.listener_event("general_command", hdr, args)
        self.handle_cluster_general_request(hdr, args, dst_addressing=dst_addressing)

    def handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: List[Any],
        *,
        dst_addressing: Optional[AddressingMode] = None,
    ):
        self.debug("No handler for cluster command %s", hdr.command_id)

    def handle_cluster_general_request(
        self,
        hdr: foundation.ZCLHeader,
        args: List,
        *,
        dst_addressing: Optional[AddressingMode] = None,
    ) -> None:
        if hdr.command_id == foundation.Command.Report_Attributes:
            valuestr = ", ".join(
                [
                    f"{self.attributes.get(a.attrid, [a.attrid])[0]}={a.value.value}"
                    for a in args[0]
                ]
            )
            self.debug("Attribute report received: %s", valuestr)
            for attr in args[0]:
                try:
                    value = self.attributes[attr.attrid][1](attr.value.value)
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
        attributes,
        allow_cache=False,
        only_cache=False,
        manufacturer=None,
    ):
        success, failure = {}, {}
        attribute_ids = []
        orig_attributes = {}
        for attribute in attributes:
            if isinstance(attribute, str):
                attrid = self.attridx[attribute]
            else:
                attrid = attribute
            attribute_ids.append(attrid)
            orig_attributes[attrid] = attribute

        to_read = []
        if allow_cache or only_cache:
            for idx, attribute in enumerate(attribute_ids):
                if attribute in self._attr_cache:
                    success[attributes[idx]] = self._attr_cache[attribute]
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
                        value = self.attributes[record.attrid][1](record.value.value)
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
                else:
                    failure[orig_attribute] = record.status

        return success, failure

    def read_attributes_rsp(self, attributes, manufacturer=None, *, tsn=None):
        args = []
        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attridx[attrid]

            a = foundation.ReadAttributeRecord(
                attrid, foundation.Status.UNSUPPORTED_ATTRIBUTE, foundation.TypeValue()
            )
            args.append(a)

            if value is None:
                continue

            try:
                a.status = foundation.Status.SUCCESS
                python_type = self.attributes[attrid][1]
                a.value.type = foundation.DATA_TYPES.pytype_to_datatype_id(python_type)
                a.value.value = python_type(value)
            except ValueError as e:
                a.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
                self.error(str(e))

        return self._read_attributes_rsp(args, manufacturer=manufacturer, tsn=tsn)

    def _write_attr_records(
        self, attributes: dict[Union[str, int], Any]
    ) -> List[foundation.Attribute]:
        args = []
        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attridx[attrid]
            if attrid not in self.attributes:
                self.error("%d is not a valid attribute id", attrid)
                continue

            attr = foundation.Attribute(attrid, foundation.TypeValue())

            python_type = self.attributes[attrid][1]
            attr.value.type = foundation.DATA_TYPES.pytype_to_datatype_id(python_type)

            try:
                attr.value.value = python_type(value)
            except ValueError as e:
                self.error(
                    "Failed to convert attribute 0x%04X from %s (%s) to type %s: %s",
                    attrid,
                    value,
                    type(value),
                    python_type,
                    e,
                )
            else:
                args.append(attr)

        return args

    async def write_attributes(
        self, attributes: dict[Union[str, int], Any], manufacturer: Optional[int] = None
    ) -> List:
        args = self._write_attr_records(attributes)
        result = await self._write_attributes(args, manufacturer=manufacturer)
        if not isinstance(result[0], list):
            return result

        records = result[0]
        if len(records) == 1 and records[0].status == foundation.Status.SUCCESS:
            for attr_rec in args:
                self._attr_cache[attr_rec.attrid] = attr_rec.value.value
        else:
            failed = [rec.attrid for rec in records]
            for attr_rec in args:
                if attr_rec.attrid not in failed:
                    self._attr_cache[attr_rec.attrid] = attr_rec.value.value

        return result

    def write_attributes_undivided(
        self, attributes: dict[Union[str, int], Any], manufacturer: Optional[int] = None
    ) -> List:
        """Either all or none of the attributes are written by the device."""
        args = self._write_attr_records(attributes)
        return self._write_attributes_undivided(args, manufacturer=manufacturer)

    def bind(self):
        return self._endpoint.device.zdo.bind(cluster=self)

    def unbind(self):
        return self._endpoint.device.zdo.unbind(cluster=self)

    def _attr_reporting_rec(
        self,
        attribute: Union[int, str],
        min_interval: int,
        max_interval: int,
        reportable_change: int = 1,
        direction: int = 0x00,
    ) -> foundation.ConfigureReportingResponseRecord:
        if isinstance(attribute, str):
            attrid = self.attridx.get(attribute)
        else:
            attrid = attribute
        if attrid is None or attrid not in self.attributes:
            raise ValueError(f"Unknown {attribute} name of {self.ep_attribute} cluster")

        cfg = foundation.AttributeReportingConfig()
        cfg.direction = direction
        cfg.attrid = attrid
        cfg.datatype = foundation.DATA_TYPES.pytype_to_datatype_id(
            self.attributes.get(attrid, (None, foundation.Unknown))[1]
        )
        cfg.min_interval = min_interval
        cfg.max_interval = max_interval
        cfg.reportable_change = reportable_change
        return cfg

    def configure_reporting(
        self,
        attribute: Union[int, str],
        min_interval: int,
        max_interval: int,
        reportable_change: int,
        manufacturer: Optional[int] = None,
    ) -> Coroutine:
        cfg = self._attr_reporting_rec(
            attribute, min_interval, max_interval, reportable_change
        )
        return self._configure_reporting([cfg], manufacturer=manufacturer)

    def configure_reporting_multiple(
        self,
        attributes: dict[Union[int, str], tuple[int, int, int]],
        manufacturer: Optional[int] = None,
    ) -> Coroutine:
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
        return self._configure_reporting(cfg, manufacturer=manufacturer)

    def command(
        self,
        command_id: Union[foundation.Command, int, t.uint8_t],
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        expect_reply: bool = True,
        tries: int = 1,
        tsn: Optional[Union[int, t.uint8_t]] = None,
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
        command_id: Union[foundation.Command, int, t.uint8_t],
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        tsn: Optional[Union[int, t.uint8_t]] = None,
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

    def _update_attribute(self, attrid, value):
        self._attr_cache[attrid] = value
        self.listener_event("attribute_updated", attrid, value)

    def log(self, lvl, msg, *args, **kwargs):
        msg = "[0x%04x:%s:0x%04x] " + msg
        args = (
            self._endpoint.device.nwk,
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
            raise AttributeError("No such command name: %s" % (name,))

    def get(self, key: Union[int, str], default: Optional[Any] = None) -> Any:
        """Get cached attribute."""
        if isinstance(key, int):
            return self._attr_cache.get(key, default)
        elif isinstance(key, str):
            try:
                attr_id = self.attridx[key]
            except KeyError:
                return default
            return self._attr_cache.get(attr_id, default)

        raise ValueError("attr_name or attr_id are accepted only")

    def __getitem__(self, key: Union[int, str]) -> Any:
        """Return cached value of the attr."""
        if isinstance(key, int):
            return self._attr_cache[key]
        elif isinstance(key, str):
            return self._attr_cache[self.attridx[key]]
        raise ValueError("attr_name or attr_id are accepted only")

    def __setitem__(self, key: Union[int, str], value: Any) -> None:
        """Set cached value through attribute write."""
        if not isinstance(key, (int, str)):
            raise ValueError("attr_name or attr_id are accepted only")
        self.create_catching_task(self.write_attributes({key: value}))

    def general_command(
        self,
        command_id: Union[foundation.Command, int, t.uint8_t],
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        expect_reply: bool = True,
        tries: int = 1,
        tsn: Optional[Union[int, t.uint8_t]] = None,
        **kwargs,
    ):
        command = foundation.COMMANDS[command_id]

        if command.is_reply:
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
        general_command, foundation.Command.Configure_Reporting
    )
    _read_attributes = functools.partialmethod(
        general_command, foundation.Command.Read_Attributes
    )
    _read_attributes_rsp = functools.partialmethod(
        general_command, foundation.Command.Read_Attributes_rsp
    )
    _write_attributes = functools.partialmethod(
        general_command, foundation.Command.Write_Attributes
    )
    _write_attributes_undivided = functools.partialmethod(
        general_command, foundation.Command.Write_Attributes_Undivided
    )
    discover_attributes = functools.partialmethod(
        general_command, foundation.Command.Discover_Attributes
    )
    discover_attributes_extended = functools.partialmethod(
        general_command, foundation.Command.Discover_Attribute_Extended
    )
    discover_commands_received = functools.partialmethod(
        general_command, foundation.Command.Discover_Commands_Received
    )
    discover_commands_generated = functools.partialmethod(
        general_command, foundation.Command.Discover_Commands_Generated
    )

    def send_default_rsp(
        self,
        hdr: foundation.ZCLHeader,
        status: foundation.Status = foundation.Status.SUCCESS,
    ) -> None:
        """Send default response unconditionally."""
        self.create_catching_task(
            self.general_command(
                foundation.Command.Default_Response,
                hdr.command_id,
                status,
                tsn=hdr.tsn,
            )
        )


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


# Import to populate the registry
from . import clusters  # noqa: F401, E402, isort:skip
