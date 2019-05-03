import enum

import zigpy.types as t


class Status(t.uint8_t, enum.Enum):
    SUCCESS = 0x00  # Operation was successful.
    FAILURE = 0x01  # Operation was not successful
    NOT_AUTHORIZED = 0x7e  # The sender of the command does not have
    RESERVED_FIELD_NOT_ZERO = 0x7f  # A reserved field/subfield/bit contains a
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
    DUPLICATE_EXISTS = 0x8a  # An attempt to create an entry in a table failed
    NOT_FOUND = 0x8b  # The requested information (e.g. table entry)
    UNREPORTABLE_ATTRIBUTE = 0x8c  # Periodic reports cannot be issued for this
    INVALID_DATA_TYPE = 0x8d  # The data type given for an attribute is
    INVALID_SELECTOR = 0x8e  # The selector for an attribute is incorrect.
    WRITE_ONLY = 0x8f  # A request has been made to read an attribute
    INCONSISTENT_STARTUP_STATE = 0x90  # Setting the requested values would put
    DEFINED_OUT_OF_BAND = 0x91  # An attempt has been made to write an
    INCONSISTENT = 0x92  # The supplied values (e.g., contents of table cells) are inconsistent
    ACTION_DENIED = 0x93  # The credentials presented by the device sending the
    TIMEOUT = 0x94  # The exchange was aborted due to excessive response time
    ABORT = 0x95  # Failed case when a client or a server decides to abort the upgrade process
    INVALID_IMAGE = 0x96  # Invalid OTA upgrade image (ex. failed signature
    WAIT_FOR_DATA = 0x97  # Server does not have data block available yet
    NO_IMAGE_AVAILABLE = 0x98  # No OTA upgrade image available for a particular client
    REQUIRE_MORE_IMAGE = 0x99  # The client still requires more OTA upgrade image
    NOTIFICATION_PENDING = 0x9a  # The command has been received and is being processed
    HARDWARE_FAILURE = 0xc0  # An operation was unsuccessful due to a
    SOFTWARE_FAILURE = 0xc1  # An operation was unsuccessful due to a
    CALIBRATION_ERROR = 0xc2  # An error occurred during calibratio
    UNSUPPORTED_CLUSTER = 0xc3  # The cluster is not supported


class Analog:
    pass


class Discrete:
    pass


class TypeValue:
    def serialize(self):
        return self.type.to_bytes(1, 'little') + self.value.serialize()

    @classmethod
    def deserialize(cls, data):
        self = cls()
        self.type, data = data[0], data[1:]
        python_type = DATA_TYPES[self.type][1]
        self.value, data = python_type.deserialize(data)
        return self, data

    def __repr__(self):
        return "<%s type=%s, value=%s>" % (self.__class__.__name__,
                                           self.value.__class__.__name__,
                                           self.value)


class TypedCollection(TypeValue):
    @classmethod
    def deserialize(cls, data):
        self = cls()
        self.type, data = data[0], data[1:]
        python_item_type = DATA_TYPES[self.type][1]
        python_type = t.LVList(python_item_type)
        self.value, data = python_type.deserialize(data)
        return self, data


