from __future__ import annotations

import asyncio
import logging
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
    MAX_ATTRIBUTE_RECORDS_BYTES,
    AttributeReadEvent,
    AttributeReportedEvent,
    AttributeUpdatedEvent,
    AttributeWrittenEvent,
    _chunk_records_by_size,
    foundation,
)
from zigpy.zcl.clusters.general import Basic, OnOff, Ota
from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.zcl.clusters.smartenergy import Metering
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


def test_attribute_report_manufacturer_specific_does_not_update_zcl_attribute(
    cluster_by_id,
):
    """Manufacturer-specific attribute report must not update a standard ZCL attribute.

    A device reports attribute 0x0302 with manufacturer code 0x1015 on the Metering
    cluster (0x0702). Even though 0x0302 is the standard ZCL "divisor" attribute, the
    report is manufacturer-specific and should NOT update the standard divisor cache.
    """
    metering = cluster_by_id(Metering.cluster_id)

    # Ensure divisor is not in the cache
    assert Metering.AttributeDefs.divisor.id not in metering._attr_cache

    attr = zcl.foundation.Attribute()
    attr.attrid = 0x0302
    attr.value = zcl.foundation.TypeValue()
    attr.value.value = 0x0200

    hdr = foundation.ZCLHeader(
        frame_control=foundation.FrameControl(
            frame_type=foundation.FrameType.GLOBAL_COMMAND,
            is_manufacturer_specific=True,
            direction=foundation.Direction.Server_to_Client,
            disable_default_response=True,
            reserved=0,
        ),
        manufacturer=0x1015,
        tsn=3,
        command_id=foundation.GeneralCommand.Report_Attributes,
    )

    cmd = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Report_Attributes
    ].schema([attr])
    metering.handle_message(hdr, cmd)

    # The standard ZCL divisor attribute's typed cache must NOT be updated
    with pytest.raises(KeyError):
        metering._attr_cache.get_value(Metering.AttributeDefs.divisor)

    # The value should only be stored in the legacy cache (keyed by raw attr ID)
    assert 0x0302 in metering._attr_cache._legacy_cache
    assert metering._attr_cache._legacy_cache[0x0302].value == 0x0200


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
    cfg_response = zcl.foundation.ConfigureReportingResponse(
        [zcl.foundation.ConfigureReportingResponseRecord(zcl.foundation.Status.SUCCESS)]
    )
    cluster.endpoint.request.return_value = [cfg_response]

    await cluster.configure_reporting(
        attribute=3,
        min_interval=5,
        max_interval=15,
        reportable_change=20,
    )
    results = await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            )
        }
    )
    assert cluster.endpoint.request.call_count == 2
    assert len(results) == 1
    assert results[Basic.AttributeDefs.hw_version] == zcl.foundation.Status.SUCCESS
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
    results = await cluster.configure_reporting_multiple(
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
    assert len(results) == 2
    assert all(
        s == zcl.foundation.Status.UNSUP_GENERAL_COMMAND for s in results.values()
    )


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
    """Configure reporting returned a single global success response."""
    cfg_response = zcl.foundation.ConfigureReportingResponse(
        [zcl.foundation.ConfigureReportingResponseRecord(zcl.foundation.Status.SUCCESS)]
    )
    cluster.endpoint.request.return_value = [cfg_response]

    results = await cluster.configure_reporting_multiple(
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
    assert len(results) == 2
    assert all(s == zcl.foundation.Status.SUCCESS for s in results.values())


async def test_configure_reporting_multiple_single_fail(cluster):
    """Configure reporting returned a single failure response.

    Per ZCL spec, only the failed attribute is in the response; the other
    attribute implicitly succeeded.
    """
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {3: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE}
    )

    results = await cluster.configure_reporting_multiple(
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
    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.manufacturer)
    assert len(results) == 2
    assert (
        results[Basic.AttributeDefs.hw_version]
        == zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE
    )
    assert results[Basic.AttributeDefs.manufacturer] == zcl.foundation.Status.SUCCESS

    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {3: zcl.foundation.Status.SUCCESS}
    )
    results = await cluster.configure_reporting_multiple(
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
    assert len(results) == 2
    assert all(s == zcl.foundation.Status.SUCCESS for s in results.values())


async def test_configure_reporting_multiple_single_unreportable(cluster):
    """Configure reporting returned a single failure response for unreportable attribute."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {4: zcl.foundation.Status.UNREPORTABLE_ATTRIBUTE}
    )

    results = await cluster.configure_reporting_multiple(
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
    assert len(results) == 2
    assert (
        results[Basic.AttributeDefs.manufacturer]
        == zcl.foundation.Status.UNREPORTABLE_ATTRIBUTE
    )
    assert results[Basic.AttributeDefs.hw_version] == zcl.foundation.Status.SUCCESS


async def test_configure_reporting_multiple_both_unsupp(cluster):
    """Configure reporting returned unsupported attributes for both."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {
            3: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
            4: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
        }
    )

    results = await cluster.configure_reporting_multiple(
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
    assert len(results) == 2
    assert all(
        s == zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE for s in results.values()
    )

    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {
            3: zcl.foundation.Status.SUCCESS,
            4: zcl.foundation.Status.SUCCESS,
        }
    )

    results = await cluster.configure_reporting_multiple(
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
    assert len(results) == 2
    assert all(s == zcl.foundation.Status.SUCCESS for s in results.values())


async def test_configure_reporting_multiple_partial_failure(cluster):
    """Per ZCL spec, only failed attributes are returned in the response."""
    cluster.endpoint.request.return_value = _mk_cfg_rsp(
        {4: zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE}
    )

    results = await cluster.configure_reporting_multiple(
        {
            Basic.AttributeDefs.hw_version: ReportingConfig(
                min_interval=5, max_interval=15, reportable_change=20
            ),
            Basic.AttributeDefs.manufacturer: ReportingConfig(
                min_interval=6, max_interval=16, reportable_change=26
            ),
        }
    )

    # Only the failed attribute is in the device response; SUCCESS is synthesized
    # for hw_version which was omitted (implicitly succeeded per ZCL spec)
    assert len(results) == 2
    assert (
        results[Basic.AttributeDefs.manufacturer]
        == zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE
    )
    assert results[Basic.AttributeDefs.hw_version] == zcl.foundation.Status.SUCCESS

    assert not cluster._attr_cache.is_unsupported(Basic.AttributeDefs.hw_version)
    assert cluster._attr_cache.is_unsupported(Basic.AttributeDefs.manufacturer)


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


def test_attr_cache_key_uses_effective_manufacturer_code():
    """Test that the attribute cache distinguishes attributes by effective manuf code."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xFC01
        ep_attribute = "test_cluster"
        _skip_registry = True

        class AttributeDefs(zcl.BaseAttributeDefs):
            standard_attr = foundation.ZCLAttributeDef(
                id=0x0010, type=t.uint8_t, is_manufacturer_specific=False
            )
            manuf_attr = foundation.ZCLAttributeDef(
                id=0x0010, type=t.uint8_t, is_manufacturer_specific=True
            )

    app = make_app({})
    dev = add_initialized_device(app, nwk=0x1234, ieee=make_ieee(1))

    ep = dev.endpoints[1]
    ep.add_input_cluster(TestCluster.cluster_id)
    cluster = ep.in_clusters[TestCluster.cluster_id]
    cache = cluster._attr_cache

    standard = TestCluster.AttributeDefs.standard_attr
    manuf = TestCluster.AttributeDefs.manuf_attr

    # Both start empty
    with pytest.raises(KeyError):
        cache.get_value(standard)
    with pytest.raises(KeyError):
        cache.get_value(manuf)

    # Setting one does not affect the other
    cache.set_value(standard, 100)
    assert cache.get_value(standard) == 100
    with pytest.raises(KeyError):
        cache.get_value(manuf)

    cache.set_value(manuf, 200)
    assert cache.get_value(manuf) == 200
    assert cache.get_value(standard) == 100

    # Overwriting one does not affect the other
    cache.set_value(standard, 111)
    assert cache.get_value(standard) == 111
    assert cache.get_value(manuf) == 200

    # Marking one unsupported does not affect the other
    cache.mark_unsupported(standard)
    assert cache.is_unsupported(standard)
    assert not cache.is_unsupported(manuf)
    assert cache.get_value(manuf) == 200

    # Setting a value clears the unsupported flag only for that attribute
    cache.mark_unsupported(manuf)
    assert cache.is_unsupported(standard)
    assert cache.is_unsupported(manuf)

    cache.set_value(manuf, 300)
    assert not cache.is_unsupported(manuf)
    assert cache.is_unsupported(standard)
    assert cache.get_value(manuf) == 300


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
            _skip_registry = True
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
        _skip_registry = True

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


def test_zcl_cluster_subclass_keeps_same_id_attributes():
    """Subclassing a cluster keeps two attribute definitions sharing an ID."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

        class AttributeDefs(zcl.BaseAttributeDefs):
            attribute = foundation.ZCLAttributeDef(id=0x0001, type=t.uint8_t)
            attribute_mfg = foundation.ZCLAttributeDef(
                id=0x0001,
                type=t.uint48_t,
                manufacturer_code=0x1234,
            )

    class TestClusterSubclass(TestCluster):
        pass

    class TestClusterSubSubclass(TestClusterSubclass):
        pass

    for cls in (TestCluster, TestClusterSubclass, TestClusterSubSubclass):
        assert set(cls.attributes_by_name) == {"attribute", "attribute_mfg"}
        assert cls.find_attribute("attribute") is cls.AttributeDefs.attribute
        assert (
            cls.find_attribute(0x0001, manufacturer_code=0x1234)
            is cls.AttributeDefs.attribute_mfg
        )


def test_zcl_cluster_subclass_keeps_same_id_commands():
    """Subclassing a cluster keeps two command definitions sharing an ID."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

        class ServerCommandDefs(zcl.BaseCommandDefs):
            command = foundation.ZCLCommandDef(id=0x00, schema={"param1": t.uint8_t})
            command_mfg = foundation.ZCLCommandDef(
                id=0x00,
                schema={"param1": t.uint8_t},
                manufacturer_code=0x1234,
            )

        class ClientCommandDefs(zcl.BaseCommandDefs):
            response = foundation.ZCLCommandDef(id=0x01, schema={})
            response_mfg = foundation.ZCLCommandDef(
                id=0x01,
                schema={},
                manufacturer_code=0x1234,
            )

    class TestClusterSubclass(TestCluster):
        pass

    class TestClusterSubSubclass(TestClusterSubclass):
        pass

    for cls in (TestCluster, TestClusterSubclass, TestClusterSubSubclass):
        assert set(cls.commands_by_name) == {
            "command",
            "command_mfg",
            "response",
            "response_mfg",
        }
        assert {cmd.name for cmd in cls.ServerCommandDefs} == {
            "command",
            "command_mfg",
        }
        assert {cmd.name for cmd in cls.ClientCommandDefs} == {
            "response",
            "response_mfg",
        }


def test_zcl_cluster_subclass_old_style_definitions():
    """Subclasses of clusters with old-style definitions inherit the rebuilt defs."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

        attributes = {
            0x1234: ("attribute", t.uint8_t),
            0x1235: ("attribute2", t.uint32_t, True),
        }

        server_commands = {
            0x00: ("server_command", (t.uint8_t,), True),
        }

        client_commands = {
            0x01: ("client_command", (t.uint8_t,), False),
        }

    class TestClusterSubclass(TestCluster):
        pass

    assert set(TestClusterSubclass.attributes_by_name) == {"attribute", "attribute2"}
    assert TestClusterSubclass.AttributeDefs.attribute.id == 0x1234
    assert TestClusterSubclass.AttributeDefs.attribute2.is_manufacturer_specific
    assert set(TestClusterSubclass.commands_by_name) == {
        "server_command",
        "client_command",
    }

    # An explicit empty old-style dict does not wipe the inherited definitions
    class TestClusterEmptyOverride(TestCluster):
        attributes = {}
        server_commands = {}
        client_commands = {}

    assert set(TestClusterEmptyOverride.attributes_by_name) == {
        "attribute",
        "attribute2",
    }
    assert set(TestClusterEmptyOverride.commands_by_name) == {
        "server_command",
        "client_command",
    }


async def test_zcl_cluster_definition_invalid_name():
    # This is fine
    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

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
            _skip_registry = True

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
            _skip_registry = True

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
            _skip_registry = True

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
            _skip_registry = True

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
            retries=None,
            retry_delay=None,
        )
    ]


