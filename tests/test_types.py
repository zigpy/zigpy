import itertools
import math
import struct

import pytest

import zigpy.types as t


def test_abstract_ints():
    assert issubclass(t.uint8_t, t.uint_t)
    assert not issubclass(t.uint8_t, t.int_t)
    assert t.int_t._signed is True
    assert t.uint_t._signed is False
    assert t.int_t._byteorder == "little"
    assert t.int_t_be._byteorder == "big"

    with pytest.raises(TypeError):
        t.int_t(0)

    with pytest.raises(TypeError):
        t.FixedIntType(0)


def test_int_out_of_bounds():
    assert t.uint8_t._size == 1
    assert t.uint8_t._bits == 8

    t.uint8_t(0)

    with pytest.raises(ValueError):
        # Normally this would throw an OverflowError. We re-raise it as a ValueError.
        t.uint8_t(-1)

    with pytest.raises(ValueError):
        t.uint8_t(0xFF + 1)


def test_int_too_short():
    with pytest.raises(ValueError):
        t.uint8_t.deserialize(b"")

    with pytest.raises(ValueError):
        t.uint16_t.deserialize(b"\x00")


def test_fractional_ints_corner():
    assert t.uint1_t._size is None
    assert t.uint1_t._bits == 1
    assert t.uint1_t.min_value == 0
    assert t.uint1_t.max_value == 1

    assert t.uint1_t(0) == 0
    assert t.uint1_t(1) == 1

    with pytest.raises(ValueError):
        t.uint1_t(-1)

    with pytest.raises(ValueError):
        t.uint1_t(2)

    n = t.uint1_t(0b1)

    with pytest.raises(TypeError):
        n.serialize()

    assert t.uint1_t(0).bits() == [0]
    assert t.uint1_t(1).bits() == [1]

    assert t.uint1_t.from_bits([1, 1]) == (1, [1])
    assert t.uint1_t.from_bits([0, 1]) == (1, [0])


def test_fractional_ints_larger():
    assert t.uint7_t._size is None
    assert t.uint7_t._bits == 7
    assert t.uint7_t.min_value == 0
    assert t.uint7_t.max_value == 2**7 - 1

    assert t.uint7_t(0) == 0
    assert t.uint7_t(1) == 1
    assert t.uint7_t(0b1111111) == 0b1111111

    with pytest.raises(ValueError):
        t.uint7_t(-1)

    with pytest.raises(ValueError):
        t.uint7_t(0b1111111 + 1)

    n = t.uint7_t(0b1111111)

    with pytest.raises(TypeError):
        n.serialize()

    assert t.uint7_t(0).bits() == [0, 0, 0, 0, 0, 0, 0]
    assert t.uint7_t(1).bits() == [0, 0, 0, 0, 0, 0, 1]
    assert t.uint7_t(0b1011111).bits() == [1, 0, 1, 1, 1, 1, 1]

    assert t.uint7_t.from_bits([1, 0, 1, 1, 1, 1, 0, 1, 1, 1]) == (0b1110111, [1, 0, 1])

    with pytest.raises(ValueError):
        assert t.uint7_t.from_bits([1] * 6)


def test_ints_signed():
    class int7s(t.int_t, bits=7):
        pass

    assert int7s._size is None
    assert int7s._bits == 7

    assert int7s(0) == 0
    assert int7s(1) == 1
    assert int7s(-1) == -1
    assert int7s(2**6 - 1) == 2**6 - 1
    assert int7s(-(2**6)) == -(2**6)

    with pytest.raises(ValueError):
        int7s(2**6)

    with pytest.raises(ValueError):
        int7s(-(2**6) - 1)

    n = int7s(2**6 - 1)

    with pytest.raises(TypeError):
        n.serialize()

    assert int7s(0).bits() == [0, 0, 0, 0, 0, 0, 0]
    assert int7s(1).bits() == [0, 0, 0, 0, 0, 0, 1]
    assert int7s(-1).bits() == [1, 1, 1, 1, 1, 1, 1]
    assert int7s(2**6 - 1).bits() == [0, 1, 1, 1, 1, 1, 1]

    assert int7s.from_bits([1, 0, 1, 0, 1, 1, 0, 1, 1, 1]) == (0b0110111, [1, 0, 1])

    with pytest.raises(TypeError):
        int7s.deserialize(b"\xff")

    t.int8s.deserialize(b"\xff")

    n = t.int8s(-126)
    bits = [1, 0] + t.Bits.deserialize(n.serialize())[0]
    assert t.int8s.from_bits(bits) == (n, [1, 0])


