import enum
import struct
from typing import Callable, Tuple, TypeVar

CALLABLE_T = TypeVar("CALLABLE_T", bound=Callable)  # pylint: disable=invalid-name


class FixedIntType(int):
    _signed = None
    _size = None

    def __new__(cls, *args, **kwargs):
        if cls._signed is None or cls._size is None:
            raise TypeError(f"{cls} is abstract and cannot be created")

        instance = super().__new__(cls, *args, **kwargs)
        instance.serialize()

        return instance

    def __init_subclass__(cls, signed=None, size=None, hex_repr=None) -> None:
        super().__init_subclass__()

        if signed is not None:
            cls._signed = signed

        if size is not None:
            cls._size = size

        if hex_repr:
            fmt = f"0x{{:0{cls._size * 2}X}}"
            cls.__str__ = cls.__repr__ = lambda self: fmt.format(self)
        elif hex_repr is not None and not hex_repr:
            cls.__str__ = super().__str__
            cls.__repr__ = super().__repr__

        # XXX: The enum module uses the first class with __new__ in its __dict__ as the
        #      member type. We have to ensure this is true for every subclass.
        if "__new__" not in cls.__dict__:
            cls.__new__ = cls.__new__

    def serialize(self) -> bytes:
        try:
            return self.to_bytes(self._size, "little", signed=self._signed)
        except OverflowError as e:
            # OverflowError is not a subclass of ValueError, making it annoying to catch
            raise ValueError(str(e)) from e

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["FixedIntType", bytes]:
        if len(data) < cls._size:
            raise ValueError(f"Data is too short to contain {cls._size} bytes")

        r = cls.from_bytes(data[: cls._size], "little", signed=cls._signed)
        data = data[cls._size :]
        return r, data


class uint_t(FixedIntType, signed=False):
    pass


class int_t(FixedIntType, signed=True):
    pass


class int8s(int_t, size=1):
    pass


class int16s(int_t, size=2):
    pass


class int24s(int_t, size=3):
    pass


class int32s(int_t, size=4):
    pass


class int40s(int_t, size=5):
    pass


class int48s(int_t, size=6):
    pass


class int56s(int_t, size=7):
    pass


class int64s(int_t, size=8):
    pass


class uint8_t(uint_t, size=1):
    pass


class uint16_t(uint_t, size=2):
    pass


class uint24_t(uint_t, size=3):
    pass


class uint32_t(uint_t, size=4):
    pass


class uint40_t(uint_t, size=5):
    pass


class uint48_t(uint_t, size=6):
    pass


class uint56_t(uint_t, size=7):
    pass


class uint64_t(uint_t, size=8):
    pass


class EnumIntFlagMixin:
    """
    Enum does not allow multiple base classes. We turn enum.IntFlag into a mixin because
    it doesn't actualy depend on the base class specifically being `int`.
    """

    # Rebind classmethods to our own class
    _missing_ = classmethod(enum.IntFlag._missing_.__func__)
    _create_pseudo_member_ = classmethod(enum.IntFlag._create_pseudo_member_.__func__)

    __or__ = enum.IntFlag.__or__
    __and__ = enum.IntFlag.__and__
    __xor__ = enum.IntFlag.__xor__
    __ror__ = enum.IntFlag.__ror__
    __rand__ = enum.IntFlag.__rand__
    __rxor__ = enum.IntFlag.__rxor__
    __invert__ = enum.IntFlag.__invert__


class _IntEnumMeta(enum.EnumMeta):
    def __call__(cls, value, names=None, *args, **kwargs):
        if isinstance(value, str) and value.startswith("0x"):
            value = int(value, base=16)
        else:
            value = int(value)
        return super().__call__(value, names, *args, **kwargs)


def enum_factory(int_type: CALLABLE_T, undefined: str = "undefined") -> CALLABLE_T:
    """Enum factory."""

    class _NewEnum(int_type, enum.Enum, metaclass=_IntEnumMeta):
        @classmethod
        def _missing_(cls, value):
            new = cls._member_type_.__new__(cls, value)
            name = f"{undefined}_0x{{:0{cls._size * 2}x}}"  # pylint: disable=protected-access
            new._name_ = name.format(value)
            new._value_ = value
            return new

    return _NewEnum


class enum8(enum_factory(uint8_t)):  # noqa: N801
    pass


class enum16(enum_factory(uint16_t)):  # noqa: N801
    pass


class bitmap8(EnumIntFlagMixin, uint8_t, enum.Flag):
    pass


class bitmap16(EnumIntFlagMixin, uint16_t, enum.Flag):
    pass


class bitmap24(EnumIntFlagMixin, uint24_t, enum.Flag):
    pass


class bitmap32(EnumIntFlagMixin, uint32_t, enum.Flag):
    pass


class bitmap40(EnumIntFlagMixin, uint40_t, enum.Flag):
    pass


class bitmap48(EnumIntFlagMixin, uint48_t, enum.Flag):
    pass


class bitmap56(EnumIntFlagMixin, uint56_t, enum.Flag):
    pass


class bitmap64(EnumIntFlagMixin, uint64_t, enum.Flag):
    pass


class Single(float):
    _fmt = "<f"

    def serialize(self):
        return struct.pack(self._fmt, self)

    @classmethod
    def deserialize(cls, data):
        size = struct.calcsize(cls._fmt)
        if len(data) < size:
            raise ValueError("Data is too short to contain %s float" % cls.__name__)

        return struct.unpack(cls._fmt, data[0:size])[0], data[size:]


class Double(Single):
    _fmt = "<d"


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
