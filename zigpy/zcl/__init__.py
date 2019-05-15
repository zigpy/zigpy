import asyncio
import functools
import logging

import zigpy.types as t
from zigpy import util
from zigpy.zcl import foundation


LOGGER = logging.getLogger(__name__)


class Registry(type):
    def __init__(cls, name, bases, nmspc):  # noqa: N805
        super(Registry, cls).__init__(name, bases, nmspc)

        if hasattr(cls, 'attributes'):
            cls._attridx = {}
            for attrid, (attrname, datatype) in cls.attributes.items():
                cls._attridx[attrname] = attrid
        if hasattr(cls, 'server_commands'):
            cls._server_command_idx = {}
            for command_id, details in cls.server_commands.items():
                command_name, schema, is_reply = details
                cls._server_command_idx[command_name] = command_id
        if hasattr(cls, 'client_commands'):
            cls._client_command_idx = {}
            for command_id, details in cls.client_commands.items():
                command_name, schema, is_reply = details
                cls._client_command_idx[command_name] = command_id

        if getattr(cls, '_skip_registry', False):
            return

        if hasattr(cls, 'cluster_id'):
            cls._registry[cls.cluster_id] = cls
        if hasattr(cls, 'cluster_id_range'):
            cls._registry_range[cls.cluster_id_range] = cls


