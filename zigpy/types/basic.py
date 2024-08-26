from __future__ import annotations

import enum
import inspect
import struct
import sys
import typing

from typing_extensions import Self

CALLABLE_T = typing.TypeVar("CALLABLE_T", bound=typing.Callable)
T = typing.TypeVar("T")


class Bits(list):
    @classmethod
    def from_bitfields(cls, fields):
        instance = cls()

        # Little endian, so [11, 1000, 00] will be packed as 00_1000_11
        for field in fields[::-1]:
            instance.extend(field.bits())

        return instance

    def serialize(self) -> bytes:
        if len(self) % 8 != 0:
            raise ValueError(f"Cannot serialize {len(self)} bits into bytes: {self}")

        serialized_bytes = []

        for index in range(0, len(self), 8):
            byte = 0x00

            for bit in self[index : index + 8]:
                byte <<= 1
                byte |= bit

            serialized_bytes.append(byte)

        return bytes(serialized_bytes)

    @classmethod
    def deserialize(cls, data) -> tuple[Bits, bytes]:
        bits: list[int] = []

        for byte in data:
            bits.extend((byte >> i) & 1 for i in range(7, -1, -1))

        return cls(bits), b""


class SerializableBytes:
    """A container object for raw bytes that enforces `serialize()` will be called."""

    def __init__(self, value: bytes = b"") -> None:
        if isinstance(value, SerializableBytes):
            value = value.value
        elif not isinstance(value, (bytes, bytearray)):
            raise ValueError(f"Object is not bytes: {value!r}")  # noqa: TRY004

        self.value: bytes | bytearray = value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented

        return self.value == other.value

    def serialize(self) -> bytes:
        return self.value

    def __repr__(self) -> str:
        return f"Serialized[{self.value!r}]"

    def __hash__(self) -> int:
        return hash(self.value)


NOT_SET = object()


