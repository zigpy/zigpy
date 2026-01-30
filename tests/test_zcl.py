from __future__ import annotations

import asyncio
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, call, patch, sentinel

import pytest

from tests.conftest import (
    add_initialized_device,
    make_app,
    make_ieee,
    mock_attribute_reads,
    mock_attribute_report,
    mock_attribute_writes,
)
from zigpy import zcl
import zigpy.device
import zigpy.endpoint
import zigpy.profiles.zha
import zigpy.types as t
from zigpy.zcl import (
    AttributeReadEvent,
    AttributeReportedEvent,
    AttributeUpdatedEvent,
    AttributeWrittenEvent,
    foundation,
)
from zigpy.zcl.clusters.general import Basic, OnOff, Ota
from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.zcl.helpers import ReportingConfig

DEFAULT_TSN = 123


@pytest.fixture
def endpoint():
    ep = zigpy.endpoint.Endpoint(MagicMock(), 1)
    ep.add_input_cluster(0)
    ep.add_input_cluster(3)
    return ep


def test_deserialize_general(endpoint):
    hdr, args = endpoint.in_clusters[0].deserialize(b"\x00\x01\x00")
    assert hdr.tsn == 1
    assert hdr.command_id == 0
    assert hdr.direction == foundation.Direction.Client_to_Server


def test_deserialize_general_unknown(endpoint):
    hdr, args = endpoint.in_clusters[0].deserialize(b"\x00\x01\xff")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is True
    assert hdr.frame_control.is_cluster is False
    assert hdr.command_id == 255
    assert hdr.direction == foundation.Direction.Client_to_Server


def test_deserialize_cluster(endpoint):
    hdr, args = endpoint.in_clusters[0].deserialize(b"\x01\x01\x00xxx")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is False
    assert hdr.frame_control.is_cluster is True
    assert hdr.command_id == 0
    assert hdr.direction == foundation.Direction.Client_to_Server


def test_deserialize_cluster_client(endpoint):
    hdr, args = endpoint.in_clusters[3].deserialize(b"\x09\x01\x00AB")
    assert hdr.tsn == 1
    assert hdr.frame_control.is_general is False
    assert hdr.frame_control.is_cluster is True
    assert hdr.command_id == 0
    assert list(args) == [0x4241]
    assert hdr.direction == foundation.Direction.Server_to_Client


def test_deserialize_cluster_unknown(endpoint):
    with pytest.raises(KeyError):
        endpoint.in_clusters[0xFF00].deserialize(b"\x05\x00\x00\x01\x00")


def test_deserialize_cluster_command_unknown(endpoint):
    hdr, args = endpoint.in_clusters[0].deserialize(b"\x01\x01\xff")
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
        epmock.device.zdo.bind = AsyncMock()
        epmock.device.zdo.unbind = AsyncMock()
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
    return Ota(epmock)


async def test_request_general(cluster):
    await cluster.request(
        general=True,
        command_id=foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Read_Attributes
        ].id,
        schema=foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Read_Attributes
        ].schema,
        attribute_ids=[],
    )
    assert cluster._endpoint.request.call_count == 1


async def test_request_manufacturer(cluster):
    command = foundation.ZCLCommandDef(
        name="test_command", id=0x00, schema={"param1": t.uint8_t}
    ).with_compiled_schema()

    await cluster.request(
        general=True,
        command_id=command.id,
        schema=command.schema,
        param1=1,
    )
    assert cluster._endpoint.request.call_count == 1

    org_size = len(cluster._endpoint.request.mock_calls[0].kwargs["data"])
    await cluster.request(
        general=True,
        command_id=command.id,
        schema=command.schema,
        param1=1,
        manufacturer=1,
    )
    assert cluster._endpoint.request.call_count == 2
    assert org_size + 2 == len(cluster._endpoint.request.mock_calls[1].kwargs["data"])


async def test_request_optional(cluster):
    command = foundation.ZCLCommandDef(
        name="test_command",
        id=0x00,
        schema={
            "param1": t.uint8_t,
            "param2": t.uint16_t,
            "param3?": t.uint16_t,
            "param4?": t.uint8_t,
        },
    ).with_compiled_schema()

    cluster.endpoint.request = AsyncMock()

    with pytest.raises(ValueError):
        await cluster.request(
            general=True,
            command_id=command.id,
            schema=command.schema,
        )

    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()

    with pytest.raises(ValueError):
        await cluster.request(
            general=True,
            command_id=command.id,
            schema=command.schema,
            param1=1,
        )

    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()

    await cluster.request(
        general=True,
        command_id=command.id,
        schema=command.schema,
        param1=1,
        param2=2,
    )
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    await cluster.request(
        general=True,
        command_id=command.id,
        schema=command.schema,
        param1=1,
        param2=2,
        param3=3,
    )
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    await cluster.request(
        general=True,
        command_id=command.id,
        schema=command.schema,
        param1=1,
        param2=2,
        param3=3,
        param4=4,
    )
    assert cluster._endpoint.request.call_count == 1
    cluster._endpoint.request.reset_mock()

    with pytest.raises(TypeError):
        await cluster.request(
            general=True,
            command_id=command.id,
            schema=command.schema,
            param1=1,
            param2=2,
            param3=3,
            param4=4,
            param5=5,
        )

    assert cluster._endpoint.request.call_count == 0
    cluster._endpoint.request.reset_mock()


async def test_reply_general(cluster):
    command = foundation.ZCLCommandDef(
        name="test_command", id=0x00, schema={}
    ).with_compiled_schema()

    await cluster.reply(general=False, command_id=command.id, schema=command.schema)
    assert cluster._endpoint.reply.call_count == 1


async def test_reply_manufacturer(cluster):
    command = foundation.ZCLCommandDef(
        name="test_command",
        id=0x00,
        schema={
            "param1": t.uint8_t,
        },
    ).with_compiled_schema()

    await cluster.reply(
        general=False, command_id=command.id, schema=command.schema, param1=1
    )
    assert cluster._endpoint.reply.call_count == 1
    org_size = len(cluster._endpoint.reply.mock_calls[0].kwargs["data"])
    await cluster.reply(
        general=False,
        command_id=command.id,
        schema=command.schema,
        param1=1,
        manufacturer=1,
    )
    assert cluster._endpoint.reply.call_count == 2
    assert org_size + 2 == len(cluster._endpoint.reply.mock_calls[1].kwargs["data"])


def test_attribute_report(cluster):
    attr = zcl.foundation.Attribute()
    attr.attrid = 4
    attr.value = zcl.foundation.TypeValue()
    attr.value.value = "manufacturer"
    hdr = foundation.ZCLHeader(
        frame_control=foundation.FrameControl(
            frame_type=foundation.FrameType.GLOBAL_COMMAND,
            is_manufacturer_specific=False,
            direction=foundation.Direction.Server_to_Client,
            disable_default_response=True,
            reserved=0,
        ),
        manufacturer=None,
        tsn=1,
        command_id=foundation.GeneralCommand.Report_Attributes,
    )

    cmd = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Report_Attributes
    ].schema([attr])
    cluster.handle_message(hdr, cmd)

    assert cluster._attr_cache[4] == "manufacturer"


