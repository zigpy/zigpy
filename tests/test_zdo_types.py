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
    assert data == b""
    assert ma2.addrmode == ma.addrmode
    assert ma2.ieee == ma.ieee
    assert ma2.endpoint == ma.endpoint


def test_multi_address_1():
    ma = types.MultiAddress()
    ma.addrmode = 1
    ma.nwk = 123
    ser = ma.serialize()

    ma2, data = types.MultiAddress.deserialize(ser)
    assert data == b""
    assert ma2.addrmode == ma.addrmode
    assert ma2.nwk == ma.nwk


def test_multi_address_invalid():
    ma = types.MultiAddress()
    ma.addrmode = 255
    with pytest.raises(ValueError):
        ma.serialize()

    with pytest.raises(ValueError):
        types.MultiAddress.deserialize(b"\xffnot read")


def test_node_descriptor():
    data = b"\x00\x01\x02\x03\x03\x04\x05\x05\x06\x06\x07\x07\x08\xff"
    nd, rest = types.NodeDescriptor.deserialize(data)

    assert rest == b"\xff"

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

    nd2 = types.NodeDescriptor(0, 1, 2, 0x0303, 0x04, 0x0505, 0x0606, 0x0707, 0x08)
    assert nd2.serialize() == new_node_desc.serialize()


def test_node_descriptor_is_valid():
    for field in types.NodeDescriptor._fields:
        nd = types.NodeDescriptor(0, 1, 2, 0x0303, 0x04, 0x0505, 0x0606, 0x0707, 0x08)
        assert nd.is_valid is True
        setattr(nd, field[0], None)
        assert nd.is_valid is False


def test_node_descriptor_props():
    props = (
        "logical_type",
        "complex_descriptor_available",
        "user_descriptor_available",
        "is_alternate_pan_coordinator",
        "is_full_function_device",
        "is_mains_powered",
        "is_receiver_on_when_idle",
        "is_security_capable",
        "allocate_address",
    )

    empty_nd = types.NodeDescriptor()
    for prop in props:
        value = getattr(empty_nd, prop)
        assert value is None

    nd = types.NodeDescriptor(
        0b11111000, 0xFF, 0xFF, 0xFFFF, 0xFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFF
    )
    assert nd.logical_type is not None
    for prop in props:
        if prop == "logical_type":
            continue
        value = getattr(nd, prop)
        assert value is True


def test_node_descriptor_logical_types():
    nd = types.NodeDescriptor()
    assert nd.is_coordinator is None
    assert nd.is_end_device is None
    assert nd.is_router is None

    nd = types.NodeDescriptor(
        0b11111000, 0xFF, 0xFF, 0xFFFF, 0xFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFF
    )
    assert nd.is_coordinator is True
    assert nd.is_end_device is False
    assert nd.is_router is False

    nd = types.NodeDescriptor(
        0b11111001, 0xFF, 0xFF, 0xFFFF, 0xFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFF
    )
    assert nd.is_coordinator is False
    assert nd.is_end_device is False
    assert nd.is_router is True

    nd = types.NodeDescriptor(
        0b11111010, 0xFF, 0xFF, 0xFFFF, 0xFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFF
    )
    assert nd.is_coordinator is False
    assert nd.is_end_device is True
    assert nd.is_router is False


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
    r = types.SizePrefixedSimpleDescriptor.deserialize(b"\x00")
    assert r == (None, b"")


def test_status_undef():
    data = b"\xaa"
    extra = b"extra"

    status, rest = types.Status.deserialize(data + extra)
    assert rest == extra
    assert status == 0xAA
    assert status.value == 0xAA
    assert status.name == "undefined_0xaa"
    assert isinstance(status, types.Status)


def test_zdo_header():
    tsn = t.uint8_t(0xAA)
    cmd_id = 0x55
    data = tsn.serialize()
    extra = b"abcdefExtraDataHere"
    hdr, rest = types.ZDOHeader.deserialize(cmd_id, data + extra)
    assert rest == extra
    assert hdr.tsn == tsn
    assert hdr.command_id == cmd_id
    assert hdr.is_reply is False

    hdr.command_id = types.ZDOCmd.Bind_rsp
    assert hdr.is_reply is True

    assert hdr.serialize() == data

    new_tsn = 0xBB
    hdr.tsn = new_tsn
    assert isinstance(hdr.tsn, t.uint8_t)
    assert hdr.tsn == new_tsn


def test_zdo_header_cmd_id():
    unk_cmd = 0x00FF
    assert unk_cmd not in list(types.ZDOCmd)
    hdr = types.ZDOHeader(unk_cmd, 0x55)
    assert isinstance(hdr.command_id, types.ZDOCmd)
    assert hdr.command_id == unk_cmd

    unk_cmd += 1
    assert unk_cmd not in list(types.ZDOCmd)
    hdr.command_id = unk_cmd
    assert isinstance(hdr.command_id, types.ZDOCmd)
    assert hdr.command_id == unk_cmd


def test_nwkupdate():
    """Test NwkUpdate class."""

    extra = b"extra data\xaa\x55"

    upd = types.NwkUpdate(t.Channels.ALL_CHANNELS, 0x05, 0x04, 0xAA, 0x1234)
    data = upd.serialize()
    assert data == b"\x00\xf8\xff\x07\x05\x04"

    new, rest = types.NwkUpdate.deserialize(data + extra)
    assert rest == extra
    assert new.ScanChannels == t.Channels.ALL_CHANNELS
    assert new.ScanDuration == 0x05
    assert new.ScanCount == 0x04
    assert new.nwkUpdateId is None
    assert new.nwkManagerAddr is None


def test_nwkupdate_nwk_update_id():
    """Test NwkUpdate class."""

    extra = b"extra data\xaa\x55"

    upd = types.NwkUpdate(t.Channels.ALL_CHANNELS, 0xFE, 0x04, 0xAA, 0x1234)
    data = upd.serialize()
    assert data == b"\x00\xf8\xff\x07\xfe\xaa"

    new, rest = types.NwkUpdate.deserialize(data + extra)
    assert rest == extra
    assert new.ScanChannels == t.Channels.ALL_CHANNELS
    assert new.ScanDuration == 0xFE
    assert new.ScanCount is None
    assert new.nwkUpdateId == 0xAA
    assert new.nwkManagerAddr is None

    upd = types.NwkUpdate(t.Channels.ALL_CHANNELS, 0xFF, 0x04, 0xAA, 0x1234)
    data = upd.serialize()
    assert data == b"\x00\xf8\xff\x07\xff\xaa\x34\x12"

    new, rest = types.NwkUpdate.deserialize(data + extra)
    assert rest == extra
    assert new.ScanChannels == t.Channels.ALL_CHANNELS
    assert new.ScanDuration == 0xFF
    assert new.ScanCount is None
    assert new.nwkUpdateId == 0xAA
    assert new.nwkManagerAddr == 0x1234
