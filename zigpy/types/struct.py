from __future__ import annotations

import dataclasses
import typing
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

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


class PartialStruct:
    """Read-only view over a partially deserialized struct, for `requires`/`length`."""

    __slots__ = ("_result", "_names")

    def __init__(self, result: dict[str, typing.Any], names: frozenset[str]) -> None:
        self._result = result
        self._names = names

    def __getattr__(self, name: str) -> typing.Any:
        if name not in self._names:
            raise AttributeError(name)

        if name in self._result:
            return self._result[name]

        return None


class IntRun:
    """Run of unconditional integer fields, (de)serialized as a single integer."""

    __slots__ = ("size", "entries", "names")

    def __init__(self, size: int, entries: tuple[tuple[typing.Any, ...], ...]) -> None:
        self.size = size
        self.entries = entries
        self.names = [entry[0].name for entry in entries]


@dataclasses.dataclass(frozen=True)
class StructField:
    name: str | None = None
    type: type[Any] | None = None

    requires: typing.Callable[[Struct], bool] | None = dataclasses.field(
        default=None, repr=False
    )
    optional: bool | None = False
    length: typing.Callable[[Struct], int] | None = dataclasses.field(
        default=None, repr=False
    )
    default: Any = dataclasses.field(default=None, repr=False)

    repr: typing.Callable[[typing.Any], str] | None = dataclasses.field(
        default=repr, repr=False
    )

    def replace(self, **kwargs) -> Self:
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


if TYPE_CHECKING:

    class ResolvedStructField(StructField):
        """`StructField` instance with name and type resolved."""

        name: str
        type: type[Any]

    class ResolvedArrayStructField(ResolvedStructField):
        """`StructField` instance with name, type, and length resolved."""

        type: type[t.List[Any]]
        length: typing.Callable[[Struct], int]
else:
    ResolvedStructField = StructField
    ResolvedArrayStructField = StructField


