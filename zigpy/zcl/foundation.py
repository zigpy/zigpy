from __future__ import annotations

import dataclasses
import enum
import functools
import keyword
import logging
import typing

from typing_extensions import Self

import zigpy.types as t

_LOGGER = logging.getLogger(__name__)


def _hex_uint16_repr(v: int) -> str:
    return t.uint16_t(v)._hex_repr()


def ensure_valid_name(name: str | None) -> None:
    """Ensures that the name of an attribute or command is valid."""
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


class DataClass(enum.Enum):
    Null = 0
    Analog = 1
    Discrete = 2
    Composite = 3


# TODO: Backwards compatibility, remove later
Null = DataClass.Null
Analog = DataClass.Analog
Discrete = DataClass.Discrete
Composite = DataClass.Composite


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
            type = other.type  # noqa: A001
            value = other.value

        self.type = type
        self.value = value

    def serialize(self) -> bytes:
        return self.type.to_bytes(1, "little") + self.value.serialize()

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[TypeValue, bytes]:
        data_type, data = t.uint8_t.deserialize(data)
        python_type = DataType.from_type_id(data_type).python_type
        value, data = python_type.deserialize(data)

        return cls(type=data_type, value=value), data

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"type={type(self.value).__name__}, value={self.value!r}"
            f")"
        )


class TypedCollection(TypeValue):
    @classmethod
    def deserialize(cls, data):
        data_type, data = t.uint8_t.deserialize(data)
        python_type = DataType.from_type_id(data_type).python_type
        values, data = t.LVList[python_type, t.uint16_t].deserialize(data)

        return cls(type=data_type, value=values), data


class Array(TypedCollection):
    pass


class Bag(TypedCollection):
    pass


class Set(TypedCollection):
    pass  # ToDo: Make this a real set?


class ZCLStructure(t.LVList, item_type=TypeValue, length_type=t.uint16_t):
    """ZCL Structure data type."""


class DataTypeId(t.enum8):
    unk = 0xFF
    nodata = 0x00
    data8 = 0x08
    data16 = 0x09
    data24 = 0x0A
    data32 = 0x0B
    data40 = 0x0C
    data48 = 0x0D
    data56 = 0x0E
    data64 = 0x0F
    bool_ = 0x10
    map8 = 0x18
    map16 = 0x19
    map24 = 0x1A
    map32 = 0x1B
    map40 = 0x1C
    map48 = 0x1D
    map56 = 0x1E
    map64 = 0x1F
    uint8 = 0x20
    uint16 = 0x21
    uint24 = 0x22
    uint32 = 0x23
    uint40 = 0x24
    uint48 = 0x25
    uint56 = 0x26
    uint64 = 0x27
    int8 = 0x28
    int16 = 0x29
    int24 = 0x2A
    int32 = 0x2B
    int40 = 0x2C
    int48 = 0x2D
    int56 = 0x2E
    int64 = 0x2F
    enum8 = 0x30
    enum16 = 0x31
    semi = 0x38
    single = 0x39
    double = 0x3A
    octstr = 0x41
    string = 0x42
    octstr16 = 0x43
    string16 = 0x44
    array = 0x48
    struct = 0x4C
    set = 0x50
    bag = 0x51
    ToD = 0xE0
    date = 0xE1
    UTC = 0xE2
    clusterId = 0xE8  # noqa: N815
    attribId = 0xE9  # noqa: N815
    bacOID = 0xEA  # noqa: N815
    EUI64 = 0xF0
    key128 = 0xF1


@dataclasses.dataclass(frozen=True)
class DataTypeInfo:
    type_id: DataTypeId
    python_type: type
    type_class: DataClass
    description: str
    non_value: typing.Any | None