def test_bigendian_ints():
    assert t.uint32_t_be(0x12345678).serialize() == b"\x12\x34\x56\x78"
    assert t.uint32_t_be.deserialize(b"\x12\x34\x56\x78") == (0x12345678, b"")
    assert t.int32s_be(0x12345678).serialize() == b"\x12\x34\x56\x78"
    assert t.int32s_be(-1).serialize() == b"\xff\xff\xff\xff"
    assert t.int32s_be.deserialize(b"\xfe\xdc\xba\x98") == (-0x01234568, b"")
    assert (
        t.uint32_t_be(0x12345678).serialize()[::-1]
        == t.uint32_t(0x12345678).serialize()
    )


def test_bits():
    assert t.Bits() == []
    assert t.Bits([1] + [0] * 15).serialize() == b"\x80\x00"
    assert t.Bits.deserialize(b"\x80\x00") == ([1] + [0] * 15, b"")

    bits = t.Bits([0] * 7)

    with pytest.raises(ValueError):
        assert bits.serialize()


def compare_with_nan(v1, v2):
    if not math.isnan(v1) ^ math.isnan(v2):
        return True

    return v1 == v2


@pytest.mark.parametrize(
    "value",
    [
        1.25,
        0,
        -1.25,
        float("nan"),
        float("+inf"),
        float("-inf"),
        # Max value held by Half
        65504,
        -65504,
    ],
)
def test_floats(value):
    extra = b"ab12!"

    for data_type in (t.Half, t.Single, t.Double):
        value2, remaining = data_type.deserialize(data_type(value).serialize() + extra)
        assert remaining == extra

        # nan != nan so make sure they're both nan or the same value
        assert compare_with_nan(value, value2)
        assert len(data_type(value).serialize()) == data_type._size


@pytest.mark.parametrize(
    ("value", "only_double"),
    [
        (2, False),
        (1.25, False),
        (0, False),
        (-1.25, False),
        (-2, False),
        (float("nan"), False),
        (float("+inf"), False),
        (float("-inf"), False),
        (struct.unpack(">f", bytes.fromhex("7f7f ffff"))[0], False),
        (struct.unpack(">f", bytes.fromhex("3f7f ffff"))[0], False),
        (struct.unpack(">d", bytes.fromhex("7f7f ffff ffff ffff"))[0], True),
        (struct.unpack(">d", bytes.fromhex("3f7f ffff ffff ffff"))[0], True),
    ],
)
def test_single_and_double_with_struct(value, only_double):
    # Float and double must match the behavior of the built-in struct module
    if not only_double:
        assert t.Single(value).serialize() == struct.pack("<f", value)
        v1, r1 = t.Single.deserialize(struct.pack("<f", value))
        assert compare_with_nan(v1, t.Single(value))
        assert r1 == b""

    assert t.Double(value).serialize() == struct.pack("<d", value)
    v2, r2 = t.Double.deserialize(struct.pack("<d", value))
    assert compare_with_nan(v2, t.Double(value))
    assert r2 == b""


def test_float_parsing_errors():
    with pytest.raises(ValueError):
        t.Double.deserialize(b"\x00\x00\x00\x00\x00\x00\x00")

    with pytest.raises(ValueError):
        t.Single.deserialize(b"\x00\x00\x00")

    with pytest.raises(ValueError):
        t.Half.deserialize(b"\x00")


