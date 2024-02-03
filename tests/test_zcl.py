from __future__ import annotations

import asyncio
from unittest import mock

import pytest

import zigpy.device
import zigpy.endpoint
import zigpy.types as t
import zigpy.zcl as zcl
import zigpy.zcl.foundation as foundation

from .async_mock import AsyncMock, MagicMock, int_sentinel, patch, sentinel

DEFAULT_TSN = 123


@pytest.fixture
def endpoint():
    ep = zigpy.endpoint.Endpoint(MagicMock(), 1)
    ep.add_input_cluster(0)
    ep.add_input_cluster(3)
    return ep


def test_deserialize_general(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x00\x01\x00")
    assert hdr.tsn == 1
    assert hdr.command_id == 0
    assert hdr.direction == foundation.Direction.Client_to_Server


def test_deserialize_general_unknown(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x00\x01\xff")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is True
    assert hdr.frame_control.is_cluster is False
    assert hdr.command_id == 255
    assert hdr.direction == foundation.Direction.Client_to_Server


def test_deserialize_cluster(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x01\x01\x00xxx")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is False
    assert hdr.frame_control.is_cluster is True
    assert hdr.command_id == 0
    assert hdr.direction == foundation.Direction.Client_to_Server


def test_deserialize_cluster_client(endpoint):
    hdr, args = endpoint.deserialize(3, b"\x09\x01\x00AB")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is False
    assert hdr.frame_control.is_cluster is True
    assert hdr.command_id == 0
    assert list(args) == [0x4241]
    assert hdr.direction == foundation.Direction.Server_to_Client


def test_deserialize_cluster_unknown(endpoint):
    with pytest.raises(KeyError):
        endpoint.deserialize(0xFF00, b"\x05\x00\x00\x01\x00")


def test_deserialize_cluster_command_unknown(endpoint):
    hdr, args = endpoint.deserialize(0, b"\x01\x01\xff")
    assert hdr.tsn == 1
    assert hdr.command_id == 255
    assert hdr.direction == foundation.Direction.Client_to_Server


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
        epmock = MagicMock()
        epmock._device.get_sequence.return_value = DEFAULT_TSN
        epmock.device.get_sequence.return_value = DEFAULT_TSN
        epmock.request = AsyncMock()
        epmock.reply = AsyncMock()
        return zcl.Cluster.from_id(epmock, cluster_id)

    return _cluster


@pytest.fixture
def cluster(cluster_by_id):
    return cluster_by_id(0)


@pytest.fixture
def client_cluster():
    epmock = AsyncMock()
    epmock.device.get_sequence = MagicMock(return_value=DEFAULT_TSN)
    return zcl.Cluster.from_id(epmock, 3)


async def test_request_general(cluster):
    await cluster.request(True, 0, [])
    assert cluster._endpoint.request.call_count == 1


async def test_request_manufacturer(cluster):
    await cluster.request(True, 0, [t.uint8_t], 1)
    assert cluster._endpoint.request.call_count == 1
    org_size = len(cluster._endpoint.request.call_args[0][2])
    await cluster.request(True, 0, [t.uint8_t], 1, manufacturer=1)
    assert cluster._endpoint.request.call_count == 2
    assert org_size + 2 == len(cluster._endpoint.request.call_args[0][2])


async def test_request_optional(cluster):
    schema = [t.uint8_t, t.uint16_t, t.Optional(t.uint16_t), t.Optional(t.uint8_t)]
    cluster.endpoint.request = AsyncMock()

    with pytest.raises(ValueError):
        await cluster.request(True, 0, schema)

    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()

    with pytest.raises(ValueError):
        await cluster.request(True, 0, schema, 1)

    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()

    await cluster.request(True, 0, schema, 1, 2)
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    await cluster.request(True, 0, schema, 1, 2, 3)
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    await cluster.request(True, 0, schema, 1, 2, 3, 4)
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    with pytest.raises(TypeError):
        await cluster.request(True, 0, schema, 1, 2, 3, 4, 5)

    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()


async def test_reply_general(cluster):
    await cluster.reply(False, 0, [])
    assert cluster._endpoint.reply.call_count == 1


async def test_reply_manufacturer(cluster):
    await cluster.reply(False, 0, [t.uint8_t], 1)
    assert cluster._endpoint.reply.call_count == 1
    org_size = len(cluster._endpoint.reply.call_args[0][2])
    await cluster.reply(False, 0, [t.uint8_t], 1, manufacturer=1)
    assert cluster._endpoint.reply.call_count == 2
    assert org_size + 2 == len(cluster._endpoint.reply.call_args[0][2])


def test_attribute_report(cluster):
    attr = zcl.foundation.Attribute()
    attr.attrid = 4
    attr.value = zcl.foundation.TypeValue()
    attr.value.value = "manufacturer"
    hdr = MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = foundation.GeneralCommand.Report_Attributes
    hdr.frame_control.is_general = True
    hdr.frame_control.is_cluster = False

    cmd = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Report_Attributes
    ].schema([attr])
    cluster.handle_message(hdr, cmd)

    assert cluster._attr_cache[4] == "manufacturer"

    attr.attrid = 0x89AB
    cluster.handle_message(hdr, cmd)
    assert cluster._attr_cache[attr.attrid] == "manufacturer"

    def mock_type(*args, **kwargs):
        raise ValueError

    with patch.dict(
        cluster.attributes,
        {0xAAAA: foundation.ZCLAttributeDef(id=0xAAAA, name="Name", type=mock_type)},
    ):
        attr.attrid = 0xAAAA
        cluster.handle_message(hdr, cmd)
        assert cluster._attr_cache[attr.attrid] == "manufacturer"


def test_handle_request_unknown(cluster):
    hdr = MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = int_sentinel.command_id
    hdr.frame_control.is_general = True
    hdr.frame_control.is_cluster = False
    cluster.listener_event = MagicMock()
    cluster._update_attribute = MagicMock()
    cluster.handle_cluster_general_request = MagicMock()
    cluster.handle_cluster_request = MagicMock()
    cluster.handle_message(hdr, sentinel.args)

    assert cluster.listener_event.call_count == 1
    assert cluster.listener_event.call_args[0][0] == "general_command"
    assert cluster._update_attribute.call_count == 0
    assert cluster.handle_cluster_general_request.call_count == 1
    assert cluster.handle_cluster_request.call_count == 0


def test_handle_cluster_request(cluster):
    hdr = MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = int_sentinel.command_id
    hdr.frame_control.is_general = False
    hdr.frame_control.is_cluster = True
    hdr.command_id.is_general = False
    cluster.listener_event = MagicMock()
    cluster._update_attribute = MagicMock()
    cluster.handle_cluster_general_request = MagicMock()
    cluster.handle_cluster_request = MagicMock()
    cluster.handle_message(hdr, sentinel.args)

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
        is_general_req, command, schema, args, manufacturer=None, **kwargs
    ):
        assert is_general_req is True
        assert command == 0
        rar0 = _mk_rar(0, 99)
        rar4 = _mk_rar(4, "Manufacturer")
        rar99 = _mk_rar(99, None, 1)
        rar199 = _mk_rar(199, 199)
        rar16 = _mk_rar(0x0010, None, zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE)
        return [[rar0, rar4, rar99, rar199, rar16]]

    cluster.request = mockrequest
    success, failure = await cluster.read_attributes([0, "manufacturer", 99, 199, 16])
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert failure[99] == 1
    assert {99, 0x0010} == failure.keys()
    assert success[199] == 199
    assert cluster.unsupported_attributes == {0x0010, "location_desc"}


async def test_read_attributes_cached(cluster):
    cluster.request = MagicMock()
    cluster._attr_cache[0] = 99
    cluster._attr_cache[4] = "Manufacturer"
    cluster.unsupported_attributes.add(0x0010)
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", 0x0010], allow_cache=True
    )
    assert cluster.request.call_count == 0
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert failure == {0x0010: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE}


