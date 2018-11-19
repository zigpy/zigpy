from unittest import mock

import pytest

import zigpy.endpoint
import zigpy.types as t
import zigpy.zcl as zcl


@pytest.fixture
def endpoint():
    ep = zigpy.endpoint.Endpoint(mock.MagicMock(), 1)
    ep.add_input_cluster(0)
    ep.add_input_cluster(3)
    return ep


def test_deserialize_general(endpoint):
    tsn, command_id, is_reply, args = endpoint.deserialize(0, b'\x00\x01\x00')
    assert tsn == 1
    assert command_id == 0
    assert is_reply is False


def test_deserialize_general_unknown(endpoint):
    tsn, command_id, is_reply, args = endpoint.deserialize(0, b'\x00\x01\xff')
    assert tsn == 1
    assert command_id == 255
    assert is_reply is False


def test_deserialize_cluster(endpoint):
    tsn, command_id, is_reply, args = endpoint.deserialize(0, b'\x01\x01\x00xxx')
    assert tsn == 1
    assert command_id == 256
    assert is_reply is False


def test_deserialize_cluster_client(endpoint):
    tsn, command_id, is_reply, args = endpoint.deserialize(3, b'\x09\x01\x00AB')
    assert tsn == 1
    assert command_id == 256
    assert is_reply is True
    assert args == [0x4241]


def test_deserialize_cluster_unknown(endpoint):
    tsn, command_id, is_reply, args = endpoint.deserialize(0xff00, b'\x05\x00\x00\x01\x00')
    assert tsn == 1
    assert command_id == 256
    assert is_reply is False


def test_deserialize_cluster_command_unknown(endpoint):
    tsn, command_id, is_reply, args = endpoint.deserialize(0, b'\x01\x01\xff')
    assert tsn == 1
    assert command_id == 255 + 256
    assert is_reply is False


def test_unknown_cluster():
    c = zcl.Cluster.from_id(None, 999)
    assert isinstance(c, zcl.Cluster)
    assert c.cluster_id == 999


def test_manufacturer_specific_cluster():
    import zigpy.zcl.clusters.manufacturer_specific as ms
    c = zcl.Cluster.from_id(None, 0xfc00)
    assert isinstance(c, ms.ManufacturerSpecificCluster)
    assert hasattr(c, 'cluster_id')
    c = zcl.Cluster.from_id(None, 0xffff)
    assert isinstance(c, ms.ManufacturerSpecificCluster)
    assert hasattr(c, 'cluster_id')


@pytest.fixture
def cluster():
    epmock = mock.MagicMock()
    epmock._device._application.get_sequence.return_value = 123
    return zcl.Cluster.from_id(epmock, 0)


@pytest.fixture
def client_cluster():
    epmock = mock.MagicMock()
    epmock._device._application.get_sequence.return_value = 123
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
    attr.value.value = 1
    cluster.handle_message(False, 0, 0x0a, [[attr]])
    assert cluster._attr_cache[4] == 1


def test_handle_request_unknown(cluster):
    cluster.handle_message(False, 0, 0xff, [])


def test_handle_cluster_request(cluster):
    cluster.handle_message(False, 0, 256, [])


def test_handle_unexpected_reply(cluster):
    cluster.handle_message(True, 0, 0, [])


def _mk_rar(attrid, value, status=0):
        r = zcl.foundation.ReadAttributeRecord()
        r.attrid = attrid
        r.status = status
        r.value = zcl.foundation.TypeValue()
        r.value.value = value
        return r


@pytest.mark.asyncio
async def test_read_attributes_uncached(cluster):
    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar0 = _mk_rar(0, 99)
        rar4 = _mk_rar(4, b'Manufacturer')
        rar99 = _mk_rar(99, None, 1)
        return [[rar0, rar4, rar99]]
    cluster.request = mockrequest
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", 99],
    )
    assert success[0] == 99
    assert success["manufacturer"] == b'Manufacturer'
    assert failure[99] == 1


@pytest.mark.asyncio
async def test_read_attributes_cached(cluster):
    cluster.request = mock.MagicMock()
    cluster._attr_cache[0] = 99
    cluster._attr_cache[4] = b'Manufacturer'
    success, failure = await cluster.read_attributes(
        [0, "manufacturer"],
        allow_cache=True,
    )
    assert cluster.request.call_count == 0
    assert success[0] == 99
    assert success["manufacturer"] == b'Manufacturer'
    assert failure == {}


