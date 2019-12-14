import enum

from . import basic
from .struct import Struct


class BroadcastAddress(basic.uint16_t, enum.Enum):
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


class UTCTime(basic.uint32_t):
    pass


class Relays(basic.LVList(NWK)):
    """Relay list for static routing."""

    pass