DATA_TYPES = {
    0x00: ('No data', None, None),
    0x08: ('General', t.fixed_list(1, t.uint8_t), Discrete),
    0x09: ('General', t.fixed_list(2, t.uint8_t), Discrete),
    0x0a: ('General', t.fixed_list(3, t.uint8_t), Discrete),
    0x0b: ('General', t.fixed_list(4, t.uint8_t), Discrete),
    0x0c: ('General', t.fixed_list(5, t.uint8_t), Discrete),
    0x0d: ('General', t.fixed_list(6, t.uint8_t), Discrete),
    0x0e: ('General', t.fixed_list(7, t.uint8_t), Discrete),
    0x0f: ('General', t.fixed_list(8, t.uint8_t), Discrete),
    0x10: ('Boolean', t.Bool, Discrete),
    0x18: ('Bitmap', t.bitmap8, Discrete),
    0x19: ('Bitmap', t.bitmap16, Discrete),
    0x1a: ('Bitmap', t.bitmap24, Discrete),
    0x1b: ('Bitmap', t.bitmap32, Discrete),
    0x1c: ('Bitmap', t.bitmap40, Discrete),
    0x1d: ('Bitmap', t.bitmap48, Discrete),
    0x1e: ('Bitmap', t.bitmap56, Discrete),
    0x1f: ('Bitmap', t.bitmap64, Discrete),
    0x20: ('Unsigned Integer', t.uint8_t, Analog),
    0x21: ('Unsigned Integer', t.uint16_t, Analog),
    0x22: ('Unsigned Integer', t.uint24_t, Analog),
    0x23: ('Unsigned Integer', t.uint32_t, Analog),
    0x24: ('Unsigned Integer', t.uint40_t, Analog),
    0x25: ('Unsigned Integer', t.uint48_t, Analog),
    0x26: ('Unsigned Integer', t.uint56_t, Analog),
    0x27: ('Unsigned Integer', t.uint64_t, Analog),
    0x28: ('Signed Integer', t.int8s, Analog),
    0x29: ('Signed Integer', t.int16s, Analog),
    0x2a: ('Signed Integer', t.int24s, Analog),
    0x2b: ('Signed Integer', t.int32s, Analog),
    0x2c: ('Signed Integer', t.int40s, Analog),
    0x2d: ('Signed Integer', t.int48s, Analog),
    0x2e: ('Signed Integer', t.int56s, Analog),
    0x2f: ('Signed Integer', t.int64s, Analog),
    0x30: ('Enumeration', t.enum8, Discrete),
    0x31: ('Enumeration', t.enum16, Discrete),
    # 0x38: ('Floating point', t.Half, Analog),
    0x39: ('Floating point', t.Single, Analog),
    0x3a: ('Floating point', t.Double, Analog),
    0x41: ('Octet string', t.LVBytes, Discrete),
    0x42: ('Character string', t.CharacterString, Discrete),
    0x43: ('Long octet string', t.LongOctetString, Discrete),
    0x44: ('Long character string', t.LongCharacterString, Discrete),
    0x48: ('Array', TypedCollection, Discrete),
    0x4c: ('Structure', t.LVList(TypeValue, 2), Discrete),
    0x50: ('Set', TypedCollection, Discrete),
    0x51: ('Bag', TypedCollection, Discrete),
    0xe0: ('Time of day', t.uint32_t, Analog),
    0xe1: ('Date', t.uint32_t, Analog),
    0xe2: ('UTCTime', t.uint32_t, Analog),
    0xe8: ('Cluster ID', t.uint16_t, Discrete),
    0xe9: ('Attribute ID', t.uint16_t, Discrete),
    0xea: ('BACNet OID', t.uint32_t, Discrete),
    0xf0: ('IEEE address', t.EUI64, Discrete),
    0xf1: ('128-bit security key', t.fixed_list(16, t.uint16_t), Discrete),
    0xff: ('Unknown', None, None),
}

DATA_TYPE_IDX = {
    t: tidx
    for tidx, (tname, t, ad) in DATA_TYPES.items()
    if ad is Analog or tname == 'Enumeration' or tname == 'Bitmap'
}
DATA_TYPE_IDX[t.uint32_t] = 0x23
DATA_TYPE_IDX[t.EUI64] = 0xf0
DATA_TYPE_IDX[t.Bool] = 0x10


class ReadAttributeRecord():
    @classmethod
    def deserialize(cls, data):
        r = cls()
        r.attrid, data = int.from_bytes(data[:2], 'little'), data[2:]
        r.status, data = data[0], data[1:]
        if r.status == 0:
            r.value, data = TypeValue.deserialize(data)

        return r, data

    def serialize(self):
        r = t.uint16_t(self.attrid).serialize()
        r += t.uint8_t(self.status).serialize()
        if self.status == 0:
            r += self.value.serialize()

        return r

    def __repr__(self):
        r = '<ReadAttributeRecord attrid=%s status=%s' % (self.attrid, self.status)
        if self.status == 0:
            r += ' value=%s' % (self.value.value, )
        r += '>'
        return r


class Attribute(t.Struct):
    _fields = [
        ('attrid', t.uint16_t),
        ('value', TypeValue),
    ]


