import enum
import typing

import pytest
import zigpy.types as t
from zigpy.zcl.foundation import Status


def test_struct_fields():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: typing.Optional[t.uint8_t]

    assert TestStruct.fields().a.name == "a"
    assert TestStruct.fields().a.type == t.uint8_t
    assert TestStruct.fields().a.concrete_type == t.uint8_t
    assert not TestStruct.fields().a.optional

    assert TestStruct.fields().b.name == "b"
    assert TestStruct.fields().b.type == typing.Optional[t.uint8_t]
    assert TestStruct.fields().b.concrete_type == t.uint8_t
    assert TestStruct.fields().b.optional


def test_struct_subclass_creation():
    # Optional fields must all be at the very end
    with pytest.raises(TypeError):

        class TestStruct1(t.Struct):
            b: typing.Optional[t.uint8_t]
            a: t.uint8_t

    with pytest.raises(TypeError):

        class TestStruct2(t.Struct):
            b: typing.Optional[t.uint8_t]
            a: t.uint8_t
            c: typing.Optional[t.uint8_t]

    # Every field must be annotated
    with pytest.raises(TypeError):

        class BadTestStruct3(t.Struct):
            a = 5

    # In-class constants are allowed
    class TestStruct3(t.Struct):
        CONSTANT1: int = 123
        CONSTANT2 = 1234
        _private1: int = 456
        _private2 = 4567

    assert not TestStruct3.fields()
    assert TestStruct3.CONSTANT1 == 123
    assert TestStruct3.CONSTANT2 == 1234
    assert TestStruct3._private1 == 456
    assert TestStruct3._private2 == 4567

    # This is fine
    class TestStruct4(t.Struct):
        a: typing.Optional[t.uint8_t]

    # Still valid
    class TestStruct5(t.Struct):
        pass

    # Fields cannot have values
    with pytest.raises(TypeError):

        class TestStruct6(t.Struct):
            a: t.uint8_t = 2

    # unless they are a StructField
    class TestStruct7(t.Struct):
        a: t.uint8_t = t.StructField()

    # Fields can only have a single concrete type
    with pytest.raises(TypeError):

        class TestStruct8(t.Struct):
            bad: typing.Union[t.uint8_t, t.uint16_t]


def test_struct_construction():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: typing.Optional[t.uint8_t]

    """
    # This breaks many unit tests
    with pytest.raises(TypeError):
        TestStruct()
    """

    s1 = TestStruct(a=1)
    s2 = TestStruct(a=1, b=None)

    assert s1 == s2
    assert s1.a == s2.a
    assert s1.replace(b=2) == s2.replace(b=2)
    assert s1.replace(b=2).serialize() == s2.replace(b=2).serialize() == b"\x01\x02"

    assert TestStruct(s1) == s1

    # You cannot use the copy constructor with other keyword arguments
    with pytest.raises(ValueError):
        TestStruct(s1, b=2)

    # Types are coerced on construction so you cannot pass bad values
    with pytest.raises(ValueError):
        TestStruct(a=object())


def test_struct_attribute_assignment():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: typing.Optional[t.uint8_t]

    s1 = TestStruct(a=1)
    s1.a = -1

    with pytest.raises(ValueError):
        s1.serialize()

    s1.a = 1

    assert s1.serialize() == TestStruct(a=1).serialize()


def test_nested_structs():
    class InnerStruct(t.Struct):
        b: t.uint8_t
        c: t.uint8_t

    class OuterStruct(t.Struct):
        a: t.uint8_t
        inner: typing.Optional[InnerStruct]
        d: typing.Optional[t.uint8_t]

    s1, remaining = OuterStruct.deserialize(b"\x00\x01\x02")
    assert not remaining
    assert s1.a == 0
    assert s1.inner.b == 1
    assert s1.inner.c == 2
    assert s1.d is None

    s2, remaining = OuterStruct.deserialize(b"\x00\x01\x02\x03")
    assert not remaining
    assert s2.a == 0
    assert s2.inner.b == 1
    assert s2.inner.c == 2
    assert s2.d == 3

    s3, remaining = OuterStruct.deserialize(b"\x00")
    assert not remaining
    assert s3.a == 0
    assert s3.inner is None
    assert s3.d is None


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