@pytest.mark.asyncio
async def test_read_attributes_mixed_cached(cluster):
    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar5 = _mk_rar(5, b'Model')
        return [[rar5]]

    cluster.request = mockrequest
    cluster._attr_cache[0] = 99
    cluster._attr_cache[4] = b'Manufacturer'
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", "model"],
        allow_cache=True,
    )
    assert success[0] == 99
    assert success["manufacturer"] == b'Manufacturer'
    assert success["model"] == b'Model'
    assert failure == {}


@pytest.mark.asyncio
async def test_read_attributes_default_response(cluster):
    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        return [0xc1]

    cluster.request = mockrequest
    success, failure = await cluster.read_attributes(
        [0, 5, 23],
        allow_cache=False,
    )
    assert success == {}
    assert failure == {0: 0xc1, 5: 0xc1, 23: 0xc1}


@pytest.mark.asyncio
async def test_item_access_attributes(cluster):
    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar5 = _mk_rar(5, b'Model')
        return [[rar5]]

    cluster.request = mockrequest
    cluster._attr_cache[0] = 99

    v = await cluster['model']
    assert v == b'Model'
    v = await cluster['zcl_version']
    assert v == 99
    with pytest.raises(KeyError):
        v = await cluster[99]


def test_write_attributes(cluster):
    cluster.write_attributes({0: 5, 'app_version': 4})
    assert cluster._endpoint.request.call_count == 1


def test_write_wrong_attribute(cluster):
    cluster.write_attributes({0xff: 5})
    assert cluster._endpoint.request.call_count == 1


def test_write_attributes_wrong_type(cluster):
    cluster.write_attributes({18: 2})
    assert cluster._endpoint.request.call_count == 1


def test_write_attributes_report(cluster):
    cluster.write_attributes({0: 5}, is_report=True)
    assert cluster._endpoint.reply.call_count == 1


def test_bind(cluster):
    cluster.bind()


def test_unbind(cluster):
    cluster.unbind()


def test_configure_reporting(cluster):
    cluster.configure_reporting(0, 10, 20, 1)


def test_configure_reporting_named(cluster):
    cluster.configure_reporting('zcl_version', 10, 20, 1)
    assert cluster._endpoint.request.call_count == 1


def test_configure_reporting_wrong_named(cluster):
    cluster.configure_reporting('wrong_attr_name', 10, 20, 1)
    assert cluster._endpoint.request.call_count == 0


def test_configure_reporting_wrong_attrid(cluster):
    cluster.configure_reporting(0xfffe, 10, 20, 1)
    assert cluster._endpoint.request.call_count == 0


def test_configure_reporting_manuf():
    ep = mock.MagicMock()
    cluster = zcl.Cluster.from_id(ep, 6)
    cluster.request = mock.MagicMock(name='request')
    cluster.configure_reporting(0, 10, 20, 1)
    cluster.request.assert_called_with(
        mock.ANY, mock.ANY, mock.ANY, mock.ANY, manufacturer=None
    )

    cluster.request.reset_mock()
    manufacturer_id = 0xfcfc
    cluster.configure_reporting(0, 10, 20, 1, manufacturer=manufacturer_id)
    cluster.request.assert_called_with(
        mock.ANY, mock.ANY, mock.ANY, mock.ANY, manufacturer=manufacturer_id
    )
    assert cluster.request.call_count == 1


def test_command(cluster):
    cluster.command(0x00)
    assert cluster._endpoint.request.call_count == 1


def test_command_attr(cluster):
    cluster.reset_fact_default()
    assert cluster._endpoint.request.call_count == 1


def test_client_command_attr(client_cluster):
    client_cluster.identify_query_response(0)
    assert client_cluster._endpoint.reply.call_count == 1


def test_command_invalid_attr(cluster):
    with pytest.raises(AttributeError):
        cluster.no_such_command()


def test_invalid_arguments_cluster_command(cluster):
    res = cluster.command(0x00, 1)
    assert type(res.exception()) == ValueError


def test_invalid_arguments_cluster_client_command(client_cluster):
    res = client_cluster.client_command(0, 0, 0)
    assert type(res.exception()) == ValueError


def test_name(cluster):
    assert cluster.name == 'Basic'


def test_commands(cluster):
    assert cluster.commands == ["reset_fact_default"]
