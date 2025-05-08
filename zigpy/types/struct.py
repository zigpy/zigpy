from __future__ import annotations

import dataclasses
import inspect
import typing

from typing_extensions import Self

import zigpy.types as t

NoneType = type(None)


# To make sure mypy is aware that `IntStruct` is technically a mixin, we need to
# convince it that it really is an integer at runtime
if typing.TYPE_CHECKING:
    IntMixin = int
else:
    IntMixin = object


class ListSubclass(list):
    # So we can call `setattr()` on it
    pass


class EmptyObject:
    # So we can call `setattr()` on it
    pass


@dataclasses.dataclass(frozen=True)
class StructField:
    name: str | None = None
    type: type = None

    requires: typing.Callable[[Struct], bool] | None = dataclasses.field(
        default=None, repr=False
    )
    optional: bool | None = False

    repr: typing.Callable[[typing.Any], str] | None = dataclasses.field(
        default=repr, repr=False
    )

    def replace(self, **kwargs) -> StructField:
        return dataclasses.replace(self, **kwargs)

    def _convert_type(self, value):
        if value is None or isinstance(value, self.type):
            return value

        try:
            return self.type(value)
        except Exception as e:  # noqa: BLE001
            raise ValueError(
                f"Failed to convert {self.name}={value!r} from type"
                f" {type(value)} to {self.type}"
            ) from e