def test_struct_optional_init():
    class TestStruct(t.Struct):
        a: t.uint8_t
        b: t.uint16_t
        c: typing.Optional[t.CharacterString]

    ts1 = TestStruct(a=1, b=0x0100)
    ts2 = TestStruct(a=1, b=0x0100, c=b"foo")

    assert ts1.serialize() + t.CharacterString(b"foo").serialize() == ts2.serialize()


def test_struct_field_dependencies():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        status: Status
        bar: t.uint8_t = t.StructField(requires=lambda s: s.status == Status.SUCCESS)
        baz1: t.uint8_t
        baz2: typing.Optional[t.uint8_t]

    """
    # bar must be defined because status is SUCCESS
    with pytest.raises(ValueError):
        TestStruct(foo=1, status=Status.SUCCESS, baz1=2)
    """

    # Status is FAILURE so bar is not defined
    TestStruct(foo=1, status=Status.FAILURE, baz1=2)

    """
    # In fact, it cannot be defined
    with pytest.raises(ValueError):
        TestStruct(foo=1, status=Status.FAILURE, bar=2, baz1=2)
    """

    ts1, remaining = TestStruct.deserialize(
        b"\x01" + Status.SUCCESS.serialize() + b"\x02\x03"
    )
    assert not remaining
    assert ts1 == TestStruct(foo=1, status=Status.SUCCESS, bar=2, baz1=3, baz2=None)

    ts2, remaining = TestStruct.deserialize(
        b"\x01" + Status.FAILURE.serialize() + b"\x02\x03"
    )
    assert not remaining
    assert ts2 == TestStruct(foo=1, status=Status.FAILURE, bar=None, baz1=2, baz2=3)

    # If a struct is created and invalid fields are assigned, they will not show up
    ts3 = TestStruct()
    ts3.foo = 1
    ts3.status = Status.FAILURE
    ts3.bar = 2
    ts3.baz1 = 3

    assert ts3 == TestStruct(foo=1, status=Status.FAILURE, baz1=3)


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


def test_struct_optional_dependencies():
    class StrictStatus(t.enum8):
        SUCCESS = 0x00
        FAILURE = 0x01

        # Missing members cause a parsing failure
        _missing_ = enum.Enum._missing_

    class TestStruct(t.Struct):
        foo: t.uint8_t

        # The first pair of (status, value) is not optional
        status1: StrictStatus
        value1: t.uint8_t = t.StructField(
            requires=lambda s: s.status1 == StrictStatus.SUCCESS
        )

        # The second one is
        status2: typing.Optional[StrictStatus]
        value2: typing.Optional[t.uint8_t] = t.StructField(
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

    # status1: failure
    ts4, remaining = TestStruct.deserialize(b"\x00" + StrictStatus.FAILURE.serialize())
    assert not remaining
    assert ts4 == TestStruct(foo=0, status1=StrictStatus.FAILURE)

    # status1: failure, invalid trailing
    ts5, remaining = TestStruct.deserialize(
        b"\x00" + StrictStatus.FAILURE.serialize() + b"\xff"
    )
    assert remaining == b"\xff"
    assert ts5 == TestStruct(foo=0, status1=StrictStatus.FAILURE)

    # status1: success, invalid trailing
    ts6, remaining = TestStruct.deserialize(
        b"\x00" + StrictStatus.SUCCESS.serialize() + b"\x01\xff"
    )
    assert remaining == b"\xff"
    assert ts6 == TestStruct(foo=0, status1=StrictStatus.SUCCESS, value1=1)


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

    assert len(TestStructSubclass.fields()) == 2
    assert len(TestCombinedStruct.fields()) == 2

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
