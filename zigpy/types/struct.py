import dataclasses
import inspect
import typing

NoneType = type(None)


class ListSubclass(list):
    # So we can call `setattr()` on it
    pass


class Struct:
    @classmethod
    def real_cls(cls) -> type:
        # The "Optional" subclass is dynamically created and breaks types.
        # We have to use a little introspection to find our real class.
        return next(c for c in cls.__mro__ if c.__name__ != "Optional")

    @classmethod
    def _annotations(cls) -> typing.List[type]:
        # First get our proper subclasses
        subclasses = []

        for subcls in cls.real_cls().__mro__:
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

        # Explicitly check for old-style structs and fail very early
        if hasattr(cls, "_fields"):
            raise TypeError(
                "Struct subclasses do not use `_fields` anymore."
                " Use class attributes with type annotations."
            )

        # We generate fields up here to fail early (and cache it)
        real_cls = cls.real_cls()
        fields = real_cls.fields()

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
                    for f in real_cls.fields()
                ]
            )

            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()

            instance = super().__new__(real_cls)

            # Set and convert the attributes to their respective types
            for name, value in bound.arguments.items():
                field = getattr(fields, name)

                if value is not None:
                    try:
                        value = field.concrete_type(value)
                    except Exception as e:
                        raise ValueError(
                            f"Failed to convert {name}={value!r} from type"
                            f" {type(value)} to {field.concrete_type}"
                        ) from e

                setattr(instance, name, value)

            return instance

        # Finally, attach the above __new__ classmethod to our subclass
        cls.__new__ = __new__

    @classmethod
    def fields(cls) -> typing.List["StructField"]:
        fields = ListSubclass()
        seen_optional = False

        # We need both to throw type errors in case a field is not annotated
        annotations = cls.real_cls()._annotations()
        variables = vars(cls.real_cls())

        # `set(annotations) | set(variables)` doesn't preserve order, which we need
        for name in list(annotations) + [v for v in variables if v not in annotations]:
            # _foo and FOO are considered constants and ignored
            if name.startswith("_") or name.upper() == name:
                continue

            field = getattr(cls, name, StructField())

            # Ignore methods and properties
            if callable(field) or isinstance(field, property):
                continue

            # It's a lot easier to debug when things break immediately instead of
            # fields being silently skipped
            if name not in annotations:
                raise TypeError(f"Field {name!r} is not annotated")

            annotation = annotations[name]

            if not isinstance(field, StructField):
                raise TypeError(
                    f"Field {name!r} must be a StructField or undefined, not {field!r}"
                )

            if field.type is not None and field.type != annotation:
                raise TypeError(
                    f"Field {name!r} type annotation conflicts with provided type:"
                    f" {annotation} != {field.type}"
                )

            field = field.replace(name=name, type=annotation)

            if field.optional:
                seen_optional = True

            if seen_optional and not field.optional:
                raise TypeError(
                    f"No required fields can come after optional fields: " f"{field!r}"
                )

            fields.append(field)
            setattr(fields, field.name, field)

        return fields

    def assigned_fields(self, *, strict=False) -> typing.List["StructField"]:
        assigned_fields = ListSubclass()

        for field in self.fields():
            value = getattr(self, field.name)

            # Ignore fields that aren't required
            if field.requires is not None and not field.requires(self):
                continue

            # Missing non-optional required fields cause an error if strict
            if value is None:
                if field.optional or not strict:
                    continue

                raise ValueError(f"Value for field {field.name} is required")

            assigned_fields.append((field, value))
            setattr(assigned_fields, field.name, (field, value))

        return assigned_fields

    def as_dict(self) -> typing.Dict[str, typing.Any]:
        return {f.name: v for f, v in self.assigned_fields()}

    def serialize(self) -> bytes:
        return b"".join(
            f.concrete_type(v).serialize() for f, v in self.assigned_fields(strict=True)
        )

    @classmethod
    def deserialize(cls, data: bytes) -> "Struct":
        instance = cls()

        for field in cls.fields():
            if field.requires is not None and not field.requires(instance):
                continue

            try:
                value, data = field.concrete_type.deserialize(data)
            except (ValueError, AssertionError):
                if field.optional:
                    break

                raise

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
        kwargs = ", ".join([f"{k}={v!r}" for k, v in self.as_dict().items()])
        return f"{type(self).__name__}({kwargs})"


@dataclasses.dataclass(frozen=True)
class StructField:
    name: typing.Optional[str] = None
    type: typing.Optional[type] = None

    requires: typing.Optional[typing.Callable[[Struct], bool]] = None

    def __post_init__(self):
        # Fail to initialize if the concrete type is invalid
        self.concrete_type

    @property
    def optional(self) -> bool:
        # typing.Optional[Foo] is really typing.Union[Foo, None]
        if getattr(self.type, "__origin__", None) is not typing.Union:
            return False

        # I can't think of a case where this is ever False but it's best to be explicit
        return NoneType in self.type.__args__

    @property
    def concrete_type(self) -> type:
        if getattr(self.type, "__origin__", None) is not typing.Union:
            return self.type

        types = set(self.type.__args__) - {NoneType}

        if len(types) > 1:
            raise TypeError(f"Struct field cannot have more than one concrete type")

        return tuple(types)[0]

    def replace(self, **kwargs) -> "StructField":
        return dataclasses.replace(self, **kwargs)