async def test_read_attributes_mixed_cached(cluster):
    """Reading cached and uncached attributes."""

    cluster.request = AsyncMock(return_value=[[_mk_rar(5, "Model")]])
    cluster._attr_cache[0] = 99
    cluster._attr_cache[4] = "Manufacturer"
    cluster.unsupported_attributes.add(0x0010)
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", "model", 0x0010], allow_cache=True
    )
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert success["model"] == "Model"
    assert cluster.request.await_count == 1
    assert cluster.request.call_args[0][3] == [0x0005]
    assert failure == {0x0010: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE}


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


async def test_read_attributes_value_normalization_error(cluster):
    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        rar5 = _mk_rar(5, "Model")
        return [[rar5]]

    def mock_type(*args, **kwargs):
        raise ValueError

    cluster.request = mockrequest
    with patch.dict(
        cluster.attributes,
        {5: foundation.ZCLAttributeDef(id=5, name="Name", type=mock_type)},
    ):
        success, failure = await cluster.read_attributes(["model"], allow_cache=True)
    assert failure == {}
    assert success["model"] == "Model"


async def test_item_access_attributes(cluster):
    cluster._attr_cache[5] = sentinel.model

    assert cluster["model"] == sentinel.model
    assert cluster[5] == sentinel.model
    assert cluster.get("model") == sentinel.model
    assert cluster.get(5) == sentinel.model
    assert cluster.get("model", sentinel.default) == sentinel.model
    assert cluster.get(5, sentinel.default) == sentinel.model
    with pytest.raises(KeyError):
        cluster[4]
    assert cluster.get(4) is None
    assert cluster.get("manufacturer") is None
    assert cluster.get(4, sentinel.default) is sentinel.default
    assert cluster.get("manufacturer", sentinel.default) is sentinel.default

    with pytest.raises(KeyError):
        cluster["manufacturer"]

    with pytest.raises(KeyError):
        # wrong attr name
        cluster["some_non_existent_attr"]

    with pytest.raises(ValueError):
        # wrong key type
        cluster[None]

    with pytest.raises(ValueError):
        # wrong key type
        cluster.get(None)

    # Test access to cached attribute via wrong attr name
    with pytest.raises(KeyError):
        cluster.get("no_such_attribute")


