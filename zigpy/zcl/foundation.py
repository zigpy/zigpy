from __future__ import annotations

import dataclasses
import enum
import functools
import keyword
import typing
import warnings

import zigpy.types as t
import zigpy.util


def _hex_uint16_repr(v: int) -> str:
    return t.uint16_t(v)._hex_repr()


def ensure_valid_name(name: str | None) -> None:
    """
    Ensures that the name of an attribute or command is valid.
    """
    if name is not None and not name.isidentifier():
        raise ValueError(f"{name!r} is not a valid identifier name.")


class Status(t.enum8):
    SUCCESS = 0x00  # Operation was successful.
    FAILURE = 0x01  # Operation was not successful
    NOT_AUTHORIZED = 0x7E  # The sender of the command does not have
    RESERVED_FIELD_NOT_ZERO = 0x7F  # A reserved field/subfield/bit contains a
    MALFORMED_COMMAND = 0x80  # The command appears to contain the wrong
    UNSUP_CLUSTER_COMMAND = 0x81  # The specified cluster command is not
    UNSUP_GENERAL_COMMAND = 0x82  # The specified general ZCL command is not
    UNSUP_MANUF_CLUSTER_COMMAND = 0x83  # A manufacturer specific unicast,
    UNSUP_MANUF_GENERAL_COMMAND = 0x84  # A manufacturer specific unicast, ZCL
    INVALID_FIELD = 0x85  # At least one field of the command contains an
    UNSUPPORTED_ATTRIBUTE = 0x86  # The specified attribute does not exist on
    INVALID_VALUE = 0x87  # Out of range error, or set to a reserved value.
    READ_ONLY = 0x88  # Attempt to write a read only attribute.
    INSUFFICIENT_SPACE = 0x89  # An operation (e.g. an attempt to create an
    DUPLICATE_EXISTS = 0x8A  # An attempt to create an entry in a table failed
    NOT_FOUND = 0x8B  # The requested information (e.g. table entry)
    UNREPORTABLE_ATTRIBUTE = 0x8C  # Periodic reports cannot be issued for this
    INVALID_DATA_TYPE = 0x8D  # The data type given for an attribute is
    INVALID_SELECTOR = 0x8E  # The selector for an attribute is incorrect.
    WRITE_ONLY = 0x8F  # A request has been made to read an attribute
    INCONSISTENT_STARTUP_STATE = 0x90  # Setting the requested values would put
    DEFINED_OUT_OF_BAND = 0x91  # An attempt has been made to write an
    INCONSISTENT = (
        0x92  # The supplied values (e.g., contents of table cells) are inconsistent
    )
    ACTION_DENIED = 0x93  # The credentials presented by the device sending the
    TIMEOUT = 0x94  # The exchange was aborted due to excessive response time
    ABORT = 0x95  # Failed case when a client or a server decides to abort the upgrade process
    INVALID_IMAGE = 0x96  # Invalid OTA upgrade image (ex. failed signature
    WAIT_FOR_DATA = 0x97  # Server does not have data block available yet
    NO_IMAGE_AVAILABLE = 0x98  # No OTA upgrade image available for a particular client
    REQUIRE_MORE_IMAGE = 0x99  # The client still requires more OTA upgrade image
    NOTIFICATION_PENDING = 0x9A  # The command has been received and is being processed
    HARDWARE_FAILURE = 0xC0  # An operation was unsuccessful due to a
    SOFTWARE_FAILURE = 0xC1  # An operation was unsuccessful due to a
    CALIBRATION_ERROR = 0xC2  # An error occurred during calibration
    UNSUPPORTED_CLUSTER = 0xC3  # The cluster is not supported

    @classmethod
    def _missing_(cls, value):
        chained = t.APSStatus(value)
        status = cls._member_type_.__new__(cls, chained.value)
        status._name_ = chained.name
        status._value_ = value
        return status


class Analog:
    pass


class Discrete:
    pass


class Null:
    pass


class Unknown(t.NoData):
    pass


