import enum
from unittest import mock

import pytest

import zigpy.types as t
from zigpy.zcl.foundation import Status


def test_struct_fields():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: t.uint16_t

    assert TestStruct.fields.a.name == "a"
    assert TestStruct.fields.a.type == t.uint8_t

    assert TestStruct.fields.b.name == "b"
    assert TestStruct.fields.b.type == t.uint16_t


def test_struct_subclass_creation():
    # In-class constants are allowed
    class TestStruct3(t.Struct):
        CONSTANT1: int = 123
        CONSTANT2 = 1234
        _private1: int = 456
        _private2 = 4567
        _PRIVATE_CONST = mock.sentinel.priv_const

        class Test:
            pass

    assert not TestStruct3.fields
    assert TestStruct3.CONSTANT1 == 123
    assert TestStruct3.CONSTANT2 == 1234
    assert TestStruct3._private1 == 456
    assert TestStruct3._private2 == 4567
    assert TestStruct3._PRIVATE_CONST is mock.sentinel.priv_const
    assert TestStruct3()._PRIVATE_CONST is mock.sentinel.priv_const
    assert TestStruct3.Test
    assert TestStruct3().Test
    assert "Test" not in TestStruct3().as_dict()

    # Still valid
    class TestStruct4(t.Struct):
        pass

    # Annotations with values are not fields
    class TestStruct5(t.Struct):
        a: t.uint8_t = 2  # not a field
        b: t.uint16_t  # is a field

    inst6 = TestStruct5(123)
    assert "a" not in inst6.as_dict()
    assert "b" in inst6.as_dict()

    # unless they are a StructField
    class TestStruct6(t.Struct):
        a: t.uint8_t = t.StructField()

    assert "a" in TestStruct6(2).as_dict()


def test_struct_construction():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: t.LVBytes

    s1 = TestStruct(a=1)
    s1.b = b"foo"

    s2 = TestStruct(a=1, b=b"foo")

    assert s1 == s2
    assert s1.a == s2.a
    assert s1.replace(b=b"foo") == s2.replace(b=b"foo")
    assert s1.serialize() == s2.serialize() == b"\x01\x03foo"

    assert TestStruct(s1) == s1

    # You cannot use the copy constructor with other keyword arguments
    with pytest.raises(ValueError):
        TestStruct(s1, b=b"foo")

    # Types are coerced on construction so you cannot pass bad values
    with pytest.raises(ValueError):
        TestStruct(a=object())

    # You can still assign bad values but serialization will fail
    s1.serialize()
    s1.b = object()

    with pytest.raises(ValueError):
        s1.serialize()


def test_nested_structs():
    class InnerStruct(t.Struct):
        b: t.uint8_t
        c: t.uint8_t

    class OuterStruct(t.Struct):
        a: t.uint8_t
        inner: InnerStruct
        d: t.uint8_t

    assert len(OuterStruct.fields) == 3
    assert OuterStruct.fields.a.type is t.uint8_t
    assert OuterStruct.fields.inner.type is InnerStruct
    assert len(OuterStruct.fields.inner.type.fields) == 2
    assert OuterStruct.fields.d.type is t.uint8_t

    s, remaining = OuterStruct.deserialize(b"\x00\x01\x02\x03" + b"asd")
    assert remaining == b"asd"
    assert s.a == 0
    assert s.inner.b == 1
    assert s.inner.c == 2
    assert s.d == 3


def test_nested_structs2():
    class OuterStruct(t.Struct):
        class InnerStruct(t.Struct):
            b: t.uint8_t
            c: t.uint8_t

        a: t.uint8_t
        inner: None = t.StructField(type=InnerStruct)
        d: t.uint8_t

    assert len(OuterStruct.fields) == 3
    assert OuterStruct.fields[0].type is t.uint8_t
    assert OuterStruct.fields[1].type is OuterStruct.InnerStruct
    assert len(OuterStruct.fields[1].type.fields) == 2
    assert OuterStruct.fields[2].type is t.uint8_t

    s, remaining = OuterStruct.deserialize(b"\x00\x01\x02\x03" + b"asd")
    assert remaining == b"asd"
    assert s.a == 0
    assert s.inner.b == 1
    assert s.inner.c == 2
    assert s.d == 3