def test_find_attribute_simple() -> None:
    """Test attribute finding with simple cluster definition."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

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
        _skip_registry = True

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


@pytest.mark.filterwarnings(
    r"ignore:Attribute .* has `is_manufacturer_specific`"
    r":DeprecationWarning"
)
def test_find_attribute_unspecified_manufacturer_code() -> None:
    """Test attribute finding when the manufacturer code is unspecified."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

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


def test_find_attributes() -> None:
    """Test find_attributes across all attribute specificity combinations."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

        class AttributeDefs(zcl.BaseAttributeDefs):
            explicit_none = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, manufacturer_code=None
            )
            explicit_false = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, is_manufacturer_specific=False
            )
            default = foundation.ZCLAttributeDef(id=0x0001, type=t.EUI64)
            manuf_no_code = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, is_manufacturer_specific=True
            )
            manuf_1234 = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, manufacturer_code=0x1234
            )
            manuf_5678 = foundation.ZCLAttributeDef(
                id=0x0001, type=t.EUI64, manufacturer_code=0x5678
            )
            specific_unique = foundation.ZCLAttributeDef(
                id=0x0002, type=t.EUI64, manufacturer_code=0x1234
            )

    # An explicitly disabled manufacturer code
    assert TestCluster.find_attributes(0x0001, manufacturer_code=None) == [
        TestCluster.AttributeDefs.explicit_none,
        TestCluster.AttributeDefs.explicit_false,
        TestCluster.AttributeDefs.default,
    ]

    # A specific manufacturer code will match the specific attribute for that code and
    # a generic manufacturer-specific one
    assert TestCluster.find_attributes(0x0001, manufacturer_code=0x1234) == [
        TestCluster.AttributeDefs.manuf_1234,
        TestCluster.AttributeDefs.manuf_no_code,
    ]
    assert TestCluster.find_attributes(0x0001, manufacturer_code=0x5678) == [
        TestCluster.AttributeDefs.manuf_5678,
        TestCluster.AttributeDefs.manuf_no_code,
    ]

    # An unknown manufacturer code will match only the generic attribute
    assert TestCluster.find_attributes(0x0001, manufacturer_code=0x9999) == [
        TestCluster.AttributeDefs.manuf_no_code,
    ]

    # No code will match all attributes with the ID
    assert TestCluster.find_attributes(0x0001) == [
        TestCluster.AttributeDefs.manuf_1234,
        TestCluster.AttributeDefs.manuf_5678,
        TestCluster.AttributeDefs.manuf_no_code,
        TestCluster.AttributeDefs.explicit_false,
        TestCluster.AttributeDefs.explicit_none,
        TestCluster.AttributeDefs.default,
    ]

    # Names and definition objects are unique
    assert TestCluster.find_attributes("explicit_false") == [
        TestCluster.AttributeDefs.explicit_false,
    ]
    assert TestCluster.find_attributes("manuf_1234") == [
        TestCluster.AttributeDefs.manuf_1234,
    ]
    assert TestCluster.find_attributes(TestCluster.AttributeDefs.manuf_5678) == [
        TestCluster.AttributeDefs.manuf_5678,
    ]

    # Missing attributes and bad combinations raise errors
    with pytest.raises(KeyError):
        TestCluster.find_attributes(0x9999)

    with pytest.raises(KeyError):
        TestCluster.find_attributes(0x0002, manufacturer_code=0xABCD)


async def test_read_attributes_complex() -> None:
    """Test reading attributes, complex scenario."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

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
        _skip_registry = True

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
        _skip_registry = True

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
        _skip_registry = True

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


