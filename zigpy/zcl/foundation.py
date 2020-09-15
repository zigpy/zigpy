from typing import Optional, Tuple, Union

import zigpy.types as t


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


class TypeValue:
    def __init__(self, python_type=None, value=None):
        # Copy constructor
        if isinstance(python_type, TypeValue):
            other = python_type

            python_type = other.type
            value = other.value

        self.type = python_type
        self.value = value

    def serialize(self):
        return self.type.to_bytes(1, "little") + self.value.serialize()

    @classmethod
    def deserialize(cls, data):
        self = cls()
        self.type, data = t.uint8_t.deserialize(data)
        python_type = DATA_TYPES[self.type][1]
        self.value, data = python_type.deserialize(data)
        return self, data

    def __repr__(self):
        return "<%s type=%s, value=%s>" % (
            self.__class__.__name__,
            self.value.__class__.__name__,
            self.value,
        )


class TypedCollection(TypeValue):
    @classmethod
    def deserialize(cls, data):
        self = cls()
        self.type, data = data[0], data[1:]
        python_item_type = DATA_TYPES[self.type][1]
        python_type = t.LVList[python_item_type]
        self.value, data = python_type.deserialize(data)
        return self, data


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

    attrid: t.uint16_t
    status: Status
    value: TypeValue = t.StructField(requires=lambda s: s.status == Status.SUCCESS)


class Attribute(t.Struct):
    attrid: t.uint16_t
    value: TypeValue


class WriteAttributesStatusRecord(t.Struct):
    status: Status
    attrid: t.uint16_t = t.StructField(requires=lambda s: s.status != Status.SUCCESS)


class WriteAttributesResponse(list):
    """Write Attributes response list.

    Response to Write Attributes request should contain only success status, in
    case when all attributes were successfully written or list of status + attr_id
    records for all failed writes.
    """

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["WriteAttributesResponse", bytes]:
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


class AttributeReportingConfig:
    def __init__(self, other=None):
        if isinstance(other, self.__class__):
            self.direction = other.direction
            self.attrid = other.attrid
            if self.direction == ReportingDirection.ReceiveReports:
                self.timeout = other.timeout
                return
            self.datatype = other.datatype
            self.min_interval = other.min_interval
            self.max_interval = other.max_interval
            self.reportable_change = other.reportable_change

    def serialize(self):
        r = ReportingDirection(self.direction).serialize()
        r += t.uint16_t(self.attrid).serialize()
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
    def deserialize(cls, data):
        self = cls()
        self.direction, data = ReportingDirection.deserialize(data)
        self.attrid, data = t.uint16_t.deserialize(data)
        if self.direction == ReportingDirection.ReceiveReports:
            # Requesting things to be received by me
            self.timeout, data = t.uint16_t.deserialize(data)
        else:
            # Notifying that I will report things to you
            self.datatype, data = t.uint8_t.deserialize(data)
            self.min_interval, data = t.uint16_t.deserialize(data)
            self.max_interval, data = t.uint16_t.deserialize(data)
            datatype = DATA_TYPES[self.datatype]
            if datatype[2] is Analog:
                self.reportable_change, data = datatype[1].deserialize(data)

        return self, data

    def __repr__(self):
        r = f"{self.__class__.__name__}("
        r += f"direction={self.direction}"
        r += f", attrid={self.attrid}"

        if self.direction == ReportingDirection.ReceiveReports:
            r += f", timeout={self.timeout}"
        else:
            r += f", datatype={self.datatype}"
            r += f", min_interval={self.min_interval}"
            r += f", max_interval={self.max_interval}"

            if self.reportable_change is not None:
                r += f", reportable_change={self.reportable_change}"

        r += ")"

        return r


class ConfigureReportingResponseRecord(t.Struct):
    status: Status
    direction: ReportingDirection
    attrid: t.uint16_t

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


class Command(t.enum8):
    """ZCL Foundation Global Command IDs."""

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


