import dataclasses


@dataclasses.dataclass(frozen=True)
class StructField:
    name: str
    type: str


class Struct:
    def __init__(self, *args, **kwargs):
        # The "Optional" subclass is dynamically created and breaks type things
        # We have to use a little introspection to find our real class
        cls = next(c for c in type(self).__mro__ if c.__name__ != "Optional")

        # Like a copy constructor
        if len(args) == 1 and isinstance(args[0], cls):
            kwargs = args[0].as_dict()
            args = ()

        bound_fields = {f.name: None for f in self.fields()}

        for index, value in enumerate(args):
            name = list(bound_fields.keys())[index]
            bound_fields[name] = value

        for name, value in kwargs.items():
            if bound_fields[name] is not None:
                raise ValueError(f"Cannot pass the same arg and kwarg: {name}")

            bound_fields[name] = value

        named_fields = {f.name: f for f in self.fields()}

        for name, value in bound_fields.items():
            if value is not None:
                value = named_fields[name].type(value)

            setattr(self, name, value)

    @classmethod
    def fields(cls):
        for name, type in cls.__annotations__.items():
            yield StructField(name, type)

    def assigned_fields(self):
        for field in self.fields():
            yield field, getattr(self, field.name)

    def as_dict(self):
        return {f.name: v for f, v in self.assigned_fields()}

    def serialize(self):
        return b"".join(f.type(v).serialize() for f, v in self.assigned_fields())

    @classmethod
    def deserialize(cls, data):
        kwargs = {}

        for field in cls.fields():
            kwargs[field.name], data = field.type.deserialize(data)

        return cls(**kwargs), data