def test_lvbytes():
    d, r = t.LVBytes.deserialize(b"\x0412345")
    assert r == b"5"
    assert d == b"1234"

    assert t.LVBytes.serialize(d) == b"\x041234"


def test_lvbytes_too_short():
    with pytest.raises(ValueError):
        t.LVBytes.deserialize(b"")

    with pytest.raises(ValueError):
        t.LVBytes.deserialize(b"\x04123")


def test_lvbytes_too_long():
    to_serialize = b"".join(itertools.repeat(b"\xbe", 255))
    with pytest.raises(ValueError):
        t.LVBytes(to_serialize).serialize()


def test_limited_lvbytes():
    d, r = t.LimitedLVBytes(5).deserialize(b"\x0412345")
    assert r == b"5"
    assert d == b"1234"

    # Make sure that a length of 5 does not throw an exception
    t.LimitedLVBytes(5)(b"12345").serialize()

    # Make sure that a length of 6 does throw an exception
    with pytest.raises(ValueError):
        t.LimitedLVBytes(5)(b"123456").serialize()


def test_lvbytes_size2():
    # Deserialize tests
    d, r = t.LVBytesSize2().deserialize(b"\x02123")
    assert d == b"12"  # Accepted data
    assert r == b"3"  # Remaining

    # Make sure we get exceptions when the length is not 2 (lower/higher)

    with pytest.raises(ValueError):
        d, r = t.LVBytesSize2().deserialize(b"\x011")

    with pytest.raises(ValueError):
        d, r = t.LVBytesSize2().deserialize(b"\x03123")

    # Serialize tests

    # Make sure that a length of 2 does not throw an exception
    t.LVBytesSize2(b"12").serialize()

    # Make sure that a length of 1 does throw an exception
    with pytest.raises(ValueError):
        t.LVBytesSize2(b"1").serialize()
    # Make sure that a length of 3 does throw an exception
    with pytest.raises(ValueError):
        t.LVBytesSize2(b"123").serialize()


def test_long_octet_string():
    assert t.LongOctetString(b"asdfoo").serialize() == b"\x06\x00asdfoo"

    orig_len = 65532
    deserialize_extra = b"1234"
    to_deserialize = (
        orig_len.to_bytes(2, "little")
        + b"".join(itertools.repeat(b"b", orig_len))
        + deserialize_extra
    )
    des, rest = t.LongOctetString.deserialize(to_deserialize)
    assert len(des) == orig_len
    assert rest == deserialize_extra


def test_long_octet_string_too_long():
    to_serialize = b"".join(itertools.repeat(b"\xbe", 65535))
    with pytest.raises(ValueError):
        t.LongOctetString(to_serialize).serialize()


def test_lvbytes_0_len():
    to_deserialize = b"\x00abcdef"
    r, rest = t.LVBytes.deserialize(to_deserialize)
    assert r == b""
    assert rest == b"abcdef"
    assert t.LVBytes(b"").serialize() == b"\00"


def test_character_string():
    assert t.CharacterString() == ""

    d, r = t.CharacterString.deserialize(b"\x0412345")
    assert r == b"5"
    assert d == "1234"

    assert t.CharacterString.serialize(d) == b"\x041234"

    # test null char stripping
    d, _ = t.CharacterString.deserialize(b"\x05abc\x00ef")
    assert d == "abc"


def test_character_string_decode_failure():
    d, _ = t.CharacterString.deserialize(b"\x04\xf9123\xff\xff45")
    assert d == "�123"


def test_char_string_0_len():
    to_deserialize = b"\x00abcdef"
    r, rest = t.CharacterString.deserialize(to_deserialize)
    assert r == ""
    assert rest == b"abcdef"
    assert t.CharacterString("").serialize() == b"\00"


def test_char_string_too_long():
    to_serialize = "".join(itertools.repeat("a", 255))
    with pytest.raises(ValueError):
        t.CharacterString(to_serialize).serialize()