def test_handle_request_unknown(cluster):
    hdr = MagicMock(auto_spec=foundation.ZCLHeader)
    hdr.command_id = 0x42
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
    hdr.command_id = 0x42
    hdr.frame_control.is_general = False
    hdr.frame_control.is_cluster = True

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
        rar1 = _mk_rar(1, None, foundation.Status.HARDWARE_FAILURE)
        rar5 = _mk_rar(5, "Model")
        rar16 = _mk_rar(0x0010, None, zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE)
        return [[rar0, rar4, rar1, rar5, rar16]]

    cluster.request = mockrequest
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", "app_version", "model", "location_desc"]
    )
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert success["model"] == "Model"
    assert failure["app_version"] == foundation.Status.HARDWARE_FAILURE
    assert set(failure.keys()) == {"app_version", "location_desc"}
    assert cluster._attr_cache.is_unsupported(Basic.AttributeDefs.location_desc)


async def test_read_attributes_cached(cluster):
    cluster.request = MagicMock()
    cluster._attr_cache.set_value(Basic.AttributeDefs.zcl_version, 99)
    cluster._attr_cache.set_value(Basic.AttributeDefs.manufacturer, "Manufacturer")
    cluster.add_unsupported_attribute("location_desc")
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", "location_desc"], allow_cache=True
    )
    assert cluster.request.call_count == 0
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert failure == {"location_desc": foundation.Status.UNSUPPORTED_ATTRIBUTE}


async def test_read_attributes_mixed_cached(cluster):
    """Reading cached and uncached attributes."""

    cluster.request = AsyncMock(return_value=[[_mk_rar(5, "Model")]])
    cluster._attr_cache.set_value(Basic.AttributeDefs.zcl_version, 99)
    cluster._attr_cache.set_value(Basic.AttributeDefs.manufacturer, "Manufacturer")
    cluster.add_unsupported_attribute("location_desc")
    success, failure = await cluster.read_attributes(
        [0, "manufacturer", "model", "location_desc"], allow_cache=True
    )
    assert success[0] == 99
    assert success["manufacturer"] == "Manufacturer"
    assert success["model"] == "Model"
    assert cluster.request.await_count == 1
    assert cluster.request.call_args[0][3] == [0x0005]
    assert failure == {"location_desc": foundation.Status.UNSUPPORTED_ATTRIBUTE}


async def test_read_attributes_default_response(cluster):
    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        return [0xC1]

    cluster.request = mockrequest
    success, failure = await cluster.read_attributes(
        ["zcl_version", "model", "hw_version"], allow_cache=False
    )
    assert success == {}
    assert failure == {"zcl_version": 0xC1, "model": 0xC1, "hw_version": 0xC1}


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

    with pytest.raises(TypeError):
        # wrong key type
        cluster[None]

    with pytest.raises(TypeError):
        # wrong key type
        cluster.get(None)

    # Test access to cached attribute via wrong attr name
    with pytest.raises(KeyError):
        cluster.get("no_such_attribute")


async def test_write_attributes(cluster):
    success_response = [
        [foundation.WriteAttributesStatusRecord(status=foundation.Status.SUCCESS)]
    ]
    with patch.object(
        cluster, "_write_attributes", new=AsyncMock(return_value=success_response)
    ):
        await cluster.write_attributes({0: 5, "app_version": 4})
        assert cluster._write_attributes.call_count == 1


