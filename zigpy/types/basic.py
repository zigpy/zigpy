import enum
import struct
import typing
from typing import Callable, TypeVar

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
    def deserialize(cls, data: bytes) -> typing.Tuple["LVList", bytes]:
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
    def deserialize(cls, data: bytes) -> typing.Tuple["LVList", bytes]:
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
    def deserialize(cls, data: bytes) -> typing.Tuple["FixedList", bytes]:
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
