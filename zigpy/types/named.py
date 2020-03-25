import enum

from . import basic
from .struct import Struct


class BroadcastAddress(basic.enum16):
    ALL_DEVICES = 0xFFFF
    RESERVED_FFFE = 0xFFFE
    RX_ON_WHEN_IDLE = 0xFFFD
    ALL_ROUTERS_AND_COORDINATOR = 0xFFFC
    LOW_POWER_ROUTER = 0xFFFB
    RESERVED_FFFA = 0xFFFA
    RESERVED_FFF9 = 0xFFF9
    RESERVED_FFF8 = 0xFFF8


class EUI64(basic.fixed_list(8, basic.uint8_t)):
    # EUI 64-bit ID (an IEEE address).
    def __repr__(self):
        return ":".join("%02x" % i for i in self[::-1])

    def __hash__(self):
        return hash(repr(self))

    @classmethod
    def convert(cls, ieee: str):
        if ieee is None:
            return None
        ieee = [basic.uint8_t(p, base=16) for p in ieee.split(":")[::-1]]
        assert len(ieee) == cls._length
        return cls(ieee)


class KeyData(basic.fixed_list(16, basic.uint8_t)):
    pass


class Bool(basic.uint8_t, enum.Enum):
    false = 0
    true = 1


class HexRepr:
    def __repr__(self):
        return ("0x{:0" + str(self._size * 2) + "x}").format(self)

    def __str__(self):
        return ("0x{:0" + str(self._size * 2) + "x}").format(self)


class AttributeId(HexRepr, basic.uint16_t):
    pass


class BACNetOid(basic.uint32_t):
    pass


class Channels(basic.bitmap32):
    """Zigbee Channels."""

    NO_CHANNELS = 0x00000000
    ALL_CHANNELS = 0x07FFF800
    CHANNEL_11 = 0x00000800
    CHANNEL_12 = 0x00001000
    CHANNEL_13 = 0x00002000
    CHANNEL_14 = 0x00004000
    CHANNEL_15 = 0x00008000
    CHANNEL_16 = 0x00010000
    CHANNEL_17 = 0x00020000
    CHANNEL_18 = 0x00040000
    CHANNEL_19 = 0x00080000
    CHANNEL_20 = 0x00100000
    CHANNEL_21 = 0x00200000
    CHANNEL_22 = 0x00400000
    CHANNEL_23 = 0x00800000
    CHANNEL_24 = 0x01000000
    CHANNEL_25 = 0x02000000
    CHANNEL_26 = 0x04000000


class ClusterId(basic.uint16_t):
    pass


class Date(Struct):
    _fields = [
        ("_year", basic.uint8_t),
        ("month", basic.uint8_t),
        ("day", basic.uint8_t),
        ("day_of_week", basic.uint8_t),
    ]

    @property
    def year(self):
        """Return year."""
        if self._year is None:
            return self._year
        return 1900 + self._year

    @year.setter
    def year(self, value):
        assert 1900 <= value <= 2155
        self._year = basic.uint8_t(value - 1900)


class NWK(HexRepr, basic.uint16_t):
    pass


class PanId(NWK):
    pass


class ExtendedPanId(EUI64):
    pass


class Group(HexRepr, basic.uint16_t):
    pass


class NoData:
    @classmethod
    def deserialize(cls, data):
        return cls(), data

    def serialize(self):
        return b""


class TimeOfDay(Struct):
    _fields = [
        ("hours", basic.uint8_t),
        ("minutes", basic.uint8_t),
        ("seconds", basic.uint8_t),
        ("hundredths", basic.uint8_t),
    ]


class _Time(basic.uint32_t):
    pass


class UTCTime(_Time):
    pass


class StandardTime(_Time):
    """Adjusted for TimeZone but not for daylight saving."""

    pass


class LocalTime(_Time):
    """Standard time adjusted for daylight saving."""

    pass


class Relays(basic.LVList(NWK)):
    """Relay list for static routing."""

    pass