def test_char_string_too_short():
    with pytest.raises(ValueError):
        t.CharacterString.deserialize(b"")

    with pytest.raises(ValueError):
        t.CharacterString.deserialize(b"\x04123")


def test_char_string_invalid():
    r, rest = t.CharacterString.deserialize(b"\xffabcd")
    assert r == ""
    assert r.invalid is True
    assert rest == b"abcd"

    assert r.serialize() == b"\xff"


def test_long_char_string():
    orig_len = 65532
    to_serialize = "".join(itertools.repeat("a", orig_len))
    ser = t.LongCharacterString(to_serialize).serialize()
    assert len(ser) == orig_len + len(orig_len.to_bytes(2, "little"))

    deserialize_extra = b"1234"
    to_deserialize = (
        orig_len.to_bytes(2, "little")
        + b"".join(itertools.repeat(b"b", orig_len))
        + deserialize_extra
    )
    des, rest = t.LongCharacterString.deserialize(to_deserialize)
    assert len(des) == orig_len
    assert rest == deserialize_extra


def test_long_char_string_too_long():
    to_serialize = "".join(itertools.repeat("a", 65535))
    with pytest.raises(ValueError):
        t.LongCharacterString(to_serialize).serialize()


def test_long_char_string_too_short():
    with pytest.raises(ValueError):
        t.LongCharacterString.deserialize(b"\x04\x00123")


def test_limited_char_string():
    assert t.LimitedCharString(5)("12345").serialize() == b"\x0512345"
    with pytest.raises(ValueError):
        t.LimitedCharString(5)("123456").serialize()


def test_lvlist():
    d, r = t.LVList[t.uint8_t, t.uint8_t].deserialize(b"\x0412345")
    assert r == b"5"
    assert d == list(map(ord, "1234"))
    assert t.LVList[t.uint8_t, t.uint8_t].serialize(d) == b"\x041234"

    assert isinstance(d, t.LVList[t.uint8_t, t.uint8_t])


def test_lvlist_too_short():
    with pytest.raises(ValueError):
        t.LVList[t.uint8_t, t.uint8_t].deserialize(b"")

    with pytest.raises(ValueError):
        t.LVList[t.uint8_t, t.uint8_t].deserialize(b"\x04123")


def test_list():
    expected = list(map(ord, "\x0123"))
    d, r = t.List[t.uint8_t].deserialize(b"\x0123")

    assert (d, r) == (expected, b"")
    assert not isinstance(expected, t.List[t.uint8_t])
    assert isinstance(d, t.List[t.uint8_t])


def test_fixedlist():
    with pytest.raises(ValueError):
        t.FixedList[t.uint8_t, 2]([]).serialize()

    with pytest.raises(ValueError):
        t.FixedList[t.uint8_t, 2]([1]).serialize()

    with pytest.raises(ValueError):
        t.FixedList[t.uint8_t, 2]([1, 2, 3]).serialize()

    assert t.FixedList[t.uint8_t, 2]([1, 2]).serialize() == b"\x01\x02"


