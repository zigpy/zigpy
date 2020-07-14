import dataclasses
import inspect
import typing

NoneType = type(None)


class ListSubclass(list):
    # So we can call `setattr()` on it
    pass


class DotDict(dict):
    __getattr__ = dict.__getitem__


class Struct:
    def replace(self, **kwargs):
        d = self.as_dict().copy()
        d.update(kwargs)

        return type(self)(**d)

    def __init_subclass__(cls):
        super().__init_subclass__()

        # The "Optional" subclass is dynamically created and breaks types.
        # We have to use a little introspection to find our real class.
        real_cls = next(c for c in cls.__mro__ if c.__name__ != "Optional")

        # We generate fields out here to fail early as well as speed things up
        fields = real_cls.fields()

        # We dynamically create our subclass's `__new__` method
        def __new__(cls, *args, **kwargs):
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

            # Set and type-coerce the provided attributes
            for name, value in bound.arguments.items():
                field = getattr(fields, name)

                if value is not None:
                    try:
                        value = field.concrete_type(value)
                    except Exception as e:
                        raise ValueError(
                            f"Failed to coerce {name}={value} to {field.concrete_type}"
                        ) from e

                setattr(instance, name, value)

            return instance

        cls.__new__ = __new__

    @classmethod
    def fields(cls):
        fields = ListSubclass()
        seen_optional = False

        annotations = getattr(cls, "__annotations__", {})
        variables = vars(cls)

        # `set(annotations) | set(variables)` doesn't preserve order, which we need
        for name in list(annotations) + [v for v in variables if v not in annotations]:
            # _foo and FOO are considered constants and ignored
            if name.startswith("_") or name.upper() == name:
                continue

            field = getattr(cls, name, None)

            # Ignore methods and properties
            if callable(field) or isinstance(field, property):
                continue

            # It's a lot easier to debug when things break immediately instead of
            # fields being silently skipped
            if name not in annotations:
                raise TypeError(f"Field {name!r} is not annotated")

            annotation = annotations[name]

            if field is None:
                field = StructField(name=name, type=annotation)
            elif isinstance(field, StructField):
                field = field.replace(name=name, type=annotation)
            else:
                raise TypeError(
                    f"Field {name!r} must be a StructField or undefined, not {field!r}"
                )

            if field.optional:
                seen_optional = True

            if seen_optional and not field.optional:
                raise TypeError(
                    f"No required fields can come after optional fields: " f"{field!r}"
                )

            fields.append(field)
            setattr(fields, field.name, field)

        return fields

    def assigned_fields(self):
        for field in self.fields():
            value = getattr(self, field.name)

            # Ignore assigned fields that should be skipped
            if field.skip_if is not None:
                should_skip = field.skip_if(self)
                value = getattr(self, field.name)

                if should_skip and value is not None:
                    continue
                elif not should_skip and value is None:
                    continue

            if value is not None:
                yield field, value

    def as_dict(self):
        return {f.name: v for f, v in self.assigned_fields()}

    def serialize(self):
        return b"".join(
            f.concrete_type(v).serialize() for f, v in self.assigned_fields()
        )

    @classmethod
    def deserialize(cls, data):
        kwargs = DotDict()

        for field in cls.fields():
            # `kwargs` behaves like our struct due to having attributes
            if field.skip_if is not None and field.skip_if(kwargs):
                continue

            try:
                kwargs[field.name], data = field.concrete_type.deserialize(data)
            except (ValueError, AssertionError):
                if field.optional:
                    break

                raise

        return cls(**kwargs), data

    def __repr__(self):
        kwargs = ", ".join([f"{k}={v!r}" for k, v in self.as_dict().items()])
        return type(self).__name__ + f"({kwargs})"

    def __eq__(self, other):
        return self.as_dict() == other.as_dict()


@dataclasses.dataclass(frozen=True)
class StructField:
    name: typing.Optional[str] = None
    type: typing.Optional[type] = None

    skip_if: typing.Optional[typing.Callable[[Struct], bool]] = None

    def __post_init__(self):
        # Fail to initialize if the concrete type is invalid
        self.concrete_type

    @property
    def optional(self):
        # typing.Optional[Foo] is really typing.Union[Foo, None]
        if getattr(self.type, "__origin__", None) is not typing.Union:
            return False

        if NoneType not in self.type.__args__:
            return False

        return True

    @property
    def concrete_type(self):
        if getattr(self.type, "__origin__", None) is not typing.Union:
            return self.type

        types = set(self.type.__args__) - {NoneType}

        if len(types) > 1:
            raise TypeError(f"Struct field cannot have more than one concrete type")

        return tuple(types)[0]

    def replace(self, **kwargs):
        return dataclasses.replace(self, **kwargs)
