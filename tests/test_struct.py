from __future__ import annotations

import enum
from unittest import mock

import pytest

import zigpy.types as t
from zigpy.zcl.foundation import Status
import zigpy.zdo.types as zdo_t


@pytest.fixture
def expose_global():
    """`typing.get_type_hints` does not work for types defined within functions"""

    objects = []

    def inner(obj):
        assert obj.__name__ not in globals()
        globals()[obj.__name__] = obj

        objects.append(obj)

        return obj

    yield inner

    for obj in objects:
        del globals()[obj.__name__]


def test_enum_fields():
    class EnumNamed(t.enum8):
        NAME1 = 0x01
        NAME2 = 0x10

    assert EnumNamed("0x01") == EnumNamed.NAME1
    assert EnumNamed("1") == EnumNamed.NAME1
    assert EnumNamed("0x10") == EnumNamed.NAME2
    assert EnumNamed("16") == EnumNamed.NAME2
    assert EnumNamed("NAME1") == EnumNamed.NAME1
    assert EnumNamed("NAME2") == EnumNamed.NAME2
    assert EnumNamed("EnumNamed.NAME1") == EnumNamed.NAME1
    assert EnumNamed("EnumNamed.NAME2") == EnumNamed.NAME2


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
    assert TestStruct3.Test  # type: ignore[truthy-function]
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


def test_nested_structs(expose_global):
    class OuterStruct(t.Struct):
        class InnerStruct(t.Struct):
            b: t.uint8_t
            c: t.uint8_t

        a: t.uint8_t
        inner: None = t.StructField(type=InnerStruct)
        d: t.uint8_t

    assert len(OuterStruct.fields) == 3
    assert OuterStruct.fields.a.type is t.uint8_t
    assert OuterStruct.fields.inner.type is OuterStruct.InnerStruct
    assert len(OuterStruct.fields.inner.type.fields) == 2
    assert OuterStruct.fields.d.type is t.uint8_t

    s, remaining = OuterStruct.deserialize(b"\x00\x01\x02\x03" + b"asd")
    assert remaining == b"asd"
    assert s.a == 0
    assert s.inner.b == 1
    assert s.inner.c == 2
    assert s.d == 3


def test_nested_structs2(expose_global):
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


def test_struct_multiple_requires(expose_global):
    @expose_global
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
    except Exception as e:  # noqa: BLE001
        error1 = e

    try:
        ts2, remaining2 = TestCombinedStruct.deserialize(data)
    except Exception as e:  # noqa: BLE001
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


def test_repr_properties():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        bar: t.uint8_t

        @property
        def baz(self):
            if self.bar is None:
                return None

            return t.Bool((self.bar & 0xF0) >> 4)

    assert repr(TestStruct(foo=1)) == "TestStruct(foo=1)"
    assert (
        repr(TestStruct(foo=1, bar=16))
        == "TestStruct(foo=1, bar=16, *baz=<Bool.true: 1>)"
    )
    assert repr(TestStruct()) == "TestStruct()"


def test_bitstruct_simple():
    class BitStruct1(t.Struct):
        foo: t.uint4_t
        bar: t.uint4_t

    s = BitStruct1(foo=0b1100, bar=0b1010)
    assert s.serialize() == bytes([0b1010_1100])

    s2, remaining = BitStruct1.deserialize(b"\x01\x02")
    assert remaining == b"\x02"
    assert s2.foo == 0b0001
    assert s2.bar == 0b0000


def test_bitstruct_nesting(expose_global):
    @expose_global
    class InnerBitStruct(t.Struct):
        baz1: t.uint1_t
        baz2: t.uint3_t
        baz3: t.uint1_t
        baz4: t.uint3_t

    class OuterStruct(t.Struct):
        foo: t.LVBytes
        bar: InnerBitStruct
        asd: t.uint8_t

    inner = InnerBitStruct(baz1=0b1, baz2=0b010, baz3=0b0, baz4=0b111)
    assert inner.serialize() == bytes([0b111_0_010_1])
    assert InnerBitStruct.deserialize(inner.serialize() + b"asd") == (inner, b"asd")

    s = OuterStruct(foo=b"asd", bar=inner, asd=0xFF)
    assert s.serialize() == b"\x03asd" + bytes([0b111_0_010_1]) + b"\xff"

    s2, remaining = OuterStruct.deserialize(s.serialize() + b"test")
    assert remaining == b"test"
    assert s == s2


def test_bitstruct_misaligned():
    class TestStruct(t.Struct):
        foo: t.uint1_t
        bar: t.uint8_t  # Even though this field is byte-serializable, it is misaligned
        baz: t.uint7_t

    s = TestStruct(foo=0b1, bar=0b10101010, baz=0b1110111)
    assert s.serialize() == bytes([0b1110111_1, 0b0101010_1])

    s2, remaining = TestStruct.deserialize(s.serialize() + b"asd")
    assert s == s2

    with pytest.raises(ValueError):
        TestStruct.deserialize(b"\xff")