def test_lvlist_types():
    # Brackets create singleton types
    anon_lst1 = t.LVList[t.uint16_t]
    anon_lst2 = t.LVList[t.uint16_t, t.uint8_t]

    assert anon_lst1._length_type is t.uint8_t
    assert anon_lst1._item_type is t.uint16_t
    assert anon_lst2._length_type is t.uint8_t
    assert anon_lst2._item_type is t.uint16_t
    assert anon_lst1 is anon_lst2
    assert issubclass(t.LVList[t.uint8_t, t.uint16_t], t.LVList[t.uint8_t, t.uint16_t])
    assert not issubclass(
        t.LVList[t.uint16_t, t.uint8_t], t.LVList[t.uint8_t, t.uint16_t]
    )

    # Bracketed types are compatible with explicit subclasses
    class LVListSubclass(t.LVList, item_type=t.uint16_t, length_type=t.uint8_t):
        pass

    assert issubclass(LVListSubclass, t.LVList[t.uint16_t, t.uint8_t])
    assert not issubclass(t.LVList[t.uint16_t, t.uint8_t], LVListSubclass)
    assert not issubclass(LVListSubclass, t.LVList[t.uint8_t, t.uint16_t])
    assert issubclass(LVListSubclass, LVListSubclass)

    # Instances are also compatible
    assert isinstance(LVListSubclass(), LVListSubclass)
    assert isinstance(LVListSubclass(), t.LVList[t.uint16_t, t.uint8_t])
    assert not isinstance(LVListSubclass(), t.LVList[t.uint8_t, t.uint16_t])
    assert not isinstance(t.LVList[t.uint16_t, t.uint8_t](), LVListSubclass)
    assert isinstance(
        t.LVList[t.uint16_t, t.uint8_t](), t.LVList[t.uint16_t, t.uint8_t]
    )

    # Similar-looking classes are not compatible
    class NewListType(list, metaclass=t.KwargTypeMeta):
        _item_type = None
        _length_type = t.uint8_t

        _getitem_kwargs = {"item_type": None, "length_type": t.uint8_t}

    class NewList(NewListType, item_type=t.uint16_t, length_type=t.uint8_t):
        pass

    assert not issubclass(NewList, t.LVList[t.uint16_t, t.uint8_t])
    assert not isinstance(NewList(), t.LVList[t.uint16_t, t.uint8_t])


def test_int_repr():
    class NwkAsHex(t.uint16_t, repr="hex"):
        pass

    nwk = NwkAsHex(0x023A)
    assert str(nwk) == "0x023A"
    assert repr(nwk) == "0x023A"

    assert str([nwk]) == "[0x023A]"
    assert repr([nwk]) == "[0x023A]"

    class NwkAsBin(t.uint16_t, repr="bin"):
        pass

    nwk = NwkAsBin(0b01110000_10101010)
    assert str(nwk) == "0b0111000010101010"
    assert repr(nwk) == "0b0111000010101010"

    assert str([nwk]) == "[0b0111000010101010]"
    assert repr([nwk]) == "[0b0111000010101010]"

    # You can turn it off as well
    class NwkWithoutHex(NwkAsHex, repr=False):
        pass

    nwk = NwkWithoutHex(1234)
    assert str(nwk) == "1234"
    assert repr(nwk) == "1234"

    assert str([nwk]) == "[1234]"
    assert repr([nwk]) == "[1234]"

    with pytest.raises(ValueError):
        # Invalid values are not allowed
        class NwkWithoutHex(NwkAsHex, repr="foo"):
            pass


def test_optional():
    d, r = t.Optional(t.uint8_t).deserialize(b"")
    assert d is None
    assert r == b""

    d, r = t.Optional(t.uint8_t).deserialize(b"\x001234aaa")
    assert d == 0
    assert r == b"1234aaa"


def test_nodata():
    """Test No Data ZCL data type."""
    data = b"\xaa\x55\xbb"
    r, rest = t.NoData.deserialize(data)
    assert isinstance(r, t.NoData)
    assert rest == data

    assert t.NoData().serialize() == b""


def test_date():
    """Test Date ZCL data type."""
    year = t.uint8_t(70)
    month = t.uint8_t(1)
    day = t.uint8_t(1)
    dow = t.uint8_t(4)

    data = year.serialize() + month.serialize() + day.serialize() + dow.serialize()
    extra = b"\xaa\x55"

    r, rest = t.Date.deserialize(data + extra)
    assert rest == extra
    assert r.years_since_1900 == 70
    assert r.year == 1970
    assert r.month == 1
    assert r.day == 1
    assert r.day_of_week == 4

    assert r.serialize() == data
    r.year = 2020
    assert r.serialize()[0] == 2020 - 1900
    assert t.Date().year is None