class DataType(DataTypeInfo, enum.Enum):
    unk = (
        DataTypeId.unk,
        Unknown,
        DataClass.Null,
        "Unknown",
        None,
    )
    nodata = (
        DataTypeId.nodata,
        t.NoData,
        DataClass.Null,
        "No data",
        None,
    )
    data8 = (
        DataTypeId.data8,
        t.data8,
        DataClass.Discrete,
        "General",
        None,
    )
    data16 = (
        DataTypeId.data16,
        t.data16,
        DataClass.Discrete,
        "General",
        None,
    )
    data24 = (
        DataTypeId.data24,
        t.data24,
        DataClass.Discrete,
        "General",
        None,
    )
    data32 = (
        DataTypeId.data32,
        t.data32,
        DataClass.Discrete,
        "General",
        None,
    )
    data40 = (
        DataTypeId.data40,
        t.data40,
        DataClass.Discrete,
        "General",
        None,
    )
    data48 = (
        DataTypeId.data48,
        t.data48,
        DataClass.Discrete,
        "General",
        None,
    )
    data56 = (
        DataTypeId.data56,
        t.data56,
        DataClass.Discrete,
        "General",
        None,
    )
    data64 = (
        DataTypeId.data64,
        t.data64,
        DataClass.Discrete,
        "General",
        None,
    )
    bool_ = (
        DataTypeId.bool_,
        t.Bool,
        DataClass.Discrete,
        "Boolean",
        t.Bool(0xFF),
    )
    map8 = (
        DataTypeId.map8,
        t.bitmap8,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map16 = (
        DataTypeId.map16,
        t.bitmap16,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map24 = (
        DataTypeId.map24,
        t.bitmap24,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map32 = (
        DataTypeId.map32,
        t.bitmap32,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map40 = (
        DataTypeId.map40,
        t.bitmap40,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map48 = (
        DataTypeId.map48,
        t.bitmap48,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map56 = (
        DataTypeId.map56,
        t.bitmap56,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    map64 = (
        DataTypeId.map64,
        t.bitmap64,
        DataClass.Discrete,
        "Bitmap",
        None,
    )
    uint8 = (
        DataTypeId.uint8,
        t.uint8_t,
        DataClass.Analog,
        "Unsigned 8-bit integer",
        t.uint8_t(0xFF),
    )
    uint16 = (
        DataTypeId.uint16,
        t.uint16_t,
        DataClass.Analog,
        "Unsigned 16-bit integer",
        t.uint16_t(0xFFFF),
    )
    uint24 = (
        DataTypeId.uint24,
        t.uint24_t,
        DataClass.Analog,
        "Unsigned 24-bit integer",
        t.uint24_t(0xFFFFFF),
    )
    uint32 = (
        DataTypeId.uint32,
        t.uint32_t,
        DataClass.Analog,
        "Unsigned 32-bit integer",
        t.uint32_t(0xFFFFFFFF),
    )
    uint40 = (
        DataTypeId.uint40,
        t.uint40_t,
        DataClass.Analog,
        "Unsigned 40-bit integer",
        t.uint40_t(0xFFFFFFFFFF),
    )
    uint48 = (
        DataTypeId.uint48,
        t.uint48_t,
        DataClass.Analog,
        "Unsigned 48-bit integer",
        t.uint48_t(0xFFFFFFFFFFFF),
    )
    uint56 = (
        DataTypeId.uint56,
        t.uint56_t,
        DataClass.Analog,
        "Unsigned 56-bit integer",
        t.uint56_t(0xFFFFFFFFFFFFFF),
    )
    uint64 = (
        DataTypeId.uint64,
        t.uint64_t,
        DataClass.Analog,
        "Unsigned 64-bit integer",
        t.uint64_t(0xFFFFFFFFFFFFFF),
    )
    int8 = (
        DataTypeId.int8,
        t.int8s,
        DataClass.Analog,
        "Signed 8-bit integer",
        t.int8s(-0x80),
    )
    int16 = (
        DataTypeId.int16,
        t.int16s,
        DataClass.Analog,
        "Signed 16-bit integer",
        t.int16s(-0x8000),
    )
    int24 = (
        DataTypeId.int24,
        t.int24s,
        DataClass.Analog,
        "Signed 24-bit integer",
        t.int24s(-0x800000),
    )
    int32 = (
        DataTypeId.int32,
        t.int32s,
        DataClass.Analog,
        "Signed 32-bit integer",
        t.int32s(-0x80000000),
    )
    int40 = (
        DataTypeId.int40,
        t.int40s,
        DataClass.Analog,
        "Signed 40-bit integer",
        t.int40s(-0x8000000000),
    )
    int48 = (
        DataTypeId.int48,
        t.int48s,
        DataClass.Analog,
        "Signed 48-bit integer",
        t.int48s(-0x800000000000),
    )
    int56 = (
        DataTypeId.int56,
        t.int56s,
        DataClass.Analog,
        "Signed 56-bit integer",
        t.int56s(-0x80000000000000),
    )
    int64 = (
        DataTypeId.int64,
        t.int64s,
        DataClass.Analog,
        "Signed 64-bit integer",
        t.int64s(-0x80000000000000),
    )
    enum8 = (
        DataTypeId.enum8,
        t.enum8,
        DataClass.Discrete,
        "8-bit enumeration",
        t.enum8(0xFF),
    )
    enum16 = (
        DataTypeId.enum16,
        t.enum16,
        DataClass.Discrete,
        "16-bit enumeration",
        t.enum16(0xFF),
    )
    semi = (
        DataTypeId.semi,
        t.Half,
        DataClass.Analog,
        "Semi-precision",
        t.Half(float("nan")),
    )
    single = (
        DataTypeId.single,
        t.Single,
        DataClass.Analog,
        "Single precision",
        t.Single(float("nan")),
    )
    double = (
        DataTypeId.double,
        t.Double,
        DataClass.Analog,
        "Double precision",
        t.Double(float("nan")),
    )
    octstr = (
        DataTypeId.octstr,
        t.LVBytes,
        DataClass.Discrete,
        "Octet string",
        None,
    )
    string = (
        DataTypeId.string,
        t.CharacterString,
        DataClass.Discrete,
        "Character string",
        None,
    )
    octstr16 = (
        DataTypeId.octstr16,
        t.LongOctetString,
        DataClass.Discrete,
        "Long octet string",
        None,
    )
    string16 = (
        DataTypeId.string16,
        t.LongCharacterString,
        DataClass.Discrete,
        "Long character string",
        None,
    )
    array = (
        DataTypeId.array,
        Array,
        DataClass.Discrete,
        "Array",
        None,
    )
    struct = (
        DataTypeId.struct,
        ZCLStructure,
        DataClass.Discrete,
        "Structure",
        None,
    )
    set = (
        DataTypeId.set,
        Set,
        DataClass.Discrete,
        "Set",
        None,
    )
    bag = (
        DataTypeId.bag,
        Bag,
        DataClass.Discrete,
        "Bag",
        None,
    )
    ToD = (
        DataTypeId.ToD,
        t.TimeOfDay,
        DataClass.Analog,
        "Time of day",
        t.TimeOfDay(hours=0xFF, minutes=0xFF, seconds=0xFF, hundredths=0xFF),
    )
    date = (
        DataTypeId.date,
        t.Date,
        DataClass.Analog,
        "Date",
        t.Date(years_since_1900=0xFF, month=0xFF, day=0xFF, day_of_week=0xFF),
    )
    UTC = (
        DataTypeId.UTC,
        t.UTCTime,
        DataClass.Analog,
        "UTCTime",
        t.UTCTime(0xFFFFFFFF),
    )
    clusterId = (  # noqa: N815
        DataTypeId.clusterId,
        t.ClusterId,
        DataClass.Discrete,
        "Cluster ID",
        t.ClusterId(0xFFFF),
    )
    attribId = (  # noqa: N815
        DataTypeId.attribId,
        t.AttributeId,
        DataClass.Discrete,
        "Attribute ID",
        t.AttributeId(0xFFFF),
    )
    bacOID = (  # noqa: N815
        DataTypeId.bacOID,
        t.BACNetOid,
        DataClass.Discrete,
        "BACNet OID",
        t.BACNetOid(0xFFFFFFFF),
    )
    EUI64 = (
        DataTypeId.EUI64,
        t.EUI64,
        DataClass.Discrete,
        "IEEE address",
        t.EUI64.convert("FF:FF:FF:FF:FF:FF:FF:FF"),
    )
    key128 = (
        DataTypeId.key128,
        t.KeyData,
        DataClass.Discrete,
        "128-bit security key",
        t.KeyData.convert("FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF"),
    )

    @classmethod
    @functools.cache
    def _python_type_index(cls: type[Self]) -> dict[type, Self]:  # noqa: N805
        return {d.python_type: d for d in cls}

    @classmethod
    def from_python_type(cls: type[Self], python_type: type) -> Self:
        """Return Zigbee Datatype ID for a give python type."""
        python_type_index = cls._python_type_index()

        # We return the most specific parent class
        for parent_cls in python_type.__mro__:
            if parent_cls in python_type_index:
                return python_type_index[parent_cls]

        return cls.unk

    @classmethod
    @functools.cache
    def _data_type_index(cls: type[Self]) -> dict[type, Self]:  # noqa: N805
        return {d.type_id: d for d in cls}

    @classmethod
    def from_type_id(cls: type[Self], type_id: DataTypeId) -> Self:
        return cls._data_type_index()[type_id]


@dataclasses.dataclass()
class ReadAttributeRecord:
    """Read Attribute Record."""

    attrid: t.uint16_t
    status: Status
    value: TypeValue | Array | Bag | Set | None

    def __init__(
        self,
        attrid: t.uint16_t | Self = t.uint16_t(0x0000),
        status: Status = Status.SUCCESS,
        value: TypeValue | Array | Bag | Set | None = None,
    ) -> None:
        if isinstance(attrid, self.__class__):
            # "Copy constructor"
            self.attrid = attrid.attrid
            self.status = attrid.status
            self.value = attrid.value
            return

        self.attrid = t.uint16_t(attrid)
        self.status = Status(status)
        self.value = value

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[Self, bytes]:
        attrid, data = t.uint16_t.deserialize(data)
        status, data = Status.deserialize(data)
        value = None

        if status == Status.SUCCESS:
            type_id, data = DataTypeId.deserialize(data)

            # Arrays, Sets, and Bags are treated differently
            if type_id in (DataTypeId.array, DataTypeId.set, DataTypeId.bag):
                value, data = DataType.from_type_id(type_id).python_type.deserialize(
                    data
                )
            else:
                value, data = TypeValue.deserialize(type_id.serialize() + data)

        return cls(attrid=attrid, status=status, value=value), data

    def serialize(self) -> bytes:
        data = self.attrid.serialize()
        data += self.status.serialize()

        if self.status == Status.SUCCESS:
            assert self.value is not None

            if isinstance(self.value, (Array, Set, Bag)):
                data += (
                    DataType.from_python_type(type(self.value)).type_id.serialize()
                    + self.value.serialize()
                )
            else:
                data += self.value.serialize()

        return data


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
            self.datatype: DataTypeId = other.datatype
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

            try:
                data_type = DataType.from_type_id(self.datatype)
            except KeyError:
                _LOGGER.warning(
                    "Unknown ZCL type %d, not setting reportable change", self.datatype
                )
            else:
                if data_type.type_class is Analog:
                    r += data_type.python_type(self.reportable_change).serialize()

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
            self.min_interval, data = t.uint16_t.deserialize(data)
            self.max_interval, data = t.uint16_t.deserialize(data)

            try:
                data_type = DataType.from_type_id(self.datatype)
            except KeyError:
                _LOGGER.warning(
                    "Unknown ZCL type %d, cannot read reportable change", self.datatype
                )
            else:
                if data_type.type_class is Analog:
                    self.reportable_change, data = data_type.python_type.deserialize(
                        data
                    )

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
    def deserialize(cls, data: bytes) -> tuple[ConfigureReportingResponseRecord, bytes]:
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

    def __repr__(self) -> str:
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

    Client_to_Server = 0
    Server_to_Client = 1

    @classmethod
    def _from_is_reply(cls, is_reply: bool) -> Direction:
        return cls.Server_to_Client if is_reply else cls.Client_to_Server


class FrameControl(t.Struct, t.uint8_t):
    """The frame control field contains information defining the command type
    and other control flags.
    """

    frame_type: FrameType
    is_manufacturer_specific: t.uint1_t
    direction: Direction
    disable_default_response: t.uint1_t
    reserved: t.uint3_t

    @classmethod
    def cluster(
        cls,
        direction: Direction = Direction.Client_to_Server,
        is_manufacturer_specific: bool = False,
    ):
        return cls(
            frame_type=FrameType.CLUSTER_COMMAND,
            is_manufacturer_specific=is_manufacturer_specific,
            direction=direction,
            disable_default_response=(direction == Direction.Server_to_Client),
            reserved=0b000,
        )

    @classmethod
    def general(
        cls,
        direction: Direction = Direction.Client_to_Server,
        is_manufacturer_specific: bool = False,
    ):
        return cls(
            frame_type=FrameType.GLOBAL_COMMAND,
            is_manufacturer_specific=is_manufacturer_specific,
            direction=direction,
            disable_default_response=(direction == Direction.Server_to_Client),
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
        cls: type[Self],
        frame_control: FrameControl | None = None,
        manufacturer: t.uint16_t | None = None,
        tsn: int | t.uint8_t | None = None,
        command_id: int | GeneralCommand | None = None,
    ) -> Self:
        # Allow "auto manufacturer ID" to be disabled in higher layers
        if manufacturer is cls.NO_MANUFACTURER_ID:
            manufacturer = None

        if frame_control is not None and manufacturer is not None:
            frame_control.is_manufacturer_specific = True

        return super().__new__(cls, frame_control, manufacturer, tsn, command_id)

    @property
    def direction(self) -> bool:
        """Return direction of Frame Control."""
        return self.frame_control.direction

    def __setattr__(
        self,
        name: str,
        value: t.uint16_t | FrameControl | t.uint8_t | GeneralCommand | None,
    ) -> None:
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
        direction: Direction = Direction.Client_to_Server,
    ) -> ZCLHeader:
        return cls(
            frame_control=FrameControl.general(
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
        direction: Direction = Direction.Client_to_Server,
    ) -> ZCLHeader:
        return cls(
            frame_control=FrameControl.cluster(
                direction=direction,
                is_manufacturer_specific=(manufacturer is not None),
            ),
            manufacturer=manufacturer,
            tsn=tsn,
            command_id=command_id,
        )


@dataclasses.dataclass(frozen=True)
class ZCLCommandDef(t.BaseDataclassMixin):
    id: t.uint8_t = None
    schema: CommandSchema = None
    direction: Direction = None
    is_manufacturer_specific: bool = None

    # set later
    name: str = None

    def __post_init__(self) -> None:
        # Backwards compatibility with positional syntax where the name was first
        if isinstance(self.id, str):
            object.__setattr__(self, "name", self.id)
            object.__setattr__(self, "id", None)

        ensure_valid_name(self.name)

        if isinstance(self.direction, bool):
            object.__setattr__(
                self, "direction", Direction._from_is_reply(self.direction)
            )

    def with_compiled_schema(self) -> ZCLCommandDef:
        """Return a copy of the ZCL command definition object with its dictionary command
        schema converted into a `CommandSchema` subclass.
        """

        if isinstance(self.schema, tuple):
            raise ValueError(  # noqa: TRY004
                f"Tuple schemas are deprecated: {self.schema!r}. Use a dictionary or a"
                f" Struct subclass."
            )
        elif not isinstance(self.schema, dict):
            # If the schema is already a struct, do nothing
            self.schema.command = self
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


class CommandSchema(t.Struct, tuple):  # noqa: SLOT001
    """Struct subclass that behaves more like a tuple."""

    command: ZCLCommandDef = None

    def __iter__(self):
        return iter(self.as_tuple())

    def __getitem__(
        self, item: slice | typing.SupportsIndex
    ) -> typing.Any | tuple[typing.Any, ...]:
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
class ZCLAttributeDef(t.BaseDataclassMixin):
    id: t.uint16_t = None
    type: type = None
    zcl_type: DataTypeId = None
    access: ZCLAttributeAccess = (
        ZCLAttributeAccess.Read | ZCLAttributeAccess.Write | ZCLAttributeAccess.Report
    )
    mandatory: bool = False
    is_manufacturer_specific: bool = False

    # The name will be specified later
    name: str = None

    def __post_init__(self) -> None:
        # Backwards compatibility with positional syntax where the name was first
        if isinstance(self.id, str):
            object.__setattr__(self, "name", self.id)
            object.__setattr__(self, "id", None)

        if self.id is not None and not isinstance(self.id, t.uint16_t):
            object.__setattr__(self, "id", t.uint16_t(self.id))

        if isinstance(self.access, str):
            object.__setattr__(self, "access", ZCLAttributeAccess.from_str(self.access))

        if self.zcl_type is None:
            object.__setattr__(
                self, "zcl_type", DataType.from_python_type(self.type).type_id
            )

        ensure_valid_name(self.name)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"id=0x{self.id:04X}, "
            f"name={self.name!r}, "
            f"type={self.type}, "
            f"zcl_type={self.zcl_type}, "
            f"access={self.access!r}, "
            f"mandatory={self.mandatory!r}, "
            f"is_manufacturer_specific={self.is_manufacturer_specific}"
            f")"
        )


class IterableMemberMeta(type):
    def __iter__(cls) -> typing.Iterator[typing.Any]:
        for name in dir(cls):
            if not name.startswith("_"):
                yield getattr(cls, name)


class BaseCommandDefs(metaclass=IterableMemberMeta):
    pass


class BaseAttributeDefs(metaclass=IterableMemberMeta):
    pass


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
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Read_Attributes_rsp: ZCLCommandDef(
        schema={"status_records": t.List[ReadAttributeRecord]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Write_Attributes: ZCLCommandDef(
        schema={"attributes": t.List[Attribute]}, direction=Direction.Client_to_Server
    ),
    GeneralCommand.Write_Attributes_Undivided: ZCLCommandDef(
        schema={"attributes": t.List[Attribute]}, direction=Direction.Client_to_Server
    ),
    GeneralCommand.Write_Attributes_rsp: ZCLCommandDef(
        schema={"status_records": WriteAttributesResponse},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Write_Attributes_No_Response: ZCLCommandDef(
        schema={"attributes": t.List[Attribute]}, direction=Direction.Client_to_Server
    ),
    GeneralCommand.Configure_Reporting: ZCLCommandDef(
        schema={"config_records": t.List[AttributeReportingConfig]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Configure_Reporting_rsp: ZCLCommandDef(
        schema={"status_records": ConfigureReportingResponse},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Read_Reporting_Configuration: ZCLCommandDef(
        schema={"attribute_records": t.List[ReadReportingConfigRecord]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Read_Reporting_Configuration_rsp: ZCLCommandDef(
        schema={"attribute_configs": t.List[AttributeReportingConfigWithStatus]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Report_Attributes: ZCLCommandDef(
        schema={"attribute_reports": t.List[Attribute]},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Default_Response: ZCLCommandDef(
        schema={"command_id": t.uint8_t, "status": Status},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Attributes: ZCLCommandDef(
        schema={"start_attribute_id": t.uint16_t, "max_attribute_ids": t.uint8_t},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Attributes_rsp: ZCLCommandDef(
        schema={
            "discovery_complete": t.Bool,
            "attribute_info": t.List[DiscoverAttributesResponseRecord],
        },
        direction=Direction.Server_to_Client,
    ),
    # Command.Read_Attributes_Structured: ZCLCommandDef(schema=(, ), direction=Direction.Client_to_Server),
    # Command.Write_Attributes_Structured: ZCLCommandDef(schema=(, ), direction=Direction.Client_to_Server),
    # Command.Write_Attributes_Structured_rsp: ZCLCommandDef(schema=(, ), direction=Direction.Server_to_Client),
    GeneralCommand.Discover_Commands_Received: ZCLCommandDef(
        schema={"start_command_id": t.uint8_t, "max_command_ids": t.uint8_t},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Commands_Received_rsp: ZCLCommandDef(
        schema={"discovery_complete": t.Bool, "command_ids": t.List[t.uint8_t]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Commands_Generated: ZCLCommandDef(
        schema={"start_command_id": t.uint8_t, "max_command_ids": t.uint8_t},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Commands_Generated_rsp: ZCLCommandDef(
        schema={"discovery_complete": t.Bool, "command_ids": t.List[t.uint8_t]},
        direction=Direction.Server_to_Client,
    ),
    GeneralCommand.Discover_Attribute_Extended: ZCLCommandDef(
        schema={"start_attribute_id": t.uint16_t, "max_attribute_ids": t.uint8_t},
        direction=Direction.Client_to_Server,
    ),
    GeneralCommand.Discover_Attribute_Extended_rsp: ZCLCommandDef(
        schema={
            "discovery_complete": t.Bool,
            "extended_attr_info": t.List[DiscoverAttributesExtendedResponseRecord],
        },
        direction=Direction.Server_to_Client,
    ),
}

for command_id, command_def in list(GENERAL_COMMANDS.items()):
    GENERAL_COMMANDS[command_id] = command_def.replace(
        id=command_id, name=command_id.name
    ).with_compiled_schema()

ZCL_CLUSTER_REVISION_ATTR = ZCLAttributeDef(
    id=0xFFFD, type=t.uint16_t, access="r", mandatory=True
)
ZCL_REPORTING_STATUS_ATTR = ZCLAttributeDef(
    id=0xFFFE, type=AttributeReportingStatus, access="r"
)
