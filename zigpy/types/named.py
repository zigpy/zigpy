import enum

from . import basic


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