class Struct:
    fields: ClassVar[list[ResolvedStructField]]

    @classmethod
    def _real_cls(cls) -> type:
        # The "Optional" subclass is dynamically created and breaks types.
        # We have to use a little introspection to find our real class.
        return next(c for c in cls.__mro__ if c.__name__ != "Optional")

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        # We generate fields up here to fail early and cache it
        cls._real_type = cls._real_cls()
        cls.fields = cls._real_type._get_fields()

        # `Struct.__setattr__` only guards frozen instances, which a new instance
        # never is. Only route through it if a subclass has its own hook.
        cls._direct_setattr = cls.__setattr__ is Struct.__setattr__
        cls._needs_temp_instance = any(
            f.requires is not None or f.length is not None for f in cls.fields
        )
        cls._field_names = frozenset(f.name for f in cls.fields)
        cls._plan = cls._build_plan()
        cls._generated_new = cls._generate_new()

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
        if len(args) == 1 and isinstance(args[0], cls._real_type):
            # Like a copy constructor
            if kwargs:
                raise ValueError(f"Cannot use copy constructor with kwargs: {kwargs!r}")

            kwargs = args[0].as_dict()
            args = ()

        return cls._generated_new(*args, **kwargs)

    @classmethod
    def _generate_new(cls) -> typing.Callable[..., Self]:
        # Generate a `__new__(p1=d1, p2=d2, ...)` so argument binding, type
        # conversion, and attribute assignment are unrolled with no per-field
        # lookups. This is much faster than `inspect.Signature.bind`.
        namespace = {
            "__real_type": cls._real_type,
            # Mixins like `tuple` must allocate the instance, not `object`
            "__base_new": super(Struct, cls._real_type).__new__,
            "__isinstance": isinstance,
        }

        params = []
        lines = []

        direct_setattr = cls._direct_setattr

        if direct_setattr:
            lines.append("    __dict = __instance.__dict__")

        for index, field in enumerate(cls.fields):
            namespace[f"__field{index}"] = field
            namespace[f"__type{index}"] = field.type
            namespace[f"__default{index}"] = field.default
            params.append(f"{field.name}=__default{index}")

            lines.append(
                f"    if {field.name} is not None"
                f" and not __isinstance({field.name}, __type{index}):"
                f" {field.name} = __field{index}._convert_type({field.name})"
            )

            if direct_setattr:
                lines.append(f"    __dict[{field.name!r}] = {field.name}")
            else:
                lines.append(f"    __instance.{field.name} = {field.name}")

        source = "\n".join(
            [
                f"def __new__({', '.join(params)}):",
                "    __instance = __base_new(__real_type)",
                *lines,
                "    return __instance",
            ]
        )

        exec(source, namespace)  # noqa: S102

        return namespace["__new__"]

    @classmethod
    def _get_fields(cls) -> list[ResolvedStructField]:
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
            # Skip ClassVar annotations (e.g. inherited from Struct base class)
            if typing.get_origin(annotation) is ClassVar:
                continue

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

            resolved_field = cast(ResolvedStructField, field)

            if resolved_field.length is not None and not issubclass(
                resolved_field.type, t.List
            ):
                raise TypeError(
                    f"Field {name!r} has a length function but is not a list type: "
                    f"{resolved_field.type}"
                )

            fields.append(resolved_field)
            setattr(fields, field.name, resolved_field)

        return fields

    def assigned_fields(
        self, *, strict=False
    ) -> list[tuple[ResolvedStructField, typing.Any]]:
        assigned_fields = ListSubclass()

        for field in self.fields:
            value = getattr(self, field.name)

            # Ignore fields that aren't required
            if field.requires is not None and not field.requires(self):
                continue

            # Missing fields cause an error if strict
            if value is None and not field.optional and field.length is None:
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

    @classmethod
    def _build_plan(cls) -> tuple[IntRun | ResolvedStructField, ...]:
        # Unconditional integer fields (including bitfields) are grouped into runs
        # that are read and written with a single integer conversion. Every other
        # field is handled on its own.
        plan: list[IntRun | ResolvedStructField] = []
        entries: list[tuple[typing.Any, ...]] = []
        bit_offset = 0

        def close_run() -> None:
            nonlocal entries, bit_offset

            if entries:
                plan.append(IntRun(bit_offset // 8, tuple(entries)))

            entries = []
            bit_offset = 0

        for field in cls.fields:
            field_type = field.type
            is_conditional = (
                field.requires is not None or field.optional or field.length is not None
            )
            is_int = issubclass(field_type, t.FixedIntType)
            is_bitfield = is_int and (field_type._bits % 8 != 0 or bit_offset % 8 != 0)

            if is_bitfield and is_conditional:
                raise TypeError(
                    f"Field {field.name!r} is not byte aligned and cannot be conditional"
                )

            if not is_bitfield and bit_offset % 8 != 0:
                raise TypeError(
                    f"Segment of bitfields before field {field.name!r} does not"
                    f" terminate on a byte boundary"
                )

            if is_int and not is_conditional and field_type._byteorder == "little":
                # Byte-aligned integers with custom (de)serialization stay opaque
                if is_bitfield or (
                    field_type.deserialize.__func__
                    in (
                        t.FixedIntType.deserialize.__func__,
                        IntStruct.deserialize.__func__,
                    )
                    and field_type.serialize
                    in (t.FixedIntType.serialize, IntStruct.serialize)
                ):
                    entries.append(
                        (
                            field,
                            field_type,
                            bit_offset,
                            (1 << field_type._bits) - 1,
                            field_type._signed,
                            # The range check in `__new__` cannot fail for unpacked
                            # values so it is skipped for plain integer types
                            field_type.__new__ is t.FixedIntType.__new__,
                        )
                    )
                    bit_offset += field_type._bits
                    continue

            close_run()
            plan.append(field)

        if bit_offset % 8 != 0:
            raise TypeError(
                f"Trailing segment of bitfields in {cls} does not terminate on a"
                f" byte boundary"
            )

        close_run()

        return tuple(plan)

    def serialize(self) -> bytes:
        chunks = []

        for op in self._plan:
            if type(op) is IntRun:
                packed = 0

                for field, field_type, shift, mask, _, _ in op.entries:
                    value = getattr(self, field.name)

                    if value is None:
                        raise ValueError(
                            f"Value for field {field.name!r} is required: {self!r}"
                        )
                    elif not isinstance(value, field_type):
                        value = field._convert_type(value)

                    packed |= (value & mask) << shift

                chunks.append(packed.to_bytes(op.size, "little"))
                continue

            field = op

            # Ignore fields that aren't required
            if field.requires is not None and not field.requires(self):
                continue

            value = getattr(self, field.name)

            if value is None:
                if field.optional:
                    continue
                elif field.length is None:
                    raise ValueError(
                        f"Value for field {field.name!r} is required: {self!r}"
                    )
            elif not isinstance(value, field.type):
                value = field._convert_type(value)

            # Fields with lengths dependent on other fields need to be validated
            if field.length is not None:
                expected_length = field.length(self)

                if expected_length == 0:
                    if value:
                        raise ValueError(
                            f"Field {field.name!r} expected an empty array,"
                            f" got: {value!r}"
                        )

                    # Special case for a list with no elements
                    value = field._convert_type([])
                elif value is None or len(value) != expected_length:
                    raise ValueError(
                        f"Field {field.name!r} expected an array with length"
                        f" {expected_length}, got: {value!r}"
                    )

            chunks.append(value.serialize())

        return b"".join(chunks)

    @classmethod
    def deserialize(cls: type[Self], data: bytes) -> tuple[Self, bytes]:
        result: dict[str, typing.Any] = {}

        # `requires` and `length` callables expect a struct-like object
        if cls._needs_temp_instance:
            partial = PartialStruct(result, cls._field_names)
        else:
            partial = None

        for op in cls._plan:
            if type(op) is IntRun:
                size = op.size

                if len(data) < size:
                    raise ValueError(f"Data is too short to contain {op.names}")

                packed = int.from_bytes(data[:size], "little")
                data = data[size:]

                for field, field_type, shift, mask, signed, direct_new in op.entries:
                    value = (packed >> shift) & mask

                    if signed and value > field_type.max_value:
                        value -= mask + 1

                    if direct_new:
                        result[field.name] = int.__new__(field_type, value)
                    else:
                        result[field.name] = field_type(value)

                continue

            field = op

            if (field.requires is not None and not field.requires(partial)) or (
                not data and field.optional
            ):
                continue

            if field.length is not None:
                field = cast(ResolvedArrayStructField, field)

                items, data = field.type.deserialize(data, count=field.length(partial))
                value = field.type(items)
            else:
                value, data = field.type.deserialize(data)

            result[field.name] = value

        return cls(**result), data

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
    _int_type: ClassVar[type[t.FixedIntType]]
    _bit_layout: ClassVar[tuple[tuple[ResolvedStructField, int, int], ...]]
    _instance_cache: ClassVar[dict[int, Any] | None]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        try:
            cls._int_type = next(
                c
                for c in cls.__mro__[1:]
                if issubclass(c, t.FixedIntType) and not issubclass(c, Struct)
            )
        except StopIteration:
            raise TypeError("Integer structs must be an integer subclasses") from None

        # Every field of an integer struct is a fixed-width integer at a fixed bit
        # offset, so the layout is computed once and used for packing and unpacking
        layout = []
        shift = 0

        for field in cls.fields:
            if field.requires is not None or field.optional or field.length is not None:
                raise TypeError(
                    f"Field {field.name!r} of an integer struct cannot be conditional"
                )

            if not issubclass(field.type, t.FixedIntType):
                raise TypeError(
                    f"Field {field.name!r} of an integer struct must be an integer"
                    f" type, not {field.type}"
                )

            layout.append((field, shift, (1 << field.type._bits) - 1))
            shift += field.type._bits

        if shift != cls._int_type._bits:
            raise TypeError(
                f"Fields of {cls} span {shift} bits but {cls._int_type} has"
                f" {cls._int_type._bits} bits"
            )

        cls._bit_layout = tuple(layout)

        # Instances are immutable so small integer structs are shared, like enum
        # members. `FrameControl` is constructed for every ZCL frame.
        if cls is not cls._real_type:
            cls._instance_cache = cls._real_type._instance_cache
        elif cls._int_type._bits <= 8:
            cls._instance_cache = {}
        else:
            cls._instance_cache = None

    def __new__(cls: type[Self], *args, **kwargs) -> Self:
        # Integers are immutable in Python so we need to know, at creation time, what
        # the integer value of this object will be. This means that these structs *must*
        # also be immutable.
        cls = cls._real_cls()  # noqa: PLW0642

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
        else:
            underlying_int = 0

            for field, shift, mask in cls._bit_layout:
                if field.name in kwargs:
                    value = kwargs.pop(field.name)
                else:
                    value = field.default

                if value is None:
                    raise ValueError(f"Value for field {field.name!r} is required")

                underlying_int |= (field._convert_type(value) & mask) << shift

            if kwargs:
                raise TypeError(f"{cls} got unexpected keyword arguments: {kwargs!r}")

        cache = cls._instance_cache

        if cache is not None:
            try:
                return cache[underlying_int]
            except KeyError:
                pass

        instance = super(Struct, cls).__new__(cls, underlying_int)

        # Attributes are always unpacked from the integer so they are canonical
        for field, shift, mask in cls._bit_layout:
            value = (underlying_int >> shift) & mask

            if field.type._signed and value > field.type.max_value:
                value -= mask + 1

            setattr(instance, field.name, field.type(value))

        # Freeze it
        instance._frozen = True

        if cache is not None:
            cache[int(instance)] = instance

        return instance

    __hash__ = int.__hash__

    def _repr_extra_parts(self) -> list[str]:
        # We override this method to omit the unnecessary `<frozen>`
        return [f"{self._int_type(int(self))._hex_repr()}"]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, int):
            raise NotImplementedError

        return int(self) == int(other)

    def serialize(self) -> bytes:
        return self._int_type.serialize(self)

    @classmethod
    def deserialize(cls: type[Self], data: bytes) -> tuple[Self, bytes]:
        underlying_int, remaining = cls._int_type.deserialize(data)
        return cls(underlying_int), remaining
