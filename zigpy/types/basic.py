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


class ListMeta(type):
    # So things like `LVList[NWK, t.uint8_t]` are singletons
    _anonymous_classes = {}

    def __new__(metaclass, name, bases, namespaces, **kwargs):
        return type.__new__(metaclass, name, bases, namespaces, **kwargs)

    def __subclasscheck__(self, subclass):
        # Only check with `t.LVList[]`, others don't make sense
        if self.__mro__[1] is LVList and issubclass(subclass, LVList):
            return issubclass(subclass._item_type, self._item_type) and issubclass(
                subclass._length_type, self._length_type
            )
        elif self.__mro__[1] is List and issubclass(subclass, List):
            return issubclass(subclass._item_type, self._item_type)
        elif self.__mro__[1] is FixedList and issubclass(subclass, FixedList):
            return (
                issubclass(subclass._item_type, self._item_type)
                and subclass._length == self._length
            )

        return super().__subclasscheck__(subclass)

    def __instancecheck__(self, subclass):
        if issubclass(type(subclass), self):
            return True

        return super().__instancecheck__(subclass)


class List(list, metaclass=ListMeta):
    _item_type = None

    def __init_subclass__(cls, *, item_type=None) -> None:
        super().__init_subclass__()

        if item_type is not None:
            cls._item_type = item_type

    def __class_getitem__(cls, key):
        if (cls, key) in cls._anonymous_classes:
            return cls._anonymous_classes[cls, key]

        item_type = key

        class AnonymousList(List, item_type=item_type):
            pass

        cls._anonymous_classes[cls, key] = AnonymousList

        return AnonymousList

    def serialize(self) -> bytes:
        assert self._item_type is not None
        return b"".join([self._item_type(i).serialize() for i in self])

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["LVList", bytes]:
        assert cls._item_type is not None

        lst = cls()

        while data:
            item, data = cls._item_type.deserialize(data)
            lst.append(item)

        return lst, data


class LVList(list, metaclass=ListMeta):
    _length_type = None
    _item_type = None

    def __init_subclass__(cls, *, length_type=None, item_type=None) -> None:
        super().__init_subclass__()

        if length_type is not None:
            cls._length_type = length_type

        if item_type is not None:
            cls._item_type = item_type

    def __class_getitem__(cls, key):
        if (cls, key) in cls._anonymous_classes:
            return cls._anonymous_classes[cls, key]

        length_type, item_type = key

        class AnonymousLVList(cls, length_type=length_type, item_type=item_type):
            pass

        cls._anonymous_classes[cls, key] = AnonymousLVList

        return AnonymousLVList

    def serialize(self) -> bytes:
        assert self._item_type is not None
        return b"".join(
            [
                i.serialize()
                for i in [self._length_type(len(self))]
                + [self._item_type(i) for i in self]
            ]
        )

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["LVList", bytes]:
        assert cls._item_type is not None
        length, data = cls._length_type.deserialize(data)
        r = cls()
        for i in range(length):
            item, data = cls._item_type.deserialize(data)
            r.append(item)
        return r, data


class FixedList(list, metaclass=ListMeta):
    _length = None
    _item_type = None

    def __init_subclass__(cls, *, length=None, item_type=None) -> None:
        super().__init_subclass__()

        if length is not None:
            cls._length = length

        if item_type is not None:
            cls._item_type = item_type

    def __class_getitem__(cls, key):
        if (cls, key) in cls._anonymous_classes:
            return cls._anonymous_classes[cls, key]

        length, item_type = key

        class AnonymousFixedList(cls, length=length, item_type=item_type):
            pass

        cls._anonymous_classes[cls, key] = AnonymousFixedList

        return AnonymousFixedList

    def serialize(self) -> bytes:
        assert self._length is not None

        if len(self) != self._length:
            raise ValueError(
                f"Invalid length for {self!r}: expected {self._length}, got {len(self)}"
            )

        return b"".join([self._item_type(i).serialize() for i in self])

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["FixedList", bytes]:
        assert cls._item_type is not None
        r = cls()
        for i in range(cls._length):
            item, data = cls._item_type.deserialize(data)
            r.append(item)
        return r, data


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


class data8(FixedList, item_type=uint8_t, length=1):
    """General data, Discrete, 8 bit."""

    pass


class data16(FixedList, item_type=uint8_t, length=2):
    """General data, Discrete, 16 bit."""

    pass


class data24(FixedList, item_type=uint8_t, length=3):
    """General data, Discrete, 24 bit."""

    pass


class data32(FixedList, item_type=uint8_t, length=4):
    """General data, Discrete, 32 bit."""

    pass


class data40(FixedList, item_type=uint8_t, length=5):
    """General data, Discrete, 40 bit."""

    pass


class data48(FixedList, item_type=uint8_t, length=6):
    """General data, Discrete, 48 bit."""

    pass


class data56(FixedList, item_type=uint8_t, length=7):
    """General data, Discrete, 56 bit."""

    pass


class data64(FixedList, item_type=uint8_t, length=8):
    """General data, Discrete, 64 bit."""

    pass
