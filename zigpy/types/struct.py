from __future__ import annotations

import dataclasses
import inspect
import typing

from typing_extensions import Self

import zigpy.types as t

NoneType = type(None)


class ListSubclass(list):
    # So we can call `setattr()` on it
    pass


@dataclasses.dataclass(frozen=True)
class StructField:
    name: str | None = None
    type: type | None = None
    dynamic_type: typing.Callable[[Struct], type] | None = None

    requires: typing.Callable[[Struct], bool] | None = dataclasses.field(
        default=None, repr=False
    )
    optional: bool | None = False

    repr: typing.Callable[[typing.Any], str] | None = dataclasses.field(
        default=repr, repr=False
    )

    def replace(self, **kwargs) -> StructField:
        return dataclasses.replace(self, **kwargs)

    def get_type(self, struct: Struct) -> type:
        if self.dynamic_type is not None:
            return self.dynamic_type(struct)

        return self.type

    def _convert_type(self, value, struct: Struct):
        field_type = self.get_type(struct)

        if value is None or isinstance(value, field_type):
            return value

        try:
            return field_type(value)
        except Exception as e:  # noqa: BLE001
            raise ValueError(
                f"Failed to convert {self.name}={value!r} from type"
                f" {type(value)} to {field_type}"
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

        # Check to see if the Struct is also an integer
        cls._int_type = next(
            (
                c
                for c in cls.__mro__[1:]
                if issubclass(c, t.FixedIntType) and not issubclass(c, Struct)
            ),
            None,
        )
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
        elif len(args) == 1 and cls._int_type is not None and isinstance(args[0], int):
            # Integer constructor
            return cls.deserialize(cls._int_type(args[0]).serialize())[0]

        # Pretend our signature is `__new__(cls, p1: t1, p2: t2, ...)`
        signature = inspect.Signature(
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

        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()

        instance = super().__new__(cls)

        # Set each attributes on the instance
        for name, value in bound.arguments.items():
            field = getattr(cls.fields, name)
            setattr(instance, name, field._convert_type(value, struct=instance))

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
            elif field.type is None and field.dynamic_type is None:
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
            field_type = field.get_type(instance)

            if issubclass(field_type, Struct):
                setattr(instance, field.name, field_type.from_dict(value))
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

            value = field._convert_type(value, struct=self)
            field_type = field.get_type(struct=self)

            # All integral types are compacted into one chunk, unless they start and end
            # on a byte boundary.
            if issubclass(field_type, t.FixedIntType) and not (
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

    @classmethod
    def deserialize(cls: type[Self], data: bytes) -> tuple[Self, bytes]:
        instance = cls()

        bit_length = 0
        bitfields = []

        for field in cls.fields:
            if (
                field.requires is not None
                and not field.requires(instance)
                or not data
                and field.optional
            ):
                continue

            field_type = field.get_type(struct=instance)

            if issubclass(field_type, t.FixedIntType) and not (
                field_type._bits % 8 == 0 and bit_length % 8 == 0
            ):
                bit_length += field_type._bits
                bitfields.append(field)

                if bit_length % 8 == 0:
                    if len(data) < bit_length // 8:
                        raise ValueError(f"Data is too short to contain {bitfields}")

                    bits, _ = t.Bits.deserialize(data[: bit_length // 8])
                    data = data[bit_length // 8 :]

                    for f in bitfields:
                        value, bits = f.type.from_bits(bits)
                        setattr(instance, f.name, value)

                    assert not bits

                    bit_length = 0
                    bitfields = []

                continue
            elif bitfields:
                raise ValueError(
                    f"Segment of bitfields did not terminate on a byte boundary: "
                    f" {bitfields}"
                )

            value, data = field_type.deserialize(data)
            setattr(instance, field.name, value)

        if bitfields:
            raise ValueError(
                f"Trailing segment of bitfields did not terminate on a byte boundary: "
                f" {bitfields}"
            )

        return instance, data

    def replace(self, **kwargs: dict[str, typing.Any]) -> Struct:
        d = self.as_dict().copy()
        d.update(kwargs)

        instance = type(self)(**d)

        if self._frozen:
            instance = instance.freeze()

        return instance

    def __eq__(self, other: object) -> bool:
        if self._int_type is not None and isinstance(other, int):
            return int(self) == other
        elif not isinstance(self, type(other)) and not isinstance(other, type(self)):
            return NotImplemented

        return self.as_dict() == other.as_dict()

    def __int__(self) -> int:
        if self._int_type is None:
            return NotImplemented

        n, remaining = self._int_type.deserialize(self.serialize())
        assert not remaining

        return int(n)

    def __lt__(self, other: object) -> bool:
        if self._int_type is None or not isinstance(other, int):
            return NotImplemented

        return int(self) < int(other)

    def __le__(self, other: object) -> bool:
        if self._int_type is None or not isinstance(other, int):
            return NotImplemented

        return int(self) <= int(other)

    def __gt__(self, other: object) -> bool:
        if self._int_type is None or not isinstance(other, int):
            return NotImplemented

        return int(self) > int(other)

    def __ge__(self, other: object) -> bool:
        if self._int_type is None or not isinstance(other, int):
            return NotImplemented

        return int(self) >= int(other)

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

        extra_parts = []

        if self._int_type is not None:
            extra_parts.append(f"{self._int_type(int(self))._hex_repr()}")

        if self._frozen:
            extra_parts.append("frozen")

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
