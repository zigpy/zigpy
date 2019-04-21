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
    data = b'\x00\x01\x02\x03\x03\x04\x05\x05\x06\x06\x07\x07\x08\xff'
    nd, rest = types.NodeDescriptor.deserialize(data)

    assert rest == b'\xff'

    new_node_desc = types.NodeDescriptor(nd)
    assert new_node_desc.byte1 == 0
    assert new_node_desc.byte2 == 1
    assert new_node_desc.mac_capability_flags == 0x02
    assert new_node_desc.manufacturer_code == 0x0303
    assert new_node_desc.maximum_buffer_size == 0x04
    assert new_node_desc.maximum_incoming_transfer_size == 0x0505
    assert new_node_desc.server_mask == 0x0606
    assert new_node_desc.maximum_outgoing_transfer_size == 0x0707
    assert new_node_desc.descriptor_capability_field == 0x08

    nd2 = types.NodeDescriptor(
        0, 1, 2, 0x0303, 0x04, 0x0505, 0x0606, 0x0707, 0x08)
    assert nd2.serialize() == new_node_desc.serialize()


def test_node_descriptor_is_valid():
    for field in types.NodeDescriptor._fields:
        nd = types.NodeDescriptor(
            0, 1, 2, 0x0303, 0x04, 0x0505, 0x0606, 0x0707, 0x08)
        assert nd.is_valid is True
        setattr(nd, field[0], None)
        assert nd.is_valid is False


def test_node_descriptor_props():
    props = (
        'logical_type', 'complex_descriptor_available',
        'user_descriptor_available', 'is_alternate_pan_coordinator',
        'is_full_function_device', 'is_mains_powered',
        'is_receiver_on_when_idle', 'is_security_capable', 'allocate_address'
    )

    empty_nd = types.NodeDescriptor()
    for prop in props:
        value = getattr(empty_nd, prop)
        assert value is None

    nd = types.NodeDescriptor(
        0b11111000, 0xff, 0xff, 0xffff, 0xff, 0xffff, 0xffff, 0xffff, 0xff)
    assert nd.logical_type is not None
    for prop in props:
        if prop == 'logical_type':
            continue
        value = getattr(nd, prop)
        assert value is True


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
