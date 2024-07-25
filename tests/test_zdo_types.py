import pytest

import zigpy.types as t
from zigpy.zdo import types


def test_multi_address_3():
    ma = types.MultiAddress()
    ma.addrmode = 3
    ma.ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    ma.endpoint = 1
    ser = ma.serialize()

    assert "ieee" in repr(ma)
    assert "endpoint" in repr(ma)
    assert "nwk" not in repr(ma)

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

    assert "ieee" not in repr(ma)
    assert "endpoint" not in repr(ma)
    assert "nwk" in repr(ma)

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


def test_channels():
    """Test Channels bitmap."""

    assert t.Channels.from_channel_list([]) == t.Channels.NO_CHANNELS
    assert t.Channels.from_channel_list(range(11, 26 + 1)) == t.Channels.ALL_CHANNELS
    assert (
        t.Channels.from_channel_list([11, 21])
        == t.Channels.CHANNEL_11 | t.Channels.CHANNEL_21
    )

    with pytest.raises(ValueError):
        t.Channels.from_channel_list([11, 13, 10])  # 10 is not a valid channel

    with pytest.raises(ValueError):
        t.Channels.from_channel_list([27, 13, 15, 18])  # 27 is not a valid channel

    assert list(t.Channels.from_channel_list([11, 13, 25])) == [11, 13, 25]
    assert list(t.Channels.ALL_CHANNELS) == list(range(11, 26 + 1))
    assert list(t.Channels.NO_CHANNELS) == []

    for expected, channel in zip(t.Channels.ALL_CHANNELS, range(11, 26 + 1)):
        assert expected == channel

    # t.Channels.from_channel_list(another_channel) should be idempotent
    channels = t.Channels.from_channel_list([11, 13, 25])
    assert channels == t.Channels.from_channel_list(channels)

    # Even though this is a "valid" channels bitmap, it has unknown channels
    invalid_channels = t.Channels(0xFFFFFFFF)

    with pytest.raises(ValueError):
        list(invalid_channels)


def test_node_descriptor():
    data = b"\x00\x01\x02\x03\x03\x04\x05\x05\x06\x06\x07\x07\x08\xff"
    nd, rest = types.NodeDescriptor.deserialize(data)

    assert rest == b"\xff"

    new_node_desc = types.NodeDescriptor(nd)
    assert new_node_desc.logical_type == 0
    assert new_node_desc.complex_descriptor_available == 0
    assert new_node_desc.user_descriptor_available == 0
    assert new_node_desc.reserved == 0
    assert new_node_desc.aps_flags == 1
    assert new_node_desc.frequency_band == 0
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
    for field in types.NodeDescriptor.fields:
        nd = types.NodeDescriptor(0, 1, 2, 0x0303, 0x04, 0x0505, 0x0606, 0x0707, 0x08)
        assert nd.is_valid is True
        setattr(nd, field.name, None)
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
        assert getattr(nd, prop)


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


def test_node_descriptor_repr():
    nd = types.NodeDescriptor(
        0b11111010, 0xFF, 0xFF, 0xFFFF, 0xFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFF
    )
    assert nd.is_coordinator is False
    assert "*is_coordinator=False" in repr(nd)

    assert nd.is_end_device is True
    assert "*is_end_device=True" in repr(nd)

    assert nd.is_router is False
    assert "*is_router=False" in repr(nd)


def test_size_prefixed_simple_descriptor():
    sd = types.SizePrefixedSimpleDescriptor()
    sd.endpoint = t.uint8_t(1)
    sd.profile = t.uint16_t(2)
    sd.device_type = t.uint16_t(3)
    sd.device_version = t.uint8_t(4)
    sd.input_clusters = t.LVList[t.uint16_t]([t.uint16_t(5), t.uint16_t(6)])
    sd.output_clusters = t.LVList[t.uint16_t]([t.uint16_t(7), t.uint16_t(8)])

    ser = sd.serialize()
    assert ser[0] == len(ser) - 1

    sd2, data = types.SizePrefixedSimpleDescriptor.deserialize(ser + b"extra")
    assert sd.input_clusters == sd2.input_clusters
    assert sd.output_clusters == sd2.output_clusters
    assert isinstance(sd2, types.SizePrefixedSimpleDescriptor)
    assert data == b"extra"


def test_empty_size_prefixed_simple_descriptor():
    r = types.SizePrefixedSimpleDescriptor.deserialize(b"\x00")
    assert r == (None, b"")


def test_invalid_size_prefixed_simple_descriptor():
    with pytest.raises(ValueError):
        types.SizePrefixedSimpleDescriptor.deserialize(b"\x01")


def test_status_undef():
    data = b"\xff"
    extra = b"extra"

    status, rest = types.Status.deserialize(data + extra)
    assert rest == extra
    assert status == 0xFF
    assert status.value == 0xFF
    assert status.name == "undefined_0xff"
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
    assert not hdr.is_reply

    hdr.command_id = types.ZDOCmd.Bind_rsp
    assert hdr.is_reply

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