async def test_write_unknown_attribute(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        with pytest.raises(KeyError):
            # Using an invalid attribute name, the call should fail
            await cluster.write_attributes({"dummy_attribute": 5})
        assert cluster._write_attributes.call_count == 0


async def test_write_attributes_wrong_type(cluster):
    with patch.object(cluster, "_write_attributes", new=AsyncMock()):
        with pytest.raises(ValueError):
            await cluster.write_attributes({18: 0x2222})

        assert cluster._write_attributes.call_count == 0


@pytest.mark.parametrize(
    ("cluster_id", "attr", "value", "serialized"),
    [
        (0, "zcl_version", 0xAA, b"\x00\x00\x20\xaa"),
        (0, "model", "model x", b"\x05\x00\x42\x07model x"),
        (0, "device_enabled", True, b"\x12\x00\x10\x01"),
        (0, "alarm_mask", 0x55, b"\x13\x00\x18\x55"),
        (0x0202, "fan_mode", 0xDE, b"\x00\x00\x30\xde"),
    ],
)
async def test_write_attribute_types(
    cluster_id: int, attr: str, value: Any, serialized: bytes, cluster_by_id
):
    cluster = cluster_by_id(cluster_id)
    success_response = [
        [foundation.WriteAttributesStatusRecord(status=foundation.Status.SUCCESS)]
    ]
    with patch.object(
        cluster.endpoint, "request", new=AsyncMock(return_value=success_response)
    ):
        await cluster.write_attributes({attr: value})
        assert cluster._endpoint.reply.call_count == 0
        assert cluster._endpoint.request.call_count == 1
        assert cluster.endpoint.request.mock_calls[0].kwargs["data"][3:] == serialized


@pytest.mark.parametrize(
    "status", [foundation.Status.SUCCESS, foundation.Status.UNSUPPORTED_ATTRIBUTE]
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
    ("attributes", "result"),
    [
        ({4: "manufacturer"}, b"\x00"),
        ({4: "manufacturer", 5: "model"}, b"\x00"),
        ({4: "manufacturer", 5: "model", 3: 12}, b"\x00"),
    ],
)
async def test_write_attributes_cache_success(cluster, attributes, result):
    event_listener = MagicMock()
    cluster.on_event(AttributeWrittenEvent.event_type, event_listener)

    rsp_type = t.List[foundation.WriteAttributesStatusRecord]
    write_mock = AsyncMock(return_value=[rsp_type.deserialize(result)[0]])
    with patch.object(cluster, "_write_attributes", write_mock):
        await cluster.write_attributes(attributes)
        assert cluster._write_attributes.call_count == 1
        for attr_id in attributes:
            assert cluster._attr_cache[attr_id] == attributes[attr_id]

    assert len(event_listener.mock_calls) == len(attributes)
    for c in event_listener.mock_calls:
        event = c.args[0]
        assert event.status == foundation.Status.SUCCESS
        assert event.value == attributes[event.attribute_id]


@pytest.mark.parametrize(
    ("attributes", "result", "failed"),
    [
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
    ],
)
async def test_write_attributes_cache_failure(cluster, attributes, result, failed):
    event_listener = MagicMock()
    cluster.on_event(AttributeWrittenEvent.event_type, event_listener)

    rsp_type = foundation.WriteAttributesResponse
    write_mock = AsyncMock(return_value=[rsp_type.deserialize(result)[0]])

    with patch.object(cluster, "_write_attributes", write_mock):
        await cluster.write_attributes(attributes)
        assert cluster._write_attributes.call_count == 1
        for attr_id in attributes:
            if attr_id in failed:
                assert attr_id not in cluster._attr_cache
            else:
                assert cluster._attr_cache[attr_id] == attributes[attr_id]

    assert len(event_listener.mock_calls) == len(attributes)
    for c in event_listener.mock_calls:
        event = c.args[0]
        if event.attribute_id in failed:
            assert event.status != foundation.Status.SUCCESS
        else:
            assert event.status == foundation.Status.SUCCESS
        assert event.value == attributes[event.attribute_id]


async def test_bind(cluster):
    result = await cluster.bind()

    cluster._endpoint.device.zdo.bind.assert_called_with(cluster=cluster)
    assert cluster._endpoint.device.zdo.bind.call_count == 1
    assert result is cluster._endpoint.device.zdo.bind.return_value


async def test_unbind(cluster):
    result = await cluster.unbind()

    cluster._endpoint.device.zdo.unbind.assert_called_with(cluster=cluster)
    assert cluster._endpoint.device.zdo.unbind.call_count == 1
    assert result is cluster._endpoint.device.zdo.unbind.return_value


async def test_configure_reporting(cluster):
    await cluster.configure_reporting(0, 10, 20, 1)


async def test_configure_reporting_named(cluster):
    await cluster.configure_reporting("zcl_version", 10, 20, 1)
    assert cluster._endpoint.request.call_count == 1


async def test_configure_reporting_wrong_named(cluster):
    with pytest.raises(KeyError):
        await cluster.configure_reporting("wrong_attr_name", 10, 20, 1)

    assert cluster._endpoint.request.call_count == 0


async def test_configure_reporting_wrong_attrid(cluster):
    with pytest.raises(KeyError):
        await cluster.configure_reporting(0xABCD, 10, 20, 1)

    assert cluster._endpoint.request.call_count == 0


async def test_configure_reporting_manuf():
    ep = MagicMock()
    cluster = zcl.Cluster.from_id(ep, 6)
    success_response = [
        [foundation.ConfigureReportingResponseRecord(status=foundation.Status.SUCCESS)]
    ]
    cluster.request = AsyncMock(name="request", return_value=success_response)
    await cluster.configure_reporting(0, 10, 20, 1)
    assert cluster.request.mock_calls == [
        call(
            True,
            foundation.GeneralCommand.Configure_Reporting,
            mock.ANY,
            mock.ANY,
            expect_reply=True,
            manufacturer=None,
            tsn=None,
        )
    ]


@pytest.mark.parametrize(
    ("cluster_id", "attr", "data_type"),
    [
        (0, "zcl_version", 0x20),
        (0, "model", 0x42),
        (0, "device_enabled", 0x10),
        (0, "alarm_mask", 0x18),
        (0x0202, "fan_mode", 0x30),
        (0x0702, "summation_formatting", 0x18),
    ],
)
async def test_configure_reporting_types(cluster_id, attr, data_type, cluster_by_id):
    cluster = cluster_by_id(cluster_id)
    await cluster.configure_reporting(attr, 0x1234, 0x2345, 0xAA)
    assert cluster._endpoint.reply.call_count == 0
    assert cluster._endpoint.request.call_count == 1
    assert cluster.endpoint.request.mock_calls[0].kwargs["data"][6] == data_type


async def test_command(cluster):
    await cluster.command(0x00)
    assert cluster._endpoint.request.call_count == 1
    assert cluster._endpoint.request.mock_calls[0].kwargs["sequence"] == DEFAULT_TSN


async def test_command_override_tsn(cluster):
    await cluster.command(0x00, tsn=22)
    assert cluster._endpoint.request.call_count == 1
    assert cluster._endpoint.request.mock_calls[0].kwargs["sequence"] == 22


async def test_command_attr(cluster):
    await cluster.reset_fact_default()
    assert cluster._endpoint.request.call_count == 1


async def test_client_command_attr(client_cluster):
    await client_cluster.query_specific_file_response(status=foundation.Status.SUCCESS)
    assert client_cluster._endpoint.reply.call_count == 1


async def test_command_invalid_attr(cluster):
    with pytest.raises(AttributeError):
        await cluster.no_such_command()


async def test_invalid_arguments_cluster_command(cluster):
    with pytest.raises(TypeError):
        await cluster.command(0x00, 1)


async def test_invalid_arguments_cluster_client_command(client_cluster):
    with pytest.raises(ValueError):
        await client_cluster.client_command(
            command_id=Ota.ClientCommandDefs.upgrade_end_response.id,
            manufacturer_code=0,
            image_type=0,
            # Missing: file_version, current_time, upgrade_time
        )


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


async def test_handle_cluster_request_handler(cluster):
    hdr = foundation.ZCLHeader.cluster(123, 0x00)
    cluster.handle_cluster_request(hdr, [sentinel.arg1, sentinel.arg2])
    await asyncio.sleep(0)


async def test_handle_cluster_general_request_disable_default_rsp(endpoint):
    hdr, values = endpoint.in_clusters[0].deserialize(
        b"\x18\xcd\x0a\x01\xff\x42\x25\x01\x21\x95\x0b\x04\x21\xa8\x43\x05\x21\x36\x00"
        b"\x06\x24\x02\x00\x05\x00\x00\x64\x29\xf8\x07\x65\x21\xd9\x0e\x66\x2b\x84\x87"
        b"\x01\x00\x0a\x21\x00\x00",
    )
    cluster = endpoint.in_clusters[0]
    event_listener = MagicMock()
    cluster.on_event(zcl.AttributeReportedEvent.event_type, event_listener)

    with patch.object(cluster, "general_command") as general_cmd_mock:
        cluster.handle_cluster_general_request(hdr, values)
        await asyncio.sleep(0)
        assert len(event_listener.mock_calls) > 0
        assert general_cmd_mock.call_count == 0

    event_listener.reset_mock()
    with patch.object(cluster, "general_command") as general_cmd_mock:
        hdr.frame_control = hdr.frame_control.replace(disable_default_response=False)
        cluster.handle_cluster_general_request(hdr, values)
        await asyncio.sleep(0)
        assert len(event_listener.mock_calls) > 0
        assert general_cmd_mock.call_count == 1
        assert general_cmd_mock.call_args[1]["tsn"] == hdr.tsn


async def test_handle_cluster_general_request_not_attr_report(cluster):
    hdr = foundation.ZCLHeader.general(1, foundation.GeneralCommand.Write_Attributes)
    with (
        patch.object(cluster, "_update_attribute") as attr_lst_mock,
        patch.object(cluster, "general_command") as response_mock,
    ):
        cluster.handle_cluster_general_request(hdr, [1, 2, 3])
        await asyncio.sleep(0)
        assert attr_lst_mock.call_count == 0
        assert response_mock.mock_calls == [
            call(
                foundation.GeneralCommand.Default_Response,
                foundation.GeneralCommand.Write_Attributes,
                foundation.Status.SUCCESS,
                tsn=mock.ANY,
                priority=t.PacketPriority.LOW,
            )
        ]


async def test_configure_reporting_multiple(cluster):
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {0: zcl.foundation.Status.SUCCESS}
    )

    await cluster.configure_reporting(
        attribute=3,
        min_interval=5,
        max_interval=15,
        reportable_change=20,
    )
    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            )
        }
    )
    assert cluster.endpoint.request.call_count == 2
    # Both methods should produce equivalent requests
    assert (
        cluster.endpoint.request.mock_calls[0] == cluster.endpoint.request.mock_calls[1]
    )


async def test_configure_reporting_multiple_def_rsp(cluster):
    """Configure reporting returned a default response. May happen."""
    cluster.endpoint.request.return_value = (
        zcl.foundation.GeneralCommand.Configure_Reporting,
        zcl.foundation.Status.UNSUP_GENERAL_COMMAND,
    )
    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 1


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
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 1
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.hw_version)
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.manufacturer)


