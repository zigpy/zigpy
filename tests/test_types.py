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
