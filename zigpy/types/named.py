import enum

from . import basic


class BroadcastAddress(basic.uint16_t, enum.Enum):
    ALL_DEVICES = 0xffff
    RESERVED_FFFE = 0xfffe
    RX_ON_WHEN_IDLE = 0xfffd
    ALL_ROUTERS_AND_COORDINATOR = 0xfffc
    LOW_POWER_ROUTER = 0xfffb
    RESERVED_FFFA = 0xfffa
    RESERVED_FFF9 = 0xfff9
    RESERVED_FFF8 = 0xfff8


class EUI64(basic.fixed_list(8, basic.uint8_t)):
    # EUI 64-bit ID (an IEEE address).
    @classmethod
    def deserialize(cls, data):
        r, data = super().deserialize(data)
        return cls(r[::-1]), data

    def serialize(self):
        assert self._length == len(self)
        return b''.join([i.serialize() for i in self[::-1]])

    def __repr__(self):
        return ':'.join('%02x' % i for i in self)

    def __hash__(self):
        return hash(repr(self))


class KeyData(basic.fixed_list(16, basic.uint8_t)):
    pass


class Bool(basic.uint8_t, enum.Enum):
    false = 0
    true = 1


class HexRepr:
    _hex_len = 2

    def __repr__(self):
        return ('0x{:0' + str(self._hex_len) + 'x}').format(self)

    def __str__(self):
        return ('0x{:0' + str(self._hex_len) + 'x}').format(self)


class NWK(HexRepr, basic.uint16_t):
    _hex_len = 4


class Group(HexRepr, basic.uint16_t):
    _hex_len = 4