class Struct:
    @classmethod
    def _real_cls(cls) -> type:
        # The "Optional" subclass is dynamically created and breaks types.
        # We have to use a little introspection to find our real class.
        return next(c for c in cls.__mro__ if c.__name__ != "Optional")

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        # We generate fields up here to fail early and cache it
        cls.fields = cls._real_cls()._get_fields()
        cls._signature = inspect.Signature(
            parameters=[
                inspect.Parameter(
                    name=f.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=None,
                    annotation=f.type,
                )
                for f in cls.fields
            ]
        )

        # Check to see if the Struct is also an integer
        if next(
            (
                c
                for c in cls.__mro__[1:]
                if issubclass(c, t.FixedIntType) and not issubclass(c, Struct)
            ),
            None,
        ) is not None and not issubclass(cls, IntStruct):
            raise TypeError("Integer structs must be subclasses of `IntStruct`")

        cls._hash = -1
        cls._frozen = False

    def __new__(cls: type[Self], *args, **kwargs) -> Self:
        cls = cls._real_cls()  # noqa: PLW0642

        if len(args) == 1 and isinstance(args[0], cls):
            # Like a copy constructor
            if kwargs:
                raise ValueError(f"Cannot use copy constructor with kwargs: {kwargs!r}")

            kwargs = args[0].as_dict()
            args = ()

        # Pretend our signature is `__new__(cls, p1: t1, p2: t2, ...)`
        bound = cls._signature.bind(*args, **kwargs)
        bound.apply_defaults()

        instance = super().__new__(cls)

        # Set each attributes on the instance
        for name, value in bound.arguments.items():
            field = getattr(cls.fields, name)
            setattr(instance, name, field._convert_type(value))

        return instance

    @classmethod
    def _get_fields(cls) -> list[StructField]:
        fields = ListSubclass()

        # We need both to throw type errors in case a field is not annotated
        annotations = typing.get_type_hints(cls._real_cls())

        # Make sure every `StructField` is annotated
        for name in vars(cls._real_cls()):
            value = getattr(cls, name)

            if isinstance(value, StructField) and name not in annotations:
                raise TypeError(
                    f"Field {name!r}={value} must have some annotation."
                    f" Use `None` if it is specified in the `StructField`."
                )

        # XXX: Python doesn't provide a simple way to get all defined attributes *and*
        #      order them with respect to annotation-only fields.
        #      Every struct field must be annotated.
        for name, annotation in annotations.items():
            field = getattr(cls, name, StructField())

            if not isinstance(field, StructField):
                continue

            field = field.replace(name=name)

            # An annotation of `None` means to use the field's type
            if annotation is not NoneType:
                if field.type is not None and field.type != annotation:
                    raise TypeError(
                        f"Field {name!r} type annotation conflicts with provided type:"
                        f" {annotation} != {field.type}"
                    )

                field = field.replace(type=annotation)
            elif field.type is None:
                raise TypeError(f"Field {name!r} has no type")

            fields.append(field)
            setattr(fields, field.name, field)

        return fields

    def assigned_fields(self, *, strict=False) -> list[tuple[StructField, typing.Any]]:
        assigned_fields = ListSubclass()

        for field in self.fields:
            value = getattr(self, field.name)

            # Ignore fields that aren't required
            if field.requires is not None and not field.requires(self):
                continue

            # Missing fields cause an error if strict
            if value is None and not field.optional:
                if strict:
                    raise ValueError(
                        f"Value for field {field.name!r} is required: {self!r}"
                    )
                else:
                    # Python bug, the following `continue` is never covered
                    continue  # pragma: no cover

            assigned_fields.append((field, value))
            setattr(assigned_fields, field.name, (field, value))

        return assigned_fields

    @classmethod
    def from_dict(cls: type[Self], obj: dict[str, typing.Any]) -> Self:
        instance = cls()

        for key, value in obj.items():
            field = getattr(cls.fields, key)

            if issubclass(field.type, Struct):
                setattr(instance, field.name, field.type.from_dict(value))
            else:
                setattr(instance, field.name, value)

        return instance

    def as_dict(
        self, *, skip_missing: bool = False, recursive: bool = False
    ) -> dict[str, typing.Any]:
        d = {}

        for f in self.fields:
            value = getattr(self, f.name)

            if value is None and skip_missing:
                continue
            elif recursive and isinstance(value, Struct):
                d[f.name] = value.as_dict(
                    skip_missing=skip_missing, recursive=recursive
                )
            else:
                d[f.name] = value

        return d

    def as_tuple(self, *, skip_missing: bool = False) -> tuple:
        return tuple(self.as_dict(skip_missing=skip_missing).values())

    def serialize(self) -> bytes:
        chunks = []

        bit_offset = 0
        bitfields = []

        for field, value in self.assigned_fields(strict=True):
            if value is None and field.optional:
                continue

            value = field._convert_type(value)

            # All integral types are compacted into one chunk, unless they start and end
            # on a byte boundary.
            if issubclass(field.type, t.FixedIntType) and not (
                value._bits % 8 == 0 and bit_offset % 8 == 0
            ):
                bit_offset += value._bits
                bitfields.append(value)

                # Serialize the current segment of bitfields once we reach a boundary
                if bit_offset % 8 == 0:
                    chunks.append(t.Bits.from_bitfields(bitfields).serialize())
                    bitfields = []

                continue
            elif bitfields:
                raise ValueError(
                    f"Segment of bitfields did not terminate on a byte boundary: "
                    f" {bitfields}"
                )

            chunks.append(value.serialize())

        if bitfields:
            raise ValueError(
                f"Trailing segment of bitfields did not terminate on a byte boundary: "
                f" {bitfields}"
            )

        return b"".join(chunks)

    @staticmethod
    def _deserialize_internal(
        fields: list[StructField], data: bytes
    ) -> tuple[dict[str, typing.Any], bytes]:
        bit_length = 0
        bitfields = []
        result = {}

        # We need to create a temporary instance to call the field's `requires` method,
        # which expects a struct-like object
        temp_instance = EmptyObject()

        for field in fields:
            setattr(temp_instance, field.name, None)

        for field in fields:
            if (field.requires is not None and not field.requires(temp_instance)) or (
                not data and field.optional
            ):
                continue

            if issubclass(field.type, t.FixedIntType) and not (
                field.type._bits % 8 == 0 and bit_length % 8 == 0
            ):
                bit_length += field.type._bits
                bitfields.append(field)

                if bit_length % 8 == 0:
                    if len(data) < bit_length // 8:
                        raise ValueError(f"Data is too short to contain {bitfields}")

                    bits, _ = t.Bits.deserialize(data[: bit_length // 8])
                    data = data[bit_length // 8 :]

                    for f in bitfields:
                        value, bits = f.type.from_bits(bits)
                        result[f.name] = value
                        setattr(temp_instance, f.name, value)

                    assert not bits

                    bit_length = 0
                    bitfields = []

                continue
            elif bitfields:
                raise ValueError(
                    f"Segment of bitfields did not terminate on a byte boundary: "
                    f" {bitfields}"
                )

            value, data = field.type.deserialize(data)
            result[field.name] = value
            setattr(temp_instance, field.name, value)

        if bitfields:
            raise ValueError(
                f"Trailing segment of bitfields did not terminate on a byte boundary: "
                f" {bitfields}"
            )

        return result, data

    @classmethod
    def deserialize(cls: type[Self], data: bytes) -> tuple[Self, bytes]:
        fields, data = cls._deserialize_internal(cls.fields, data)
        return cls(**fields), data

    def replace(self, **kwargs: dict[str, typing.Any]) -> Struct:
        d = self.as_dict().copy()
        d.update(kwargs)

        instance = type(self)(**d)

        if self._frozen:
            instance = instance.freeze()

        return instance

    def __eq__(self, other: object) -> bool:
        if not isinstance(self, type(other)) and not isinstance(other, type(self)):
            return NotImplemented

        return self.as_dict() == other.as_dict()

    def _repr_extra_parts(self) -> list[str]:
        extra_parts = []

        if self._frozen:
            extra_parts.append("frozen")

        return extra_parts

    def __repr__(self) -> str:
        fields = []

        # Assigned fields are displayed as `field=value`
        for f, v in self.assigned_fields():
            fields.append(f"{f.name}={f.repr(v)}")

        cls = type(self)

        # Properties are displayed as `*prop=value`
        for attr in dir(cls):
            cls_attr = getattr(cls, attr)

            if not isinstance(cls_attr, property) or hasattr(Struct, attr):
                continue

            value = getattr(self, attr)

            if value is not None:
                fields.append(f"*{attr}={value!r}")

        extra_parts = self._repr_extra_parts()
        if extra_parts:
            extra = f"<{', '.join(extra_parts)}>"
        else:
            extra = ""

        return f"{type(self).__name__}{extra}({', '.join(fields)})"

    @property
    def is_valid(self) -> bool:
        try:
            self.serialize()
        except ValueError:
            return False
        else:
            return True

    def matches(self, other: Struct) -> bool:
        if not isinstance(self, type(other)) and not isinstance(other, type(self)):
            return False

        for field in self.fields:
            actual = getattr(self, field.name)
            expected = getattr(other, field.name)

            if expected is None:
                continue

            if isinstance(expected, Struct):
                if not actual.matches(expected):
                    return False
            elif actual != expected:
                return False

        return True

    def __setattr__(self, name: str, value: typing.Any) -> None:
        if self._frozen:
            raise AttributeError("Frozen structs are immutable, use `replace` instead")

        return super().__setattr__(name, value)

    def __hash__(self) -> int:
        if self._frozen:
            return self._hash

        # XXX: This implementation is incorrect only for a single case:
        # `isinstance(struct, collections.abc.Hashable)` always returns True
        raise TypeError(f"Unhashable type: {type(self)}")

    def freeze(self) -> Self:
        """Freeze a Struct instance, making it hashable and immutable."""
        if self._frozen:
            return self

        kwargs = {}

        for f in self.fields:
            value = getattr(self, f.name)

            if isinstance(value, Struct):
                value = value.freeze()

            kwargs[f.name] = value

        cls = self._real_cls()
        instance = cls(**kwargs)
        instance._hash = hash((cls, tuple(kwargs.items())))
        instance._frozen = True

        return instance


class IntStruct(Struct, IntMixin):
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        try:
            cls._int_type: type[t.FixedIntType] = next(
                c
                for c in cls.__mro__[1:]
                if issubclass(c, t.FixedIntType) and not issubclass(c, Struct)
            )
        except StopIteration:
            raise TypeError("Integer structs must be an integer subclasses") from None

    def __new__(
        cls: type[Self], *args, _underlying_int: int | None = None, **kwargs
    ) -> Self:
        # Integers are immutable in Python so we need to know, at creation time, what
        # the integer value of this object will be. This means that these structs *must*
        # also be immutable.
        cls = cls._real_cls()  # noqa: PLW0642
        underlying_int = _underlying_int

        if len(args) > 1:
            raise TypeError(f"{cls} takes no positional arguments")

        # Like a copy constructor
        if len(args) == 1:
            if not isinstance(args[0], int) or kwargs:
                raise TypeError(
                    f"{cls} can only be constructed from an integer"
                    f" or with just keyword arguments"
                )

            underlying_int = args[0]

            data = cls._int_type(underlying_int).serialize()
            kwargs, _ = cls._deserialize_internal(cls.fields, data)
            args = ()

        if underlying_int is None:
            # To compute the underlying integer, we create a temp instance and serialize
            temp_instance = super(Struct, cls).__new__(cls, 0)

            # Set the correct attributes on the instance so we can serialize
            bound = cls._signature.bind(*args, **kwargs)
            bound.apply_defaults()

            for name, value in bound.arguments.items():
                field = getattr(cls.fields, name)
                setattr(temp_instance, name, value)

            # Finally, serialize
            underlying_int, rest = cls._int_type.deserialize(temp_instance.serialize())
            assert not rest

            # Pretend we were called with the correct kwargs
            args = ()
            kwargs = temp_instance.as_dict()

        bound = cls._signature.bind(*args, **kwargs)
        bound.apply_defaults()

        instance = super(Struct, cls).__new__(cls, underlying_int)

        # Set attributes on the final instance
        for name, value in bound.arguments.items():
            field = getattr(cls.fields, name)
            setattr(instance, name, field._convert_type(value))

        # Freeze it
        instance._frozen = True

        return instance

    __hash__ = int.__hash__

    def _repr_extra_parts(self) -> list[str]:
        # We override this method to omit the unnecessary `<frozen>`
        return [f"{self._int_type(int(self))._hex_repr()}"]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, int):
            raise NotImplementedError

        return int(self) == int(other)

    @classmethod
    def deserialize(cls: type[Self], data: bytes) -> tuple[Self, bytes]:
        fields, remaining = cls._deserialize_internal(cls.fields, data)
        underlying_int, _ = cls._int_type.deserialize(
            data[: len(data) - len(remaining)]
        )

        # We overload deserialization to avoid an unnecessary serialize-deserialize
        # during `cls.__new__` to compute the underlying integer, since we have all the
        # data here already
        return cls(_underlying_int=underlying_int, **fields), remaining