def test_struct_init():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: t.uint16_t
        c: t.CharacterString

    ts = TestStruct(a=1, b=0x0100, c="TestStruct")
    assert repr(ts)
    assert isinstance(ts.a, t.uint8_t)
    assert isinstance(ts.b, t.uint16_t)
    assert isinstance(ts.c, t.CharacterString)
    assert ts.a == 1
    assert ts.b == 0x100
    assert ts.c == "TestStruct"

    ts2, remaining = TestStruct.deserialize(b"\x01\x00\x01\x0aTestStruct")
    assert not remaining
    assert ts == ts2
    assert ts.serialize() == ts2.serialize()

    ts3 = ts2.replace(b=0x0100)
    assert ts3 == ts2
    assert ts3.serialize() == ts2.serialize()

    ts4 = ts2.replace(b=0x0101)
    assert ts4 != ts2
    assert ts4.serialize() != ts2.serialize()


def test_struct_string_is_none():
    class TestStruct(t.Struct):
        a: t.CharacterString

    # str(None) == "None", which is bad
    with pytest.raises(ValueError):
        TestStruct(a=None).serialize()


def test_struct_field_dependencies():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        status: Status
        bar: t.uint8_t = t.StructField(requires=lambda s: s.status == Status.SUCCESS)
        baz: t.uint8_t

    # Status is FAILURE so bar is not defined
    TestStruct(foo=1, status=Status.FAILURE, baz=2)

    ts1, remaining = TestStruct.deserialize(
        b"\x01" + Status.SUCCESS.serialize() + b"\x02\x03"
    )
    assert not remaining
    assert ts1 == TestStruct(foo=1, status=Status.SUCCESS, bar=2, baz=3)

    ts2, remaining = TestStruct.deserialize(
        b"\x01" + Status.FAILURE.serialize() + b"\x02\x03"
    )
    assert remaining == b"\x03"
    assert ts2 == TestStruct(foo=1, status=Status.FAILURE, bar=None, baz=2)


def test_struct_field_invalid_dependencies():
    class TestStruct(t.Struct):
        status: t.uint8_t
        value: t.uint8_t = t.StructField(requires=lambda s: s.status == 0x00)

    # Value will be ignored during serialization even though it has been assigned
    ts1 = TestStruct(status=0x01, value=0x02)
    assert ts1.serialize() == b"\x01"
    assert len(ts1.assigned_fields()) == 1

    # Value wasn't provided but it is required
    ts2 = TestStruct(status=0x00, value=None)
    assert len(ts1.assigned_fields()) == 1

    with pytest.raises(ValueError):
        ts2.serialize()

    # Value is not optional but doesn't need to be passed due to dependencies
    ts3 = TestStruct(status=0x01)
    assert ts3.serialize() == b"\x01"
    assert len(ts3.assigned_fields()) == 1