async def test_write_attributes_multiple_manufacturer_groups(app_mock) -> None:
    """Test write_attributes with attributes spanning multiple manufacturer groups."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            manuf_attr = foundation.ZCLAttributeDef(
                id=0xB001,
                type=t.uint8_t,
                manufacturer_code=0x5678,
            )

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    dev.node_desc.manufacturer_code = 0x1234

    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    with mock_attribute_writes(
        cluster,
        {
            Basic.AttributeDefs.location_desc: foundation.Status.SUCCESS,
            TestCluster.AttributeDefs.manuf_attr: foundation.Status.SUCCESS,
        },
    ) as (mock_write, _):
        [results] = await cluster.write_attributes(
            {
                Basic.AttributeDefs.location_desc: "Test",
                TestCluster.AttributeDefs.manuf_attr: 42,
            }
        )

    assert len(results) == 2
    assert all(r.status == foundation.Status.SUCCESS for r in results)

    # Two separate requests, one per manufacturer group
    assert mock_write.call_count == 2
    assert mock_write.call_args_list == [
        call(
            [
                foundation.Attribute(
                    attrid=Basic.AttributeDefs.location_desc.id,
                    value=foundation.TypeValue(
                        type=Basic.AttributeDefs.location_desc.zcl_type,
                        value=Basic.AttributeDefs.location_desc.type("Test"),
                    ),
                )
            ],
            manufacturer=None,
        ),
        call(
            [
                foundation.Attribute(
                    attrid=TestCluster.AttributeDefs.manuf_attr.id,
                    value=foundation.TypeValue(
                        type=TestCluster.AttributeDefs.manuf_attr.zcl_type,
                        value=TestCluster.AttributeDefs.manuf_attr.type(42),
                    ),
                )
            ],
            manufacturer=0x5678,
        ),
    ]


async def test_configure_reporting_multiple_manufacturer_groups(app_mock) -> None:
    """Test configure_reporting_multiple with attributes spanning multiple manufacturer
    groups, including colliding attribute IDs that differ only by manufacturer code.
    """

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            # Same numeric ID as hw_version (0x0003) but manufacturer-specific
            manuf_hw_version = foundation.ZCLAttributeDef(
                id=0x0003,
                type=t.uint8_t,
                manufacturer_code=0x5678,
            )

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    dev.node_desc.manufacturer_code = 0x1234

    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    cfg_success = zcl.foundation.ConfigureReportingResponse(
        [zcl.foundation.ConfigureReportingResponseRecord(zcl.foundation.Status.SUCCESS)]
    )
    cfg_fail = zcl.foundation.ConfigureReportingResponse(
        [
            zcl.foundation.ConfigureReportingResponseRecord(
                zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE,
                zcl.foundation.ReportingDirection.ReceiveReports,
                0x0003,
            )
        ]
    )

    # Standard fails, manufacturer-specific succeeds
    with patch.object(
        cluster,
        "_configure_reporting",
        new_callable=AsyncMock,
        side_effect=[[cfg_fail], [cfg_success]],
    ) as mock_configure:
        results = await cluster.configure_reporting_multiple(
            {
                Basic.AttributeDefs.hw_version: ReportingConfig(
                    min_interval=5, max_interval=15, reportable_change=20
                ),
                TestCluster.AttributeDefs.manuf_hw_version: ReportingConfig(
                    min_interval=10, max_interval=30, reportable_change=5
                ),
            }
        )

    assert len(results) == 2
    assert (
        results[Basic.AttributeDefs.hw_version]
        == zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE
    )
    assert (
        results[TestCluster.AttributeDefs.manuf_hw_version]
        == zcl.foundation.Status.SUCCESS
    )

    # Two separate requests should have been made (one per manufacturer group)
    assert mock_configure.await_count == 2

    # First call: standard attribute (no manufacturer code)
    std_call = mock_configure.call_args_list[0]
    assert std_call.kwargs["manufacturer"] is None
    assert len(std_call.args[0]) == 1
    assert std_call.args[0][0].attrid == Basic.AttributeDefs.hw_version.id
    assert std_call.args[0][0].min_interval == 5
    assert std_call.args[0][0].max_interval == 15
    assert std_call.args[0][0].reportable_change == 20

    # Second call: manufacturer-specific attribute (same attrid, different manuf code)
    manuf_call = mock_configure.call_args_list[1]
    assert manuf_call.kwargs["manufacturer"] == 0x5678
    assert len(manuf_call.args[0]) == 1
    assert manuf_call.args[0][0].attrid == TestCluster.AttributeDefs.manuf_hw_version.id
    assert manuf_call.args[0][0].min_interval == 10
    assert manuf_call.args[0][0].max_interval == 30
    assert manuf_call.args[0][0].reportable_change == 5


async def test_configure_reporting_multiple_chunked_by_size(app_mock) -> None:
    """Configure_reporting_multiple splits requests so no single one exceeds
    MAX_ATTRIBUTE_RECORDS_BYTES of serialized records.
    """

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            # 6 uint8 attrs, each serializing to 9 bytes as a SendReports config
            # (1 dir + 2 attrid + 1 type + 2 min + 2 max + 1 reportable_change).
            # 6 * 9 = 54 bytes > 50, so the request must split into 2 chunks.
            attr_a = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)
            attr_b = foundation.ZCLAttributeDef(id=0xFF01, type=t.uint8_t)
            attr_c = foundation.ZCLAttributeDef(id=0xFF02, type=t.uint8_t)
            attr_d = foundation.ZCLAttributeDef(id=0xFF03, type=t.uint8_t)
            attr_e = foundation.ZCLAttributeDef(id=0xFF04, type=t.uint8_t)
            attr_f = foundation.ZCLAttributeDef(id=0xFF05, type=t.uint8_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    cfg_success = zcl.foundation.ConfigureReportingResponse(
        [zcl.foundation.ConfigureReportingResponseRecord(zcl.foundation.Status.SUCCESS)]
    )

    cfg = ReportingConfig(min_interval=1, max_interval=2, reportable_change=3)
    attrs = [
        TestCluster.AttributeDefs.attr_a,
        TestCluster.AttributeDefs.attr_b,
        TestCluster.AttributeDefs.attr_c,
        TestCluster.AttributeDefs.attr_d,
        TestCluster.AttributeDefs.attr_e,
        TestCluster.AttributeDefs.attr_f,
    ]

    with patch.object(
        cluster,
        "_configure_reporting",
        new_callable=AsyncMock,
        side_effect=[[cfg_success], [cfg_success]],
    ) as mock_configure:
        results = await cluster.configure_reporting_multiple(dict.fromkeys(attrs, cfg))

    assert mock_configure.await_count == 2

    sent_attrids = []
    for call_obj in mock_configure.call_args_list:
        chunk_configs = call_obj.args[0]
        chunk_size = sum(len(c.serialize()) for c in chunk_configs)
        assert chunk_size <= MAX_ATTRIBUTE_RECORDS_BYTES
        sent_attrids.extend(c.attrid for c in chunk_configs)

    assert sent_attrids == [a.id for a in attrs]

    assert len(results) == 6
    assert all(s == zcl.foundation.Status.SUCCESS for s in results.values())


async def test_read_attributes_chunked_by_count(app_mock) -> None:
    """Read_attributes splits requests into chunks of at most five."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_0 = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)
            attr_1 = foundation.ZCLAttributeDef(id=0xFF01, type=t.uint8_t)
            attr_2 = foundation.ZCLAttributeDef(id=0xFF02, type=t.uint8_t)
            attr_3 = foundation.ZCLAttributeDef(id=0xFF03, type=t.uint8_t)
            attr_4 = foundation.ZCLAttributeDef(id=0xFF04, type=t.uint8_t)
            attr_5 = foundation.ZCLAttributeDef(id=0xFF05, type=t.uint8_t)
            attr_6 = foundation.ZCLAttributeDef(id=0xFF06, type=t.uint8_t)
            attr_7 = foundation.ZCLAttributeDef(id=0xFF07, type=t.uint8_t)
            attr_8 = foundation.ZCLAttributeDef(id=0xFF08, type=t.uint8_t)
            attr_9 = foundation.ZCLAttributeDef(id=0xFF09, type=t.uint8_t)
            attr_10 = foundation.ZCLAttributeDef(id=0xFF0A, type=t.uint8_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    attrs = [getattr(TestCluster.AttributeDefs, f"attr_{i}") for i in range(11)]

    # Exclude 2 and 7 so the mock returns UNSUPPORTED
    supported = {attr: i for i, attr in enumerate(attrs) if i not in (2, 7)}
    with mock_attribute_reads(cluster, supported) as (mock_read, _):
        success, failure = await cluster.read_attributes(attrs)

    # 11 attributes, at most MAX_READ_ATTRIBUTES_PER_REQ (5) per request -> 5 + 5 + 1
    chunks = [call_obj.args[0] for call_obj in mock_read.call_args_list]
    assert [len(chunk) for chunk in chunks] == [5, 5, 1]

    # Every attribute was requested exactly once, in order, across the chunks
    requested_ids = []
    for chunk in chunks:
        requested_ids.extend(chunk)
    assert requested_ids == [attr.id for attr in attrs]

    # Supported attributes succeed; the two omitted ones fail
    assert success == supported
    assert failure == {
        attrs[2]: foundation.Status.UNSUPPORTED_ATTRIBUTE,
        attrs[7]: foundation.Status.UNSUPPORTED_ATTRIBUTE,
    }


async def test_read_attributes_insufficient_space_retry_success(app_mock) -> None:
    """An INSUFFICIENT_SPACE record is re-read individually and can then succeed."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_0 = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)
            attr_1 = foundation.ZCLAttributeDef(id=0xFF01, type=t.uint8_t)
            attr_2 = foundation.ZCLAttributeDef(id=0xFF02, type=t.uint8_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    attrs = [
        TestCluster.AttributeDefs.attr_0,
        TestCluster.AttributeDefs.attr_1,
        TestCluster.AttributeDefs.attr_2,
    ]

    supported = {
        TestCluster.AttributeDefs.attr_0: 10,
        # Runs out of space in the batched read, but fits when read alone
        TestCluster.AttributeDefs.attr_1: mock.Mock(
            side_effect=[foundation.Status.INSUFFICIENT_SPACE, 20]
        ),
        TestCluster.AttributeDefs.attr_2: 30,
    }

    events = []
    cluster.on_event(AttributeReadEvent.event_type, events.append)
    cluster.on_event(AttributeUpdatedEvent.event_type, events.append)

    with mock_attribute_reads(cluster, supported) as (mock_read, _):
        success, failure = await cluster.read_attributes(attrs)

    assert success == {
        TestCluster.AttributeDefs.attr_0: 10,
        TestCluster.AttributeDefs.attr_1: 20,
        TestCluster.AttributeDefs.attr_2: 30,
    }
    assert failure == {}

    # The batched read, then a solo re-read of the attribute that didn't fit
    chunks = [call_obj.args[0] for call_obj in mock_read.call_args_list]
    assert chunks == [[0xFF00, 0xFF01, 0xFF02], [0xFF01]]

    assert events == [
        AttributeReadEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=TestCluster.cluster_id,
            attribute_name=TestCluster.AttributeDefs.attr_0.name,
            attribute_id=TestCluster.AttributeDefs.attr_0.id,
            manufacturer_code=None,
            raw_value=10,
            value=10,
        ),
        AttributeReadEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=TestCluster.cluster_id,
            attribute_name=TestCluster.AttributeDefs.attr_2.name,
            attribute_id=TestCluster.AttributeDefs.attr_2.id,
            manufacturer_code=None,
            raw_value=30,
            value=30,
        ),
        # No event for attr_1's INSUFFICIENT_SPACE record; the solo re-read then emits
        # its AttributeReadEvent last, after the two attributes that succeeded in the
        # batch
        AttributeReadEvent(
            device_ieee=str(dev.ieee),
            endpoint_id=1,
            cluster_type=zcl.ClusterType.Server,
            cluster_id=TestCluster.cluster_id,
            attribute_name=TestCluster.AttributeDefs.attr_1.name,
            attribute_id=TestCluster.AttributeDefs.attr_1.id,
            manufacturer_code=None,
            raw_value=20,
            value=20,
        ),
    ]


async def test_read_attributes_insufficient_space_retry_persistent(app_mock) -> None:
    """An attribute that still doesn't fit when read alone is a terminal failure."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_0 = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)
            attr_1 = foundation.ZCLAttributeDef(id=0xFF01, type=t.uint8_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    attrs = [TestCluster.AttributeDefs.attr_0, TestCluster.AttributeDefs.attr_1]

    supported = {
        TestCluster.AttributeDefs.attr_0: 10,
        # Never fits, even when read alone
        TestCluster.AttributeDefs.attr_1: mock.Mock(
            return_value=foundation.Status.INSUFFICIENT_SPACE
        ),
    }

    with mock_attribute_reads(cluster, supported) as (mock_read, _):
        success, failure = await cluster.read_attributes(attrs)

    assert success == {TestCluster.AttributeDefs.attr_0: 10}
    assert failure == {
        TestCluster.AttributeDefs.attr_1: foundation.Status.INSUFFICIENT_SPACE
    }

    chunks = [call_obj.args[0] for call_obj in mock_read.call_args_list]
    assert chunks == [[0xFF00, 0xFF01], [0xFF01]]


async def test_read_attributes_insufficient_space_single_chunk_no_retry(
    app_mock,
) -> None:
    """A single-attribute chunk is already isolated, so it is not re-read."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_0 = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    supported = {
        TestCluster.AttributeDefs.attr_0: mock.Mock(
            return_value=foundation.Status.INSUFFICIENT_SPACE
        ),
    }

    with mock_attribute_reads(cluster, supported) as (mock_read, _):
        success, failure = await cluster.read_attributes(
            [TestCluster.AttributeDefs.attr_0]
        )

    assert success == {}
    assert failure == {
        TestCluster.AttributeDefs.attr_0: foundation.Status.INSUFFICIENT_SPACE
    }

    # Read exactly once: no redundant solo re-read of an already-isolated attribute
    chunks = [call_obj.args[0] for call_obj in mock_read.call_args_list]
    assert chunks == [[0xFF00]]


@pytest.mark.parametrize("omitted_again", [False, True])
async def test_read_attributes_omitted_record_retry(
    app_mock, omitted_again: bool
) -> None:
    """Records omitted from a response are re-read individually (ZCL R8 §2.5.2.3)."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_0 = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)
            attr_1 = foundation.ZCLAttributeDef(id=0xFF01, type=t.uint8_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    attrs = [TestCluster.AttributeDefs.attr_0, TestCluster.AttributeDefs.attr_1]

    supported = {
        TestCluster.AttributeDefs.attr_0: 10,
        TestCluster.AttributeDefs.attr_1: mock.Mock(
            side_effect=[None, None] if omitted_again else [None, 20]
        ),
    }

    with mock_attribute_reads(cluster, supported) as (mock_read, _):
        success, failure = await cluster.read_attributes(attrs)

    if omitted_again:
        assert success == {TestCluster.AttributeDefs.attr_0: 10}
        assert failure == {
            TestCluster.AttributeDefs.attr_1: foundation.Status.INSUFFICIENT_SPACE
        }
    else:
        assert success == {
            TestCluster.AttributeDefs.attr_0: 10,
            TestCluster.AttributeDefs.attr_1: 20,
        }
        assert failure == {}

    chunks = [call_obj.args[0] for call_obj in mock_read.call_args_list]
    assert chunks == [[0xFF00, 0xFF01], [0xFF01]]


async def test_write_attributes_chunked_by_size(app_mock) -> None:
    """Write_attributes splits requests if a single one would exceed the limit."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_a = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint64_t)
            attr_b = foundation.ZCLAttributeDef(id=0xFF01, type=t.uint64_t)
            attr_c = foundation.ZCLAttributeDef(id=0xFF02, type=t.uint64_t)
            attr_d = foundation.ZCLAttributeDef(id=0xFF03, type=t.uint64_t)
            attr_e = foundation.ZCLAttributeDef(id=0xFF04, type=t.uint64_t)
            attr_f = foundation.ZCLAttributeDef(id=0xFF05, type=t.uint64_t)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    attrs = [
        TestCluster.AttributeDefs.attr_a,
        TestCluster.AttributeDefs.attr_b,
        TestCluster.AttributeDefs.attr_c,
        TestCluster.AttributeDefs.attr_d,
        TestCluster.AttributeDefs.attr_e,
        TestCluster.AttributeDefs.attr_f,
    ]

    with mock_attribute_writes(
        cluster, dict.fromkeys(attrs, foundation.Status.SUCCESS)
    ) as (mock_write, _):
        [results] = await cluster.write_attributes(dict.fromkeys(attrs, 1))

    # 6 records of 11 bytes each split into 2 chunks: 44 bytes + 22 bytes
    assert mock_write.call_count == 2

    sent_attrids = []
    for call_obj in mock_write.call_args_list:
        chunk_attrs = call_obj.args[0]
        chunk_size = sum(len(a.serialize()) for a in chunk_attrs)
        assert chunk_size <= MAX_ATTRIBUTE_RECORDS_BYTES
        sent_attrids.extend(a.attrid for a in chunk_attrs)

    assert sent_attrids == [attr.id for attr in attrs]

    assert len(results) == 6
    assert all(r.status == foundation.Status.SUCCESS for r in results)


@pytest.mark.parametrize(
    ("sizes", "max_bytes", "expected"),
    [
        # No records produces no chunks
        ([], 10, []),
        # Records that all fit stay in a single chunk
        ([3, 3, 3], 10, [[3, 3, 3]]),
        # Filling exactly to the limit does not start a new chunk
        ([5, 5], 10, [[5, 5]]),
        # A single record exactly at the limit is allowed
        ([10], 10, [[10]]),
        # Exceeding the limit rolls over into a new chunk
        ([5, 5, 1], 10, [[5, 5], [1]]),
    ],
)
def test_chunk_records_by_size(sizes, max_bytes, expected) -> None:
    """The chunker packs records into chunks that never exceed max_bytes."""
    chunks = _chunk_records_by_size(sizes, lambda size: size, max_bytes=max_bytes)
    assert chunks == expected


@pytest.mark.parametrize(
    ("sizes", "max_bytes", "expected"),
    [
        # A single record larger than the limit, on its own
        ([15], 10, [[15]]),
        # An oversized record does not take the records around it down with it
        ([3, 15, 4], 10, [[3], [15], [4]]),
        # Records before an oversized one still pack together
        ([3, 3, 15, 4], 10, [[3, 3], [15], [4]]),
        # Consecutive oversized records each get a chunk of their own
        ([15, 15], 10, [[15], [15]]),
    ],
)
def test_chunk_records_by_size_oversized_record(
    sizes, max_bytes, expected, caplog
) -> None:
    """A record that on its own exceeds max_bytes is emitted as its own chunk."""
    with caplog.at_level(logging.DEBUG, logger="zigpy.zcl"):
        chunks = _chunk_records_by_size(sizes, lambda size: size, max_bytes=max_bytes)

    assert chunks == expected
    assert caplog.text.count("exceeds the 10 byte request budget") == sum(
        size > max_bytes for size in sizes
    )


async def test_write_attributes_oversized_record(app_mock) -> None:
    """An attribute record over the size budget is still sent, on its own."""

    class TestCluster(Basic):
        _skip_registry = True

        class AttributeDefs(Basic.AttributeDefs):
            attr_small = foundation.ZCLAttributeDef(id=0xFF00, type=t.uint8_t)
            attr_big = foundation.ZCLAttributeDef(id=0xFF01, type=t.LVBytes)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    # 2 bytes of attribute id + 1 type + 1 length prefix + 55 bytes of value
    oversized = b"\xaa" * 55

    with mock_attribute_writes(
        cluster,
        {
            TestCluster.AttributeDefs.attr_small: foundation.Status.SUCCESS,
            TestCluster.AttributeDefs.attr_big: foundation.Status.SUCCESS,
        },
    ) as (mock_write, _):
        [results] = await cluster.write_attributes(
            {
                TestCluster.AttributeDefs.attr_small: 1,
                TestCluster.AttributeDefs.attr_big: oversized,
            }
        )

    # The small record is sent normally, the oversized one in a request of its own
    assert mock_write.call_count == 2
    chunks = [call_obj.args[0] for call_obj in mock_write.call_args_list]
    assert [[a.attrid for a in chunk] for chunk in chunks] == [[0xFF00], [0xFF01]]

    [big_record] = chunks[1]
    assert len(big_record.serialize()) == 59 > MAX_ATTRIBUTE_RECORDS_BYTES

    assert len(results) == 2
    assert all(r.status == foundation.Status.SUCCESS for r in results)


def test_manufacturer_id_override_manuf_specific_cluster(app_mock) -> None:
    """Test class-level `manufacturer_id_override` for custom clusters."""

    class TestCluster(zcl.Cluster):
        cluster_id = 0xFEED  # Manufacturer-specific cluster range
        ep_attribute = "test_cluster"
        _skip_registry = True
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


async def test_quirk_manufacturer_code_context_isolation(app_mock) -> None:
    """Test that manufacturer code context is properly handled in _update_attribute.

    When a manufacturer-specific attribute is reported and the cluster has multiple
    attributes sharing the same ID (with different manufacturer codes), the
    _update_attribute call must use the correct manufacturer code. This tests that:
    1. The value is stored directly in the typed cache (not via legacy cache fallback)
    2. Other attributes updated by quirks don't inherit the manufacturer code context
    """

    class TestCluster(zcl.Cluster):
        cluster_id = 0xABCD
        ep_attribute = "test_cluster"
        _skip_registry = True

        class AttributeDefs(zcl.foundation.BaseAttributeDefs):
            # Two attributes sharing the same ID with different manufacturer codes
            manuf_attr = foundation.ZCLAttributeDef(
                id=0x0001,
                type=t.uint8_t,
                manufacturer_code=0x1234,
            )
            standard_attr = foundation.ZCLAttributeDef(
                id=0x0001,
                type=t.uint8_t,
                manufacturer_code=None,
            )
            # A different attribute that the quirk will also update
            other_attr = foundation.ZCLAttributeDef(
                id=0x0002,
                type=t.uint8_t,
            )

        def _update_attribute(self, attrid, value):
            super()._update_attribute(attrid, value)

            # When updating the manufacturer-specific attribute, also update other_attr
            if attrid == self.AttributeDefs.manuf_attr.id:
                super()._update_attribute(self.AttributeDefs.other_attr.id, 99)

    dev = add_initialized_device(app_mock, nwk=0x1234, ieee=make_ieee(1))
    cluster = TestCluster(dev.endpoints[1])
    dev.endpoints[1].add_input_cluster(TestCluster.cluster_id, cluster)

    events = []
    cluster.on_event(AttributeReportedEvent.event_type, events.append)
    cluster.on_event(AttributeUpdatedEvent.event_type, events.append)

    # The attribute is currently marked as unsupported
    cluster.add_unsupported_attribute(TestCluster.AttributeDefs.manuf_attr)

    # Report the manufacturer-specific attribute
    await mock_attribute_report(
        cluster, {TestCluster.AttributeDefs.manuf_attr: t.uint8_t(42)}
    )

    # The legacy cache should not contain the attribute, as the typed cache was used
    assert 0x0001 not in cluster._attr_cache._legacy_cache

    # Verify that the manufacturer-specific attribute was stored correctly
    assert cluster._attr_cache.get_value(TestCluster.AttributeDefs.manuf_attr) == 42

    # Verify that the standard attribute (same ID, no manufacturer code) was NOT updated
    with pytest.raises(KeyError):
        cluster._attr_cache.get_value(TestCluster.AttributeDefs.standard_attr)

    # Verify that other_attr was updated (by the quirk) without manufacturer code context
    assert cluster._attr_cache.get_value(TestCluster.AttributeDefs.other_attr) == 99

    # Verify the events have the correct manufacturer codes
    assert len(events) == 2

    # First event: other_attr updated by quirk (should have no manufacturer code)
    assert events[0] == AttributeUpdatedEvent(
        device_ieee=str(dev.ieee),
        endpoint_id=1,
        cluster_type=zcl.ClusterType.Server,
        cluster_id=TestCluster.cluster_id,
        attribute_name="other_attr",
        attribute_id=TestCluster.AttributeDefs.other_attr.id,
        manufacturer_code=None,
        value=99,
    )

    # Second event: manuf_attr reported (should have the manufacturer code)
    assert events[1] == AttributeReportedEvent(
        device_ieee=str(dev.ieee),
        endpoint_id=1,
        cluster_type=zcl.ClusterType.Server,
        cluster_id=TestCluster.cluster_id,
        attribute_name="manuf_attr",
        attribute_id=TestCluster.AttributeDefs.manuf_attr.id,
        manufacturer_code=0x1234,
        raw_value=42,
        value=42,
    )


async def test_read_attributes_structured_raw(cluster):
    """Test read_attributes_structured_raw sends the correct request."""
    mock_response = [
        [
            foundation.ReadAttributeRecord(
                attrid=0x0001, status=foundation.Status.SUCCESS
            )
        ]
    ]

    with patch.object(
        cluster.endpoint, "request", new=AsyncMock(return_value=mock_response)
    ):
        result = await cluster.read_attributes_structured_raw(
            [
                foundation.ReadAttributeStructured(
                    attrid=0x0001,
                    selector=foundation.Selector(depth=0),
                ),
            ]
        )

        assert result == mock_response
        assert cluster.endpoint.request.call_count == 1

        # Verify the serialized payload contains attr_id + selector
        data = cluster.endpoint.request.mock_calls[0].kwargs["data"]
        assert data[3:] == b"\x01\x00\x00"  # attr_id=0x0001 + indicator=0x00


async def test_write_attributes_structured_raw(cluster):
    """Test write_attributes_structured_raw sends the correct request."""
    mock_response = [
        foundation.WriteAttributesStructuredResponse(
            [
                foundation.WriteAttributesStructuredStatusRecord(
                    status=foundation.Status.SUCCESS,
                )
            ]
        )
    ]

    with patch.object(
        cluster.endpoint, "request", new=AsyncMock(return_value=mock_response)
    ):
        result = await cluster.write_attributes_structured_raw(
            [
                foundation.WriteAttributeStructured(
                    attrid=0x0001,
                    selector=foundation.Selector(depth=0),
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(0x42),
                    ),
                ),
            ]
        )

        assert result == mock_response
        assert cluster.endpoint.request.call_count == 1


async def test_read_attributes_structured_raw_nested(cluster):
    """Test read_attributes_structured_raw with nested index selector."""
    mock_response = [
        [
            foundation.ReadAttributeRecord(
                attrid=0x0005, status=foundation.Status.SUCCESS
            )
        ]
    ]

    with patch.object(
        cluster.endpoint, "request", new=AsyncMock(return_value=mock_response)
    ):
        result = await cluster.read_attributes_structured_raw(
            [
                foundation.ReadAttributeStructured(
                    attrid=0x0005,
                    selector=foundation.Selector(depth=2, indexes=[5, 3]),
                ),
            ]
        )

        assert result == mock_response

        data = cluster.endpoint.request.mock_calls[0].kwargs["data"]
        # attr_id=0x0005 + indicator=0x02 + index1=5 + index2=3
        assert data[3:] == b"\x05\x00\x02\x05\x00\x03\x00"