def test_status_enum():
    """Test Status enums chaining."""
    status_names = [e.name for e in types.Status]
    aps_names = [e.name for e in t.APSStatus]
    nwk_names = [e.name for e in t.NWKStatus]
    mac_names = [e.name for e in t.MACStatus]

    status = types.Status(0x80)
    assert status.name in status_names
    assert status.name not in aps_names
    assert status.name not in nwk_names
    assert status.name not in mac_names

    status = types.Status(0xAE)
    assert status.name not in status_names
    assert status.name in aps_names
    assert status.name not in nwk_names
    assert status.name not in mac_names

    status = types.Status(0xD0)
    assert status.name not in status_names
    assert status.name not in aps_names
    assert status.name in nwk_names
    assert status.name not in mac_names

    status = types.Status(0xE9)
    assert status.name not in status_names
    assert status.name not in aps_names
    assert status.name not in nwk_names
    assert status.name in mac_names

    status = types.Status(0xFF)
    assert status.name not in status_names
    assert status.name not in aps_names
    assert status.name not in nwk_names
    assert status.name not in mac_names
    assert status.name == "undefined_0xff"


def test_neighbors():
    """Test ZDO neignbors struct."""

    data = (
        b"\x05\x00\x03\xa2\xaf\x8cY\xf5\x03\x96\xb4:p\x07\xfe\xffW\xb4\x14\xd1"
        b"\xb7\x12\x01\x01H\xa2\xaf\x8cY\xf5\x03\x96\xb4X\xb76\x02\x00\x8d\x15\x00=X"
        b"\x12\x01\x01:\xa2\xaf\x8cY\xf5\x03\x96\xb4\x9b-0\xfe\xff\xbd\x1b\xec$\xcb\x12"
        b"\x01\x01F"
    )
    extra = b"\x55\xaaextra\x00"
    neighbours, rest = types.Neighbors().deserialize(data + extra)
    assert rest == extra


def test_neighbor():
    """Test neighbor struct."""
    data = b"\xa2\xaf\x8cY\xf5\x03\x96\xb4:p\x07\xfe\xffW\xb4\x14\xd1\xb7\x12\x01\x01H"
    extra = b"\x55\xaaextra\x00"

    neighbor, rest = types.Neighbor.deserialize(data + extra)
    assert rest == extra

    assert str(neighbor.extended_pan_id) == "b4:96:03:f5:59:8c:af:a2"
    assert str(neighbor.ieee) == "14:b4:57:ff:fe:07:70:3a"
    assert neighbor.nwk == 0xB7D1
    assert neighbor.device_type == types.Neighbor.DeviceType.EndDevice
    assert neighbor.rx_on_when_idle == types.Neighbor.RxOnWhenIdle.Off
    assert neighbor.relationship == types.Neighbor.RelationShip.Child
    assert neighbor.reserved1 == 0
    assert neighbor.permit_joining == types.Neighbor.PermitJoins.Accepting
    assert neighbor.reserved2 == 0
    assert neighbor.device_type == types.Neighbor.DeviceType.EndDevice
    assert neighbor.relationship == types.Neighbor.RelationShip.Child
    assert neighbor.rx_on_when_idle == types.Neighbor.RxOnWhenIdle.Off
    assert neighbor.permit_joining == 1
    assert neighbor.depth == 1
    assert neighbor.lqi == 72


def test_neighbor_struct_device_type():
    """Test neighbor packed struct device_type."""

    for dev_type in range(3):
        struct = types.Neighbor()
        assert struct.device_type is None
        struct.device_type = dev_type
        assert struct.device_type == dev_type

    for i in range(127):
        struct = types.Neighbor(**types.Neighbor._parse_packed(i))
        orig_rx = struct.rx_on_when_idle
        orig_rel = struct.relationship
        for dev_type in range(3):
            struct.device_type = dev_type
            assert struct.rx_on_when_idle == orig_rx
            assert struct.relationship == orig_rel
            assert struct.device_type == dev_type


def test_neighbor_struct_rx_on_when_idle():
    """Test neighbor packed struct rx_on_when_idle."""

    for rx_on_when_idle in range(3):
        struct = types.Neighbor()
        assert struct.rx_on_when_idle is None
        struct.rx_on_when_idle = rx_on_when_idle
        assert struct.rx_on_when_idle == rx_on_when_idle

    for i in range(127):
        struct = types.Neighbor(**types.Neighbor._parse_packed(i))
        orig_dev_type = struct.device_type
        orig_rel = struct.relationship
        for rx_on_when_idle in range(3):
            struct.rx_on_when_idle = rx_on_when_idle
            assert struct.device_type == orig_dev_type
            assert struct.relationship == orig_rel
            assert struct.rx_on_when_idle == rx_on_when_idle


def test_neighbor_struct_relationship():
    """Test neighbor packed struct relationship."""

    for relationship in range(7):
        struct = types.Neighbor()
        assert struct.relationship is None
        struct.relationship = relationship
        assert struct.relationship == relationship

    for i in range(127):
        struct = types.Neighbor(**types.Neighbor._parse_packed(i))
        orig_dev_type = struct.device_type
        orig_rx = struct.rx_on_when_idle
        for relationship in range(7):
            struct.relationship = relationship
            assert struct.device_type == orig_dev_type
            assert struct.rx_on_when_idle == orig_rx
            assert struct.relationship == relationship