def test_non_byte_sized_struct():
    class TestStruct(t.Struct):
        foo: t.uint1_t
        bar: t.uint8_t

    s = TestStruct(foo=1, bar=2)

    with pytest.raises(ValueError):
        s.serialize()

    with pytest.raises(ValueError):
        TestStruct.deserialize(b"\x00\x00\x00\x00")


def test_non_aligned_struct_non_integer_types():
    class TestStruct(t.Struct):
        foo: t.uint1_t
        bar: t.data8
        foo: t.uint7_t

    s = TestStruct(foo=1, bar=[2])

    with pytest.raises(ValueError):
        s.serialize()

    with pytest.raises(ValueError):
        TestStruct.deserialize(b"\x00\x00\x00\x00")


def test_bitstruct_complex():
    data = (
        b"\x11\x00\xff\xee\xdd\xcc\xbb\xaa\x08\x07\x06"
        b"\x05\x04\x03\x02\x01\x00\x00\x24\x02\x00\x7c"
    )

    neighbor, rest = zdo_t.Neighbor.deserialize(data + b"asd")
    assert rest == b"asd"

    neighbor2 = zdo_t.Neighbor(
        extended_pan_id=t.ExtendedPanId.convert("aa:bb:cc:dd:ee:ff:00:11"),
        ieee=t.EUI64.convert("01:02:03:04:05:06:07:08"),
        nwk=0x0000,
        device_type=zdo_t.Neighbor.DeviceType.Coordinator,
        rx_on_when_idle=zdo_t.Neighbor.RxOnWhenIdle.On,
        relationship=zdo_t.Neighbor.RelationShip.Sibling,
        reserved1=0b0,
        permit_joining=zdo_t.Neighbor.PermitJoins.Unknown,
        reserved2=0b000000,
        depth=0,
        lqi=124,
    )

    assert neighbor == neighbor2
    assert neighbor2.serialize() == data


def test_int_struct():
    class NonIntegralStruct(t.Struct):
        foo: t.uint8_t

    with pytest.raises(TypeError):
        int(NonIntegralStruct(123))

    class IntegralStruct(t.Struct, t.uint32_t):
        foo: t.uint8_t
        bar: t.uint16_t
        baz: t.uint7_t
        asd: t.uint1_t

    class IntegralStruct2(IntegralStruct):
        pass

    assert (
        IntegralStruct(0b0_1110001_1100110011001100_10101010)
        == IntegralStruct(
            foo=0b10101010,
            bar=0b1100110011001100,
            baz=0b1110001,
            asd=0b0,
        )
        == 0b0_1110001_1100110011001100_10101010
    )

    assert (
        IntegralStruct2(0b0_1110001_1100110011001100_10101010)
        == IntegralStruct2(
            foo=0b10101010,
            bar=0b1100110011001100,
            baz=0b1110001,
            asd=0b0,
        )
        == 0b0_1110001_1100110011001100_10101010
    )

    with pytest.raises(ValueError):
        # One extra bit
        IntegralStruct(0b1_0_1110001_1100110011001100_10101010)

    assert issubclass(IntegralStruct, t.uint32_t)
    assert issubclass(IntegralStruct, int)

    assert isinstance(IntegralStruct(), t.uint32_t)
    assert isinstance(IntegralStruct(), int)


def test_struct_optional():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        bar: t.uint16_t
        baz: t.uint8_t = t.StructField(requires=lambda s: s.bar == 2, optional=True)

    s1 = TestStruct(foo=1, bar=2, baz=3)
    assert s1.serialize() == b"\x01\x02\x00\x03"
    assert TestStruct.deserialize(s1.serialize() + b"asd") == (s1, b"asd")
    assert s1.replace(baz=None).serialize() == b"\x01\x02\x00"
    assert s1.replace(bar=4).serialize() == b"\x01\x04\x00"
    assert TestStruct.deserialize(b"\x01\x03\x00\x04") == (
        TestStruct(foo=1, bar=3),
        b"\x04",
    )


def test_struct_field_repr():
    class TestStruct(t.Struct):
        foo: t.uint8_t = t.StructField(repr=lambda v: v + 1)
        bar: t.uint16_t = t.StructField(repr=lambda v: "bar")
        baz: t.CharacterString = t.StructField(repr=lambda v: "baz")

    s1 = TestStruct(foo=1, bar=2, baz="asd")

    assert repr(s1) == "TestStruct(foo=2, bar=bar, baz=baz)"


def test_skip_missing():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        bar: t.uint16_t

    assert TestStruct(foo=1).as_dict() == {"foo": 1, "bar": None}
    assert TestStruct(foo=1).as_dict(skip_missing=True) == {"foo": 1}

    assert TestStruct(foo=1).as_tuple() == (1, None)
    assert TestStruct(foo=1).as_tuple(skip_missing=True) == (1,)


def test_from_dict(expose_global):
    @expose_global
    class InnerStruct(t.Struct):
        field1: t.uint8_t
        field2: t.CharacterString

    class TestStruct(t.Struct):
        foo: t.uint8_t
        bar: InnerStruct
        baz: t.CharacterString

    s = TestStruct(foo=1, bar=InnerStruct(field1=2, field2="field2"), baz="field3")

    assert s == TestStruct.from_dict(s.as_dict(recursive=True))