class WriteAttributesStatusRecord(t.Struct):
    _fields = [
        ('status', Status),
        ('attrid', t.uint16_t),
    ]


class AttributeReportingConfig:
    def serialize(self):
        r = int.to_bytes(self.direction, 1, 'little')
        r += int.to_bytes(self.attrid, 2, 'little')
        if self.direction:
            r += int.to_bytes(self.timeout, 2, 'little')
        else:
            r += (
                int.to_bytes(self.datatype, 1, 'little') +
                int.to_bytes(self.min_interval, 2, 'little') +
                int.to_bytes(self.max_interval, 2, 'little')
            )
            datatype = DATA_TYPES.get(self.datatype, None)
            if datatype and datatype[2] is Analog:
                datatype = datatype[1]
                r += datatype(self.reportable_change).serialize()
        return r

    @classmethod
    def deserialize(cls, data):
        self = cls()
        self.direction, data = t.Bool.deserialize(data)
        self.attrid, data = t.uint16_t.deserialize(data)
        if self.direction:
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


class ConfigureReportingResponseRecord(t.Struct):
    _fields = [
        ('status', t.uint8_t),
        ('direction', t.uint8_t),
        ('attrid', t.uint16_t),
    ]


class ReadReportingConfigRecord(t.Struct):
    _fields = [
        ('direction', t.uint8_t),
        ('attrid', t.uint16_t),
    ]


class DiscoverAttributesResponseRecord(t.Struct):
    _fields = [
        ('attrid', t.uint16_t),
        ('datatype', t.uint8_t),
    ]


class AttributeAccessControl(t.uint8_t, enum.Enum):
    NO_ACCESS = 0b000
    REPORT = 0b001
    WRITE = 0b010
    WRITE_REPORT = 0b011
    READ = 0b100
    READ_REPORT = 0b101
    READ_WRITE = 0b110
    READ_WRITE_REPORT = 0b111


class DiscoverAttributesExtendedResponseRecord(t.Struct):
    _fields = [
        ('attrid', t.uint16_t),
        ('datatype', t.uint8_t),
        ('acl', AttributeAccessControl),
    ]


COMMANDS = {
    # id: (name, params, is_response)
    0x00: ('Read attributes', (t.List(t.uint16_t), ), False),
    0x01: ('Read attributes response', (t.List(ReadAttributeRecord), ), True),
    0x02: ('Write attributes', (t.List(Attribute), ), False),
    0x03: ('Write attributes undivided', (t.List(Attribute), ), False),
    0x04: ('Write attributes response', (t.List(WriteAttributesStatusRecord), ), True),
    0x05: ('Write attributes no response', (t.List(Attribute), ), False),
    0x06: ('Configure reporting', (t.List(AttributeReportingConfig), ), False),
    0x07: ('Configure reporting response', (t.List(ConfigureReportingResponseRecord), ), True),
    0x08: ('Read reporting configuration', (t.List(ReadReportingConfigRecord), ), False),
    0x09: ('Read reporting configuration response', (t.List(AttributeReportingConfig), ), True),
    0x0a: ('Report attributes', (t.List(Attribute), ), False),
    0x0b: ('Default response', (t.uint8_t, Status), True),
    0x0c: ('Discover attributes', (t.uint16_t, t.uint8_t), False),
    0x0d: ('Discover attributes response', (t.Bool, t.List(DiscoverAttributesResponseRecord), ), True),
    # 0x0e: ('Read attributes structured', (, ), False),
    # 0x0f: ('Write attributes structured', (, ), False),
    # 0x10: ('Write attributes structured response', (, ), True),
    0x11: ('Discover commands received', (t.uint8_t, t.uint8_t), False),
    0x12: ('Discover commands received response', (t.Bool, t.List(t.uint8_t)), True),
    0x13: ('Discover commands generated', (t.uint8_t, t.uint8_t), False),
    0x14: ('Discover commands generated response', (t.Bool, t.List(t.uint8_t)), True),
    0x15: ('Discover attributes extended', (t.uint16_t, t.uint8_t), False),
    0x16: ('Discover attributes extended response', (t.Bool, t.List(DiscoverAttributesExtendedResponseRecord)), True),
}
