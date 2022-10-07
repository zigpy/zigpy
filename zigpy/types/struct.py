from __future__ import annotations

import dataclasses
import inspect
import typing

import zigpy.types as t

NoneType = type(None)


class ListSubclass(list):
    # So we can call `setattr()` on it
    pass


@dataclasses.dataclass(frozen=True)
class StructField:
    name: str | None = None
    type: type | None = None

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
        except Exception as e:
            raise ValueError(
                f"Failed to convert {self.name}={value!r} from type"
                f" {type(value)} to {self.type}"
            ) from e


_STRUCT = typing.TypeVar("_STRUCT", bound="Struct")


class Struct:
    @classmethod
    def _real_cls(cls) -> type:
        # The "Optional" subclass is dynamically created and breaks types.
        # We have to use a little introspection to find our real class.
        return next(c for c in cls.__mro__ if c.__name__ != "Optional")

    def __init_subclass__(cls):
        super().__init_subclass__()

        # Explicitly check for old-style structs
        if hasattr(cls, "_fields"):
            raise TypeError(
                "Struct subclasses do not use `_fields` anymore."
                " Use class attributes with type annotations."
            )

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

    def __new__(cls: type[_STRUCT], *args, **kwargs) -> _STRUCT:
        cls = cls._real_cls()

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
                    pass  # Python bug, the following `continue` is never covered
                    continue  # pragma: no cover

            assigned_fields.append((field, value))
            setattr(assigned_fields, field.name, (field, value))

        return assigned_fields

    @classmethod
    def from_dict(cls: type[_STRUCT], obj: dict[str, typing.Any]) -> _STRUCT:
        parsed = {}

        for key, value in obj.items():
            field = getattr(cls.fields, key)

            if issubclass(field.type, Struct):
                parsed[field.name] = field.type.from_dict(value)
            else:
                parsed[field.name] = value

        return cls(**parsed)

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

    @classmethod
    def deserialize(cls: type[_STRUCT], data: bytes) -> tuple[_STRUCT, bytes]:
        instance = cls()

        bit_length = 0
        bitfields = []

        for field in cls.fields:
            if field.requires is not None and not field.requires(instance):
                continue
            elif not data and field.optional:
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

            value, data = field.type.deserialize(data)
            setattr(instance, field.name, value)

        if bitfields:
            raise ValueError(
                f"Trailing segment of bitfields did not terminate on a byte boundary: "
                f" {bitfields}"
            )

        return instance, data

    # TODO: improve? def replace(self: typing.Type[_STRUCT], **kwargs) -> _STRUCT:
    def replace(self, **kwargs: dict[str, typing.Any]) -> Struct:
        d = self.as_dict().copy()
        d.update(kwargs)

        return type(self)(**d)

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

        return f"{type(self).__name__}({', '.join(fields)})"

    @property
    def is_valid(self) -> bool:
        try:
            self.serialize()
            return True
        except ValueError:
            return False