class FixedIntType(int):
    _signed = None
    _bits = None
    _size = None  # Only for backwards compatibility, not set for smaller ints
    _byteorder = None

    min_value: int
    max_value: int

    def __new__(cls, *args, **kwargs):
        if cls._signed is None or cls._bits is None:
            raise TypeError(f"{cls} is abstract and cannot be created")

        n = super().__new__(cls, *args, **kwargs)

        # We use `n + 0` to convert `n` into an integer without calling `int()`
        if not cls.min_value <= n + 0 <= cls.max_value:
            raise ValueError(
                f"{int(n)} is not an {'un' if not cls._signed else ''}signed"
                f" {cls._bits} bit integer"
            )

        return n

    def _hex_repr(self):
        assert self._bits % 4 == 0
        return f"0x{{:0{self._bits // 4}X}}".format(int(self))

    def _bin_repr(self):
        return f"0b{{:0{self._bits}b}}".format(int(self))

    def __init_subclass__(
        cls, signed=NOT_SET, bits=NOT_SET, repr=NOT_SET, byteorder=NOT_SET
    ) -> None:
        super().__init_subclass__()

        if signed is not NOT_SET:
            cls._signed = signed

        if bits is not NOT_SET:
            cls._bits = bits

            if bits % 8 == 0:
                cls._size = bits // 8
            else:
                cls._size = None

        if cls._bits is not None and cls._signed is not None:
            if cls._signed:
                cls.min_value = -(2 ** (cls._bits - 1))
                cls.max_value = 2 ** (cls._bits - 1) - 1
            else:
                cls.min_value = 0
                cls.max_value = 2**cls._bits - 1

        if repr == "hex":
            assert cls._bits % 4 == 0
            cls.__str__ = cls.__repr__ = cls._hex_repr
        elif repr == "bin":
            cls.__str__ = cls.__repr__ = cls._bin_repr
        elif not repr:
            cls.__str__ = super().__str__
            cls.__repr__ = super().__repr__
        elif repr is not NOT_SET:
            raise ValueError(f"Invalid repr value {repr!r}. Must be either hex or bin")

        if byteorder is not NOT_SET:
            cls._byteorder = byteorder
        elif cls._byteorder is None:
            cls._byteorder = "little"

        if sys.version_info < (3, 10):
            # XXX: The enum module uses the first class with __new__ in its __dict__
            #      as the member type. We have to ensure this is true for
            #      every subclass.
            # Fixed with https://github.com/python/cpython/pull/26658
            if "__new__" not in cls.__dict__:
                cls.__new__ = cls.__new__

        # XXX: The enum module sabotages pickling using the same logic.
        if "__reduce_ex__" not in cls.__dict__:
            cls.__reduce_ex__ = cls.__reduce_ex__

    def bits(self) -> Bits:
        return Bits([(self >> n) & 0b1 for n in range(self._bits - 1, -1, -1)])

    @classmethod
    def from_bits(cls, bits: Bits) -> tuple[FixedIntType, Bits]:
        if len(bits) < cls._bits:
            raise ValueError(f"Not enough bits to decode {cls}: {bits}")

        n = 0

        for bit in bits[-cls._bits :]:
            n <<= 1
            n |= bit & 1

        if cls._signed and n >= 2 ** (cls._bits - 1):
            n -= 2**cls._bits

        return cls(n), bits[: -cls._bits]

    def serialize(self) -> bytes:
        if self._bits % 8 != 0:
            raise TypeError(f"Integer type with {self._bits} bits is not byte aligned")

        return self.to_bytes(self._bits // 8, self._byteorder, signed=self._signed)

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[FixedIntType, bytes]:
        if cls._bits % 8 != 0:
            raise TypeError(f"Integer type with {cls._bits} bits is not byte aligned")

        byte_size = cls._bits // 8

        if len(data) < byte_size:
            raise ValueError(f"Data is too short to contain {byte_size} bytes")

        r = cls.from_bytes(data[:byte_size], cls._byteorder, signed=cls._signed)
        data = data[byte_size:]
        return r, data


class uint_t(FixedIntType, signed=False):
    pass


class int_t(FixedIntType, signed=True):
    pass


class int8s(int_t, bits=8):
    pass


class int16s(int_t, bits=16):
    pass


class int24s(int_t, bits=24):
    pass


class int32s(int_t, bits=32):
    pass


class int40s(int_t, bits=40):
    pass


class int48s(int_t, bits=48):
    pass


class int56s(int_t, bits=56):
    pass


class int64s(int_t, bits=64):
    pass


class uint1_t(uint_t, bits=1):
    pass


class uint2_t(uint_t, bits=2):
    pass


class uint3_t(uint_t, bits=3):
    pass


class uint4_t(uint_t, bits=4):
    pass


class uint5_t(uint_t, bits=5):
    pass


class uint6_t(uint_t, bits=6):
    pass


class uint7_t(uint_t, bits=7):
    pass


class uint8_t(uint_t, bits=8):
    pass


class uint16_t(uint_t, bits=16):
    pass


class uint24_t(uint_t, bits=24):
    pass


class uint32_t(uint_t, bits=32):
    pass


class uint40_t(uint_t, bits=40):
    pass


class uint48_t(uint_t, bits=48):
    pass


class uint56_t(uint_t, bits=56):
    pass


class uint64_t(uint_t, bits=64):
    pass


class uint_t_be(FixedIntType, signed=False, byteorder="big"):
    pass


class int_t_be(FixedIntType, signed=True, byteorder="big"):
    pass


class int16s_be(int_t_be, bits=16):
    pass


class int24s_be(int_t_be, bits=24):
    pass


class int32s_be(int_t_be, bits=32):
    pass


class int40s_be(int_t_be, bits=40):
    pass


class int48s_be(int_t_be, bits=48):
    pass


class int56s_be(int_t_be, bits=56):
    pass


class int64s_be(int_t_be, bits=64):
    pass


class uint16_t_be(uint_t_be, bits=16):
    pass


class uint24_t_be(uint_t_be, bits=24):
    pass


class uint32_t_be(uint_t_be, bits=32):
    pass


class uint40_t_be(uint_t_be, bits=40):
    pass


class uint48_t_be(uint_t_be, bits=48):
    pass


class uint56_t_be(uint_t_be, bits=56):
    pass


class uint64_t_be(uint_t_be, bits=64):
    pass


class AlwaysCreateEnumType(enum.EnumMeta):
    """Enum metaclass that skips the functional creation API."""

    def __call__(self, value, names=None, *values) -> type[enum.Enum]:  # type: ignore[override]  # noqa: N804
        """Custom implementation of Enum.__new__.

        From https://github.com/python/cpython/blob/v3.11.5/Lib/enum.py#L1091-L1140
        """
        # all enum instances are actually created during class construction
        # without calling this method; this method is called by the metaclass'
        # __call__ (i.e. Color(3) ), and by pickle
        if type(value) is self:
            # For lookups like Color(Color.RED)
            return value
        # by-value search for a matching enum member
        # see if it's in the reverse mapping (for hashable values)
        try:
            return self._value2member_map_[value]
        except KeyError:
            # Not found, no need to do long O(n) search
            pass
        except TypeError:
            # not there, now do long search -- O(n) behavior
            for member in self._member_map_.values():
                if member._value_ == value:
                    return member
        # still not found -- try _missing_ hook
        try:
            exc = None
            result = self._missing_(value)
        except Exception as e:  # noqa: BLE001
            exc = e
            result = None
        try:
            if isinstance(result, self) or (
                enum.Flag is not None
                and issubclass(self, enum.Flag)
                and self._boundary_ is enum.EJECT
                and isinstance(result, int)
            ):
                return result
            else:
                ve_exc = ValueError(f"{value!r} is not a valid {self.__qualname__}")
                if result is None and exc is None:
                    raise ve_exc
                elif exc is None:
                    exc = TypeError(
                        f"error in {self.__name__}._missing_: returned {result!r} instead of None or a valid member"
                    )
                if not isinstance(exc, ValueError):
                    exc.__context__ = ve_exc
                raise exc
        finally:
            # ensure all variables that could hold an exception are destroyed
            exc = None
            ve_exc = None


class _IntEnumMeta(AlwaysCreateEnumType):
    def __call__(self, value, names=None, *args, **kwargs):  # noqa: N804
        if isinstance(value, str):
            if value.startswith("0x"):
                value = int(value, base=16)
            elif value.isnumeric():
                value = int(value)
            elif value.startswith(self.__name__ + "."):
                value = self[value[len(self.__name__) + 1 :]].value
            else:
                value = self[value].value
        return super().__call__(value, names, *args, **kwargs)


def bitmap_factory(int_type: CALLABLE_T) -> CALLABLE_T:
    """Mixins are broken by Python 3.8.6 so we must dynamically create the enum with the
    appropriate methods but with only one non-Enum parent class.
    """

    if sys.version_info >= (3, 11):

        class _NewEnum(
            int_type,
            enum.ReprEnum,
            enum.Flag,
            boundary=enum.KEEP,
            metaclass=AlwaysCreateEnumType,
        ):
            pass

    else:

        class _NewEnum(int_type, enum.Flag):
            # Rebind classmethods to our own class
            _missing_ = classmethod(enum.IntFlag._missing_.__func__)
            _create_pseudo_member_ = classmethod(  # type: ignore[var-annotated]
                enum.IntFlag._create_pseudo_member_.__func__
            )

            __or__ = enum.IntFlag.__or__
            __and__ = enum.IntFlag.__and__
            __xor__ = enum.IntFlag.__xor__
            __ror__ = enum.IntFlag.__ror__
            __rand__ = enum.IntFlag.__rand__
            __rxor__ = enum.IntFlag.__rxor__
            __invert__ = enum.IntFlag.__invert__

    return _NewEnum


def enum_factory(int_type: CALLABLE_T, undefined: str = "undefined") -> CALLABLE_T:
    """Enum factory."""

    class _NewEnum(int_type, enum.Enum, metaclass=_IntEnumMeta):
        @classmethod
        def _missing_(cls, value):
            new = cls._member_type_.__new__(cls, value)

            if cls._bits % 8 == 0:
                name = f"{undefined}_{new._hex_repr().lower()}"
            else:
                name = f"{undefined}_{new._bin_repr()}"

            new._name_ = name.format(value)
            new._value_ = value
            return new

        def __format__(self, format_spec: str) -> str:
            if format_spec:
                # Allow formatting the integer enum value
                return self._member_type_.__format__(self, format_spec)
            else:
                # Otherwise, format it as its string representation
                return object.__format__(repr(self), format_spec)

    return _NewEnum


class enum1(enum_factory(uint1_t)):  # noqa: N801
    pass


class enum2(enum_factory(uint2_t)):  # noqa: N801
    pass


class enum3(enum_factory(uint3_t)):  # noqa: N801
    pass


class enum4(enum_factory(uint4_t)):  # noqa: N801
    pass


class enum5(enum_factory(uint5_t)):  # noqa: N801
    pass


class enum6(enum_factory(uint6_t)):  # noqa: N801
    pass


class enum7(enum_factory(uint7_t)):  # noqa: N801
    pass


class enum8(enum_factory(uint8_t)):  # noqa: N801
    pass


class enum16(enum_factory(uint16_t)):  # noqa: N801
    pass


class enum32(enum_factory(uint32_t)):  # noqa: N801
    pass


class enum16_be(enum_factory(uint16_t_be)):  # noqa: N801
    pass


class enum32_be(enum_factory(uint32_t_be)):  # noqa: N801
    pass


class bitmap2(bitmap_factory(uint2_t)):
    pass


class bitmap3(bitmap_factory(uint3_t)):
    pass


class bitmap4(bitmap_factory(uint4_t)):
    pass


class bitmap5(bitmap_factory(uint5_t)):
    pass


class bitmap6(bitmap_factory(uint6_t)):
    pass


class bitmap7(bitmap_factory(uint7_t)):
    pass


class bitmap8(bitmap_factory(uint8_t)):
    pass


class bitmap16(bitmap_factory(uint16_t)):
    pass


class bitmap24(bitmap_factory(uint24_t)):
    pass


class bitmap32(bitmap_factory(uint32_t)):
    pass


class bitmap40(bitmap_factory(uint40_t)):
    pass


class bitmap48(bitmap_factory(uint48_t)):
    pass


class bitmap56(bitmap_factory(uint56_t)):
    pass


class bitmap64(bitmap_factory(uint64_t)):
    pass


class bitmap16_be(bitmap_factory(uint16_t_be)):
    pass


class bitmap24_be(bitmap_factory(uint24_t_be)):
    pass


class bitmap32_be(bitmap_factory(uint32_t_be)):
    pass


class bitmap40_be(bitmap_factory(uint40_t_be)):
    pass


class bitmap48_be(bitmap_factory(uint48_t_be)):
    pass


class bitmap56_be(bitmap_factory(uint56_t_be)):
    pass


class bitmap64_be(bitmap_factory(uint64_t_be)):
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
    def _convert_format(*, src: BaseFloat, dst: BaseFloat, n: int) -> int:
        """Converts an integer representing a float from one format into another. Note:

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
            dst_biased_exp = 2**dst._exponent_bits - 1
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
    def deserialize(cls, data: bytes) -> tuple[BaseFloat, bytes]:
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


def LimitedLVBytes(max_len):  # noqa: N802
    class LimitedLVBytes(LVBytes):
        _max_len = max_len

        def serialize(self):
            if len(self) > self._max_len:
                raise ValueError(f"LVBytes is too long (>{self._max_len})")
            return super().serialize()

    return LimitedLVBytes


class LVBytesSize2(LVBytes):
    def serialize(self):
        if len(self) != 2:
            raise ValueError("LVBytes must be of size 2")
        return super().serialize()

    @classmethod
    def deserialize(cls, data):
        d, r = super().deserialize(data)

        if len(d) != 2:
            raise ValueError("LVBytes must be of size 2")
        return d, r


class LongOctetString(LVBytes):
    _prefix_length = 2


class KwargTypeMeta(type):
    # So things like `LVList[NWK, t.uint8_t]` are singletons
    _anonymous_classes = {}  # type:ignore[var-annotated]

    def __new__(cls, name, bases, namespaces, **kwargs):
        cls_kwarg_attrs = namespaces.get("_getitem_kwargs", {})

        def __init_subclass__(cls, **kwargs):
            filtered_kwargs = kwargs.copy()

            for key in kwargs:
                if key in cls_kwarg_attrs:
                    setattr(cls, f"_{key}", filtered_kwargs.pop(key))

            super().__init_subclass__(**filtered_kwargs)

        if "__init_subclass__" not in namespaces:
            namespaces["__init_subclass__"] = __init_subclass__

        return type.__new__(cls, name, bases, namespaces, **kwargs)

    def __getitem__(cls, key):
        # Make sure Foo[a] is the same as Foo[a,]
        if not isinstance(key, tuple):
            key = (key,)

        signature = inspect.Signature(
            parameters=[
                inspect.Parameter(
                    name=k,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=v if v is not None else inspect.Parameter.empty,
                )
                for k, v in cls._getitem_kwargs.items()
            ]
        )

        bound = signature.bind(*key)
        bound.apply_defaults()

        # Default types need to work, which is why we need to create the key down here
        expanded_key = tuple(bound.arguments.values())

        if (cls, expanded_key) in cls._anonymous_classes:
            return cls._anonymous_classes[cls, expanded_key]

        class AnonSubclass(cls, **bound.arguments):
            pass

        AnonSubclass.__name__ = AnonSubclass.__qualname__ = f"Anonymous{cls.__name__}"
        cls._anonymous_classes[cls, expanded_key] = AnonSubclass

        return AnonSubclass

    def __subclasscheck__(cls, subclass):
        if type(subclass) is not KwargTypeMeta:
            return False

        # Named subclasses are handled normally
        if not cls.__name__.startswith("Anonymous"):
            return super().__subclasscheck__(subclass)

        # Anonymous subclasses must be identical
        if subclass.__name__.startswith("Anonymous"):
            return cls is subclass

        # A named class is a "subclass" of an anonymous subclass only if its ancestors
        # are all the same
        if subclass.__mro__[-len(cls.__mro__) + 1 :] != cls.__mro__[1:]:
            return False

        # They must also have the same class kwargs
        for key in cls._getitem_kwargs:
            key = f"_{key}"

            if getattr(cls, key) != getattr(subclass, key):
                return False

        return True

    def __instancecheck__(cls, subclass):
        # We rely on __subclasscheck__ to do the work
        if issubclass(type(subclass), cls):
            return True

        return super().__instancecheck__(subclass)


class List(list, metaclass=KwargTypeMeta):
    _item_type = None
    _getitem_kwargs = {"item_type": None}

    def serialize(self) -> bytes:
        assert self._item_type is not None
        return b"".join([self._item_type(i).serialize() for i in self])

    @classmethod
    def deserialize(cls: type[T], data: bytes) -> tuple[T, bytes]:
        assert cls._item_type is not None

        lst = cls()
        while data:
            item, data = cls._item_type.deserialize(data)
            lst.append(item)

        return lst, data


class LVList(list, metaclass=KwargTypeMeta):
    _item_type = None
    _length_type = uint8_t

    _getitem_kwargs = {"item_type": None, "length_type": uint8_t}

    def serialize(self) -> bytes:
        assert self._item_type is not None
        return self._length_type(len(self)).serialize() + b"".join(
            [self._item_type(i).serialize() for i in self]
        )

    @classmethod
    def deserialize(cls: type[T], data: bytes) -> tuple[T, bytes]:
        assert cls._item_type is not None
        length, data = cls._length_type.deserialize(data)
        r = cls()
        for _i in range(length):
            item, data = cls._item_type.deserialize(data)
            r.append(item)
        return r, data


class FixedList(list, metaclass=KwargTypeMeta):
    _item_type = None
    _length = None

    _getitem_kwargs = {"item_type": None, "length": None}

    def serialize(self) -> bytes:
        assert self._length is not None

        if len(self) != self._length:
            raise ValueError(
                f"Invalid length for {self!r}: expected {self._length}, got {len(self)}"
            )

        return b"".join([self._item_type(i).serialize() for i in self])

    @classmethod
    def deserialize(cls: type[T], data: bytes) -> tuple[T, bytes]:
        assert cls._item_type is not None
        r = cls()
        for _i in range(cls._length):
            item, data = cls._item_type.deserialize(data)
            r.append(item)
        return r, data


class CharacterString(str):
    __slots__ = ("invalid", "raw")

    _prefix_length = 1
    _invalid_length = (1 << (8 * _prefix_length)) - 1

    def __new__(cls, value: str = "", *, invalid: bool = False) -> Self:
        instance = super().__new__(cls, value)
        instance.invalid = invalid
        instance.raw = value

        return instance

    def serialize(self) -> bytes:
        if len(self) >= pow(256, self._prefix_length) - 1:
            raise ValueError("String is too long")

        if self.invalid:
            return self._invalid_length.to_bytes(self._prefix_length, "little")

        return len(self).to_bytes(
            self._prefix_length, "little", signed=False
        ) + self.encode("utf8")

    @classmethod
    def deserialize(cls: type[T], data: bytes) -> tuple[T, bytes]:
        if len(data) < cls._prefix_length:
            raise ValueError("Data is too short")

        length = int.from_bytes(data[: cls._prefix_length], "little")

        if length == cls._invalid_length:
            return cls("", invalid=True), data[cls._prefix_length :]  # type:ignore[call-arg]

        if len(data) < cls._prefix_length + length:
            raise ValueError("Data is too short")

        raw = data[cls._prefix_length : cls._prefix_length + length]
        text = raw.split(b"\x00")[0].decode("utf8", errors="replace")

        # FIXME: figure out how to get this working: `T` is not behaving as expected in
        # the classmethod when it is not bound.
        r = cls(text)  # type:ignore[call-arg]
        r.raw = raw
        return r, data[cls._prefix_length + length :]


class LongCharacterString(CharacterString):
    _prefix_length = 2


def LimitedCharString(max_len):  # noqa: N802
    class LimitedCharString(CharacterString):
        _max_len = max_len

        def serialize(self) -> bytes:
            if len(self) > self._max_len:
                raise ValueError(f"String is too long (>{self._max_len})")
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


class data16(FixedList, item_type=uint8_t, length=2):
    """General data, Discrete, 16 bit."""


class data24(FixedList, item_type=uint8_t, length=3):
    """General data, Discrete, 24 bit."""


class data32(FixedList, item_type=uint8_t, length=4):
    """General data, Discrete, 32 bit."""


class data40(FixedList, item_type=uint8_t, length=5):
    """General data, Discrete, 40 bit."""


class data48(FixedList, item_type=uint8_t, length=6):
    """General data, Discrete, 48 bit."""


class data56(FixedList, item_type=uint8_t, length=7):
    """General data, Discrete, 56 bit."""


class data64(FixedList, item_type=uint8_t, length=8):
    """General data, Discrete, 64 bit."""