async def test_configure_reporting_multiple_single_fail(cluster):
    """Configure reporting returned a single failure response."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {3: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE}
    )

    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster._attr_cache.is_unsupported(Basic.AttributeDefs.hw_version)

    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {3: zcl.foundation.Status.SUCCESS}
    )
    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 2
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.hw_version)


async def test_configure_reporting_multiple_single_unreportable(cluster):
    """Configure reporting returned a single failure response for unreportable attribute."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {4: zcl.foundation.Status.UNREPORTABLE_ATTRIBUTE}
    )

    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 1
    # UNREPORTABLE_ATTRIBUTE doesn't mark the attribute as unsupported
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.manufacturer)


async def test_configure_reporting_multiple_both_unsupp(cluster):
    """Configure reporting returned unsupported attributes for both."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {
            3: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
            4: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
        }
    )

    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 1
    assert cluster._attr_cache.is_unsupported(Basic.AttributeDefs.hw_version)
    assert cluster._attr_cache.is_unsupported(Basic.AttributeDefs.manufacturer)

    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {
            3: zcl.foundation.Status.SUCCESS,
            4: zcl.foundation.Status.SUCCESS,
        }
    )

    await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )
    assert cluster.endpoint.request.await_count == 2
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.hw_version)
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.manufacturer)


def test_unsupported_attr_add(cluster):
    """Test adding unsupported attributes."""
    assert not cluster.is_attribute_unsupported(Basic.AttributeDefs.manufacturer)
    assert not cluster.is_attribute_unsupported(Basic.AttributeDefs.model)

    cluster.add_unsupported_attribute(Basic.AttributeDefs.model.id)
    assert cluster.is_attribute_unsupported(Basic.AttributeDefs.model)

    cluster.add_unsupported_attribute("manufacturer")
    assert cluster.is_attribute_unsupported(Basic.AttributeDefs.manufacturer)


def test_unsupported_attr_add_unknown_attribute(cluster):
    """Test adding unsupported attributes for unknown attributes raises KeyError."""

    with pytest.raises(KeyError):
        cluster.add_unsupported_attribute("no_such_attr")

    with pytest.raises(KeyError):
        cluster.add_unsupported_attribute(0xDEED)


def test_attr_cache_deprecated_setter(cluster, caplog):
    """Test deprecated _attr_cache setter logs warning and updates values."""
    cluster._attr_cache = {0x0004: "test_manufacturer", 0x0005: "test_model"}

    assert "Updating the attribute cache directly is deprecated" in caplog.text
    assert cluster.get(Basic.AttributeDefs.manufacturer) == "test_manufacturer"
    assert cluster.get(Basic.AttributeDefs.model) == "test_model"


def test_attribute_def_removal():
    """Test that setting an attribute definition to None removes it."""

    class ParentCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "parent"

        class AttributeDefs(zcl.BaseAttributeDefs):
            attr1 = foundation.ZCLAttributeDef(id=0x0001, type=t.uint8_t)
            attr2 = foundation.ZCLAttributeDef(id=0x0002, type=t.uint8_t)

    class ChildCluster(ParentCluster):
        class AttributeDefs(ParentCluster.AttributeDefs):
            attr1 = None  # Remove attr1

    assert ParentCluster.AttributeDefs.attr1 is not None
    assert ParentCluster.AttributeDefs.attr2 is not None
    assert ChildCluster.AttributeDefs.attr1 is None
    assert ChildCluster.AttributeDefs.attr2 is not None


async def test_read_attributes_duplicate(cluster):
    """Test that reading the same attribute twice raises ValueError."""
    with pytest.raises(ValueError, match="Cannot read the same attribute twice"):
        await cluster.read_attributes(
            [
                Basic.AttributeDefs.manufacturer,
                Basic.AttributeDefs.manufacturer,
            ]
        )


def test_zcl_command_duplicate_name_prevention():
    assert 0x1234 not in zcl.clusters.CLUSTERS_BY_ID

    with pytest.raises(TypeError):

        class TestCluster(zcl.Cluster):
            cluster_id = 0x1234
            ep_attribute = "test_cluster"
            server_commands = {
                0x00: foundation.ZCLCommandDef(name="command1", schema={}),
                0x01: foundation.ZCLCommandDef(name="command1", schema={}),
            }


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
    assert req == req  # noqa: PLR0124
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
    hdr1, _ = foundation.ZCLHeader.deserialize(ep.request.mock_calls[0].kwargs["data"])
    assert hdr1.direction == foundation.Direction.Client_to_Server

    ep.request.reset_mock()

    # Output cluster
    await ep.out_clusters[zcl.clusters.general.OnOff.cluster_id].on()
    hdr2, _ = foundation.ZCLHeader.deserialize(ep.request.mock_calls[0].kwargs["data"])
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

    ep.on_off.handle_message(hdr, cmd)

    await asyncio.sleep(0.1)

    packet = app_mock.send_packet.mock_calls[0].args[0]
    assert packet.cluster_id == zcl.clusters.general.OnOff.cluster_id

    # The direction is correct
    packet_hdr, _ = foundation.ZCLHeader.deserialize(packet.data.serialize())
    assert packet_hdr.direction == foundation.Direction.Client_to_Server


async def test_zcl_cluster_definition_backwards_compatibility():
    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        attributes = {
            0x1234: ("attribute", t.uint8_t),
            0x1235: ("attribute2", t.uint32_t, True),
        }

        server_commands = {
            0x00: ("server_command", (t.uint8_t,), True),
        }

        client_commands = {
            0x01: ("client_command", (t.uint8_t, t.uint16_t), False),
        }

    assert TestCluster.cluster_id == 0xABCD

    assert TestCluster.AttributeDefs.attribute.id == 0x1234
    assert TestCluster.AttributeDefs.attribute.type == t.uint8_t
    assert TestCluster.AttributeDefs.attribute.is_manufacturer_specific is False

    assert TestCluster.AttributeDefs.attribute2.id == 0x1235
    assert TestCluster.AttributeDefs.attribute2.type == t.uint32_t
    assert TestCluster.AttributeDefs.attribute2.is_manufacturer_specific is True

    assert TestCluster.ServerCommandDefs.server_command.id == 0x00
    assert len(TestCluster.ServerCommandDefs.server_command.schema.fields) == 1
    assert (
        TestCluster.ServerCommandDefs.server_command.schema.fields.param1.type
        == t.uint8_t
    )

    assert TestCluster.ClientCommandDefs.client_command.id == 0x01
    assert len(TestCluster.ClientCommandDefs.client_command.schema.fields) == 2
    assert (
        TestCluster.ClientCommandDefs.client_command.schema.fields.param1.type
        == t.uint8_t
    )
    assert (
        TestCluster.ClientCommandDefs.client_command.schema.fields.param2.type
        == t.uint16_t
    )


async def test_zcl_cluster_definition_invalid_name():
    # This is fine
    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        class AttributeDefs(zcl.BaseAttributeDefs):
            upgrade_server_id = foundation.ZCLAttributeDef(
                name="upgrade_server_id",
                id=0x0000,
                type=t.EUI64,
                access="r",
                mandatory=True,
            )

        class ServerCommandDefs(zcl.BaseCommandDefs):
            upgrade_end = foundation.ZCLCommandDef(
                name="upgrade_end",
                id=0x06,
                schema={
                    "status": foundation.Status,
                    "manufacturer_code": t.uint16_t,
                    "image_type": t.uint16_t,
                    "file_version": t.uint32_t,
                },
            )

    # This is not
    with pytest.raises(TypeError):

        class TestCluster(zcl.Cluster):
            cluster_id = 0xABCD
            ep_attribute = "test_cluster"

            class AttributeDefs(zcl.BaseAttributeDefs):
                upgrade_server_id = foundation.ZCLAttributeDef(
                    name="some_other_name",
                    id=0x0000,
                    type=t.EUI64,
                    access="r",
                    mandatory=True,
                )

    # Nor is this
    with pytest.raises(TypeError):

        class TestCluster(zcl.Cluster):
            cluster_id = 0xABCD
            ep_attribute = "test_cluster"

            class ServerCommandDefs(zcl.BaseCommandDefs):
                upgrade_end = foundation.ZCLCommandDef(
                    name="some_other_name",
                    id=0x06,
                    schema={
                        "status": foundation.Status,
                        "manufacturer_code": t.uint16_t,
                        "image_type": t.uint16_t,
                        "file_version": t.uint32_t,
                    },
                )


async def test_cluster_definition_invalid_direction():
    # Test that incorrect direction on server command triggers warning
    # ServerCommandDefs should have direction Server_to_Client, so Client_to_Server is wrong
    with pytest.warns(
        DeprecationWarning, match="Command 'server_command' has an incorrect direction"
    ):

        class TestCluster(zcl.Cluster):
            cluster_id = 0xABCD
            ep_attribute = "test_cluster"

            class ServerCommandDefs(zcl.BaseCommandDefs):
                server_command = foundation.ZCLCommandDef(
                    name="server_command",
                    id=0x00,
                    schema={},
                    direction=foundation.Direction.Client_to_Server,  # Wrong direction
                )

    # Verify direction was auto-corrected
    assert (
        TestCluster.ServerCommandDefs.server_command.direction
        == foundation.Direction.Server_to_Client
    )

    # Test that incorrect direction on client command also triggers warning
    # ClientCommandDefs should have direction Client_to_Server, so Server_to_Client is wrong
    with pytest.warns(
        DeprecationWarning, match="Command 'client_command' has an incorrect direction"
    ):

        class TestCluster2(zcl.Cluster):
            cluster_id = 0xDEF0
            ep_attribute = "test_cluster2"

            class ClientCommandDefs(zcl.BaseCommandDefs):
                client_command = foundation.ZCLCommandDef(
                    name="client_command",
                    id=0x00,
                    schema={},
                    direction=foundation.Direction.Server_to_Client,  # Wrong direction
                )

    # Verify direction was auto-corrected
    assert (
        TestCluster2.ClientCommandDefs.client_command.direction
        == foundation.Direction.Client_to_Server
    )


async def test_received_onoff_toggle_generates_default_response():
    """Test that a received OnOff:toggle generates a default response."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )

    # The device has both
    _on_off_server = dev.endpoints[1].add_input_cluster(
        zcl.clusters.general.OnOff.cluster_id
    )
    on_off_client = dev.endpoints[1].add_output_cluster(
        zcl.clusters.general.OnOff.cluster_id
    )

    await dev.initialize()

    req_hdr, req_cmd = on_off_client._create_request(
        general=False,
        command_id=OnOff.ServerCommandDefs.toggle.id,
        schema=OnOff.ServerCommandDefs.toggle.schema,
        tsn=45,
        disable_default_response=False,
        direction=foundation.Direction.Client_to_Server,
        args=(),
        kwargs={},
    )

    with patch.object(dev.endpoints[1], "reply") as mock_request:
        dev.application.packet_received(
            t.ZigbeePacket(
                src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
                src_ep=1,
                dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
                dst_ep=1,
                tsn=req_hdr.tsn,
                profile_id=zigpy.profiles.zha.PROFILE_ID,
                cluster_id=OnOff.cluster_id,
                data=t.SerializableBytes(req_hdr.serialize() + req_cmd.serialize()),
                lqi=255,
                rssi=-30,
            )
        )
        await asyncio.sleep(0)

    expected_rsp_hdr, expected_rsp_cmd = on_off_client._create_request(
        general=True,
        command_id=foundation.GeneralCommand.Default_Response,
        schema=foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema,
        tsn=req_hdr.tsn,
        disable_default_response=True,
        direction=foundation.Direction.Server_to_Client,
        args=(),
        kwargs={
            "command_id": OnOff.ServerCommandDefs.toggle.id,
            "status": foundation.Status.SUCCESS,
        },
    )

    assert mock_request.mock_calls == [
        call(
            cluster=OnOff.cluster_id,
            sequence=expected_rsp_hdr.tsn,
            command_id=foundation.GeneralCommand.Default_Response,
            data=expected_rsp_hdr.serialize() + expected_rsp_cmd.serialize(),
            timeout=5,
            expect_reply=False,
            use_ieee=False,
            ask_for_ack=None,
            priority=t.PacketPriority.LOW,
        )
    ]