COMMANDS = {
    # id: (params, is_response)
    Command.Configure_Reporting: ((t.List[AttributeReportingConfig],), False),
    Command.Configure_Reporting_rsp: ((ConfigureReportingResponse,), True),
    Command.Default_Response: ((t.uint8_t, Status), True),
    Command.Discover_Attributes: ((t.uint16_t, t.uint8_t), False),
    Command.Discover_Attributes_rsp: (
        (t.Bool, t.List[DiscoverAttributesResponseRecord]),
        True,
    ),
    Command.Discover_Attribute_Extended: ((t.uint16_t, t.uint8_t), False),
    Command.Discover_Attribute_Extended_rsp: (
        (t.Bool, t.List[DiscoverAttributesExtendedResponseRecord]),
        True,
    ),
    Command.Discover_Commands_Generated: ((t.uint8_t, t.uint8_t), False),
    Command.Discover_Commands_Generated_rsp: ((t.Bool, t.List[t.uint8_t]), True),
    Command.Discover_Commands_Received: ((t.uint8_t, t.uint8_t), False),
    Command.Discover_Commands_Received_rsp: ((t.Bool, t.List[t.uint8_t]), True),
    Command.Read_Attributes: ((t.List[t.uint16_t],), False),
    Command.Read_Attributes_rsp: ((t.List[ReadAttributeRecord],), True),
    # Command.Read_Attributes_Structured: ((, ), False),
    Command.Read_Reporting_Configuration: ((t.List[ReadReportingConfigRecord],), False),
    Command.Read_Reporting_Configuration_rsp: (
        (t.List[AttributeReportingConfig],),
        True,
    ),
    Command.Report_Attributes: ((t.List[Attribute],), False),
    Command.Write_Attributes: ((t.List[Attribute],), False),
    Command.Write_Attributes_No_Response: ((t.List[Attribute],), False),
    Command.Write_Attributes_rsp: ((WriteAttributesResponse,), True),
    # Command.Write_Attributes_Structured: ((, ), False),
    # Command.Write_Attributes_Structured_rsp: ((, ), True),
    Command.Write_Attributes_Undivided: ((t.List[Attribute],), False),
}


class FrameType(t.enum8):
    """ZCL Frame Type."""

    GLOBAL_COMMAND = 0b00
    CLUSTER_COMMAND = 0b01
    RESERVED_2 = 0b10
    RESERVED_3 = 0b11


class FrameControl:
    """The frame control field contains information defining the command type
    and other control flags."""

    def __init__(self, frame_control: int = 0x00) -> None:
        self.value = frame_control

    @property
    def disable_default_response(self) -> bool:
        """Return True if default response is disabled."""
        return bool(self.value & 0b10000)

    @disable_default_response.setter
    def disable_default_response(self, value: bool) -> None:
        """Disable the default response."""
        if value:
            self.value |= 0b10000
            return
        self.value &= 0b11101111

    @property
    def frame_type(self) -> FrameType:
        """Return frame type."""
        return FrameType(self.value & 0b00000011)

    @frame_type.setter
    def frame_type(self, value: FrameType) -> None:
        """Sets frame type to Global general command."""
        self.value &= 0b11111100
        self.value |= value

    @property
    def is_cluster(self) -> bool:
        """Return True if command is a local cluster specific command."""
        return bool(self.frame_type == FrameType.CLUSTER_COMMAND)

    @property
    def is_general(self) -> bool:
        """Return True if command is a global ZCL command."""
        return bool(self.frame_type == FrameType.GLOBAL_COMMAND)

    @property
    def is_manufacturer_specific(self) -> bool:
        """Return True if manufacturer code is present."""
        return bool(self.value & 0b100)

    @is_manufacturer_specific.setter
    def is_manufacturer_specific(self, value: bool) -> None:
        """Sets manufacturer specific code."""
        if value:
            self.value |= 0b100
            return
        self.value &= 0b11111011

    @property
    def is_reply(self) -> bool:
        """Return True if is a reply (server cluster -> client cluster."""
        return bool(self.value & 0b1000)

    # in ZCL specs the above is the "direction" field
    direction = is_reply

    @is_reply.setter
    def is_reply(self, value: bool) -> None:
        """Sets the direction."""
        if value:
            self.value |= 0b1000
            return
        self.value &= 0b11110111

    def __repr__(self) -> str:
        """Representation."""
        return (
            "<{} frame_type={} manufacturer_specific={} is_reply={} "
            "disable_default_response={}>"
        ).format(
            self.__class__.__name__,
            self.frame_type.name,
            self.is_manufacturer_specific,
            self.is_reply,
            self.disable_default_response,
        )

    def serialize(self) -> bytes:
        return t.uint8_t(self.value).serialize()

    @classmethod
    def cluster(cls, is_reply: bool = False):
        """New Local Cluster specific command frame control."""
        r = cls(FrameType.CLUSTER_COMMAND)
        r.is_reply = is_reply
        if is_reply:
            r.disable_default_response = True
        return r

    @classmethod
    def deserialize(cls, data):
        frc, data = t.uint8_t.deserialize(data)
        return cls(frc), data

    @classmethod
    def general(cls, is_reply: bool = False):
        """New General ZCL command frame control."""
        r = cls(FrameType.GLOBAL_COMMAND)
        r.is_reply = is_reply
        if is_reply:
            r.disable_default_response = True
        return r


