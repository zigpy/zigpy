import enum
import struct
from typing import Callable, Tuple, TypeVar

CALLABLE_T = TypeVar("CALLABLE_T", bound=Callable)  # pylint: disable=invalid-name


class int_t(int):  # noqa: N801
    _signed = True

    def serialize(self):
        return self.to_bytes(self._size, "little", signed=self._signed)

    @classmethod
    def deserialize(cls, data):
        if len(data) < cls._size:
            raise ValueError("Data is too short to contain %d bytes" % cls._size)

        r = cls.from_bytes(data[: cls._size], "little", signed=cls._signed)
        return r, data[cls._size :]


class int8s(int_t):  # noqa: N801
    _size = 1


class int16s(int_t):  # noqa: N801
    _size = 2


class int24s(int_t):  # noqa: N801
    _size = 3


class int32s(int_t):  # noqa: N801
    _size = 4


class int40s(int_t):  # noqa: N801
    _size = 5


class int48s(int_t):  # noqa: N801
    _size = 6


class int56s(int_t):  # noqa: N801
    _size = 7


class int64s(int_t):  # noqa: N801
    _size = 8


class uint_t(int_t):  # noqa: N801
    _signed = False


class uint8_t(uint_t):  # noqa: N801
    _size = 1


class uint16_t(uint_t):  # noqa: N801
    _size = 2


class uint24_t(uint_t):  # noqa: N801
    _size = 3


class uint32_t(uint_t):  # noqa: N801
    _size = 4


class uint40_t(uint_t):  # noqa: N801
    _size = 5


class uint48_t(uint_t):  # noqa: N801
    _size = 6


class uint56_t(uint_t):  # noqa: N801
    _size = 7


class uint64_t(uint_t):  # noqa: N801
    _size = 8


class _IntEnumMeta(enum.EnumMeta):
    def __call__(cls, value, names=None, *args, **kwargs):
        if isinstance(value, str) and value.startswith("0x"):
            value = int(value, base=16)
        else:
            value = int(value)
        return super().__call__(value, names, *args, **kwargs)


def enum_factory(int_type: CALLABLE_T, undefined: str = "undefined") -> CALLABLE_T:
    """Enum factory."""

    class _NewEnum(enum.IntEnum, metaclass=_IntEnumMeta):
        def serialize(self):
            """Serialize enum."""
            return int_type(self.value).serialize()

        @classmethod
        def deserialize(cls, data: bytes) -> (bytes, bytes):
            """Deserialize data."""
            val, data = int_type.deserialize(data)
            return cls(val), data

        @classmethod
        def _missing_(cls, value):
            new = int_type.__new__(cls, value)
            name = f"{undefined}_0x{{:0{int_type._size * 2}x}}"  # pylint: disable=protected-access
            new._name_ = name.format(value)
            new._value_ = value
            return new

    return _NewEnum


class enum8(enum_factory(uint8_t)):  # noqa: N801
    pass


class enum16(enum_factory(uint16_t)):  # noqa: N801
    pass


def bitmap_factory(int_type: CALLABLE_T) -> CALLABLE_T:
    """Bitmap factory."""

    class _NewBitmap(enum.IntFlag):
        def serialize(self):
            """Serialize enum."""
            return int_type(self.value).serialize()

        @classmethod
        def deserialize(cls, data: bytes) -> (bytes, bytes):
            """Deserialize data."""
            val, data = int_type.deserialize(data)
            return cls(val), data

    return _NewBitmap


class bitmap8(bitmap_factory(uint8_t)):  # noqa: N801
    pass


class bitmap16(bitmap_factory(uint16_t)):  # noqa: N801
    pass


class bitmap24(bitmap_factory(uint24_t)):  # noqa: N801
    pass


class bitmap32(bitmap_factory(uint32_t)):  # noqa: N801
    pass


class bitmap40(bitmap_factory(uint40_t)):  # noqa: N801
    pass


class bitmap48(bitmap_factory(uint48_t)):  # noqa: N801
    pass


class bitmap56(bitmap_factory(uint56_t)):  # noqa: N801
    pass


class bitmap64(bitmap_factory(uint64_t)):  # noqa: N801
    pass


class BaseFloat(float):
    _exponent_bits = None
    _fraction_bits = None
    _size = None

    def __init_subclass__(cls, exponent_bits, fraction_bits):
        size_bits = 1 + exponent_bits + fraction_bits
        assert size_bits % 8 == 0

        cls._exponent_bits = exponent_bits
        cls._fraction_bits = fraction_bits
        cls._size = size_bits // 8

    @staticmethod
    def _convert_format(*, src: "BaseFloat", dst: "BaseFloat", n: int) -> int:
        """
        Converts an integer representing a float from one format into another. Note:

         1. Format is assumed to be little endian: 0b[sign bit] [exponent] [fraction]
         2. Truncates/extends the exponent, preserving the special cases of all 1's
            and all 0's.
         3. Truncates/extends the fractional bits from the right, allowing lossless
            conversion to a "bigger" representation.
        """

        src_sign = n >> (src._exponent_bits + src._fraction_bits)
        src_frac = n & ((1 << src._fraction_bits) - 1)
        src_biased_exp = (n >> src._fraction_bits) & ((1 << src._exponent_bits) - 1)
        src_exp = src_biased_exp - 2 ** (src._exponent_bits - 1)

        if src_biased_exp == (1 << src._exponent_bits) - 1:
            dst_biased_exp = 2 ** dst._exponent_bits - 1
        elif src_biased_exp == 0:
            dst_biased_exp = 0
        else:
            dst_min_exp = 2 - 2 ** (dst._exponent_bits - 1)  # Can't be all zeroes
            dst_max_exp = 2 ** (dst._exponent_bits - 1) - 2  # Can't be all ones
            dst_exp = min(max(dst_min_exp, src_exp), dst_max_exp)
            dst_biased_exp = dst_exp + 2 ** (dst._exponent_bits - 1)

        # We add/remove LSBs
        if src._fraction_bits > dst._fraction_bits:
            dst_frac = src_frac >> (src._fraction_bits - dst._fraction_bits)
        else:
            dst_frac = src_frac << (dst._fraction_bits - src._fraction_bits)

        return (
            src_sign << (dst._exponent_bits + dst._fraction_bits)
            | dst_biased_exp << (dst._fraction_bits)
            | dst_frac
        )

    def serialize(self) -> bytes:
        return self._convert_format(
            src=Double, dst=self, n=int.from_bytes(struct.pack("<d", self), "little")
        ).to_bytes(self._size, "little")

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["BaseFloat", bytes]:
        if len(data) < cls._size:
            raise ValueError(f"Data is too short to contain {cls._size} bytes")

        double_bytes = cls._convert_format(
            src=cls, dst=Double, n=int.from_bytes(data[: cls._size], "little")
        ).to_bytes(Double._size, "little")

        return cls(struct.unpack("<d", double_bytes)[0]), data[cls._size :]