def test_find_attribute_simple() -> None:
    """Test attribute finding with simple cluster definition."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        class AttributeDefs(zcl.BaseAttributeDefs):
            attribute1 = foundation.ZCLAttributeDef(id=0x0001, type=t.EUI64)
            attribute2 = foundation.ZCLAttributeDef(
                id=0x0002, type=t.EUI64, manufacturer_code=0x1234
            )

    assert (
        TestCluster.find_attribute("attribute1") is TestCluster.AttributeDefs.attribute1
    )
    assert TestCluster.find_attribute(0x0001) is TestCluster.AttributeDefs.attribute1
    assert TestCluster.find_attribute(0x0002) is TestCluster.AttributeDefs.attribute2
    assert (
        TestCluster.find_attribute(TestCluster.AttributeDefs.attribute2)
        is TestCluster.AttributeDefs.attribute2
    )

    with pytest.raises(KeyError):
        TestCluster.find_attribute(0x0003)

    with pytest.raises(TypeError):
        TestCluster.find_attribute(b"attribute1")


def test_find_attribute_colliding_manufacturer_codes() -> None:
    """Test attribute finding with simple cluster definition."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        class AttributeDefs(zcl.BaseAttributeDefs):
            attribute1 = foundation.ZCLAttributeDef(id=0x0001, type=t.EUI64)
            attribute2 = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, manufacturer_code=0x1234
            )
            attribute3 = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, manufacturer_code=0x5678
            )
            attribute4 = foundation.ZCLAttributeDef(id=0x0002, type=t.EUI64)

    assert (
        TestCluster.find_attribute("attribute1") is TestCluster.AttributeDefs.attribute1
    )

    with pytest.raises(KeyError, match="Multiple definitions exist for attribute"):
        TestCluster.find_attribute(0x0001)

    assert (
        TestCluster.find_attribute(0x0001, manufacturer_code=0x1234)
        is TestCluster.AttributeDefs.attribute2
    )
    assert (
        TestCluster.find_attribute(0x0001, manufacturer_code=0x5678)
        is TestCluster.AttributeDefs.attribute3
    )
    assert TestCluster.find_attribute(0x0002) is TestCluster.AttributeDefs.attribute4