@dataclasses.dataclass()
class TypeValue:
    type: t.uint8_t = dataclasses.field(default=None)
    value: typing.Any = dataclasses.field(default=None)

    def __init__(self, type: t.uint8_t | None = None, value: typing.Any = None) -> None:
        # "Copy constructor"
        if type is not None and value is None and isinstance(type, self.__class__):
            other = type
            type = other.type
            value = other.value

        self.type = type
        self.value = value

    def serialize(self):
        return self.type.to_bytes(1, "little") + self.value.serialize()

    @classmethod
    def deserialize(cls, data):
        type, data = t.uint8_t.deserialize(data)
        python_type = DATA_TYPES[type][1]
        value, data = python_type.deserialize(data)

        return cls(type=type, value=value), data

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"type={type(self.value).__name__}, value={self.value!r}"
            f")"
        )


class TypedCollection(TypeValue):
    @classmethod
    def deserialize(cls, data):
        type, data = t.uint8_t.deserialize(data)
        python_type = DATA_TYPES[type][1]
        values, data = t.LVList[python_type].deserialize(data)

        return cls(type=type, value=values), data


class Array(TypedCollection):
    pass


class Bag(TypedCollection):
    pass


class Set(TypedCollection):
    pass  # ToDo: Make this a real set?


class DataTypes(dict):
    """DataTypes container."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._idx_by_class = {
            _type: type_id for type_id, (name, _type, ad) in self.items()
        }

    def pytype_to_datatype_id(self, python_type) -> int:
        """Return Zigbee Datatype ID for a give python type."""

        # We return the most specific parent class
        for cls in python_type.__mro__:
            if cls in self._idx_by_class:
                return self._idx_by_class[cls]

        return 0xFF


class ZCLStructure(t.LVList, item_type=TypeValue, length_type=t.uint16_t):
    """ZCL Structure data type."""


DATA_TYPES = DataTypes(
    {
        0x00: ("No data", t.NoData, Null),
        0x08: ("General", t.data8, Discrete),
        0x09: ("General", t.data16, Discrete),
        0x0A: ("General", t.data24, Discrete),
        0x0B: ("General", t.data32, Discrete),
        0x0C: ("General", t.data40, Discrete),
        0x0D: ("General", t.data48, Discrete),
        0x0E: ("General", t.data56, Discrete),
        0x0F: ("General", t.data64, Discrete),
        0x10: ("Boolean", t.Bool, Discrete),
        0x18: ("Bitmap", t.bitmap8, Discrete),
        0x19: ("Bitmap", t.bitmap16, Discrete),
        0x1A: ("Bitmap", t.bitmap24, Discrete),
        0x1B: ("Bitmap", t.bitmap32, Discrete),
        0x1C: ("Bitmap", t.bitmap40, Discrete),
        0x1D: ("Bitmap", t.bitmap48, Discrete),
        0x1E: ("Bitmap", t.bitmap56, Discrete),
        0x1F: ("Bitmap", t.bitmap64, Discrete),
        0x20: ("Unsigned Integer", t.uint8_t, Analog),
        0x21: ("Unsigned Integer", t.uint16_t, Analog),
        0x22: ("Unsigned Integer", t.uint24_t, Analog),
        0x23: ("Unsigned Integer", t.uint32_t, Analog),
        0x24: ("Unsigned Integer", t.uint40_t, Analog),
        0x25: ("Unsigned Integer", t.uint48_t, Analog),
        0x26: ("Unsigned Integer", t.uint56_t, Analog),
        0x27: ("Unsigned Integer", t.uint64_t, Analog),
        0x28: ("Signed Integer", t.int8s, Analog),
        0x29: ("Signed Integer", t.int16s, Analog),
        0x2A: ("Signed Integer", t.int24s, Analog),
        0x2B: ("Signed Integer", t.int32s, Analog),
        0x2C: ("Signed Integer", t.int40s, Analog),
        0x2D: ("Signed Integer", t.int48s, Analog),
        0x2E: ("Signed Integer", t.int56s, Analog),
        0x2F: ("Signed Integer", t.int64s, Analog),
        0x30: ("Enumeration", t.enum8, Discrete),
        0x31: ("Enumeration", t.enum16, Discrete),
        0x38: ("Floating point", t.Half, Analog),
        0x39: ("Floating point", t.Single, Analog),
        0x3A: ("Floating point", t.Double, Analog),
        0x41: ("Octet string", t.LVBytes, Discrete),
        0x42: ("Character string", t.CharacterString, Discrete),
        0x43: ("Long octet string", t.LongOctetString, Discrete),
        0x44: ("Long character string", t.LongCharacterString, Discrete),
        0x48: ("Array", Array, Discrete),
        0x4C: ("Structure", ZCLStructure, Discrete),
        0x50: ("Set", Set, Discrete),
        0x51: ("Bag", Bag, Discrete),
        0xE0: ("Time of day", t.TimeOfDay, Analog),
        0xE1: ("Date", t.Date, Analog),
        0xE2: ("UTCTime", t.UTCTime, Analog),
        0xE8: ("Cluster ID", t.ClusterId, Discrete),
        0xE9: ("Attribute ID", t.AttributeId, Discrete),
        0xEA: ("BACNet OID", t.BACNetOid, Discrete),
        0xF0: ("IEEE address", t.EUI64, Discrete),
        0xF1: ("128-bit security key", t.KeyData, Discrete),
        0xFF: ("Unknown", Unknown, None),
    }
)


class ReadAttributeRecord(t.Struct):
    """Read Attribute Record."""

    attrid: t.uint16_t = t.StructField(repr=_hex_uint16_repr)
    status: Status
    value: TypeValue = t.StructField(requires=lambda s: s.status == Status.SUCCESS)


class Attribute(t.Struct):
    attrid: t.uint16_t = t.StructField(repr=_hex_uint16_repr)
    value: TypeValue


class WriteAttributesStatusRecord(t.Struct):
    status: Status
    attrid: t.uint16_t = t.StructField(
        requires=lambda s: s.status != Status.SUCCESS, repr=_hex_uint16_repr
    )


class WriteAttributesResponse(list):
    """Write Attributes response list.

    Response to Write Attributes request should contain only success status, in
    case when all attributes were successfully written or list of status + attr_id
    records for all failed writes.
    """

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[WriteAttributesResponse, bytes]:
        record, data = WriteAttributesStatusRecord.deserialize(data)
        r = cls([record])
        if record.status == Status.SUCCESS:
            return r, data

        while len(data) >= 3:
            record, data = WriteAttributesStatusRecord.deserialize(data)
            r.append(record)
        return r, data

    def serialize(self):
        failed = [record for record in self if record.status != Status.SUCCESS]
        if failed:
            return b"".join(
                [WriteAttributesStatusRecord(i).serialize() for i in failed]
            )
        return Status.SUCCESS.serialize()


class ReportingDirection(t.enum8):
    SendReports = 0x00
    ReceiveReports = 0x01


class AttributeReportingStatus(t.enum8):
    Pending = 0x00
    Attribute_Reporting_Complete = 0x01


class AttributeReportingConfig:
    def __init__(self, other: AttributeReportingConfig | None = None) -> None:
        if isinstance(other, self.__class__):
            self.direction: ReportingDirection = other.direction
            self.attrid: t.uint16_t = other.attrid
            if self.direction == ReportingDirection.ReceiveReports:
                self.timeout: int = other.timeout
                return
            self.datatype: int = other.datatype
            self.min_interval: int = other.min_interval
            self.max_interval: int = other.max_interval
            self.reportable_change: int = other.reportable_change

    def serialize(self, *, _only_dir_and_attrid: bool = False) -> bytes:
        r = ReportingDirection(self.direction).serialize()
        r += t.uint16_t(self.attrid).serialize()

        if _only_dir_and_attrid:
            return r

        if self.direction == ReportingDirection.ReceiveReports:
            r += t.uint16_t(self.timeout).serialize()
        else:
            r += t.uint8_t(self.datatype).serialize()
            r += t.uint16_t(self.min_interval).serialize()
            r += t.uint16_t(self.max_interval).serialize()
            datatype = DATA_TYPES.get(self.datatype, None)
            if datatype and datatype[2] is Analog:
                datatype = datatype[1]
                r += datatype(self.reportable_change).serialize()
        return r

    @classmethod
    def deserialize(
        cls, data, *, _only_dir_and_attrid: bool = False
    ) -> tuple[AttributeReportingConfig, bytes]:
        self = cls()
        self.direction, data = ReportingDirection.deserialize(data)
        self.attrid, data = t.uint16_t.deserialize(data)

        # The report is only a direction and attribute
        if _only_dir_and_attrid:
            return self, data

        if self.direction == ReportingDirection.ReceiveReports:
            # Requesting things to be received by me
            self.timeout, data = t.uint16_t.deserialize(data)
        else:
            # Notifying that I will report things to you
            self.datatype, data = t.uint8_t.deserialize(data)
            datatype = DATA_TYPES[self.datatype]
            self.min_interval, data = t.uint16_t.deserialize(data)
            self.max_interval, data = t.uint16_t.deserialize(data)
            if datatype[2] is Analog:
                self.reportable_change, data = datatype[1].deserialize(data)

        return self, data

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}("
        r += f"direction={self.direction}"
        r += f", attrid=0x{self.attrid:04X}"

        if self.direction == ReportingDirection.ReceiveReports:
            r += f", timeout={self.timeout}"
        elif hasattr(self, "datatype"):
            r += f", datatype={self.datatype}"
            r += f", min_interval={self.min_interval}"
            r += f", max_interval={self.max_interval}"

            if self.reportable_change is not None:
                r += f", reportable_change={self.reportable_change}"

        r += ")"

        return r


class AttributeReportingConfigWithStatus(t.Struct):
    status: Status
    config: AttributeReportingConfig

    @classmethod
    def deserialize(
        cls, data: bytes
    ) -> tuple[AttributeReportingConfigWithStatus, bytes]:
        status, data = Status.deserialize(data)

        # FIXME: The reporting configuration will not include anything other than the
        # direction and the attribute ID when the status is not successful. This
        # information isn't a part of the attribute reporting config structure so we
        # have to pass it in externally.
        config, data = AttributeReportingConfig.deserialize(
            data, _only_dir_and_attrid=(status != Status.SUCCESS)
        )

        return cls(status=status, config=config), data

    def serialize(self) -> bytes:
        return self.status.serialize() + self.config.serialize(
            _only_dir_and_attrid=(self.status != Status.SUCCESS)
        )


class ConfigureReportingResponseRecord(t.Struct):
    status: Status
    direction: ReportingDirection
    attrid: t.uint16_t = t.StructField(repr=_hex_uint16_repr)

    @classmethod
    def deserialize(cls, data):
        r = cls()
        r.status, data = Status.deserialize(data)
        if r.status == Status.SUCCESS:
            r.direction, data = t.Optional(t.uint8_t).deserialize(data)
            if r.direction is not None:
                r.direction = ReportingDirection(r.direction)
            r.attrid, data = t.Optional(t.uint16_t).deserialize(data)
            return r, data

        r.direction, data = ReportingDirection.deserialize(data)
        r.attrid, data = t.uint16_t.deserialize(data)
        return r, data

    def serialize(self):
        r = Status(self.status).serialize()
        if self.status != Status.SUCCESS:
            r += ReportingDirection(self.direction).serialize()
            r += t.uint16_t(self.attrid).serialize()
        return r

    def __repr__(self):
        r = f"{self.__class__.__name__}(status={self.status}"
        if self.status != Status.SUCCESS:
            r += f", direction={self.direction}, attrid={self.attrid}"
        r += ")"
        return r


class ConfigureReportingResponse(t.List[ConfigureReportingResponseRecord]):
    # In the case of successful configuration of all attributes, only a single
    # attribute status record SHALL be included in the command, with the status
    # field set to SUCCESS and the direction and attribute identifier fields omitted

    def serialize(self):
        if not self:
            raise ValueError("Cannot serialize empty list")

        failed = [record for record in self if record.status != Status.SUCCESS]

        if not failed:
            return ConfigureReportingResponseRecord(status=Status.SUCCESS).serialize()

        # Note that attribute status records are not included for successfully
        # configured attributes, in order to save bandwidth.
        return b"".join(
            [ConfigureReportingResponseRecord(r).serialize() for r in failed]
        )


class ReadReportingConfigRecord(t.Struct):
    direction: t.uint8_t
    attrid: t.uint16_t


class DiscoverAttributesResponseRecord(t.Struct):
    attrid: t.uint16_t
    datatype: t.uint8_t


class AttributeAccessControl(t.bitmap8):
    READ = 0x01
    WRITE = 0x02
    REPORT = 0x04


class DiscoverAttributesExtendedResponseRecord(t.Struct):
    attrid: t.uint16_t
    datatype: t.uint8_t
    acl: AttributeAccessControl


class FrameType(t.enum2):
    """ZCL Frame Type."""

    GLOBAL_COMMAND = 0b00
    CLUSTER_COMMAND = 0b01
    RESERVED_2 = 0b10
    RESERVED_3 = 0b11


class Direction(t.enum1):
    """ZCL frame control direction."""

    Server_to_Client = 0
    Client_to_Server = 1

    @classmethod
    def _from_is_reply(cls, is_reply: bool) -> Direction:
        return cls.Client_to_Server if is_reply else cls.Server_to_Client


class FrameControl(t.Struct, t.uint8_t):
    """The frame control field contains information defining the command type
    and other control flags."""

    frame_type: FrameType
    is_manufacturer_specific: t.uint1_t
    direction: Direction
    disable_default_response: t.uint1_t
    reserved: t.uint3_t

    @property
    def is_reply(self) -> bool | None:
        warnings.warn("`is_reply` is deprecated, use `direction`", DeprecationWarning)

        if self.direction is None:
            return None

        return bool(self.direction)

    @is_reply.setter
    def is_reply(self, value: bool | None):
        warnings.warn("`is_reply` is deprecated, use `direction`", DeprecationWarning)

        if value is None:
            self.direction = None
        else:
            self.direction = Direction(value)

    @classmethod
    def cluster(
        cls,
        direction: Direction = Direction.Server_to_Client,
        is_reply: bool | None = None,
        is_manufacturer_specific: bool = False,
    ):
        if is_reply is not None:
            warnings.warn(
                "`is_reply` is deprecated, use `direction`", DeprecationWarning
            )
            direction = Direction(is_reply)

        return cls(
            frame_type=FrameType.CLUSTER_COMMAND,
            is_manufacturer_specific=is_manufacturer_specific,
            direction=direction,
            disable_default_response=(direction == Direction.Client_to_Server),
            reserved=0b000,
        )

    @classmethod
    def general(
        cls,
        direction: Direction = Direction.Server_to_Client,
        is_reply: bool | None = None,
        is_manufacturer_specific: bool = False,
    ):
        if is_reply is not None:
            warnings.warn(
                "`is_reply` is deprecated, use `direction`", DeprecationWarning
            )
            direction = Direction(is_reply)

        return cls(
            frame_type=FrameType.GLOBAL_COMMAND,
            is_manufacturer_specific=is_manufacturer_specific,
            direction=direction,
            disable_default_response=(direction == Direction.Client_to_Server),
            reserved=0b000,
        )

    @property
    def is_cluster(self) -> bool:
        """Return True if command is a local cluster specific command."""
        return bool(self.frame_type == FrameType.CLUSTER_COMMAND)

    @property
    def is_general(self) -> bool:
        """Return True if command is a global ZCL command."""
        return bool(self.frame_type == FrameType.GLOBAL_COMMAND)


class ZCLHeader(t.Struct):
    NO_MANUFACTURER_ID = -1  # type: typing.Literal

    frame_control: FrameControl
    manufacturer: t.uint16_t = t.StructField(
        requires=lambda hdr: hdr.frame_control.is_manufacturer_specific
    )
    tsn: t.uint8_t
    command_id: t.uint8_t

    def __new__(
        cls, frame_control=None, manufacturer=None, tsn=None, command_id=None
    ) -> ZCLHeader:
        # Allow "auto manufacturer ID" to be disabled in higher layers
        if manufacturer is cls.NO_MANUFACTURER_ID:
            manufacturer = None

        if frame_control is not None and manufacturer is not None:
            frame_control.is_manufacturer_specific = True

        return super().__new__(cls, frame_control, manufacturer, tsn, command_id)

    @property
    def is_reply(self) -> bool:
        """Return direction of Frame Control."""
        return self.frame_control.direction == Direction.Client_to_Server

    @property
    def direction(self) -> bool:
        """Return direction of Frame Control."""
        return self.frame_control.direction

    def __setattr__(self, name, value) -> None:
        if name == "manufacturer" and value is self.NO_MANUFACTURER_ID:
            value = None

        super().__setattr__(name, value)

        if name == "manufacturer" and self.frame_control is not None:
            self.frame_control.is_manufacturer_specific = value is not None

    @classmethod
    def general(
        cls,
        tsn: int | t.uint8_t,
        command_id: int | t.uint8_t,
        manufacturer: int | t.uint16_t | None = None,
        is_reply: bool = None,
        direction: Direction = Direction.Server_to_Client,
    ) -> ZCLHeader:
        return cls(
            frame_control=FrameControl.general(
                is_reply=is_reply,  # deprecated
                direction=direction,
                is_manufacturer_specific=(manufacturer is not None),
            ),
            manufacturer=manufacturer,
            tsn=tsn,
            command_id=command_id,
        )

    @classmethod
    def cluster(
        cls,
        tsn: int | t.uint8_t,
        command_id: int | t.uint8_t,
        manufacturer: int | t.uint16_t | None = None,
        is_reply: bool = None,
        direction: Direction = Direction.Server_to_Client,
    ) -> ZCLHeader:
        return cls(
            frame_control=FrameControl.cluster(
                is_reply=is_reply,  # deprecated
                direction=direction,
                is_manufacturer_specific=(manufacturer is not None),
            ),
            manufacturer=manufacturer,
            tsn=tsn,
            command_id=command_id,
        )


@dataclasses.dataclass(frozen=True)
class ZCLCommandDef:
    name: str = None
    schema: CommandSchema = None
    direction: Direction = None
    id: t.uint8_t = None
    is_manufacturer_specific: bool = None

    # Deprecated
    is_reply: bool = None

    def __post_init__(self):
        ensure_valid_name(self.name)

        if self.is_reply is not None:
            warnings.warn(
                "`is_reply` is deprecated, use `direction`", DeprecationWarning
            )
            object.__setattr__(self, "direction", Direction(self.is_reply))

        object.__setattr__(self, "is_reply", bool(self.direction))

    def with_compiled_schema(self):
        """
        Return a copy of the ZCL command definition object with its dictionary command
        schema converted into a `CommandSchema` subclass.
        """

        # If the schema is already a struct, do nothing
        if not isinstance(self.schema, dict):
            return self

        assert self.id is not None
        assert self.name is not None

        cls_attrs = {
            "__annotations__": {},
            "command": self,
        }

        for name, param_type in self.schema.items():
            plain_name = name.rstrip("?")

            # Make sure parameters with names like "foo bar" and "class" can't exist
            if not plain_name.isidentifier() or keyword.iskeyword(plain_name):
                raise ValueError(
                    f"Schema parameter {name} must be a valid Python identifier"
                )

            cls_attrs["__annotations__"][plain_name] = "None"
            cls_attrs[plain_name] = t.StructField(
                type=param_type,
                optional=name.endswith("?"),
            )

        schema = type(self.name, (CommandSchema,), cls_attrs)

        return self.replace(schema=schema)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"id=0x{self.id:02X}, "
            f"name={self.name!r}, "
            f"direction={self.direction}, "
            f"schema={self.schema}, "
            f"is_manufacturer_specific={self.is_manufacturer_specific}"
            f")"
        )

    def replace(self, **kwargs) -> ZCLCommandDef:
        return dataclasses.replace(self, is_reply=None, **kwargs)

    def __getitem__(self, key):
        warnings.warn("Attributes should be accessed by name", DeprecationWarning)
        return (self.name, self.schema, self.direction)[key]


class CommandSchema(t.Struct, tuple):
    """
    Struct subclass that behaves more like a tuple.
    """

    command: ZCLCommandDef = None

    def __iter__(self):
        return iter(self.as_tuple())

    def __getitem__(self, item):
        return self.as_tuple()[item]

    def __len__(self) -> int:
        return len(self.as_tuple())

    def __eq__(self, other) -> bool:
        if isinstance(other, tuple) and not isinstance(other, type(self)):
            return self.as_tuple() == other

        return super().__eq__(other)


class ZCLAttributeAccess(enum.Flag):
    NONE = 0
    Read = 1
    Write = 2
    Write_Optional = 4
    Report = 8
    Scene = 16

    _names: dict[ZCLAttributeAccess, str]

    @classmethod
    @functools.lru_cache(None)
    def from_str(cls: ZCLAttributeAccess, value: str) -> ZCLAttributeAccess:
        orig_value = value
        access = cls.NONE

        while value:
            for mode, prefix in cls._names.items():
                if value.startswith(prefix):
                    value = value[len(prefix) :]
                    access |= mode
                    break
            else:
                raise ValueError(f"Invalid access mode: {orig_value!r}")

        return cls(access)


ZCLAttributeAccess._names = {
    ZCLAttributeAccess.Write_Optional: "*w",
    ZCLAttributeAccess.Write: "w",
    ZCLAttributeAccess.Read: "r",
    ZCLAttributeAccess.Report: "p",
    ZCLAttributeAccess.Scene: "s",
}


@dataclasses.dataclass(frozen=True)
class ZCLAttributeDef:
    name: str = None
    type: type = None
    access: ZCLAttributeAccess = dataclasses.field(
        default=(
            ZCLAttributeAccess.Read
            | ZCLAttributeAccess.Write
            | ZCLAttributeAccess.Report
        ),
    )
    mandatory: bool = False
    is_manufacturer_specific: bool = False

    # The ID will be specified later
    id: t.uint16_t = None

    def __post_init__(self):
        if self.id is not None and not isinstance(self.id, t.uint16_t):
            object.__setattr__(self, "id", t.uint16_t(self.id))

        if isinstance(self.access, str):
            ZCLAttributeAccess.NONE
            object.__setattr__(self, "access", ZCLAttributeAccess.from_str(self.access))

        ensure_valid_name(self.name)

    def replace(self, **kwargs) -> ZCLAttributeDef:
        return dataclasses.replace(self, **kwargs)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"id=0x{self.id:04X}, "
            f"name={self.name!r}, "
            f"type={self.type}, "
            f"access={self.access!r}, "
            f"mandatory={self.mandatory!r}, "
            f"is_manufacturer_specific={self.is_manufacturer_specific}"
            f")"
        )

    def __getitem__(self, key):
        warnings.warn("Attributes should be accessed by name", DeprecationWarning)
        return (self.name, self.type)[key]


class GeneralCommand(t.enum8):
    """ZCL Foundation General Command IDs."""

    Read_Attributes = 0x00
    Read_Attributes_rsp = 0x01
    Write_Attributes = 0x02
    Write_Attributes_Undivided = 0x03
    Write_Attributes_rsp = 0x04
    Write_Attributes_No_Response = 0x05
    Configure_Reporting = 0x06
    Configure_Reporting_rsp = 0x07
    Read_Reporting_Configuration = 0x08
    Read_Reporting_Configuration_rsp = 0x09
    Report_Attributes = 0x0A
    Default_Response = 0x0B
    Discover_Attributes = 0x0C
    Discover_Attributes_rsp = 0x0D
    # Read_Attributes_Structured = 0x0e
    # Write_Attributes_Structured = 0x0f
    # Write_Attributes_Structured_rsp = 0x10
    Discover_Commands_Received = 0x11
    Discover_Commands_Received_rsp = 0x12
    Discover_Commands_Generated = 0x13
    Discover_Commands_Generated_rsp = 0x14
    Discover_Attribute_Extended = 0x15
    Discover_Attribute_Extended_rsp = 0x16


GENERAL_COMMANDS = COMMANDS = {
    GeneralCommand.Read_Attributes: ZCLCommandDef(
        schema={"attribute_ids": t.List[t.uint16_t]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Read_Attributes_rsp: ZCLCommandDef(
        schema={"status_records": t.List[ReadAttributeRecord]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Write_Attributes: ZCLCommandDef(
        schema={"attributes": t.List[Attribute]}, direction=Direction.Server_to_Client
    ),
    GeneralCommand.Write_Attributes_Undivided: ZCLCommandDef(
        schema={"attributes": t.List[Attribute]}, direction=Direction.Server_to_Client
    ),
    GeneralCommand.Write_Attributes_rsp: ZCLCommandDef(
        schema={"status_records": WriteAttributesResponse},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Write_Attributes_No_Response: ZCLCommandDef(
        schema={"attributes": t.List[Attribute]}, direction=Direction.Server_to_Client
    ),
    GeneralCommand.Configure_Reporting: ZCLCommandDef(
        schema={"config_records": t.List[AttributeReportingConfig]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Configure_Reporting_rsp: ZCLCommandDef(
        schema={"status_records": ConfigureReportingResponse},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Read_Reporting_Configuration: ZCLCommandDef(
        schema={"attribute_records": t.List[ReadReportingConfigRecord]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Read_Reporting_Configuration_rsp: ZCLCommandDef(
        schema={"attribute_configs": t.List[AttributeReportingConfigWithStatus]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Report_Attributes: ZCLCommandDef(
        schema={"attribute_reports": t.List[Attribute]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Default_Response: ZCLCommandDef(
        schema={"command_id": t.uint8_t, "status": Status},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Attributes: ZCLCommandDef(
        schema={"start_attribute_id": t.uint16_t, "max_attribute_ids": t.uint8_t},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Attributes_rsp: ZCLCommandDef(
        schema={
            "discovery_complete": t.Bool,
            "attribute_info": t.List[DiscoverAttributesResponseRecord],
        },
        direction=Direction.Client_to_Server,
    ),
    # Command.Read_Attributes_Structured: ZCLCommandDef(schema=(, ), direction=Direction.Server_to_Client),
    # Command.Write_Attributes_Structured: ZCLCommandDef(schema=(, ), direction=Direction.Server_to_Client),
    # Command.Write_Attributes_Structured_rsp: ZCLCommandDef(schema=(, ), direction=Direction.Client_to_Server),
    GeneralCommand.Discover_Commands_Received: ZCLCommandDef(
        schema={"start_command_id": t.uint8_t, "max_command_ids": t.uint8_t},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Commands_Received_rsp: ZCLCommandDef(
        schema={"discovery_complete": t.Bool, "command_ids": t.List[t.uint8_t]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Commands_Generated: ZCLCommandDef(
        schema={"start_command_id": t.uint8_t, "max_command_ids": t.uint8_t},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Commands_Generated_rsp: ZCLCommandDef(
        schema={"discovery_complete": t.Bool, "command_ids": t.List[t.uint8_t]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Attribute_Extended: ZCLCommandDef(
        schema={"start_attribute_id": t.uint16_t, "max_attribute_ids": t.uint8_t},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Attribute_Extended_rsp: ZCLCommandDef(
        schema={
            "discovery_complete": t.Bool,
            "extended_attr_info": t.List[DiscoverAttributesExtendedResponseRecord],
        },
        direction=Direction.Client_to_Server,
    ),
}

for command_id, command_def in list(GENERAL_COMMANDS.items()):
    GENERAL_COMMANDS[command_id] = command_def.replace(
        id=command_id, name=command_id.name
    ).with_compiled_schema()

ZCL_CLUSTER_REVISION_ATTR = ZCLAttributeDef(
    "cluster_revision", type=t.uint16_t, access="r", mandatory=True
)
ZCL_REPORTING_STATUS_ATTR = ZCLAttributeDef(
    "attr_reporting_status", type=AttributeReportingStatus, access="r"
)


__getattr__ = zigpy.util.deprecated_attrs({"Command": GeneralCommand})