class ZCLHeader:
    """ZCL Header."""

    def __init__(
        self,
        frame_control: FrameControl,
        tsn: Union[int, t.uint8_t] = 0,
        command_id: Union[Command, int, t.uint8_t] = 0,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
    ) -> None:
        """Initialize ZCL Frame instance."""
        self._frc = frame_control
        if frame_control.is_general:
            self._cmd_id = Command(command_id)
        else:
            self._cmd_id = t.uint8_t(command_id)
        self._manufacturer = manufacturer
        if manufacturer is not None:
            self.frame_control.is_manufacturer_specific = True
        self._tsn = t.uint8_t(tsn)

    @property
    def frame_control(self) -> FrameControl:
        """Return frame control."""
        return self._frc

    @property
    def command_id(self) -> Command:
        """Return command identifier."""
        return self._cmd_id

    @command_id.setter
    def command_id(self, value: Command) -> None:
        """Setter for command identifier."""
        if self.frame_control.is_general:
            self._cmd_id = Command(value)
            return
        self._cmd_id = t.uint8_t(value)

    @property
    def is_reply(self) -> bool:
        """Return direction of Frame Control."""
        return self.frame_control.is_reply

    @property
    def manufacturer(self) -> Optional[t.uint16_t]:
        """Return manufacturer id."""
        if self._manufacturer is None:
            return None
        return t.uint16_t(self._manufacturer)

    @manufacturer.setter
    def manufacturer(self, value: t.uint16_t) -> None:
        self.frame_control.is_manufacturer_specific = bool(value)
        self._manufacturer = value

    @property
    def tsn(self) -> t.uint8_t:
        """Return transaction seq number."""
        return self._tsn

    @tsn.setter
    def tsn(self, value: t.uint8_t) -> None:
        """Setter for tsn."""
        self._tsn = t.uint8_t(value)

    @classmethod
    def deserialize(cls, data):
        """Deserialize from bytes."""
        frc, data = FrameControl.deserialize(data)
        r = cls(frc)
        if frc.is_manufacturer_specific:
            r.manufacturer, data = t.uint16_t.deserialize(data)
        r.tsn, data = t.uint8_t.deserialize(data)
        r.command_id, data = Command.deserialize(data)
        return r, data

    def serialize(self):
        """Serialize to bytes."""
        d = self.frame_control.serialize()
        if self.frame_control.is_manufacturer_specific:
            d += self.manufacturer.serialize()
        d += self.tsn.serialize()
        d += self.command_id.serialize()
        return d

    @classmethod
    def general(
        cls,
        tsn: Union[int, t.uint8_t],
        command_id: Union[int, t.uint8_t],
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        is_reply: bool = False,
    ) -> "ZCLHeader":
        r = cls(FrameControl.general(is_reply), tsn, command_id, manufacturer)
        if manufacturer is not None:
            r.frame_control.is_manufacturer_specific = True
        return r

    @classmethod
    def cluster(
        cls,
        tsn: Union[int, t.uint8_t],
        command_id: Union[int, t.uint8_t],
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        is_reply: bool = False,
    ) -> "ZCLHeader":
        r = cls(FrameControl.cluster(is_reply), tsn, command_id, manufacturer)
        if manufacturer is not None:
            r.frame_control.is_manufacturer_specific = True
        return r

    def __repr__(self) -> str:
        """Representation."""
        return "<{} frame_control={} manufacturer={} tsn={} command_id={}>".format(
            self.__class__.__name__,
            self.frame_control,
            self.manufacturer,
            self.tsn,
            str(self.command_id),
        )
