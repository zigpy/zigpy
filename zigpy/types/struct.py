class Struct:
    def __init__(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], self.__class__):
            # copy constructor
            for field in self._fields:
                setattr(self, field[0], getattr(args[0], field[0]))

    def serialize(self):
        r = b''
        for field in self._fields:
            r += getattr(self, field[0]).serialize()
        return r

    @classmethod
    def deserialize(cls, data):
        r = cls()
        for field_name, field_type in cls._fields:
            v, data = field_type.deserialize(data)
            setattr(r, field_name, v)
        return r, data

    def __repr__(self):
        r = '<%s ' % (self.__class__.__name__, )
        r += ' '.join(
            ['%s=%s' % (f[0], getattr(self, f[0], None)) for f in self._fields]
        )
        r += '>'
        return r