def test_find_attribute_unspecified_manufacturer_code() -> None:
    """Test attribute finding when the manufacturer code is unspecified."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        class AttributeDefs(zcl.BaseAttributeDefs):
            attribute1 = foundation.ZCLAttributeDef(id=0x0001, type=t.EUI64)
            attribute2 = foundation.ZCLAttributeDef(
                id=0x0002, type=t.EUI64, is_manufacturer_specific=True
            )
            attribute3 = foundation.ZCLAttributeDef(id=0x0002, type=t.EUI64)
            attribute4 = foundation.ZCLAttributeDef(
                id=0x0003, type=t.EUI64, manufacturer_code=0x1234
            )

    assert TestCluster.find_attribute(0x0001) is TestCluster.AttributeDefs.attribute1

    assert (
        TestCluster.find_attribute(0x0002, manufacturer_code=0x1234)
        is TestCluster.AttributeDefs.attribute2
    )
    assert (
        TestCluster.find_attribute(0x0002, manufacturer_code=None)
        is TestCluster.AttributeDefs.attribute3
    )

    with pytest.raises(KeyError):
        TestCluster.find_attribute(0x0003, manufacturer_code=0x5678)


async def test_read_attributes_complex() -> None:
    """Test reading attributes, complex scenario."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        class AttributeDefs(zcl.BaseAttributeDefs):
            attribute1 = foundation.ZCLAttributeDef(id=0x0001, type=t.uint8_t)
            attribute2 = foundation.ZCLAttributeDef(id=0x0002, type=t.uint8_t)

            # These two can be read together
            attribute3 = foundation.ZCLAttributeDef(
                id=0x0001, type=t.uint8_t, manufacturer_code=0x1234
            )
            attribute4 = foundation.ZCLAttributeDef(
                id=0x0002, type=t.uint8_t, manufacturer_code=0x1234
            )

            # As can these two
            attribute5 = foundation.ZCLAttributeDef(
                id=0x0003, type=t.uint8_t, manufacturer_code=0x5678
            )
            attribute6 = foundation.ZCLAttributeDef(
                id=0x0004, type=t.uint8_t, manufacturer_code=0x5678
            )

    endpoint = AsyncMock(spec=zigpy.endpoint.Endpoint)
    cluster = TestCluster(endpoint)

    async def mock_read_attributes(
        attribute_ids: list[int], manufacturer: int | None = None, **kwargs
    ):
        status_records = {
            (None, (0x0001, 0x0002)): [
                # One is supported
                foundation.ReadAttributeRecord(
                    attrid=0x0001,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(123),
                    ),
                ),
                # The other is not
                foundation.ReadAttributeRecord(
                    attrid=0x0002,
                    status=foundation.Status.UNSUPPORTED_ATTRIBUTE,
                ),
            ],
            (0x1234, (0x0001, 0x0002)): [
                # Both are supported
                foundation.ReadAttributeRecord(
                    attrid=0x0001,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(12),
                    ),
                ),
                foundation.ReadAttributeRecord(
                    attrid=0x0002,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(34),
                    ),
                ),
            ],
            (0x5678, (0x0003, 0x0004)): [
                # Neither of these are supported
                foundation.ReadAttributeRecord(
                    attrid=0x0003,
                    status=foundation.Status.UNSUPPORTED_ATTRIBUTE,
                ),
                foundation.ReadAttributeRecord(
                    attrid=0x0004,
                    status=foundation.Status.UNSUPPORTED_ATTRIBUTE,
                ),
            ],
        }[manufacturer, tuple(attribute_ids)]

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Read_Attributes_rsp
        ].schema(status_records=status_records)

    with patch.object(
        cluster, "_read_attributes", side_effect=mock_read_attributes
    ) as mock_raw:
        success, failure = await cluster.read_attributes(
            [
                # These are arranged "randomly" but will still be read in order within
                # a particular batch
                TestCluster.AttributeDefs.attribute1,  # Batch 1  (no code)
                TestCluster.AttributeDefs.attribute5,  # Batch 2  (0x5678)
                TestCluster.AttributeDefs.attribute3,  # Batch 3  (0x1234)
                TestCluster.AttributeDefs.attribute2,  # Batch 1  (no code)
                TestCluster.AttributeDefs.attribute4,  # Batch 2  (0x5678)
                TestCluster.AttributeDefs.attribute6,  # Batch 3  (0x1234)
            ]
        )

    assert success == {
        TestCluster.AttributeDefs.attribute1: 123,
        TestCluster.AttributeDefs.attribute3: 12,
        TestCluster.AttributeDefs.attribute4: 34,
    }

    assert failure == {
        TestCluster.AttributeDefs.attribute2: foundation.Status.UNSUPPORTED_ATTRIBUTE,
        TestCluster.AttributeDefs.attribute5: foundation.Status.UNSUPPORTED_ATTRIBUTE,
        TestCluster.AttributeDefs.attribute6: foundation.Status.UNSUPPORTED_ATTRIBUTE,
    }

    assert mock_raw.mock_calls == [
        call([0x0001, 0x0002], manufacturer=None),
        call([0x0003, 0x0004], manufacturer=0x5678),
        call([0x0001, 0x0002], manufacturer=0x1234),
    ]


