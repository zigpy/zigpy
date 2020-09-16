import dataclasses
import inspect
import typing

NoneType = type(None)


class ListSubclass(list):
    # So we can call `setattr()` on it
    pass


class Struct:
    @classmethod
    def _real_cls(cls) -> type:
        # The "Optional" subclass is dynamically created and breaks types.
        # We have to use a little introspection to find our real class.
        return next(c for c in cls.__mro__ if c.__name__ != "Optional")

    @classmethod
    def _annotations(cls) -> typing.List[type]:
        # First get our proper subclasses
        subclasses = []

        for subcls in cls._real_cls().__mro__:
            if subcls is Struct:
                break

            subclasses.append(subcls)

        annotations = {}

        # Iterate over the annotations *backwards*.
        # We want subclasses' annotations to override their parent classes'.
        for subcls in subclasses[::-1]:
            annotations.update(getattr(subcls, "__annotations__", {}))

        return annotations

    def __init_subclass__(cls):
        super().__init_subclass__()

        # Explicitly check for old-style structs
        if hasattr(cls, "_fields"):
            raise TypeError(
                "Struct subclasses do not use `_fields` anymore."
                " Use class attributes with type annotations."
            )

        # We generate fields up here to fail early and cache it
        real_cls = cls._real_cls()
        cls.fields = real_cls._get_fields()

        # We dynamically create our subclass's `__new__` method
        def __new__(cls, *args, **kwargs) -> "Struct":
            # Like a copy constructor
            if len(args) == 1 and isinstance(args[0], real_cls):
                if kwargs:
                    raise ValueError(
                        f"Cannot use copy constructor with kwargs: " f"{kwargs!r}"
                    )

                kwargs = args[0].as_dict()
                args = ()

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

            instance = super().__new__(real_cls)

            # Set each attributes on the instance
            for name, value in bound.arguments.items():
                field = getattr(cls.fields, name)
                setattr(instance, name, field._convert_type(value))

            return instance

        # Finally, attach the above __new__ classmethod to our subclass
        cls.__new__ = __new__

    @classmethod
    def _get_fields(cls) -> typing.List["StructField"]:
        fields = ListSubclass()

        # We need both to throw type errors in case a field is not annotated
        annotations = cls._real_cls()._annotations()

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
            if annotation is not None:
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

    def assigned_fields(self, *, strict=False) -> typing.List["StructField"]:
        assigned_fields = ListSubclass()

        for field in self.fields:
            value = getattr(self, field.name)

            # Ignore fields that aren't required
            if field.requires is not None and not field.requires(self):
                continue

            # Missing fields cause an error if strict
            if value is None:
                if strict:
                    raise ValueError(f"Value for field {field.name!r} is required")
                else:
                    pass  # Python bug, the following `continue` is never covered
                    continue  # pragma: no cover

            assigned_fields.append((field, value))
            setattr(assigned_fields, field.name, (field, value))

        return assigned_fields

    def as_dict(self) -> typing.Dict[str, typing.Any]:
        return {f.name: getattr(self, f.name) for f in self.fields}

    def serialize(self) -> bytes:
        return b"".join(
            f._convert_type(v).serialize() for f, v in self.assigned_fields(strict=True)
        )

    @classmethod
    def deserialize(cls, data: bytes) -> "Struct":
        instance = cls()

        for field in cls.fields:
            if field.requires is not None and not field.requires(instance):
                continue

            value, data = field.type.deserialize(data)
            setattr(instance, field.name, value)

        return instance, data

    def replace(self, **kwargs) -> "Struct":
        d = self.as_dict().copy()
        d.update(kwargs)

        return type(self)(**d)

    def __eq__(self, other: "Struct") -> bool:
        if not isinstance(self, type(other)) and not isinstance(other, type(self)):
            return False

        return self.as_dict() == other.as_dict()

    def __repr__(self) -> str:
        kwargs = ", ".join([f"{f.name}={v!r}" for f, v in self.assigned_fields()])
        return f"{type(self).__name__}({kwargs})"


@dataclasses.dataclass(frozen=True)
class StructField:
    name: typing.Optional[str] = None
    type: typing.Optional[type] = None

    requires: typing.Optional[typing.Callable[[Struct], bool]] = None

    def replace(self, **kwargs) -> "StructField":
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
