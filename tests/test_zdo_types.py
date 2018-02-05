import pytest

import zigpy.types as t
import zigpy.zdo.types as types


def test_multi_address_3():
    ma = types.MultiAddress()
    ma.addrmode = 3
    ma.ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    ma.endpoint = 1
    ser = ma.serialize()

    ma2, data = types.MultiAddress.deserialize(ser)
    assert data == b''
    assert ma2.addrmode == ma.addrmode
    assert ma2.ieee == ma.ieee
    assert ma2.endpoint == ma.endpoint


def test_multi_address_1():
    ma = types.MultiAddress()
    ma.addrmode = 1
    ma.nwk = 123
    ser = ma.serialize()

    ma2, data = types.MultiAddress.deserialize(ser)
    assert data == b''
    assert ma2.addrmode == ma.addrmode
    assert ma2.nwk == ma.nwk


def test_multi_address_invalid():
    ma = types.MultiAddress()
    ma.addrmode = 255
    with pytest.raises(ValueError):
        ma.serialize()

    with pytest.raises(ValueError):
        types.MultiAddress.deserialize(b'\xffnot read')


def test_node_descriptor():
    data = b'\x00\x00\x01\x02\x02\x03\x04\x04\x05\x05\x06\x06\x07\xff'
    nd, data = types.NodeDescriptor.deserialize(data)

    assert data == b'\xff'


def test_size_prefixed_simple_descriptor():
    sd = types.SizePrefixedSimpleDescriptor()
    sd.endpoint = t.uint8_t(1)
    sd.profile = t.uint16_t(2)
    sd.device_type = t.uint16_t(3)
    sd.device_version = t.uint8_t(4)
    sd.input_clusters = t.LVList(t.uint16_t)([t.uint16_t(5), t.uint16_t(6)])
    sd.output_clusters = t.LVList(t.uint16_t)([t.uint16_t(7), t.uint16_t(8)])

    ser = sd.serialize()
    assert ser[0] == len(ser) - 1

    sd2, data = types.SizePrefixedSimpleDescriptor.deserialize(ser)
    assert sd.input_clusters == sd2.input_clusters
    assert sd.output_clusters == sd2.output_clusters


def test_empty_size_prefixed_simple_descriptor():
    r = types.SizePrefixedSimpleDescriptor.deserialize(b'\x00')
    assert r == (None, b'')
