import asyncio
import enum
import functools
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union

from zigpy import util
import zigpy.types as t
from zigpy.typing import EndpointType
from zigpy.zcl import foundation

LOGGER = logging.getLogger(__name__)


class Registry(type):
    def __init__(cls, name, bases, nmspc):  # noqa: N805
        super(Registry, cls).__init__(name, bases, nmspc)

        if hasattr(cls, "cluster_id"):
            cls.cluster_id = t.ClusterId(cls.cluster_id)
        manufacturer_attributes = getattr(cls, "manufacturer_attributes", None)
        if manufacturer_attributes:
            cls.attributes = {**cls.attributes, **manufacturer_attributes}
        cls.attridx: Dict[str, int] = {
            attr_name: attr_id for attr_id, (attr_name, _) in cls.attributes.items()
        }

        for commands_type in ("server_commands", "client_commands"):
            commands = getattr(cls, commands_type, None)
            manufacturer_specific = getattr(cls, f"manufacturer_{commands_type}", {})
            commands_idx = {}
            if manufacturer_specific:
                commands = {**commands, **manufacturer_specific}
                setattr(cls, commands_type, commands)
            for command_id, (command_name, _, _) in commands.items():
                commands_idx[command_name] = command_id
            setattr(cls, f"_{commands_type}_idx", commands_idx)

        if getattr(cls, "_skip_registry", False):
            if cls.__name__ != "CustomCluster":
                cls._registry_custom_clusters.add(cls)
            return

        if hasattr(cls, "cluster_id"):
            cls._registry[cls.cluster_id] = cls
        if hasattr(cls, "cluster_id_range"):
            cls._registry_range[cls.cluster_id_range] = cls


class ClusterType(enum.IntEnum):
    Server = 0
    Client = 1