async def test_command_explicit_manufacturer():
    """Test that explicit manufacturer= overrides command definition's manufacturer_code."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"

        class ServerCommandDefs(zcl.foundation.BaseCommandDefs):
            test_cmd = foundation.ZCLCommandDef(id=0x00, schema={})

    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = TestCluster(endpoint)

    with patch.object(cluster, "request", autospec=True) as mock_request:
        await cluster.command(0x00, manufacturer=0x9999)

    assert mock_request.mock_calls[0].kwargs["manufacturer"] == 0x9999


async def test_read_attribute_manufacturer_code_none_on_manuf_cluster():
    """Test that manufacturer_code=None suppresses manufacturer code on manuf clusters."""

    class ManufCluster(zcl.Cluster):
        cluster_id = 0xFC11  # Manufacturer-specific cluster range
        ep_attribute = "manuf_cluster"

        class AttributeDefs(zcl.BaseAttributeDefs):
            # Explicitly no manufacturer code, even though cluster is manufacturer-specific
            valve_opening = foundation.ZCLAttributeDef(
                id=0x600B, type=t.uint8_t, manufacturer_code=None
            )

    endpoint = MagicMock(spec=zigpy.endpoint.Endpoint)
    cluster = ManufCluster(endpoint)

    with mock_attribute_reads(
        cluster, {ManufCluster.AttributeDefs.valve_opening: t.uint8_t(100)}
    ) as (mock_read, _):
        await cluster.read_attributes([ManufCluster.AttributeDefs.valve_opening])

    assert mock_read.mock_calls == [call([0x600B], manufacturer=None)]


async def test_report_attributes_quirk_transforms_value(app_mock):
    """Test that quirks transforming values emit both reported and updated events."""
    MOTION_ATTRIBUTE = 0x0112  # Unknown attribute that triggers motion

    class DoublingCluster(zcl.Cluster):
        """A quirk cluster that doubles reported values."""

        cluster_id = 0xABCD
        ep_attribute = "doubling"

        class AttributeDefs(zcl.foundation.BaseAttributeDefs):
            test_attr = foundation.ZCLAttributeDef(
                id=0x0001, type=t.uint8_t, access="r"
            )
            other_attr = foundation.ZCLAttributeDef(
                id=0x0002, type=t.uint8_t, access="r"
            )
            passthrough_attr = foundation.ZCLAttributeDef(
                id=0x0003, type=t.uint8_t, access="r"
            )
            swallowed_attr = foundation.ZCLAttributeDef(
                id=0x0004, type=t.uint8_t, access="r"
            )

        def _update_attribute(self, attrid, value):
            if attrid == self.AttributeDefs.test_attr.id:
                # Double the value
                value = value * 2
                super()._update_attribute(attrid, value)

                # Also update a different attribute
                super()._update_attribute(self.AttributeDefs.other_attr.id, 123)

                # Update an attribute that doesn't have a definition
                super()._update_attribute(0xABCD, 45)
            elif attrid == MOTION_ATTRIBUTE:
                # Unknown attribute that updates a different cluster (like motion sensors)
                super()._update_attribute(attrid, value)
                self.endpoint.occupancy.update_attribute(
                    OccupancySensing.AttributeDefs.occupancy.id,
                    OccupancySensing.Occupancy.Occupied,
                )
            elif attrid == self.AttributeDefs.swallowed_attr.id:
                # Swallow the attribute update entirely (no super() call)
                return
            else:
                # Pass through unchanged
                super()._update_attribute(attrid, value)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = DoublingCluster(dev.endpoints[1])
    occupancy_cluster = OccupancySensing(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(DoublingCluster.cluster_id, cluster)
    dev.endpoints[1].add_input_cluster(OccupancySensing.cluster_id, occupancy_cluster)

    events = []
    cluster.on_event(AttributeReadEvent.event_type, events.append)
    cluster.on_event(AttributeReportedEvent.event_type, events.append)
    cluster.on_event(AttributeUpdatedEvent.event_type, events.append)
    occupancy_cluster.on_event(AttributeReportedEvent.event_type, events.append)
    occupancy_cluster.on_event(AttributeUpdatedEvent.event_type, events.append)

    await mock_attribute_report(
        cluster,
        {
            DoublingCluster.AttributeDefs.test_attr: t.uint8_t(50),
            DoublingCluster.AttributeDefs.passthrough_attr: t.uint8_t(99),
            DoublingCluster.AttributeDefs.swallowed_attr: t.uint8_t(42),
            MOTION_ATTRIBUTE: t.uint8_t(1),  # Unknown attribute (raw ID)
        },
    )

    assert events == [
        # No event for swallowed_attr since quirk swallows it entirely
        # No AttributeReportedEvent for test_attr since the value was transformed
        # AttributeUpdatedEvent for other_attr (quirk side-effect)
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name="other_attr",
            attribute_id=DoublingCluster.AttributeDefs.other_attr.id,
            manufacturer_code=None,
            value=123,
        ),
        # AttributeUpdatedEvent for unknown attribute
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name=None,
            attribute_id=0xABCD,
            manufacturer_code=None,
            value=45,
        ),
        # AttributeUpdatedEvent for test_attr with transformed value (doubled)
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name="test_attr",
            attribute_id=DoublingCluster.AttributeDefs.test_attr.id,
            manufacturer_code=None,
            value=100,
        ),
        # AttributeReportedEvent for passthrough_attr (no transformation)
        AttributeReportedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name="passthrough_attr",
            attribute_id=DoublingCluster.AttributeDefs.passthrough_attr.id,
            manufacturer_code=None,
            raw_value=99,
            value=99,
        ),
        # No AttributeUpdatedEvent for passthrough_attr since value wasn't transformed
        # AttributeUpdatedEvent for occupancy (quirk updates different cluster)
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=OccupancySensing.cluster_id,
            attribute_name="occupancy",
            attribute_id=OccupancySensing.AttributeDefs.occupancy.id,
            manufacturer_code=None,
            value=OccupancySensing.Occupancy.Occupied,
        ),
        # AttributeReportedEvent for unknown MOTION_ATTRIBUTE (no transformation)
        AttributeReportedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name=None,
            attribute_id=MOTION_ATTRIBUTE,
            manufacturer_code=None,
            raw_value=1,
            value=1,
        ),
    ]

    # Now test the read path
    events.clear()

    with mock_attribute_reads(
        cluster,
        {
            DoublingCluster.AttributeDefs.test_attr: t.uint8_t(25),
            DoublingCluster.AttributeDefs.passthrough_attr: t.uint8_t(77),
            DoublingCluster.AttributeDefs.swallowed_attr: t.uint8_t(99),
        },
    ):
        await cluster.read_attributes(
            [
                DoublingCluster.AttributeDefs.test_attr,
                DoublingCluster.AttributeDefs.passthrough_attr,
                DoublingCluster.AttributeDefs.swallowed_attr,
            ]
        )

    assert events == [
        # No event for swallowed_attr since quirk swallows it entirely
        # No AttributeReadEvent for test_attr since the value was transformed
        # AttributeUpdatedEvent for other_attr (quirk side-effect)
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name="other_attr",
            attribute_id=DoublingCluster.AttributeDefs.other_attr.id,
            manufacturer_code=None,
            value=123,
        ),
        # AttributeUpdatedEvent for unknown attribute
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name=None,
            attribute_id=0xABCD,
            manufacturer_code=None,
            value=45,
        ),
        # AttributeUpdatedEvent for test_attr with transformed value (doubled)
        AttributeUpdatedEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name="test_attr",
            attribute_id=DoublingCluster.AttributeDefs.test_attr.id,
            manufacturer_code=None,
            value=50,  # Doubled from 25
        ),
        # AttributeReadEvent for passthrough_attr (no transformation)
        AttributeReadEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=DoublingCluster.cluster_id,
            attribute_name="passthrough_attr",
            attribute_id=DoublingCluster.AttributeDefs.passthrough_attr.id,
            manufacturer_code=None,
            raw_value=77,
            value=77,
        ),
        # No AttributeUpdatedEvent for passthrough_attr since value wasn't transformed
    ]


async def test_zcl_write_attributes_update_cache(app_mock) -> None:
    """Test that `write_attributes` can skip updating the attribute cache."""
    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))

    cluster = Basic(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(Basic.cluster_id, cluster)

    cluster.add_unsupported_attribute(Basic.AttributeDefs.product_url)

    # The cache updates by default
    with mock_attribute_writes(
        cluster,
        {
            Basic.AttributeDefs.location_desc: foundation.Status.SUCCESS,
            Basic.AttributeDefs.serial_number: foundation.Status.UNSUPPORTED_ATTRIBUTE,
            Basic.AttributeDefs.product_url: foundation.Status.SUCCESS,
        },
    ):
        await cluster.write_attributes(
            {
                Basic.AttributeDefs.location_desc: "Test",
                Basic.AttributeDefs.serial_number: "1234",
                Basic.AttributeDefs.product_url: "5678",
            }
        )

    # The cache updated and all attribute state makes sense
    assert cluster._attr_cache.get(Basic.AttributeDefs.location_desc) == "Test"
    assert cluster.is_attribute_unsupported(Basic.AttributeDefs.serial_number) is True
    assert not cluster.is_attribute_unsupported(Basic.AttributeDefs.product_url)
    assert cluster._attr_cache.get(Basic.AttributeDefs.product_url) == "5678"

    events = []
    cluster.on_all_events(events.append)

    with mock_attribute_writes(
        cluster,
        {
            Basic.AttributeDefs.location_desc: foundation.Status.SUCCESS,
            # We flip things around: `serial_number` is reported as supported
            Basic.AttributeDefs.serial_number: foundation.Status.SUCCESS,
            # And `product_url` is now unsupported
            Basic.AttributeDefs.product_url: foundation.Status.UNSUPPORTED_ATTRIBUTE,
        },
    ):
        await cluster.write_attributes(
            {
                Basic.AttributeDefs.location_desc: "Test 2",
                Basic.AttributeDefs.serial_number: "abcd",
                Basic.AttributeDefs.product_url: "efgh",
            },
            update_cache=False,
        )

    # Nothing changes, however
    assert cluster._attr_cache.get(Basic.AttributeDefs.location_desc) == "Test"
    assert cluster.is_attribute_unsupported(Basic.AttributeDefs.serial_number) is True
    assert not cluster.is_attribute_unsupported(Basic.AttributeDefs.product_url)
    assert cluster._attr_cache.get(Basic.AttributeDefs.product_url) == "5678"

    # No events should have been emitted
    assert events == []


def test_manufacturer_id_override_manuf_specific_cluster(app_mock) -> None:
    """Test class-level `manufacturer_id_override` for custom clusters."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xFEED  # Manufacturer-specific cluster range
        ep_attribute = "test_cluster"
        manufacturer_id_override = 0x5678

        class AttributeDefs(zcl.BaseAttributeDefs):
            test_attr1 = foundation.ZCLAttributeDef(
                id=0xB001,
                type=t.uint8_t,
                # Definition-level override takes priority
                manufacturer_code=0xABCD,
            )
            test_attr2 = foundation.ZCLAttributeDef(
                id=0xB002,
                type=t.uint8_t,
                # Definition-level override takes priority
                manufacturer_code=None,
            )
            test_attr3 = foundation.ZCLAttributeDef(
                id=0xB003,
                type=t.uint8_t,
                # While not strictly necessary, it is correct
                is_manufacturer_specific=True,
            )
            test_attr4 = foundation.ZCLAttributeDef(
                id=0xB004,
                type=t.uint8_t,
            )
            test_attr5 = foundation.ZCLAttributeDef(
                id=0xB005,
                type=t.uint8_t,
                is_manufacturer_specific=False,
                # This is technically incorrect but since this cluster ID is in the
                # manufacturer range, the default value of `is_manufacturer_specific`
                # is effectively ignored, it must be
            )

        class ServerCommandDefs(zcl.BaseCommandDefs):
            test_cmd1 = foundation.ZCLCommandDef(
                id=0xB1, schema={}, manufacturer_code=0xABCD
            )
            test_cmd2 = foundation.ZCLCommandDef(
                id=0xB2, schema={}, manufacturer_code=None
            )
            test_cmd3 = foundation.ZCLCommandDef(
                id=0xB3, schema={}, is_manufacturer_specific=True
            )
            test_cmd4 = foundation.ZCLCommandDef(id=0xB4, schema={})
            test_cmd5 = foundation.ZCLCommandDef(
                id=0xB5, schema={}, is_manufacturer_specific=False
            )

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    dev.node_desc.manufacturer_code = 0x1234

    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    for definition, expected in [
        (TestCluster.AttributeDefs.test_attr1, 0xABCD),
        (TestCluster.ServerCommandDefs.test_cmd1, 0xABCD),
        (TestCluster.AttributeDefs.test_attr2, None),
        (TestCluster.ServerCommandDefs.test_cmd2, None),
        (TestCluster.AttributeDefs.test_attr3, 0x5678),
        (TestCluster.ServerCommandDefs.test_cmd3, 0x5678),
        (TestCluster.AttributeDefs.test_attr4, 0x5678),
        (TestCluster.ServerCommandDefs.test_cmd4, 0x5678),
        (TestCluster.AttributeDefs.test_attr5, None),
        (TestCluster.ServerCommandDefs.test_cmd5, None),
    ]:
        assert cluster._get_effective_manufacturer_code(definition) is expected