def test_eui64():
    """Test EUI64."""
    data = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    extra = b"\xaa\x55"

    ieee, rest = t.EUI64.deserialize(data + extra)
    assert ieee[0] == 1
    assert ieee[1] == 2
    assert ieee[2] == 3
    assert ieee[3] == 4
    assert ieee[4] == 5
    assert ieee[5] == 6
    assert ieee[6] == 7
    assert ieee[7] == 8
    assert rest == extra
    assert ieee.serialize() == data


def test_eui64_convert():
    ieee = t.EUI64.convert("08:07:06:05:04:03:02:01")
    assert ieee[0] == 1
    assert ieee[1] == 2
    assert ieee[2] == 3
    assert ieee[3] == 4
    assert ieee[4] == 5
    assert ieee[5] == 6
    assert ieee[6] == 7
    assert ieee[7] == 8

    assert t.EUI64.convert(None) is None


def test_keydata():
    data = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    extra = b"extra"

    key, rest = t.KeyData.deserialize(data + extra)
    assert rest == extra
    assert key == t.KeyData.convert("00:01:02:03:04:05:06:07:08:09:0a:0b:0c:0d:0e:0f")
    assert repr(key) == "00:01:02:03:04:05:06:07:08:09:0a:0b:0c:0d:0e:0f"
    assert list(key) == list(data)
    assert key.serialize() == data
    assert t.KeyData(key) == key


def test_enum_uint():
    class TestBitmap(t.bitmap16):
        ALL = 0xFFFF
        CH_1 = 0x0001
        CH_2 = 0x0002
        CH_3 = 0x0004
        CH_5 = 0x0008
        CH_6 = 0x0010
        CH_Z = 0x8000

    extra = b"The rest of the data\x55\xaa"
    data = b"\x12\x80"

    r, rest = TestBitmap.deserialize(data + extra)
    assert rest == extra
    assert r == 0x8012
    assert r == (TestBitmap.CH_2 | TestBitmap.CH_6 | TestBitmap.CH_Z)

    assert r.serialize() == data
    assert TestBitmap(0x8012).serialize() == data

    r, _ = TestBitmap.deserialize(b"\x12\x84")
    assert r == 0x8412
    assert r.value == 0x8412
    assert TestBitmap.CH_2 in r
    assert TestBitmap.CH_6 in r
    assert TestBitmap.CH_Z in r


def test_enum_undef():
    class TestEnum(t.enum8):
        ALL = 0xAA

    data = b"\x55"
    extra = b"extra"

    r, rest = TestEnum.deserialize(data + extra)
    assert rest == extra
    assert r == 0x55
    assert r.value == 0x55
    assert r.name == "undefined_0x55"
    assert r.serialize() == data
    assert isinstance(r, TestEnum)

    r = TestEnum("85")
    assert r == 0x55
    assert r.value == 0x55
    assert r.name == "undefined_0x55"
    assert r.serialize() == data
    assert isinstance(r, TestEnum)

    r = TestEnum("0x55")
    assert r == 0x55
    assert r.value == 0x55
    assert r.name == "undefined_0x55"
    assert r.serialize() == data
    assert isinstance(r, TestEnum)


def test_enum():
    class TestEnum(t.enum8):
        ALL = 0x55
        ERR = 1

    data = b"\x55"
    extra = b"extra"

    r, rest = TestEnum.deserialize(data + extra)
    assert rest == extra
    assert r == 0x55
    assert r.value == 0x55
    assert r.name == "ALL"
    assert isinstance(r, TestEnum)
    assert TestEnum.ALL + TestEnum.ERR == 0x56

    r = TestEnum("85")
    assert r == 0x55
    assert r.value == 0x55
    assert r.name == "ALL"
    assert isinstance(r, TestEnum)
    assert TestEnum.ALL + TestEnum.ERR == 0x56

    r = TestEnum("0x55")
    assert r == 0x55
    assert r.value == 0x55
    assert r.name == "ALL"
    assert isinstance(r, TestEnum)
    assert TestEnum.ALL + TestEnum.ERR == 0x56