def test_matching(expose_global):
    @expose_global
    class InnerStruct(t.Struct):
        field1: t.uint8_t
        field2: t.CharacterString

    class TestStruct(t.Struct):
        foo: t.uint8_t
        bar: InnerStruct
        baz: t.CharacterString

    assert TestStruct().matches(TestStruct())
    assert not TestStruct().matches(InnerStruct())
    assert TestStruct(foo=1).matches(TestStruct(foo=1))
    assert not TestStruct(foo=1).matches(TestStruct(foo=2))
    assert TestStruct(foo=1).matches(TestStruct())

    s = TestStruct(foo=1, bar=InnerStruct(field1=2, field2="asd"), baz="foo")
    assert s.matches(s)
    assert s.matches(TestStruct())
    assert s.matches(TestStruct(bar=InnerStruct()))
    assert s.matches(TestStruct(bar=InnerStruct(field1=2, field2="asd")))
    assert not s.matches(TestStruct(bar=InnerStruct(field1=3)))


def test_dynamic_type():
    class TestStruct(t.Struct):
        foo: t.uint8_t
        baz: None = t.StructField(
            dynamic_type=lambda s: t.LVBytes if s.foo == 0x00 else t.uint8_t
        )

    assert TestStruct.deserialize(b"\x00\x04test") == (
        TestStruct(foo=0x00, baz=b"test"),
        b"",
    )
    assert TestStruct.deserialize(b"\x01\x04test") == (
        TestStruct(foo=0x01, baz=0x04),
        b"test",
    )

    assert TestStruct(foo=0x00, baz=b"test").serialize() == b"\x00\x04test"
    assert TestStruct(foo=0x01, baz=0x04).serialize() == b"\x01\x04"


def test_int_comparison(expose_global):
    @expose_global
    class FirmwarePlatform(t.enum8):
        Conbee = 0x05
        Conbee_II = 0x07
        Conbee_III = 0x09

    class FirmwareVersion(t.Struct, t.uint32_t):
        reserved: t.uint8_t
        platform: FirmwarePlatform
        minor: t.uint8_t
        major: t.uint8_t

    fw_ver = FirmwareVersion(0x264F0900)
    assert fw_ver == FirmwareVersion(
        reserved=0, platform=FirmwarePlatform.Conbee_III, minor=79, major=38
    )
    assert fw_ver == 0x264F0900
    assert int(fw_ver) == 0x264F0900
    assert "0x264F0900" in str(fw_ver)

    assert int(fw_ver) <= fw_ver
    assert fw_ver <= int(fw_ver)

    assert int(fw_ver) - 1 < fw_ver
    assert fw_ver < int(fw_ver) + 1

    assert int(fw_ver) >= fw_ver
    assert fw_ver >= int(fw_ver)

    assert int(fw_ver) + 1 > fw_ver
    assert fw_ver > int(fw_ver) - 1


def test_int_comparison_non_int(expose_global):
    @expose_global
    class FirmwarePlatform(t.enum8):
        Conbee = 0x05
        Conbee_II = 0x07
        Conbee_III = 0x09

    # This isn't an integer
    class FirmwareVersion(t.Struct):
        reserved: t.uint8_t
        platform: FirmwarePlatform
        minor: t.uint8_t
        major: t.uint8_t

    fw_ver = FirmwareVersion(
        reserved=0, platform=FirmwarePlatform.Conbee_III, minor=79, major=38
    )

    with pytest.raises(TypeError):
        fw_ver < 0  # noqa: B015

    with pytest.raises(TypeError):
        fw_ver <= 0  # noqa: B015

    with pytest.raises(TypeError):
        fw_ver > 0  # noqa: B015

    with pytest.raises(TypeError):
        fw_ver >= 0  # noqa: B015


def test_frozen_struct():
    class OuterStruct(t.Struct):
        class InnerStruct(t.Struct):
            b: t.uint8_t
            c: t.uint8_t

        a: t.uint8_t
        inner: None = t.StructField(type=InnerStruct)
        d: t.uint8_t
        e: t.uint16_t

    struct = OuterStruct(a=1, inner=OuterStruct.InnerStruct(b=2, c=3), d=4)
    frozen = struct.freeze()

    assert "frozen" not in repr(struct)
    assert "frozen" in repr(frozen)

    with pytest.raises(TypeError, match="Unhashable type"):
        hash(struct)

    # Setting attributes has no effect
    assert frozen.a == 1
    assert frozen.inner.b == 2

    with pytest.raises(AttributeError):
        frozen.a = 2

    with pytest.raises(AttributeError):
        frozen.inner.b = 5

    assert frozen.a == 1
    assert frozen.inner.b == 2

    assert {frozen: 2}[frozen] == 2
    assert {frozen, frozen} == {frozen}
    assert frozen == frozen.replace(a=1)
    assert {frozen, frozen, frozen.replace(a=1), frozen.replace(a=2)} == {
        frozen,
        frozen.replace(a=2),
    }
