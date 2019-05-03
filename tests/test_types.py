import itertools
import pytest

import zigpy.types as t


def test_single():
    v = t.Single(1.25)
    ser = v.serialize()
    assert t.Single.deserialize(ser) == (1.25, b'')


def test_double():
    v = t.Double(1.25)
    ser = v.serialize()
    assert t.Double.deserialize(ser) == (1.25, b'')


def test_lvbytes():
    d, r = t.LVBytes.deserialize(b'\x0412345')
    assert r == b'5'
    assert d == b'1234'

    assert t.LVBytes.serialize(d) == b'\x041234'


def test_lvbytes_too_long():
    to_serialize = b''.join(itertools.repeat(b'\xbe', 255))
    with pytest.raises(ValueError):
        t.LVBytes(to_serialize).serialize()


def test_long_octet_string_too_long():
    to_serialize = b''.join(itertools.repeat(b'\xbe', 65535))
    with pytest.raises(ValueError):
        t.LongOctetString(to_serialize).serialize()


def test_lvbytes_0_len():
    to_deserialize = b'\x00abcdef'
    r, rest = t.LVBytes.deserialize(to_deserialize)
    assert r == b''
    assert rest == b'abcdef'
    assert t.LVBytes(b'').serialize() == b'\00'


def test_character_string():
    d, r = t.CharacterString.deserialize(b'\x0412345')
    assert r == b'5'
    assert d == '1234'

    assert t.CharacterString.serialize(d) == b'\x041234'

    # test null char stripping
    d, _ = t.CharacterString.deserialize(b'\x05abc\x00ef')
    assert d == 'abc'


def test_character_string_decode_failure():
    d, _ = t.CharacterString.deserialize(b'\x04\xf9123\xff\xff45')
    assert d == '�123'


def test_char_string_0_len():
    to_deserialize = b'\x00abcdef'
    r, rest = t.CharacterString.deserialize(to_deserialize)
    assert r == ''
    assert rest == b'abcdef'
    assert t.CharacterString('').serialize() == b'\00'


def test_char_string_too_long():
    to_serialize = ''.join(itertools.repeat('a', 255))
    with pytest.raises(ValueError):
        t.CharacterString(to_serialize).serialize()


def test_long_char_string_too_long():
    to_serialize = ''.join(itertools.repeat('a', 65535))
    with pytest.raises(ValueError):
        t.LongCharacterString(to_serialize).serialize()


def test_limited_char_string():
    assert t.LimitedCharString(5)('12345').serialize() == b'\x0512345'
    with pytest.raises(ValueError):
        t.LimitedCharString(5)('123456').serialize()


def test_lvlist():
    d, r = t.LVList(t.uint8_t).deserialize(b'\x0412345')
    assert r == b'5'
    assert d == list(map(ord, '1234'))
    assert t.LVList(t.uint8_t).serialize(d) == b'\x041234'


def test_list():
    expected = list(map(ord, '\x0123'))
    assert t.List(t.uint8_t).deserialize(b'\x0123') == (expected, b'')


def test_struct():
    class TestStruct(t.Struct):
        _fields = [('a', t.uint8_t), ('b', t.uint8_t)]

    ts = TestStruct()
    ts.a = t.uint8_t(0xaa)
    ts.b = t.uint8_t(0xbb)
    ts2 = TestStruct(ts)
    assert ts2.a == ts.a
    assert ts2.b == ts.b

    r = repr(ts)
    assert 'TestStruct' in r
    assert r.startswith('<') and r.endswith('>')

    s = ts2.serialize()
    assert s == b'\xaa\xbb'


def test_hex_repr():
    class NwkAsHex(t.HexRepr, t.uint16_t):
        _hex_len = 4
    nwk = NwkAsHex(0x1234)
    assert str(nwk) == '0x1234'
    assert repr(nwk) == '0x1234'