class Cluster(util.ListenableMixin, util.CatchingTaskMixin, metaclass=Registry):
    """A cluster on an endpoint"""

    _registry: Dict = {}
    _registry_custom_clusters: Set = set()
    _registry_range: Dict = {}
    _server_commands_idx: Dict[str, int] = {}
    _client_commands_idx: Dict[str, int] = {}
    attridx: Dict[str, int]
    attributes: Dict[int, Tuple[str, Callable]] = {}
    ep_attribute: str = None
    client_commands: Dict[int, Tuple[str, Tuple, bool]] = {}
    server_commands: Dict[int, Tuple[str, Tuple, bool]] = {}

    def __init__(self, endpoint: EndpointType, is_server: bool = True):
        self._endpoint: EndpointType = endpoint
        self._attr_cache: Dict[int, Any] = {}
        self._listeners = {}
        if is_server:
            self._type: ClusterType = ClusterType.Server
        else:
            self._type: ClusterType = ClusterType.Client

    @classmethod
    def from_id(
        cls, endpoint: EndpointType, cluster_id: int, is_server: bool = True
    ) -> ClusterType:
        if cluster_id in cls._registry:
            c = cls._registry[cluster_id](endpoint, is_server)
            return c
        else:
            for cluster_id_range, cluster in cls._registry_range.items():
                if cluster_id_range[0] <= cluster_id <= cluster_id_range[1]:
                    c = cluster(endpoint, is_server)
                    c.cluster_id = t.ClusterId(cluster_id)
                    return c

        LOGGER.warning("Unknown cluster %s", cluster_id)
        c = cls(endpoint, is_server)
        c.cluster_id = t.ClusterId(cluster_id)
        return c

    def deserialize(self, data):
        hdr, data = foundation.ZCLHeader.deserialize(data)
        self.debug("ZCL deserialize: %s", hdr)
        if hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND:
            # Cluster command
            if hdr.is_reply:
                commands = self.client_commands
            else:
                commands = self.server_commands

            try:
                schema = commands[hdr.command_id][1]
                hdr.frame_control.is_reply = commands[hdr.command_id][2]
            except KeyError:
                self.warning("Unknown cluster-specific command %s", hdr.command_id)
                return hdr, data
        else:
            # General command
            try:
                schema = foundation.COMMANDS[hdr.command_id][0]
                hdr.frame_control.is_reply = foundation.COMMANDS[hdr.command_id][1]
            except KeyError:
                self.warning("Unknown foundation command %s", hdr.command_id)
                return hdr, data

        value, data = t.deserialize(data, schema)
        if data != b"":
            self.warning("Data remains after deserializing ZCL frame")

        return hdr, value

    @util.retryable_request
    def request(
        self,
        general: bool,
        command_id: Union[foundation.Command, int, t.uint8_t],
        schema: Tuple,
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        expect_reply: bool = True,
        tsn: Optional[Union[int, t.uint8_t]] = None,
    ):
        optional = len([s for s in schema if hasattr(s, "optional") and s.optional])
        if len(schema) < len(args) or len(args) < len(schema) - optional:
            self.error("Schema and args lengths do not match in request")
            error = asyncio.Future()
            error.set_exception(
                ValueError(
                    "Wrong number of parameters for request, expected %d argument(s)"
                    % len(schema)
                )
            )
            return error

        if tsn is None:
            tsn = self._endpoint.device.application.get_sequence()
        if general:
            hdr = foundation.ZCLHeader.general(tsn, command_id, manufacturer)
        else:
            hdr = foundation.ZCLHeader.cluster(tsn, command_id, manufacturer)
        hdr.manufacturer = manufacturer
        data = hdr.serialize() + t.serialize(args, schema)

        return self._endpoint.request(
            self.cluster_id, tsn, data, expect_reply=expect_reply, command_id=command_id
        )

    def reply(
        self,
        general: bool,
        command_id: Union[foundation.Command, int, t.uint8_t],
        schema: Tuple,
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        tsn: Optional[Union[int, t.uint8_t]] = None,
    ):
        if len(schema) != len(args) and foundation.Status not in schema:
            self.debug("Schema and args lengths do not match in reply")

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
        hdr.manufacturer = manufacturer
        data = hdr.serialize() + t.serialize(args, schema)

        return self._endpoint.reply(self.cluster_id, tsn, data, command_id=command_id)

    def handle_message(
        self,
        hdr: foundation.ZCLHeader,
        args: List[Any],
        *,
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
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
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
    ):
        self.debug("No handler for cluster command %s", hdr.command_id)

    def handle_cluster_general_request(
        self,
        hdr: foundation.ZCLHeader,
        args: List,
        *,
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
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
        self, attributes: Dict[Union[str, int], Any]
    ) -> List[foundation.Attribute]:
        args = []
        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attridx[attrid]
            if attrid not in self.attributes:
                self.error("%d is not a valid attribute id", attrid)
                continue

            a = foundation.Attribute(attrid, foundation.TypeValue())

            try:
                python_type = self.attributes[attrid][1]
                a.value.type = foundation.DATA_TYPES.pytype_to_datatype_id(python_type)
                a.value.value = python_type(value)
                args.append(a)
            except ValueError as e:
                self.error(str(e))
        return args

    async def write_attributes(
        self, attributes: Dict[Union[str, int], Any], manufacturer: Optional[int] = None
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
        self, attributes: Dict[Union[str, int], Any], manufacturer: Optional[int] = None
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
        attributes: Dict[Union[int, str], Tuple[int, int, int]],
        manufacturer: Optional[int] = None,
    ) -> Coroutine:
        """Configure attribute reporting for multiple attributes in the same request.

        :param attributes: dict of attributes to configure attribute reporting.
        Key is either int or str for attribute id or attribute name.
        Value is a Tuple of:
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
    ):
        schema = self.server_commands[command_id][1]
        return self.request(
            False,
            command_id,
            schema,
            *args,
            manufacturer=manufacturer,
            expect_reply=expect_reply,
            tries=tries,
            tsn=tsn,
        )

    def client_command(
        self,
        command_id: Union[foundation.Command, int, t.uint8_t],
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        tsn: Optional[Union[int, t.uint8_t]] = None,
    ):
        schema = self.client_commands[command_id][1]
        return self.reply(
            False, command_id, schema, *args, manufacturer=manufacturer, tsn=tsn
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
    ):
        schema = foundation.COMMANDS[command_id][0]
        if foundation.COMMANDS[command_id][1]:
            # should reply be retryable?
            return self.reply(
                True, command_id, schema, *args, manufacturer=manufacturer, tsn=tsn
            )

        return self.request(
            True,
            command_id,
            schema,
            *args,
            manufacturer=manufacturer,
            expect_reply=expect_reply,
            tries=tries,
            tsn=tsn,
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