class Half(BaseFloat, exponent_bits=5, fraction_bits=10):
    pass


class Single(BaseFloat, exponent_bits=8, fraction_bits=23):
    pass


class Double(BaseFloat, exponent_bits=11, fraction_bits=52):
    pass


class LVBytes(bytes):
    _prefix_length = 1

    def serialize(self):
        if len(self) >= pow(256, self._prefix_length) - 1:
            raise ValueError("OctetString is too long")
        return len(self).to_bytes(self._prefix_length, "little", signed=False) + self

    @classmethod
    def deserialize(cls, data):
        if len(data) < cls._prefix_length:
            raise ValueError("Data is too short")

        num_bytes = int.from_bytes(data[: cls._prefix_length], "little")

        if len(data) < cls._prefix_length + num_bytes:
            raise ValueError("Data is too short")

        s = data[cls._prefix_length : cls._prefix_length + num_bytes]

        return cls(s), data[cls._prefix_length + num_bytes :]


class LongOctetString(LVBytes):
    _prefix_length = 2


class _List(list):
    _length = None

    def serialize(self):
        assert self._length is None or len(self) == self._length
        return b"".join([self._itemtype(i).serialize() for i in self])

    @classmethod
    def deserialize(cls, data):
        r = cls()
        while data:
            item, data = r._itemtype.deserialize(data)
            r.append(item)
        return r, data


class _LVList(_List):
    _prefix_length = 1

    def serialize(self):
        head = len(self).to_bytes(self._prefix_length, "little")
        data = super().serialize()
        return head + data

    @classmethod
    def deserialize(cls, data):
        r = cls()

        if len(data) < cls._prefix_length:
            raise ValueError("Data is too short")

        length = int.from_bytes(data[: cls._prefix_length], "little")
        data = data[cls._prefix_length :]
        for i in range(length):
            item, data = r._itemtype.deserialize(data)
            r.append(item)
        return r, data


def List(itemtype):  # noqa: N802
    class List(_List):
        _itemtype = itemtype

    return List


def LVList(itemtype, prefix_length=1):  # noqa: N802
    class LVList(_LVList):
        _itemtype = itemtype
        _prefix_length = prefix_length

    return LVList


class _FixedList(_List):
    @classmethod
    def deserialize(cls, data):
        r = cls()
        for i in range(r._length):
            item, data = r._itemtype.deserialize(data)
            r.append(item)
        return r, data


def fixed_list(length, itemtype):
    class FixedList(_FixedList):
        _length = length
        _itemtype = itemtype

    return FixedList


class CharacterString(str):
    _prefix_length = 1

    def serialize(self):
        if len(self) >= pow(256, self._prefix_length) - 1:
            raise ValueError("String is too long")
        return len(self).to_bytes(
            self._prefix_length, "little", signed=False
        ) + self.encode("utf8")

    @classmethod
    def deserialize(cls, data):
        if len(data) < cls._prefix_length:
            raise ValueError("Data is too short")

        length = int.from_bytes(data[: cls._prefix_length], "little")

        if len(data) < cls._prefix_length + length:
            raise ValueError("Data is too short")

        raw = data[cls._prefix_length : cls._prefix_length + length]
        r = cls(raw.split(b"\x00")[0].decode("utf8", errors="replace"))
        r.raw = raw
        return r, data[cls._prefix_length + length :]


class LongCharacterString(CharacterString):
    _prefix_length = 2


def LimitedCharString(max_len):  # noqa: N802
    class LimitedCharString(CharacterString):
        _max_len = max_len

        def serialize(self):
            if len(self) > self._max_len:
                raise ValueError("String is too long")
            return super().serialize()

    return LimitedCharString


def Optional(optional_item_type):
    class Optional(optional_item_type):
        optional = True

        @classmethod
        def deserialize(cls, data):
            try:
                return super().deserialize(data)
            except ValueError:
                return None, b""

    return Optional


class data8(_FixedList):
    """General data, Discrete, 8 bit."""

    _itemtype = uint8_t
    _length = 1


class data16(data8):
    """General data, Discrete, 16 bit."""

    _length = 2


class data24(data8):
    """General data, Discrete, 24 bit."""

    _length = 3


class data32(data8):
    """General data, Discrete, 32 bit."""

    _length = 4


class data40(data8):
    """General data, Discrete, 40 bit."""

    _length = 5


class data48(data8):
    """General data, Discrete, 48 bit."""

    _length = 6


class data56(data8):
    """General data, Discrete, 56 bit."""

    _length = 7


class data64(data8):
    """General data, Discrete, 64 bit."""

    _length = 8