def test_enum_instance_types():
    class TestEnum(t.enum8):
        Member = 0x00

    assert TestEnum._member_type_ is t.uint8_t
    assert type(TestEnum.Member.value) is t.uint8_t
    assert isinstance(TestEnum.Member, t.uint8_t)
    assert issubclass(TestEnum, t.uint8_t)


def test_enum_formatting():
    class TestEnum(t.enum8):
        Member = 0x00

    assert f"{TestEnum.Member}" == "<TestEnum.Member: 0>"
    assert f"0x{TestEnum.Member:02X}" == "0x00"


def test_bitmap():
    """Test bitmaps."""

    class TestBitmap(t.bitmap16):
        CH_1 = 0x0010
        CH_2 = 0x0020
        CH_3 = 0x0040
        CH_4 = 0x0080
        ALL = 0x00F0

    extra = b"extra data\xaa\55"
    data = b"\xf0\x00"
    r, rest = TestBitmap.deserialize(data + extra)
    assert rest == extra
    assert r is TestBitmap.ALL
    assert r.name == "ALL"
    assert r.value == 0x00F0
    assert r.serialize() == data

    data = b"\x60\x00"
    r, rest = TestBitmap.deserialize(data + extra)
    assert rest == extra
    assert TestBitmap.CH_1 not in r
    assert TestBitmap.CH_2 in r
    assert TestBitmap.CH_3 in r
    assert TestBitmap.CH_4 not in r
    assert TestBitmap.ALL not in r
    assert r.value == 0x0060
    assert r.serialize() == data


def test_bitmap_undef():
    """Test bitmaps with some undefined flags."""

    class TestBitmap(t.bitmap16):
        CH_1 = 0x0010
        CH_2 = 0x0020
        CH_3 = 0x0040
        CH_4 = 0x0080
        ALL = 0x00F0

    extra = b"extra data\xaa\55"
    data = b"\x60\x0f"
    r, rest = TestBitmap.deserialize(data + extra)
    assert rest == extra
    assert TestBitmap.CH_1 not in r
    assert TestBitmap.CH_2 in r
    assert TestBitmap.CH_3 in r
    assert TestBitmap.CH_4 not in r
    assert TestBitmap.ALL not in r
    assert r.value == 0x0F60
    assert r.serialize() == data


def test_bitmap_instance_types():
    class TestBitmap(t.bitmap16):
        CH_1 = 0x0010
        CH_2 = 0x0020
        CH_3 = 0x0040
        CH_4 = 0x0080
        ALL = 0x00F0

    assert TestBitmap._member_type_ is t.uint16_t
    assert type(TestBitmap.ALL.value) is t.uint16_t
    assert isinstance(TestBitmap.ALL, t.uint16_t)
    assert issubclass(TestBitmap, t.uint16_t)
    assert isinstance(TestBitmap(0xFF00), t.uint16_t)
    assert isinstance(TestBitmap(0xFF00), TestBitmap)


def test_nwk_convert():
    assert t.NWK.convert(str(t.NWK(0x1234))[2:]) == t.NWK(0x1234)
    assert str(t.NWK(0x0012))[2:] == "0012"
    assert str(t.NWK(0x1200))[2:] == "1200"


def test_serializable_bytes():
    obj = t.SerializableBytes(b"test")
    assert obj == obj  # noqa: PLR0124
    assert obj == t.SerializableBytes(b"test")
    assert t.SerializableBytes(obj) == obj
    assert obj != b"test"
    assert obj.serialize() == b"test"
    assert "test" in repr([obj])

    with pytest.raises(TypeError):
        obj + b"test"

    with pytest.raises(ValueError):
        t.SerializableBytes("test")

    with pytest.raises(ValueError):
        t.SerializableBytes([1, 2, 3])