async def test_item_set_attributes(cluster):
    with patch.object(cluster, "write_attributes") as write_mock:
        cluster["model"] = sentinel.model
        await asyncio.sleep(0)
    assert write_mock.await_count == 1
    assert write_mock.call_args[0][0] == {"model": sentinel.model}

    with pytest.raises(ValueError):
        cluster[None] = sentinel.manufacturer


async def test_write_attributes(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        await cluster.write_attributes({0: 5, "app_version": 4})
        assert cluster._write_attributes.call_count == 1


async def test_write_wrong_attribute(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        await cluster.write_attributes({0xFF: 5})
        assert cluster._write_attributes.call_count == 1


async def test_write_unknown_attribute(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        with pytest.raises(KeyError):
            # Using an invalid attribute name, the call should fail
            await cluster.write_attributes({"dummy_attribute": 5})
        assert cluster._write_attributes.call_count == 0


async def test_write_attributes_wrong_type(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        await cluster.write_attributes({18: 0x2222})
        assert cluster._write_attributes.call_count == 1


async def test_write_attributes_raw(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        # write_attributes_raw does not check the attributes,
        # send to unknown attribute in cluster, the write should be effective
        await cluster.write_attributes_raw({0: 5, 0x3000: 5})
        assert cluster._write_attributes.call_count == 1


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
async def test_write_attribute_types(
    cluster_id, attr, value, serialized, cluster_by_id
):
    cluster = cluster_by_id(cluster_id)
    with patch.object(cluster.endpoint, "request", new=AsyncMock()):
        await cluster.write_attributes({attr: value})
        assert cluster._endpoint.reply.call_count == 0
        assert cluster._endpoint.request.call_count == 1
        assert cluster.endpoint.request.call_args[0][2][3:] == serialized


@pytest.mark.parametrize(
    "status", (foundation.Status.SUCCESS, foundation.Status.UNSUPPORTED_ATTRIBUTE)
)
async def test_write_attributes_cache_default_response(cluster, status):
    write_mock = AsyncMock(
        return_value=[foundation.GeneralCommand.Write_Attributes, status]
    )
    with patch.object(cluster, "_write_attributes", write_mock):
        attributes = {4: "manufacturer", 5: "model", 12: 12}
        await cluster.write_attributes(attributes)
        assert cluster._write_attributes.call_count == 1
        for attr_id in attributes:
            assert attr_id not in cluster._attr_cache


@pytest.mark.parametrize(
    "attributes, result",
    (
        ({4: "manufacturer"}, b"\x00"),
        ({4: "manufacturer", 5: "model"}, b"\x00"),
        ({4: "manufacturer", 5: "model", 3: 12}, b"\x00"),
        ({4: "manufacturer", 5: "model"}, b"\x00\x00"),
        ({4: "manufacturer", 5: "model", 3: 12}, b"\x00\x00\x00"),
    ),
)
async def test_write_attributes_cache_success(cluster, attributes, result):
    listener = MagicMock()
    cluster.add_listener(listener)

    rsp_type = t.List[foundation.WriteAttributesStatusRecord]
    write_mock = AsyncMock(return_value=[rsp_type.deserialize(result)[0]])
    with patch.object(cluster, "_write_attributes", write_mock):
        await cluster.write_attributes(attributes)
        assert cluster._write_attributes.call_count == 1
        for attr_id in attributes:
            assert cluster._attr_cache[attr_id] == attributes[attr_id]
            listener.attribute_updated.assert_any_call(
                attr_id, attributes[attr_id], mock.ANY
            )


@pytest.mark.parametrize(
    "attributes, result, failed",
    (
        ({4: "manufacturer"}, b"\x86\x04\x00", [4]),
        ({4: "manufacturer", 5: "model"}, b"\x86\x05\x00", [5]),
        ({4: "manufacturer", 5: "model"}, b"\x86\x04\x00\x86\x05\x00", [4, 5]),
        (
            {4: "manufacturer", 5: "model", 3: 12},
            b"\x86\x05\x00",
            [5],
        ),
        (
            {4: "manufacturer", 5: "model", 3: 12},
            b"\x86\x05\x00\x01\x03\x00",
            [5, 3],
        ),
        (
            {4: "manufacturer", 5: "model", 3: 12},
            b"\x02\x04\x00\x86\x05\x00\x01\x03\x00",
            [4, 5, 3],
        ),
    ),
)
async def test_write_attributes_cache_failure(cluster, attributes, result, failed):
    listener = MagicMock()
    cluster.add_listener(listener)

    rsp_type = foundation.WriteAttributesResponse
    write_mock = AsyncMock(return_value=[rsp_type.deserialize(result)[0]])

    with patch.object(cluster, "_write_attributes", write_mock):
        await cluster.write_attributes(attributes)
        assert cluster._write_attributes.call_count == 1
        for attr_id in attributes:
            if attr_id in failed:
                assert attr_id not in cluster._attr_cache

                # Failed writes do not propagate
                with pytest.raises(AssertionError):
                    listener.attribute_updated.assert_any_call(
                        attr_id, attributes[attr_id]
                    )
            else:
                assert cluster._attr_cache[attr_id] == attributes[attr_id]
                listener.attribute_updated.assert_any_call(
                    attr_id, attributes[attr_id], mock.ANY
                )


async def test_read_attributes_response(cluster):
    await cluster.read_attributes_rsp({0: 5})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0


async def test_read_attributes_resp_unsupported(cluster):
    await cluster.read_attributes_rsp({0: 5})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0
    orig_len = len(cluster._endpoint.reply.call_args[0][2])

    await cluster.read_attributes_rsp({0: 5, 2: None})
    assert cluster._endpoint.reply.call_count == 2
    assert cluster._endpoint.request.call_count == 0
    assert len(cluster._endpoint.reply.call_args[0][2]) == orig_len + 3


async def test_read_attributes_resp_str(cluster):
    await cluster.read_attributes_rsp({"hw_version": 32})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0


async def test_read_attributes_resp_exc(cluster):
    with patch.object(foundation.DATA_TYPES, "pytype_to_datatype_id") as mck:
        mck.side_effect = ValueError
        await cluster.read_attributes_rsp({"hw_version": 32})
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
async def test_read_attribute_resp(cluster_id, attr, value, serialized, cluster_by_id):
    cluster = cluster_by_id(cluster_id)
    await cluster.read_attributes_rsp({attr: value})
    assert cluster._endpoint.reply.call_count == 1
    assert cluster._endpoint.request.call_count == 0
    assert cluster.endpoint.reply.call_args[0][2][3:] == serialized


def test_bind(cluster):
    cluster.bind()


def test_unbind(cluster):
    cluster.unbind()


async def test_configure_reporting(cluster):
    await cluster.configure_reporting(0, 10, 20, 1)


async def test_configure_reporting_named(cluster):
    await cluster.configure_reporting("zcl_version", 10, 20, 1)
    assert cluster._endpoint.request.call_count == 1


async def test_configure_reporting_wrong_named(cluster):
    with pytest.raises(ValueError):
        await cluster.configure_reporting("wrong_attr_name", 10, 20, 1)
        assert cluster._endpoint.request.call_count == 0


async def test_configure_reporting_wrong_attrid(cluster):
    with pytest.raises(ValueError):
        await cluster.configure_reporting(0xABCD, 10, 20, 1)
        assert cluster._endpoint.request.call_count == 0


async def test_configure_reporting_manuf():
    ep = MagicMock()
    cluster = zcl.Cluster.from_id(ep, 6)
    cluster.request = AsyncMock(name="request")
    await cluster.configure_reporting(0, 10, 20, 1)
    cluster.request.assert_called_with(
        True,
        0x06,
        mock.ANY,
        mock.ANY,
        expect_reply=True,
        manufacturer=None,
        tsn=mock.ANY,
    )

    cluster.request.reset_mock()
    manufacturer_id = 0xFCFC
    await cluster.configure_reporting(0, 10, 20, 1, manufacturer=manufacturer_id)
    cluster.request.assert_called_with(
        True,
        0x06,
        mock.ANY,
        mock.ANY,
        expect_reply=True,
        manufacturer=manufacturer_id,
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
async def test_configure_reporting_types(cluster_id, attr, data_type, cluster_by_id):
    cluster = cluster_by_id(cluster_id)
    await cluster.configure_reporting(attr, 0x1234, 0x2345, 0xAA)
    assert cluster._endpoint.reply.call_count == 0
    assert cluster._endpoint.request.call_count == 1
    assert cluster.endpoint.request.call_args[0][2][6] == data_type


async def test_command(cluster):
    await cluster.command(0x00)
    assert cluster._endpoint.request.call_count == 1
    assert cluster._endpoint.request.call_args[0][1] == DEFAULT_TSN


async def test_command_override_tsn(cluster):
    await cluster.command(0x00, tsn=22)
    assert cluster._endpoint.request.call_count == 1
    assert cluster._endpoint.request.call_args[0][1] == 22


async def test_command_attr(cluster):
    await cluster.reset_fact_default()
    assert cluster._endpoint.request.call_count == 1


async def test_client_command_attr(client_cluster):
    await client_cluster.identify_query_response(timeout=0)
    assert client_cluster._endpoint.reply.call_count == 1


async def test_command_invalid_attr(cluster):
    with pytest.raises(AttributeError):
        await cluster.no_such_command()


async def test_invalid_arguments_cluster_command(cluster):
    with pytest.raises(TypeError):
        await cluster.command(0x00, 1)


async def test_invalid_arguments_cluster_client_command(client_cluster):
    with pytest.raises(TypeError):
        await client_cluster.client_command(0, 0, 0)


def test_name(cluster):
    assert cluster.name == "Basic"


def test_commands(cluster):
    assert cluster.commands == [cluster.ServerCommandDefs.reset_fact_default]


def test_general_command(cluster):
    cluster.request = MagicMock()
    cluster.reply = MagicMock()
    cmd_id = 0x0C
    cluster.general_command(cmd_id, sentinel.start, sentinel.items, manufacturer=0x4567)

    assert cluster.reply.call_count == 0
    assert cluster.request.call_count == 1
    cluster.request.assert_called_with(
        True,
        cmd_id,
        mock.ANY,
        sentinel.start,
        sentinel.items,
        expect_reply=True,
        manufacturer=0x4567,
        tsn=mock.ANY,
    )


def test_general_command_reply(cluster):
    cluster.request = MagicMock()
    cluster.reply = MagicMock()
    cmd_id = 0x0D
    cluster.general_command(cmd_id, True, [], manufacturer=0x4567)

    assert cluster.request.call_count == 0
    assert cluster.reply.call_count == 1
    cluster.reply.assert_called_with(
        True, cmd_id, mock.ANY, True, [], manufacturer=0x4567, tsn=None
    )

    cluster.request.reset_mock()
    cluster.reply.reset_mock()
    cluster.general_command(cmd_id, True, [], manufacturer=0x4567, tsn=sentinel.tsn)

    assert cluster.request.call_count == 0
    assert cluster.reply.call_count == 1
    cluster.reply.assert_called_with(
        True, cmd_id, mock.ANY, True, [], manufacturer=0x4567, tsn=sentinel.tsn
    )


def test_handle_cluster_request_handler(cluster):
    hdr = foundation.ZCLHeader.cluster(123, 0x00)
    cluster.handle_cluster_request(hdr, [sentinel.arg1, sentinel.arg2])


async def test_handle_cluster_general_request_disable_default_rsp(endpoint):
    hdr, values = endpoint.deserialize(
        0,
        b"\x18\xCD\x0A\x01\xFF\x42\x25\x01\x21\x95\x0B\x04\x21\xA8\x43\x05\x21\x36\x00"
        b"\x06\x24\x02\x00\x05\x00\x00\x64\x29\xF8\x07\x65\x21\xD9\x0E\x66\x2B\x84\x87"
        b"\x01\x00\x0A\x21\x00\x00",
    )
    cluster = endpoint.in_clusters[0]
    p1 = patch.object(cluster, "_update_attribute")
    p2 = patch.object(cluster, "general_command")
    with p1 as attr_lst_mock, p2 as general_cmd_mock:
        cluster.handle_cluster_general_request(hdr, values)
        await asyncio.sleep(0)
        assert attr_lst_mock.call_count > 0
        assert general_cmd_mock.call_count == 0

    with p1 as attr_lst_mock, p2 as general_cmd_mock:
        hdr.frame_control.disable_default_response = False
        cluster.handle_cluster_general_request(hdr, values)
        await asyncio.sleep(0)
        assert attr_lst_mock.call_count > 0
        assert general_cmd_mock.call_count == 1
        assert general_cmd_mock.call_args[1]["tsn"] == hdr.tsn


async def test_handle_cluster_general_request_not_attr_report(cluster):
    hdr = foundation.ZCLHeader.general(1, foundation.GeneralCommand.Write_Attributes)
    p1 = patch.object(cluster, "_update_attribute")
    p2 = patch.object(cluster, "create_catching_task")
    with p1 as attr_lst_mock, p2 as response_mock:
        cluster.handle_cluster_general_request(hdr, [1, 2, 3])
        await asyncio.sleep(0)
        assert attr_lst_mock.call_count == 0
        assert response_mock.call_count == 0


async def test_write_attributes_undivided(cluster):
    with patch.object(cluster, "request", new=AsyncMock()):
        i = cluster.write_attributes_undivided({0: 5, "app_version": 4})
        await i
        assert cluster.request.call_count == 1


async def test_configure_reporting_multiple(cluster):
    await cluster.configure_reporting(3, 5, 15, 20, manufacturer=0x2345)
    await cluster.configure_reporting_multiple({3: (5, 15, 20)}, manufacturer=0x2345)
    assert cluster.endpoint.request.call_count == 2
    assert (
        cluster.endpoint.request.call_args_list[0][0][2]
        == cluster.endpoint.request.call_args_list[1][0][2]
    )


async def test_configure_reporting_multiple_def_rsp(cluster):
    """Configure reporting returned a default response. May happen."""
    cluster.endpoint.request.return_value = (
        zcl.foundation.GeneralCommand.Configure_Reporting,
        zcl.foundation.Status.UNSUP_GENERAL_COMMAND,
    )
    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster.unsupported_attributes == set()


def _mk_cfg_rsp(responses: dict[int, zcl.foundation.Status]):
    """A helper to create a configure response record."""
    cfg_response = zcl.foundation.ConfigureReportingResponse()
    for attrid, status in responses.items():
        cfg_response.append(
            zcl.foundation.ConfigureReportingResponseRecord(
                status, zcl.foundation.ReportingDirection.ReceiveReports, attrid
            )
        )
    return [cfg_response]


async def test_configure_reporting_multiple_single_success(cluster):
    """Configure reporting returned a single success response."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {0: zcl.foundation.Status.SUCCESS}
    )

    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster.unsupported_attributes == set()


async def test_configure_reporting_multiple_single_fail(cluster):
    """Configure reporting returned a single failure response."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {3: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE}
    )

    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster.unsupported_attributes == {"hw_version", 3}

    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {3: zcl.foundation.Status.SUCCESS}
    )
    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 2
    assert cluster.unsupported_attributes == set()


async def test_configure_reporting_multiple_single_unreportable(cluster):
    """Configure reporting returned a single failure response for unreportable attribute."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {4: zcl.foundation.Status.UNREPORTABLE_ATTRIBUTE}
    )

    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster.unsupported_attributes == set()


async def test_configure_reporting_multiple_both_unsupp(cluster):
    """Configure reporting returned unsupported attributes for both."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {
            3: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
            4: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
        }
    )

    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster.unsupported_attributes == {"hw_version", 3, "manufacturer", 4}

    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {
            3: zcl.foundation.Status.SUCCESS,
            4: zcl.foundation.Status.SUCCESS,
        }
    )

    await cluster.configure_reporting_multiple(
        {3: (5, 15, 20), 4: (6, 16, 26)}, manufacturer=0x2345
    )
    assert cluster.endpoint.request.await_count == 2
    assert cluster.unsupported_attributes == set()


def test_unsupported_attr_add(cluster):
    """Test adding unsupported attributes."""

    assert "manufacturer" not in cluster.unsupported_attributes
    assert 4 not in cluster.unsupported_attributes
    assert "model" not in cluster.unsupported_attributes
    assert 5 not in cluster.unsupported_attributes

    cluster.add_unsupported_attribute(4)
    assert "manufacturer" in cluster.unsupported_attributes
    assert 4 in cluster.unsupported_attributes

    cluster.add_unsupported_attribute("model")
    assert "model" in cluster.unsupported_attributes
    assert 5 in cluster.unsupported_attributes


def test_unsupported_attr_add_no_reverse_attr_name(cluster):
    """Test adding unsupported attributes without corresponding reverse attr name."""

    assert "no_such_attr" not in cluster.unsupported_attributes
    assert 0xDEED not in cluster.unsupported_attributes

    cluster.add_unsupported_attribute("no_such_attr")
    cluster.add_unsupported_attribute("no_such_attr")
    assert "no_such_attr" in cluster.unsupported_attributes

    cluster.add_unsupported_attribute(0xDEED)
    assert 0xDEED in cluster.unsupported_attributes


def test_unsupported_attr_remove(cluster):
    """Test removing unsupported attributes."""

    assert "manufacturer" not in cluster.unsupported_attributes
    assert 4 not in cluster.unsupported_attributes
    assert "model" not in cluster.unsupported_attributes
    assert 5 not in cluster.unsupported_attributes

    cluster.add_unsupported_attribute(4)
    assert "manufacturer" in cluster.unsupported_attributes
    assert 4 in cluster.unsupported_attributes

    cluster.add_unsupported_attribute("model")
    assert "model" in cluster.unsupported_attributes
    assert 5 in cluster.unsupported_attributes

    cluster.remove_unsupported_attribute(4)
    assert "manufacturer" not in cluster.unsupported_attributes
    assert 4 not in cluster.unsupported_attributes

    cluster.remove_unsupported_attribute("model")
    assert "model" not in cluster.unsupported_attributes
    assert 5 not in cluster.unsupported_attributes


def test_unsupported_attr_remove_no_reverse_attr_name(cluster):
    """Test removing unsupported attributes without corresponding reverse attr name."""

    assert "no_such_attr" not in cluster.unsupported_attributes
    assert 0xDEED not in cluster.unsupported_attributes

    cluster.add_unsupported_attribute("no_such_attr")
    assert "no_such_attr" in cluster.unsupported_attributes

    cluster.add_unsupported_attribute(0xDEED)
    assert 0xDEED in cluster.unsupported_attributes

    cluster.remove_unsupported_attribute("no_such_attr")
    assert "no_such_attr" not in cluster.unsupported_attributes

    cluster.remove_unsupported_attribute(0xDEED)
    assert 0xDEED not in cluster.unsupported_attributes


def test_zcl_command_duplicate_name_prevention():
    assert 0x1234 not in zcl.clusters.CLUSTERS_BY_ID

    with pytest.raises(TypeError):

        class TestCluster(zcl.Cluster):
            cluster_id = 0x1234
            ep_attribute = "test_cluster"
            server_commands = {
                0x00: foundation.ZCLCommandDef(
                    name="command1", schema={}, direction=False
                ),
                0x01: foundation.ZCLCommandDef(
                    name="command1", schema={}, direction=False
                ),
            }


def test_zcl_attridx_deprecation(cluster):
    with pytest.deprecated_call():
        cluster.attridx

    with pytest.deprecated_call():
        assert cluster.attridx is cluster.attributes_by_name


def test_zcl_response_type_tuple_like():
    req = (
        zcl.clusters.general.OnOff(None)
        .commands_by_name["on_with_timed_off"]
        .schema(
            on_off_control=0,
            on_time=1,
            off_wait_time=2,
        )
    )

    on_off_control, on_time, off_wait_time = req
    assert req.on_off_control == on_off_control == req[0] == 0
    assert req.on_time == on_time == req[1] == 1
    assert req.off_wait_time == off_wait_time == req[2] == 2

    assert req == (0, 1, 2)
    assert req == req
    assert req == req.replace()


async def test_zcl_request_direction():
    """Test that the request header's `direction` field is properly set."""
    dev = MagicMock()

    ep = zigpy.endpoint.Endpoint(dev, 1)
    ep._device.get_sequence.return_value = DEFAULT_TSN
    ep.device.get_sequence.return_value = DEFAULT_TSN
    ep.request = AsyncMock()

    ep.add_input_cluster(zcl.clusters.general.OnOff.cluster_id)
    ep.add_input_cluster(zcl.clusters.lighting.Color.cluster_id)
    ep.add_output_cluster(zcl.clusters.general.OnOff.cluster_id)

    # Input cluster
    await ep.in_clusters[zcl.clusters.general.OnOff.cluster_id].on()
    hdr1, _ = foundation.ZCLHeader.deserialize(ep.request.mock_calls[0].args[2])
    assert hdr1.direction == foundation.Direction.Client_to_Server

    ep.request.reset_mock()

    # Output cluster
    await ep.out_clusters[zcl.clusters.general.OnOff.cluster_id].on()
    hdr2, _ = foundation.ZCLHeader.deserialize(ep.request.mock_calls[0].args[2])
    assert hdr2.direction == foundation.Direction.Server_to_Client

    # Color cluster that also uses `direction` as a kwarg
    await ep.light_color.move_to_hue(
        hue=0,
        direction=zcl.clusters.lighting.Color.Direction.Shortest_distance,
        transition_time=10,
    )


async def test_zcl_reply_direction(app_mock):
    """Test that the reply header's `direction` field is properly set."""
    dev = zigpy.device.Device(
        application=app_mock,
        ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
        nwk=0x1234,
    )

    dev._send_sequence = DEFAULT_TSN

    ep = dev.add_endpoint(1)
    ep.add_input_cluster(zcl.clusters.general.OnOff.cluster_id)

    hdr = foundation.ZCLHeader(
        frame_control=foundation.FrameControl(
            frame_type=foundation.FrameType.GLOBAL_COMMAND,
            is_manufacturer_specific=0,
            direction=foundation.Direction.Server_to_Client,
            disable_default_response=0,
            reserved=0,
        ),
        tsn=87,
        command_id=foundation.GeneralCommand.Report_Attributes,
    )

    attr = zcl.foundation.Attribute()
    attr.attrid = zcl.clusters.general.OnOff.AttributeDefs.on_off.id
    attr.value = zcl.foundation.TypeValue()
    attr.value.value = t.Bool.true

    cmd = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Report_Attributes
    ].schema([attr])

    ep.handle_message(
        profile=260,
        cluster=zcl.clusters.general.OnOff.cluster_id,
        hdr=hdr,
        args=cmd,
    )

    await asyncio.sleep(0.1)

    packet = app_mock.send_packet.mock_calls[0].args[0]
    assert packet.cluster_id == zcl.clusters.general.OnOff.cluster_id

    # The direction is correct
    packet_hdr, _ = foundation.ZCLHeader.deserialize(packet.data.serialize())
    assert packet_hdr.direction == foundation.Direction.Client_to_Server