def test_struct_multiple_requires():
    class StrictStatus(t.enum8):
        SUCCESS = 0x00
        FAILURE = 0x01

        # Missing members cause a parsing failure
        _missing_ = enum.Enum._missing_

    class TestStruct(t.Struct):
        foo: t.uint8_t

        status1: StrictStatus
        value1: t.uint8_t = t.StructField(
            requires=lambda s: s.status1 == StrictStatus.SUCCESS
        )

        status2: StrictStatus
        value2: t.uint8_t = t.StructField(
            requires=lambda s: s.status2 == StrictStatus.SUCCESS
        )

    # status1: success, status2: success
    ts0, remaining = TestStruct.deserialize(
        b"\x00"
        + StrictStatus.SUCCESS.serialize()
        + b"\x01"
        + StrictStatus.SUCCESS.serialize()
        + b"\x02"
    )
    assert not remaining
    assert ts0 == TestStruct(
        foo=0,
        status1=StrictStatus.SUCCESS,
        value1=1,
        status2=StrictStatus.SUCCESS,
        value2=2,
    )

    # status1: failure, status2: success
    ts1, remaining = TestStruct.deserialize(
        b"\x00"
        + StrictStatus.FAILURE.serialize()
        + StrictStatus.SUCCESS.serialize()
        + b"\x02"
    )
    assert not remaining
    assert ts1 == TestStruct(
        foo=0, status1=StrictStatus.FAILURE, status2=StrictStatus.SUCCESS, value2=2
    )

    # status1: success, status2: failure, trailing
    ts2, remaining = TestStruct.deserialize(
        b"\x00"
        + StrictStatus.SUCCESS.serialize()
        + b"\x01"
        + StrictStatus.FAILURE.serialize()
        + b"\x02"
    )
    assert remaining == b"\x02"
    assert ts2 == TestStruct(
        foo=0, status1=StrictStatus.SUCCESS, value1=1, status2=StrictStatus.FAILURE
    )

    # status1: failure, status2: failure
    ts3, remaining = TestStruct.deserialize(
        b"\x00" + StrictStatus.FAILURE.serialize() + StrictStatus.FAILURE.serialize()
    )
    assert not remaining
    assert ts3 == TestStruct(
        foo=0, status1=StrictStatus.FAILURE, status2=StrictStatus.FAILURE
    )

    with pytest.raises(ValueError):
        # status1: failure
        TestStruct.deserialize(b"\x00" + StrictStatus.FAILURE.serialize())

    with pytest.raises(ValueError):
        # status1: failure, invalid trailing
        TestStruct.deserialize(b"\x00" + StrictStatus.FAILURE.serialize() + b"\xff")


def test_struct_equality():
    class TestStruct1(t.Struct):
        foo: t.uint8_t

    class TestStruct2(t.Struct):
        foo: t.uint8_t

    assert TestStruct1() != TestStruct2()
    assert TestStruct1(foo=1) != TestStruct2(foo=1)

    assert TestStruct1() == TestStruct1()
    assert TestStruct1(foo=1) == TestStruct1(foo=1)


@pytest.mark.parametrize(
    "data",
    [
        b"\x00",
        b"\x00\x00",
        b"\x01",
        b"\x01\x00",
        b"\x01\x02\x03",
        b"",
        b"\x00\x00\x00\x00",
    ],
)
def test_struct_subclass_extension(data):
    class TestStruct(t.Struct):
        foo: t.uint8_t

    class TestStructSubclass(TestStruct):
        bar: t.uint8_t = t.StructField(requires=lambda s: s.foo == 0x01)

    class TestCombinedStruct(t.Struct):
        foo: t.uint8_t
        bar: t.uint8_t = t.StructField(requires=lambda s: s.foo == 0x01)

    assert len(TestStructSubclass.fields) == 2
    assert len(TestCombinedStruct.fields) == 2

    error1 = None
    error2 = None

    try:
        ts1, remaining1 = TestStructSubclass.deserialize(data)
    except Exception as e:
        error1 = e

    try:
        ts2, remaining2 = TestCombinedStruct.deserialize(data)
    except Exception as e:
        error2 = e

    assert (error1 and error2) or (not error1 and not error2)

    if error1 or error2:
        assert repr(error1) == repr(error2)
    else:
        assert ts1.as_dict() == ts2.as_dict()
        assert remaining1 == remaining2


def test_optional_struct_special_case():
    class TestStruct(t.Struct):
        foo: t.uint8_t

    OptionalTestStruct = t.Optional(TestStruct)

    assert OptionalTestStruct.deserialize(b"") == (None, b"")
    assert OptionalTestStruct.deserialize(b"\x00") == (
        OptionalTestStruct(foo=0x00),
        b"",
    )


def test_old_style_struct():
    with pytest.raises(TypeError):
        # `_fields` would typically be ignored but this would be very bad
        class OldStruct(t.Struct):
            _fields = [("foo", t.uint8_t)]


def test_conflicting_types():
    class GoodStruct(t.Struct):
        foo: t.uint8_t = t.StructField(type=t.uint8_t)

    with pytest.raises(TypeError):

        class BadStruct(t.Struct):
            foo: t.uint8_t = t.StructField(type=t.uint16_t)


