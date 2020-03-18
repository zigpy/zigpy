from unittest import mock

import pytest
import zigpy.endpoint
import zigpy.types as t
import zigpy.zcl as zcl
import zigpy.zcl.foundation as foundation

DEFAULT_TSN = 123


@pytest.fixture
def endpoint():
    ep = zigpy.endpoint.Endpoint(mock.MagicMock(), 1)
    ep.add_input_cluster(0)
    ep.add_input_cluster(3)
    return ep


def test_deserialize_general(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x00\x01\x00")
    assert hdr.tsn == 1
    assert hdr.command_id == 0
    assert hdr.is_reply is False


def test_deserialize_general_unknown(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x00\x01\xff")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is True
    assert hdr.frame_control.is_cluster is False
    assert hdr.command_id == 255
    assert hdr.is_reply is False


def test_deserialize_cluster(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x01\x01\x00xxx")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is False
    assert hdr.frame_control.is_cluster is True
    assert hdr.command_id == 0
    assert hdr.is_reply is False


def test_deserialize_cluster_client(endpoint):
    hdr, args = endpoint.deserialize(3, b"\x09\x01\x00AB")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is False
    assert hdr.frame_control.is_cluster is True
    assert hdr.command_id == 0
    assert hdr.is_reply is True
    assert args == [0x4241]


def test_deserialize_cluster_unknown(endpoint):
    with pytest.raises(KeyError):
        endpoint.deserialize(0xFF00, b"\x05\x00\x00\x01\x00")


def test_deserialize_cluster_command_unknown(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x01\x01\xff")
    assert hdr.tsn == 1
    assert hdr.command_id == 255
    assert hdr.is_reply is False


def test_unknown_cluster():
    c = zcl.Cluster.from_id(None, 999)
    assert isinstance(c, zcl.Cluster)
    assert c.cluster_id == 999


def test_manufacturer_specific_cluster():
    import zigpy.zcl.clusters.manufacturer_specific as ms

    c = zcl.Cluster.from_id(None, 0xFC00)
    assert isinstance(c, ms.ManufacturerSpecificCluster)
    assert hasattr(c, "cluster_id")
    c = zcl.Cluster.from_id(None, 0xFFFF)
    assert isinstance(c, ms.ManufacturerSpecificCluster)
    assert hasattr(c, "cluster_id")


@pytest.fixture
def cluster_by_id():
    def _cluster(cluster_id=0):
        epmock = mock.MagicMock()
        epmock._device.application.get_sequence.return_value = DEFAULT_TSN
        epmock.device.application.get_sequence.return_value = DEFAULT_TSN
        return zcl.Cluster.from_id(epmock, cluster_id)

    return _cluster


@pytest.fixture
def cluster(cluster_by_id):
    return cluster_by_id(0)


@pytest.fixture
def client_cluster():
    epmock = mock.MagicMock()
    epmock._device._application.get_sequence.return_value = DEFAULT_TSN
    return zcl.Cluster.from_id(epmock, 3)


def test_request_general(cluster):
    cluster.request(True, 0, [])
    assert cluster._endpoint.request.call_count == 1


def test_request_manufacturer(cluster):
    cluster.request(True, 0, [t.uint8_t], 1)
    assert cluster._endpoint.request.call_count == 1
    org_size = len(cluster._endpoint.request.call_args[0][2])
    cluster.request(True, 0, [t.uint8_t], 1, manufacturer=1)
    assert cluster._endpoint.request.call_count == 2
    assert org_size + 2 == len(cluster._endpoint.request.call_args[0][2])


async def test_request_optional(cluster):
    schema = [t.uint8_t, t.uint16_t, t.Optional(t.uint16_t), t.Optional(t.uint8_t)]

    res = cluster.request(True, 0, schema)
    assert isinstance(res.exception(), ValueError)
    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()

    res = cluster.request(True, 0, schema, 1)
    assert isinstance(res.exception(), ValueError)
    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()

    cluster.request(True, 0, schema, 1, 2)
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    cluster.request(True, 0, schema, 1, 2, 3)
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    cluster.request(True, 0, schema, 1, 2, 3, 4)
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    res = cluster.request(True, 0, schema, 1, 2, 3, 4, 5)
    assert isinstance(res.exception(), ValueError)
    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()


def test_reply_general(cluster):
    cluster.reply(False, 0, [])
    assert cluster._endpoint.reply.call_count == 1


def test_reply_manufacturer(cluster):
    cluster.reply(False, 0, [t.uint8_t], 1)
    assert cluster._endpoint.reply.call_count == 1
    org_size = len(cluster._endpoint.reply.call_args[0][2])
    cluster.reply(False, 0, [t.uint8_t], 1, manufacturer=1)
    assert cluster._endpoint.reply.call_count == 2
    assert org_size + 2 == len(cluster._endpoint.reply.call_args[0][2])


def test_attribute_report(cluster):
    attr = zcl.foundation.Attribute()
    attr.attrid = 4
    attr.value = zcl.foundation.TypeValue()
    attr.value.value = "manufacturer"
    hdr = mock.MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = foundation.Command.Report_Attributes
    hdr.frame_control.is_general = True
    hdr.frame_control.is_cluster = False
    cluster.handle_message(hdr, [[attr]])
    assert cluster._attr_cache[4] == "manufacturer"

    attr.attrid = 0x89AB
    cluster.handle_message(hdr, [[attr]])
    assert cluster._attr_cache[attr.attrid] == "manufacturer"


def test_handle_request_unknown(cluster):
    hdr = mock.MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = mock.sentinel.command_id
    hdr.frame_control.is_general = True
    hdr.frame_control.is_cluster = False
    cluster.listener_event = mock.MagicMock()
    cluster._update_attribute = mock.MagicMock()
    cluster.handle_cluster_general_request = mock.MagicMock()
    cluster.handle_cluster_request = mock.MagicMock()
    cluster.handle_message(hdr, mock.sentinel.args)

    assert cluster.listener_event.call_count == 1
    assert cluster.listener_event.call_args[0][0] == "general_command"
    assert cluster._update_attribute.call_count == 0
    assert cluster.handle_cluster_general_request.call_count == 1
    assert cluster.handle_cluster_request.call_count == 0


def test_handle_cluster_request(cluster):
    hdr = mock.MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = mock.sentinel.command_id
    hdr.frame_control.is_general = False
    hdr.frame_control.is_cluster = True
    hdr.command_id.is_general = False
    cluster.listener_event = mock.MagicMock()
    cluster._update_attribute = mock.MagicMock()
    cluster.handle_cluster_general_request = mock.MagicMock()
    cluster.handle_cluster_request = mock.MagicMock()
    cluster.handle_message(hdr, mock.sentinel.args)

    assert cluster.listener_event.call_count == 1
    assert cluster.listener_event.call_args[0][0] == "cluster_command"
    assert cluster._update_attribute.call_count == 0
    assert cluster.handle_cluster_general_request.call_count == 0
    assert cluster.handle_cluster_request.call_count == 1


def _mk_rar(attrid, value, status=0):
    r = zcl.foundation.ReadAttributeRecord()
    r.attrid = attrid
    r.status = status
    r.value = zcl.foundation.TypeValue()
    r.value.value = value
    return r


async def test_read_attributes_uncached(cluster):
    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        rar0 = _mk_rar(0, 99)
        rar4 = _mk_rar(4, "Manufacturer")
        rar99 = _mk_rar(99, None, 1)
        rar199 = _mk_rar(199, 199)
        return [[rar0, rar4, rar99, rar199]]

    cluster.request = mockrequest
    success, failure = await cluster.read_attributes([0, "manufacturer", 99, 199])
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert failure[99] == 1
    assert success[199] == 199


async def test_read_attributes_cached(cluster):
    cluster.request = mock.MagicMock()
    cluster._attr_cache[0] = 99
    cluster._attr_cache[4] = "Manufacturer"
    success, failure = await cluster.read_attributes(
        [0, "manufacturer"], allow_cache=True
    )
    assert cluster.request.call_count == 0
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert failure == {}


async def test_read_attributes_mixed_cached(cluster):
    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        rar5 = _mk_rar(5, "Model")
        return [[rar5]]

    cluster.request = mockrequest
    cluster._attr_cache[0] = 99
    cluster._attr_cache[4] = "Manufacturer"
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", "model"], allow_cache=True
    )
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert success["model"] == "Model"
    assert failure == {}


async def test_read_attributes_default_response(cluster):
    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        return [0xC1]

    cluster.request = mockrequest
    success, failure = await cluster.read_attributes([0, 5, 23], allow_cache=False)
    assert success == {}
    assert failure == {0: 0xC1, 5: 0xC1, 23: 0xC1}


async def test_item_access_attributes(cluster):
    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        rar5 = _mk_rar(5, "Model")
        return [[rar5]]

    cluster.request = mockrequest
    cluster._attr_cache[0] = 99

    v = await cluster["model"]
    assert v == "Model"
    v = await cluster["zcl_version"]
    assert v == 99
    with pytest.raises(KeyError):
        v = await cluster[99]


def test_write_attributes(cluster):
    cluster.write_attributes({0: 5, "app_version": 4})
    assert cluster._endpoint.request.call_count == 1


def test_write_wrong_attribute(cluster):
    cluster.write_attributes({0xFF: 5})
    assert cluster._endpoint.request.call_count == 1


def test_write_attributes_wrong_type(cluster):
    cluster.write_attributes({18: 2})
    assert cluster._endpoint.request.call_count == 1


@pytest.mark.parametrize(
    "cluster_id, attr, value, serialized",
    (
        (0, "zcl_version", 0xAA, b"\x00\x00\x20\xaa"),
        (0, "model", "model x", b"\x05\x00\x42\x07model x"),
        (0, "device_enabled", True, b"\x12\x00\x10\x01"),
        (0, "alarm_mask", 0x55, b"\x13\x00\x18\x55"),
        (0x0202, "fan_mode", 0xDE, b"\x00\x00\x30\xde"),
    ),
)
def test_write_attribute_types(cluster_id, attr, value, serialized, cluster_by_id):
    cluster = cluster_by_id(cluster_id)
    cluster.write_attributes({attr: value})
    assert cluster._endpoint.reply.call_count == 0
    assert cluster._endpoint.request.call_count == 1
    assert cluster.endpoint.request.call_args[0][2][3:] == serialized


def test_read_attributes_response(cluster):
    cluster.read_attributes_rsp({0: 5})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0


def test_read_attributes_resp_unsupported(cluster):
    cluster.read_attributes_rsp({0: 5})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0
    orig_len = len(cluster._endpoint.reply.call_args[0][2])

    cluster.read_attributes_rsp({0: 5, 2: None})
    assert cluster._endpoint.reply.call_count == 2
    assert cluster._endpoint.request.call_count == 0
    assert len(cluster._endpoint.reply.call_args[0][2]) == orig_len + 3


def test_read_attributes_resp_str(cluster):
    cluster.read_attributes_rsp({"hw_version": 32})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0


def test_read_attributes_resp_exc(cluster):
    with mock.patch.object(foundation.DATA_TYPES, "pytype_to_datatype_id") as mck:
        mck.side_effect = ValueError
        cluster.read_attributes_rsp({"hw_version": 32})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0
    assert cluster.endpoint.reply.call_args[0][2][-3:] == b"\x03\x00\x86"


@pytest.mark.parametrize(
    "cluster_id, attr, value, serialized",
    (
        (0, "zcl_version", 0xAA, b"\x00\x00\x00\x20\xaa"),
        (0, "model", "model x", b"\x05\x00\x00\x42\x07model x"),
        (0, "device_enabled", True, b"\x12\x00\x00\x10\x01"),
        (0, "alarm_mask", 0x55, b"\x13\x00\x00\x18\x55"),
        (0x0202, "fan_mode", 0xDE, b"\x00\x00\x00\x30\xde"),
    ),
)
def test_read_attribute_resp(cluster_id, attr, value, serialized, cluster_by_id):
    cluster = cluster_by_id(cluster_id)
    cluster.read_attributes_rsp({attr: value})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0
    assert cluster.endpoint.reply.call_args[0][2][3:] == serialized


def test_bind(cluster):
    cluster.bind()


def test_unbind(cluster):
    cluster.unbind()


def test_configure_reporting(cluster):
    cluster.configure_reporting(0, 10, 20, 1)


def test_configure_reporting_named(cluster):
    cluster.configure_reporting("zcl_version", 10, 20, 1)
    assert cluster._endpoint.request.call_count == 1


def test_configure_reporting_wrong_named(cluster):
    cluster.configure_reporting("wrong_attr_name", 10, 20, 1)
    assert cluster._endpoint.request.call_count == 0


def test_configure_reporting_wrong_attrid(cluster):
    cluster.configure_reporting(0xFFFE, 10, 20, 1)
    assert cluster._endpoint.request.call_count == 0


def test_configure_reporting_manuf():
    ep = mock.MagicMock()
    cluster = zcl.Cluster.from_id(ep, 6)
    cluster.request = mock.MagicMock(name="request")
    cluster.configure_reporting(0, 10, 20, 1)
    cluster.request.assert_called_with(
        True,
        0x06,
        mock.ANY,
        mock.ANY,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=mock.ANY,
    )

    cluster.request.reset_mock()
    manufacturer_id = 0xFCFC
    cluster.configure_reporting(0, 10, 20, 1, manufacturer=manufacturer_id)
    cluster.request.assert_called_with(
        True,
        0x06,
        mock.ANY,
        mock.ANY,
        expect_reply=True,
        manufacturer=manufacturer_id,
        tries=1,
        tsn=mock.ANY,
    )
    assert cluster.request.call_count == 1


@pytest.mark.parametrize(
    "cluster_id, attr, data_type",
    (
        (0, "zcl_version", 0x20),
        (0, "model", 0x42),
        (0, "device_enabled", 0x10),
        (0, "alarm_mask", 0x18),
        (0x0202, "fan_mode", 0x30),
    ),
)
def test_configure_reporting_types(cluster_id, attr, data_type, cluster_by_id):
    cluster = cluster_by_id(cluster_id)
    cluster.configure_reporting(attr, 0x1234, 0x2345, 0xAA)
    assert cluster._endpoint.reply.call_count == 0
    assert cluster._endpoint.request.call_count == 1
    assert cluster.endpoint.request.call_args[0][2][6] == data_type


def test_command(cluster):
    cluster.command(0x00)
    assert cluster._endpoint.request.call_count == 1
    assert cluster._endpoint.request.call_args[0][1] == DEFAULT_TSN


def test_command_override_tsn(cluster):
    cluster.command(0x00, tsn=22)
    assert cluster._endpoint.request.call_count == 1
    assert cluster._endpoint.request.call_args[0][1] == 22


def test_command_attr(cluster):
    cluster.reset_fact_default()
    assert cluster._endpoint.request.call_count == 1


def test_client_command_attr(client_cluster):
    client_cluster.identify_query_response(0)
    assert client_cluster._endpoint.reply.call_count == 1


def test_command_invalid_attr(cluster):
    with pytest.raises(AttributeError):
        cluster.no_such_command()


async def test_invalid_arguments_cluster_command(cluster):
    res = cluster.command(0x00, 1)
    assert isinstance(res.exception(), ValueError)


def test_invalid_arguments_cluster_client_command(client_cluster):
    client_cluster.client_command(0, 0, 0)
    assert client_cluster._endpoint.reply.call_count == 1


def test_name(cluster):
    assert cluster.name == "Basic"


def test_commands(cluster):
    assert cluster.commands == ["reset_fact_default"]


def test_general_command(cluster):
    cluster.request = mock.MagicMock()
    cluster.reply = mock.MagicMock()
    s = mock.sentinel
    cmd_id = 0x0C
    cluster.general_command(cmd_id, s.start, s.items, manufacturer=0x4567)

    assert cluster.reply.call_count == 0
    assert cluster.request.call_count == 1
    cluster.request.assert_called_with(
        True,
        cmd_id,
        mock.ANY,
        s.start,
        s.items,
        expect_reply=True,
        manufacturer=0x4567,
        tries=1,
        tsn=mock.ANY,
    )


def test_general_command_reply(cluster):
    cluster.request = mock.MagicMock()
    cluster.reply = mock.MagicMock()
    cmd_id = 0x0D
    cluster.general_command(cmd_id, True, [], manufacturer=0x4567)

    assert cluster.request.call_count == 0
    assert cluster.reply.call_count == 1
    cluster.reply.assert_called_with(
        True, cmd_id, mock.ANY, True, [], manufacturer=0x4567, tsn=None
    )

    cluster.request.reset_mock()
    cluster.reply.reset_mock()
    cluster.general_command(
        cmd_id, True, [], manufacturer=0x4567, tsn=mock.sentinel.tsn
    )

    assert cluster.request.call_count == 0
    assert cluster.reply.call_count == 1
    cluster.reply.assert_called_with(
        True, cmd_id, mock.ANY, True, [], manufacturer=0x4567, tsn=mock.sentinel.tsn
    )


def test_handle_cluster_request_handler(cluster):
    cluster.handle_cluster_request(
        mock.sentinel.tsn, mock.sentinel.command_id, mock.sentinel.args
    )


def test_handle_cluster_general_request(cluster):
    cluster.handle_cluster_general_request(
        mock.sentinel.tsn, mock.sentinel.command_id, mock.sentinel.args
    )