def test_manufacturer_id_override_extended_zcl_cluster(app_mock) -> None:
    """Test class-level `manufacturer_id_override` for extended ZCL clusters."""

    class TestCluster(Basic):
        _skip_registry = True
        manufacturer_id_override = 0x5678

        class AttributeDefs(Basic.AttributeDefs):
            test_attr1 = foundation.ZCLAttributeDef(
                id=0xB001,
                type=t.uint8_t,
                # Definition-level override takes priority
                manufacturer_code=0xABCD,
            )
            test_attr2 = foundation.ZCLAttributeDef(
                id=0xB002,
                type=t.uint8_t,
                # Definition-level override takes priority
                manufacturer_code=None,
            )
            test_attr3 = foundation.ZCLAttributeDef(
                id=0xB003,
                type=t.uint8_t,
                is_manufacturer_specific=True,
            )
            test_attr4 = foundation.ZCLAttributeDef(
                id=0xB004,
                type=t.uint8_t,
                # A normal attribute
            )
            test_attr5 = foundation.ZCLAttributeDef(
                id=0xB005,
                type=t.uint8_t,
                # While not strictly necessary, it is correct
                is_manufacturer_specific=False,
            )

        class ServerCommandDefs(Basic.ServerCommandDefs):
            test_cmd1 = foundation.ZCLCommandDef(
                id=0xB1, schema={}, manufacturer_code=0xABCD
            )
            test_cmd2 = foundation.ZCLCommandDef(
                id=0xB2, schema={}, manufacturer_code=None
            )
            test_cmd3 = foundation.ZCLCommandDef(
                id=0xB3, schema={}, is_manufacturer_specific=True
            )
            test_cmd4 = foundation.ZCLCommandDef(id=0xB4, schema={})
            test_cmd5 = foundation.ZCLCommandDef(
                id=0xB5, schema={}, is_manufacturer_specific=False
            )

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    dev.node_desc.manufacturer_code = 0x1234

    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    for definition, expected in [
        (TestCluster.AttributeDefs.test_attr1, 0xABCD),
        (TestCluster.ServerCommandDefs.test_cmd1, 0xABCD),
        (TestCluster.AttributeDefs.test_attr2, None),
        (TestCluster.ServerCommandDefs.test_cmd2, None),
        (TestCluster.AttributeDefs.test_attr3, 0x5678),
        (TestCluster.ServerCommandDefs.test_cmd3, 0x5678),
        (TestCluster.AttributeDefs.test_attr4, None),
        (TestCluster.ServerCommandDefs.test_cmd4, None),
        (TestCluster.AttributeDefs.test_attr5, None),
        (TestCluster.ServerCommandDefs.test_cmd5, None),
        (TestCluster.AttributeDefs.model, None),
        (TestCluster.ServerCommandDefs.reset_fact_default, None),
    ]:
        assert cluster._get_effective_manufacturer_code(definition) is expected