def test_requires_uses_instance_of_struct():
    class TestStruct(t.Struct):
        foo: t.uint8_t

        # the first parameter is really an instance of TestStruct
        bar: t.uint8_t = t.StructField(requires=lambda s: s.test)

        @property
        def test(self):
            assert isinstance(self, TestStruct)
            return self.foo == 0x01

    assert TestStruct.deserialize(b"\x00\x00") == (TestStruct(foo=0x00), b"\x00")
    assert TestStruct.deserialize(b"\x01\x00") == (TestStruct(foo=0x01, bar=0x00), b"")


def test_uppercase_field():
    class Neighbor(t.Struct):
        """Neighbor Descriptor"""

        PanId: t.EUI64
        IEEEAddr: t.EUI64
        NWKAddr: t.NWK
        NeighborType: t.uint8_t
        PermitJoining: t.uint8_t
        Depth: t.uint8_t
        LQI: t.uint8_t  # this should not be a constant

    assert len(Neighbor.fields) == 7
    assert Neighbor.fields[6].name == "LQI"
    assert Neighbor.fields[6].type == t.uint8_t


def test_non_annotated_field():
    with pytest.raises(TypeError):

        class TestStruct1(t.Struct):
            field1: t.uint8_t

            # Python does not provide any simple way to get the order of both defined
            # class attributes and annotations. This is bad.
            field2 = t.StructField(type=t.uint16_t)
            field3: t.uint32_t

    class TestStruct2(t.Struct):
        field1: t.uint8_t
        field2: None = t.StructField(type=t.uint16_t)
        field3: t.uint32_t

    assert len(TestStruct2.fields) == 3
    assert TestStruct2.fields[0] == t.StructField(name="field1", type=t.uint8_t)
    assert TestStruct2.fields[1] == t.StructField(name="field2", type=t.uint16_t)
    assert TestStruct2.fields[2] == t.StructField(name="field3", type=t.uint32_t)


def test_allowed_non_fields():
    class Other:
        def bar(self):
            return "bar"

    def foo2_(_):
        return "foo2"

    class TestStruct(t.Struct):
        @property
        def prop(self):
            return "prop"

        @prop.setter
        def prop(self, value):
            return

        foo1 = lambda _: "foo1"  # noqa: E731
        foo2 = foo2_
        bar = Other.bar

        field: t.uint8_t
        CONSTANT1: t.uint8_t = "CONSTANT1"
        CONSTANT2 = "CONSTANT2"

    assert len(TestStruct.fields) == 1
    assert TestStruct.CONSTANT1 == "CONSTANT1"
    assert TestStruct.CONSTANT2 == "CONSTANT2"
    assert TestStruct().prop == "prop"
    assert TestStruct().foo1() == "foo1"
    assert TestStruct().foo2() == "foo2"
    assert TestStruct().bar() == "bar"

    instance = TestStruct()
    instance.prop = None
    assert instance.prop == "prop"


def test_as_dict_empty_fields():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        bar: t.uint8_t = t.StructField(requires=lambda s: s.foo == 0x01)

    assert TestStruct(foo=1, bar=2).as_dict() == {"foo": 1, "bar": 2}
    assert TestStruct(foo=0, bar=2).as_dict() == {"foo": 0, "bar": 2}
    assert TestStruct(foo=0).as_dict() == {"foo": 0, "bar": None}

    # Same thing as above but assigned as attributes
    ts1 = TestStruct()
    ts1.foo = 1
    ts1.bar = 2
    assert ts1.as_dict() == {"foo": 1, "bar": 2}

    ts2 = TestStruct()
    ts2.foo = 0
    ts2.bar = 2
    assert ts2.as_dict() == {"foo": 0, "bar": 2}

    ts3 = TestStruct()
    ts3.foo = 0
    assert ts3.as_dict() == {"foo": 0, "bar": None}


def test_no_types():
    with pytest.raises(TypeError):

        class TestBadStruct(t.Struct):
            field: None = t.StructField()


def test_repr():
    class TestStruct(t.Struct):
        foo: t.uint8_t

    assert repr(TestStruct(foo=1)) == "TestStruct(foo=1)"
    assert repr(TestStruct(foo=None)) == "TestStruct()"

    # Invalid values still work
    ts = TestStruct()
    ts.foo = 1j
    assert repr(ts) == "TestStruct(foo=1j)"