class Cluster(util.ListenableMixin, util.LocalLogMixin, metaclass=Registry):
    """A cluster on an endpoint"""
    _registry = {}
    _registry_range = {}
    _server_command_idx = {}
    _client_command_idx = {}

    def __init__(self, endpoint):
        self._endpoint = endpoint
        self._attr_cache = {}
        self._listeners = {}

    @classmethod
    def from_id(cls, endpoint, cluster_id):
        if cluster_id in cls._registry:
            return cls._registry[cluster_id](endpoint)
        else:
            for cluster_id_range, cluster in cls._registry_range.items():
                if cluster_id_range[0] <= cluster_id <= cluster_id_range[1]:
                    c = cluster(endpoint)
                    c.cluster_id = cluster_id
                    return c

        LOGGER.warning("Unknown cluster %s", cluster_id)
        c = cls(endpoint)
        c.cluster_id = cluster_id
        return c

    def deserialize(self, tsn, frame_type, is_reply, command_id, data):
        if frame_type == 1:
            # Cluster command
            if is_reply:
                commands = self.client_commands
            else:
                commands = self.server_commands

            try:
                schema = commands[command_id][1]
                is_reply = commands[command_id][2]
            except KeyError:
                LOGGER.warning("Unknown cluster-specific command %s", command_id)
                return tsn, command_id + 256, is_reply, data

            # Bad hack to differentiate foundation vs cluster
            command_id = command_id + 256
        else:
            # General command
            try:
                schema = foundation.COMMANDS[command_id][1]
                is_reply = foundation.COMMANDS[command_id][2]
            except KeyError:
                LOGGER.warning("Unknown foundation command %s", command_id)
                return tsn, command_id, is_reply, data

        value, data = t.deserialize(data, schema)
        if data != b'':
            LOGGER.warning("Data remains after deserializing ZCL frame")

        return tsn, command_id, is_reply, value

    @util.retryable_request
    def request(self, general, command_id, schema, *args, manufacturer=None, expect_reply=True):
        if len(schema) != len(args):
            self.error("Schema and args lengths do not match in request")
            error = asyncio.Future()
            error.set_exception(ValueError("Wrong number of parameters for request, expected %d argument(s)" % len(schema)))
            return error

        sequence = self._endpoint._device.application.get_sequence()
        if general:
            frame_control = 0x00
        else:
            frame_control = 0x01
        if manufacturer is not None:
            frame_control |= 0b0100
            manufacturer = manufacturer.to_bytes(2, 'little')
        else:
            manufacturer = b''
        data = bytes([frame_control]) + manufacturer + bytes([sequence, command_id])
        data += t.serialize(args, schema)

        return self._endpoint.request(self.cluster_id, sequence, data, expect_reply=expect_reply, command_id=command_id)

    def reply(self, general, command_id, schema, *args, manufacturer=None):
        if len(schema) != len(args) and foundation.Status not in schema:
            self.debug("Schema and args lengths do not match in reply")

        sequence = self._endpoint._device.application.get_sequence()
        frame_control = 0b1000  # Cluster reply command
        if not general:
            frame_control |= 0x01
        if manufacturer is not None:
            frame_control |= 0b0100
            manufacturer = manufacturer.to_bytes(2, 'little')
        else:
            manufacturer = b''
        data = bytes([frame_control]) + manufacturer + bytes([sequence, command_id])
        data += t.serialize(args, schema)

        return self._endpoint.reply(self.cluster_id, sequence, data)

    def handle_message(self, is_reply, tsn, command_id, args):
        if is_reply:
            self.debug("Unexpected ZCL reply 0x%04x: %s", command_id, args)
            return

        self.debug("ZCL request 0x%04x: %s", command_id, args)
        if command_id <= 0xff:
            self.listener_event('zdo_command', tsn, command_id, args)
        else:
            # Unencapsulate bad hack
            command_id -= 256
            self.listener_event('cluster_command', tsn, command_id, args)
            self.handle_cluster_request(tsn, command_id, args)
            return

        if command_id == 0x0a:  # Report attributes
            valuestr = ", ".join([
                "%s=%s" % (self.attributes.get(a.attrid, [a.attrid])[0],
                           a.value.value) for a in args[0]
            ])
            self.debug("Attribute report received: %s", valuestr)
            for attr in args[0]:
                self._update_attribute(attr.attrid, attr.value.value)
        else:
            self.handle_cluster_general_request(tsn, command_id, args)

    def handle_cluster_request(self, tsn, command_id, args):
        self.debug("No handler for cluster command %s", command_id)

    def handle_cluster_general_request(self, tsn, command_id, args):
        self.debug("No handler for general command %s", command_id)

    async def read_attributes_raw(self, attributes, manufacturer=None):
        schema = foundation.COMMANDS[0x00][1]
        attributes = [t.uint16_t(a) for a in attributes]
        v = await self.request(True, 0x00, schema, attributes, manufacturer=manufacturer)
        return v

    async def read_attributes(self, attributes, allow_cache=False, only_cache=False, raw=False, manufacturer=None):
        if raw:
            assert len(attributes) == 1
        success, failure = {}, {}
        attribute_ids = []
        orig_attributes = {}
        for attribute in attributes:
            if isinstance(attribute, str):
                attrid = self._attridx[attribute]
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
            if raw:
                return success[attributes[0]]
            return success, failure

        result = await self.read_attributes_raw(to_read, manufacturer=manufacturer)
        if not isinstance(result[0], list):
            for attrid in to_read:
                orig_attribute = orig_attributes[attrid]
                failure[orig_attribute] = result[0]  # Assume default response
        else:
            for record in result[0]:
                orig_attribute = orig_attributes[record.attrid]
                if record.status == 0:
                    self._update_attribute(record.attrid, record.value.value)
                    success[orig_attribute] = record.value.value
                else:
                    failure[orig_attribute] = record.status

        if raw:
            # KeyError is an appropriate exception here, I think.
            return success[attributes[0]]
        return success, failure

    def write_attributes(self, attributes, is_report=False, manufacturer=None,
                         unsupported_attrs=[]):
        args = []
        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self._attridx[attrid]
            if attrid not in self.attributes:
                self.error("%d is not a valid attribute id", attrid)
                continue

            if is_report:
                a = foundation.ReadAttributeRecord()
                a.status = 0
            else:
                a = foundation.Attribute()

            a.attrid = t.uint16_t(attrid)
            a.value = foundation.TypeValue()

            try:
                python_type = self.attributes[attrid][1]
                a.value.type = t.uint8_t(foundation.DATA_TYPE_IDX[python_type])
                a.value.value = python_type(value)
                args.append(a)
            except ValueError as e:
                self.error(str(e))

        if is_report and unsupported_attrs:
            for attrid in unsupported_attrs:
                a = foundation.ReadAttributeRecord()
                a.attrid = attrid
                a.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
                args.append(a)

        if is_report:
            schema = foundation.COMMANDS[0x01][1]
            return self.reply(True, 0x01, schema, args, manufacturer=manufacturer)
        else:
            schema = foundation.COMMANDS[0x02][1]
            return self.request(True, 0x02, schema, args, manufacturer=manufacturer)

    def bind(self):
        return self._endpoint.device.zdo.bind(self._endpoint.endpoint_id, self.cluster_id)

    def unbind(self):
        return self._endpoint.device.zdo.unbind(self._endpoint.endpoint_id, self.cluster_id)

    def configure_reporting(self, attribute, min_interval, max_interval,
                            reportable_change, manufacturer=None):
        if isinstance(attribute, str):
            attrid = self._attridx.get(attribute, None)
        else:
            attrid = attribute
        if attrid not in self.attributes or attrid is None:
            self.error("{} is not a valid attribute id".format(attribute))
            return

        schema = foundation.COMMANDS[0x06][1]
        cfg = foundation.AttributeReportingConfig()
        cfg.direction = 0
        cfg.attrid = attrid
        cfg.datatype = foundation.DATA_TYPE_IDX.get(
            self.attributes.get(attrid, (None, None))[1],
            None)
        cfg.min_interval = min_interval
        cfg.max_interval = max_interval
        cfg.reportable_change = reportable_change
        return self.request(
            True, 0x06, schema, [cfg], manufacturer=manufacturer
        )

    def command(self, command, *args, manufacturer=None, expect_reply=True):
        schema = self.server_commands[command][1]
        return self.request(False, command, schema, *args, manufacturer=manufacturer, expect_reply=expect_reply)

    def client_command(self, command, *args):
        schema = self.client_commands[command][1]
        return self.reply(False, command, schema, *args)

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def endpoint(self):
        return self._endpoint

    @property
    def commands(self):
        return list(self._server_command_idx.keys())

    def _update_attribute(self, attrid, value):
        self._attr_cache[attrid] = value
        self.listener_event('attribute_updated', attrid, value)

    def log(self, lvl, msg, *args):
        msg = '[0x%04x:%s:0x%04x] ' + msg
        args = (
            self._endpoint.device.nwk,
            self._endpoint.endpoint_id,
            self.cluster_id,
        ) + args
        return LOGGER.log(lvl, msg, *args)

    def __getattr__(self, name):
        if name in self._client_command_idx:
            return functools.partial(
                self.client_command,
                self._client_command_idx[name],
            )
        elif name in self._server_command_idx:
            return functools.partial(
                self.command,
                self._server_command_idx[name],
            )
        else:
            raise AttributeError("No such command name: %s" % (name, ))

    def __getitem__(self, key):
        return self.read_attributes([key], allow_cache=True, raw=True)

    @util.retryable_request
    def _discover(self, cmd_id, start_item, num_of_items,
                  manufacturer=None, tries=3):
        schema = foundation.COMMANDS[cmd_id][1]
        return self.request(
            True, cmd_id, schema, start_item, num_of_items,
            manufacturer=manufacturer)

    discover_attributes = functools.partialmethod(_discover, 0x0c)
    discover_attributes_extended = functools.partialmethod(_discover, 0x15)
    discover_commands_received = functools.partialmethod(_discover, 0x11)
    discover_commands_generated = functools.partialmethod(_discover, 0x13)


class ClusterPersistingListener:
    def __init__(self, applistener, cluster):
        self._applistener = applistener
        self._cluster = cluster

    def attribute_updated(self, attrid, value):
        self._applistener.attribute_updated(self._cluster, attrid, value)

    def cluster_command(self, *args, **kwargs):
        pass

    def zdo_command(self, *args, **kwargs):
        pass


# Import to populate the registry
from . import clusters  # noqa: F401, F402
