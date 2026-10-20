from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone, tzinfo
import io
import re
import struct
import threading
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from zigpy import device, types, zcl
import zigpy.endpoint
from zigpy.ota import OTA, OtaImagesResult
from zigpy.time import INVALID_TIME, MAX_TIME, ZIGBEE_EPOCH, TimeService, zigbee_time
from zigpy.zcl import OtaImageAvailableEvent, OtaQueryCacheUpdatedEvent, foundation
from zigpy.zcl.clusters.general import Basic, KeepAlive, Ota, Time
import zigpy.zcl.clusters.security as sec
from zigpy.zdo import types as zdo_t

from .async_mock import AsyncMock, MagicMock, call, patch, sentinel

IMAGE_SIZE = 0x2345
IMAGE_OFFSET = 0x2000


def test_registry():
    for cluster_id, cluster in zcl.Cluster._registry.items():
        assert 0 <= getattr(cluster, "cluster_id", -1) <= 65535
        assert cluster_id == cluster.cluster_id
        assert issubclass(cluster, zcl.Cluster)


def test_attributes():
    for cluster in zcl.Cluster._registry.values():
        for attrid, attr in cluster.attributes.items():
            assert 0 <= attrid <= 0xFFFF
            assert isinstance(attr, zcl.foundation.ZCLAttributeDef)
            assert attr.id == attrid
            assert attr.name
            assert attr.type
            assert callable(attr.type.deserialize)
            assert callable(attr.type.serialize)


def _test_commands(cmdattr):
    for cluster in zcl.Cluster._registry.values():
        for cmdid, cmdspec in getattr(cluster, cmdattr).items():
            assert 0 <= cmdid <= 0xFF

            assert cmdspec.id == cmdid
            assert isinstance(cmdspec, zcl.foundation.ZCLCommandDef)
            assert issubclass(cmdspec.schema, types.Struct)

            for field in cmdspec.schema.fields:
                assert callable(field.type.deserialize)
                assert callable(field.type.serialize)


def test_server_commands():
    _test_commands("server_commands")


def test_client_commands():
    _test_commands("client_commands")


def test_ep_attributes():
    seen = set()
    for cluster in zcl.Cluster._registry.values():
        assert isinstance(cluster.ep_attribute, str)
        assert re.match(r"^[a-z_][a-z0-9_]*$", cluster.ep_attribute)
        assert cluster.ep_attribute not in seen
        seen.add(cluster.ep_attribute)

        ep = zigpy.endpoint.Endpoint(None, 1)
        assert not hasattr(ep, cluster.ep_attribute)


async def read_attributes(cluster, attribute_ids: list[int]) -> dict[int, Any]:
    schema = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes
    ].schema
    hdr, _ = cluster._create_request(
        general=True,
        command_id=foundation.GeneralCommand.Read_Attributes,
        schema=schema,
        disable_default_response=False,
        direction=foundation.Direction.Client_to_Server,
        args=(),
        kwargs={"attribute_ids": attribute_ids},
    )

    command = schema(attribute_ids=attribute_ids)

    response = asyncio.get_running_loop().create_future()

    async def capture_reply(*args, **kwargs):
        response.set_result((args, kwargs))

    with patch.object(cluster, "reply", side_effect=capture_reply):
        cluster.handle_message(hdr, command)
        args, kwargs = await asyncio.wait_for(response, timeout=10)

    assert args[0] is True
    assert args[1] == foundation.GeneralCommand.Read_Attributes_rsp
    assert kwargs["tsn"] == hdr.tsn
    return args[2](args[3])


async def test_basic_cluster():
    ep = MagicMock()
    ep.reply = AsyncMock()

    cluster = Basic(ep)

    rsp = await read_attributes(
        cluster,
        [
            Basic.AttributeDefs.zcl_version.id,
            Basic.AttributeDefs.power_source.id,
            Basic.AttributeDefs.serial_number.id,
        ],
    )

    assert rsp.status_records[0] == foundation.ReadAttributeRecord(
        attrid=Basic.AttributeDefs.zcl_version.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.uint8,
            value=8,
        ),
    )

    assert rsp.status_records[1] == foundation.ReadAttributeRecord(
        attrid=Basic.AttributeDefs.power_source.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.enum8,
            value=Basic.PowerSource.DC_Source,
        ),
    )

    assert rsp.status_records[2] == foundation.ReadAttributeRecord(
        attrid=Basic.AttributeDefs.serial_number.id,
        status=foundation.Status.UNSUPPORTED_ATTRIBUTE,
    )


async def test_keepalive_cluster() -> None:
    ep = MagicMock()
    ep.reply = AsyncMock()

    cluster = KeepAlive(ep)

    rsp = await read_attributes(
        cluster,
        [
            KeepAlive.AttributeDefs.tc_keep_alive_base.id,
            KeepAlive.AttributeDefs.tc_keep_alive_jitter.id,
        ],
    )

    assert rsp.status_records[0] == foundation.ReadAttributeRecord(
        attrid=KeepAlive.AttributeDefs.tc_keep_alive_base.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.uint8,
            value=10,
        ),
    )

    assert rsp.status_records[1] == foundation.ReadAttributeRecord(
        attrid=KeepAlive.AttributeDefs.tc_keep_alive_jitter.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.uint16,
            value=300,
        ),
    )


@pytest.mark.parametrize(
    ("fake_now", "expected_utc", "expected_tz", "expected_standard", "expected_local"),
    [
        pytest.param(
            # January: PST (UTC-8), no DST
            datetime(2000, 1, 2, 0, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
            # UTC time: midnight Jan 2 PST = 08:00 Jan 2 UTC = 1 day + 8 hours
            24 * 60 * 60 + 8 * 60 * 60,
            # Standard timezone offset: UTC-8
            -(8 * 60 * 60),
            # Standard time: Time + TimeZone = midnight Jan 2 local (no DST)
            24 * 60 * 60,
            # Local time: midnight Jan 2 = 1 day from epoch
            24 * 60 * 60,
            id="winter_no_dst",
        ),
        pytest.param(
            # July: PDT (UTC-7), DST active
            datetime(2000, 7, 2, 0, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
            # UTC time: midnight Jul 2 PDT = 07:00 Jul 2 UTC
            183 * 24 * 60 * 60 + 7 * 60 * 60,
            # Standard timezone offset: still UTC-8 (DST not included)
            -(8 * 60 * 60),
            # Standard time: Time + TimeZone = 11 PM Jul 1 standard (no DST adjustment)
            183 * 24 * 60 * 60 - 1 * 60 * 60,
            # Local time: midnight Jul 2 local
            183 * 24 * 60 * 60,
            id="summer_with_dst",
        ),
    ],
)
async def test_time_cluster(
    fake_now, expected_utc, expected_tz, expected_standard, expected_local, app_mock
):
    ep = MagicMock()
    ep.reply = AsyncMock()
    ep.device.application = app_mock
    app_mock.local_timezone = fake_now.tzinfo

    cluster = Time(ep)

    Read_Attributes_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    with patch("zigpy.zcl.clusters.general.datetime", wraps=datetime) as clock:
        clock.now.return_value = fake_now.astimezone(UTC)
        # Supported attributes
        rsp1 = await read_attributes(
            cluster,
            [
                Time.AttributeDefs.time.id,
                Time.AttributeDefs.time_status.id,
                Time.AttributeDefs.time_zone.id,
                Time.AttributeDefs.standard_time.id,
                Time.AttributeDefs.local_time.id,
            ],
        )

    assert rsp1.status_records[0] == foundation.ReadAttributeRecord(
        attrid=Time.AttributeDefs.time.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.UTC,
            value=expected_utc,
        ),
    )

    assert rsp1.status_records[1] == foundation.ReadAttributeRecord(
        attrid=Time.AttributeDefs.time_status.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.map8,
            value=(Time.TimeStatus.Master | Time.TimeStatus.Master_for_Zone_and_DST),
        ),
    )

    assert rsp1.status_records[2] == foundation.ReadAttributeRecord(
        attrid=Time.AttributeDefs.time_zone.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.int32,
            value=expected_tz,
        ),
    )

    assert rsp1.status_records[3] == foundation.ReadAttributeRecord(
        attrid=Time.AttributeDefs.standard_time.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.uint32,
            value=expected_standard,
        ),
    )

    assert rsp1.status_records[4] == foundation.ReadAttributeRecord(
        attrid=Time.AttributeDefs.local_time.id,
        status=foundation.Status.SUCCESS,
        value=foundation.TypeValue(
            type=foundation.DataTypeId.uint32,
            value=expected_local,
        ),
    )

    # Unsupported
    rsp2 = await read_attributes(cluster, [0xABCD])
    assert rsp2 == Read_Attributes_rsp(
        status_records=[
            foundation.ReadAttributeRecord(
                attrid=0xABCD,
                status=foundation.Status.UNSUPPORTED_ATTRIBUTE,
            )
        ]
    )


async def test_time_cluster_dst_attributes(app_mock):
    ep = MagicMock()
    ep.reply = AsyncMock()
    ep.device.application = app_mock
    cluster = Time(ep)

    response = await read_attributes(cluster, [0x0003, 0x0004, 0x0005])

    assert [record.status for record in response.status_records] == [
        foundation.Status.SUCCESS,
        foundation.Status.SUCCESS,
        foundation.Status.SUCCESS,
    ]


@pytest.mark.parametrize(
    ("zone_name", "instant", "start", "end", "shift"),
    [
        ("Europe/Berlin", "2026-01-15", "2026-03-29T01:00", "2026-10-25T01:00", 3600),
        ("Europe/Berlin", "2026-07-15", "2026-03-29T01:00", "2026-10-25T01:00", 3600),
        ("Europe/Berlin", "2026-12-15", "2027-03-28T01:00", "2027-10-31T01:00", 3600),
        (
            "America/Los_Angeles",
            "2026-07-15",
            "2026-03-08T10:00",
            "2026-11-01T09:00",
            3600,
        ),
        (
            "Australia/Sydney",
            "2026-01-15",
            "2025-10-04T16:00",
            "2026-04-04T16:00",
            3600,
        ),
        (
            "Australia/Sydney",
            "2026-07-15",
            "2026-10-03T16:00",
            "2027-04-03T16:00",
            3600,
        ),
        (
            "Australia/Sydney",
            "2026-12-15",
            "2026-10-03T16:00",
            "2027-04-03T16:00",
            3600,
        ),
        (
            "Australia/Lord_Howe",
            "2026-01-15",
            "2025-10-04T15:30",
            "2026-04-04T15:00",
            1800,
        ),
        ("Australia/Sydney", "2000-01-02", "2000-01-01", "2000-03-25T16:00", 3600),
    ],
)
async def test_time_cluster_dst_period(zone_name, instant, start, end, shift, app_mock):
    zone = ZoneInfo(zone_name)
    now = datetime.fromisoformat(instant).replace(tzinfo=UTC)
    ep = MagicMock()
    ep.reply = AsyncMock()
    ep.device.application = app_mock
    app_mock.local_timezone = zone
    service = app_mock._time_service
    cluster = Time(ep)

    with patch("zigpy.zcl.clusters.general.datetime", wraps=datetime) as clock:
        clock.now.return_value = now
        response = await read_attributes(cluster, list(range(8)))
        clock.now.assert_called_once_with(UTC)

    assert all(
        record.status == foundation.Status.SUCCESS for record in response.status_records
    )
    values = {record.attrid: record.value.value for record in response.status_records}
    assert values[3] == zigbee_time(datetime.fromisoformat(start).replace(tzinfo=UTC))
    assert values[4] == zigbee_time(datetime.fromisoformat(end).replace(tzinfo=UTC)) - 1
    assert values[5] == shift
    assert response.status_records[3].value.type == foundation.DataTypeId.uint32
    assert response.status_records[4].value.type == foundation.DataTypeId.uint32
    assert response.status_records[5].value.type == foundation.DataTypeId.int32
    assert values[6] == values[0] + values[2]
    assert values[7] == values[6] + (
        shift if values[3] <= values[0] <= values[4] else 0
    )
    assert values[7] == zigbee_time(now + now.astimezone(zone).utcoffset())
    assert cluster._read_snapshot is None
    assert service._cache is not None


@pytest.mark.parametrize(
    "zone", [UTC, timezone(timedelta(hours=5, minutes=30)), ZoneInfo("Asia/Tokyo")]
)
def test_time_service_no_dst(zone):
    now = datetime(2026, 7, 15, tzinfo=UTC)
    snapshot = TimeService(zone).snapshot(now)
    assert snapshot.authoritative
    assert (snapshot.dst_start, snapshot.dst_end, snapshot.dst_shift) == (
        INVALID_TIME,
        INVALID_TIME,
        0,
    )
    assert snapshot.standard_time == snapshot.local_time
    assert snapshot.local_time == snapshot.time + snapshot.time_zone


@pytest.mark.parametrize(
    "zone_name",
    [
        "Europe/Berlin",
        "Australia/Sydney",
        "Australia/Lord_Howe",
        "Europe/Dublin",
        "Africa/Casablanca",
    ],
)
def test_time_service_transition_boundaries(zone_name):
    zone = ZoneInfo(zone_name)
    service = TimeService(zone)
    for start, end, offset, shift in service._scan_periods(zone, 2026)[1:-1]:
        for transition in (start, end):
            for seconds in (-1, 0, 1):
                now = transition + timedelta(seconds=seconds)
                snapshot = service.snapshot(now)
                current_shift = int(
                    (now.astimezone(zone).dst() or timedelta(0)).total_seconds()
                )
                advertised_shift = (
                    snapshot.dst_shift
                    if snapshot.dst_start <= snapshot.time <= snapshot.dst_end
                    else 0
                )
                assert snapshot.authoritative
                assert advertised_shift == current_shift
                assert snapshot.local_time == snapshot.standard_time + current_shift
                assert snapshot.local_time == zigbee_time(
                    now + now.astimezone(zone).utcoffset()
                )


def test_time_service_cache_and_timezone_change():
    zone = ZoneInfo("Europe/Berlin")
    service = TimeService(zone)
    with patch.object(
        TimeService, "_scan_periods", wraps=service._scan_periods
    ) as scan:
        winter = service.snapshot(datetime(2026, 1, 15, tzinfo=UTC))
        summer = service.snapshot(datetime(2026, 7, 15, tzinfo=UTC))
        assert winter.dst_start == summer.dst_start
        assert winter.dst_shift == summer.dst_shift == 3600
        assert scan.call_count == 1
        assert service.snapshot(datetime(2026, 1, 15, tzinfo=UTC)) == winter
        service.snapshot(datetime(2027, 1, 15, tzinfo=UTC))
        assert scan.call_count == 2
        zone = ZoneInfo("Australia/Sydney")
        service.timezone = zone
        changed = service.snapshot(datetime(2027, 1, 15, tzinfo=UTC))
        assert changed.time_zone == 36000
        assert scan.call_count == 3
        service.clear_cache()
        assert service.snapshot(datetime(2027, 1, 15, tzinfo=UTC)) == changed
        assert scan.call_count == 4


def test_time_service_negative_dst():
    start = datetime(2026, 3, 1, tzinfo=UTC)
    end = datetime(2026, 6, 1, tzinfo=UTC)
    header = b"TZif\0" + bytes(15) + struct.pack(">6I", 0, 0, 0, 3, 2, 8)
    transitions = struct.pack(
        ">3i",
        int(datetime(2025, 1, 1, tzinfo=UTC).timestamp()),
        int(start.timestamp()),
        int(end.timestamp()),
    )
    offsets = struct.pack(">iBBiBB", 3600, 0, 0, 0, 1, 4)
    zone = ZoneInfo.from_file(
        io.BytesIO(header + transitions + b"\0\1\0" + offsets + b"STD\0DST\0")
    )
    service = TimeService(zone)
    now = datetime(2026, 4, 15, tzinfo=UTC)
    snapshot = service.snapshot(now)
    assert snapshot.time_zone == 3600
    assert snapshot.dst_shift == -3600
    assert snapshot.local_time == snapshot.time
    assert snapshot.dst_start == zigbee_time(start)
    assert snapshot.dst_end == zigbee_time(end) - 1
    assert types.int32s.deserialize(types.int32s(snapshot.dst_shift).serialize()) == (
        -3600,
        b"",
    )


@pytest.mark.parametrize("seconds", [-0.5, -1, INVALID_TIME, INVALID_TIME + 1])
def test_time_service_out_of_range(seconds):
    snapshot = TimeService(UTC).snapshot(ZIGBEE_EPOCH + timedelta(seconds=seconds))
    assert snapshot.time == INVALID_TIME
    assert not snapshot.authoritative


@pytest.mark.parametrize("seconds", [0, 1, MAX_TIME])
def test_time_service_valid_range(seconds):
    snapshot = TimeService(UTC).snapshot(ZIGBEE_EPOCH + timedelta(seconds=seconds))
    assert snapshot.time == seconds
    assert snapshot.authoritative


def test_time_service_missing_timezone():
    now = datetime(2026, 7, 15, tzinfo=UTC)
    snapshot = TimeService().snapshot(now)
    assert not snapshot.authoritative
    assert snapshot.local_time == zigbee_time(now + now.astimezone().utcoffset())
    assert snapshot.dst_start == snapshot.dst_end == INVALID_TIME


def test_time_service_standard_offset_change():
    zone = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 1, 15, tzinfo=UTC)
    start = datetime(2026, 3, 1, tzinfo=UTC)
    end = datetime(2026, 10, 1, tzinfo=UTC)
    periods = [
        (datetime(2026, 1, 1, tzinfo=UTC), start, 3600, 0),
        (start, end, 10800, 3600),
        (end, datetime(2027, 1, 1, tzinfo=UTC), 7200, 0),
    ]
    service = TimeService(zone)
    with patch.object(TimeService, "_scan_periods", return_value=periods):
        snapshot = service.snapshot(now)
    assert snapshot.time_zone == 3600
    assert snapshot.dst_start == snapshot.dst_end == INVALID_TIME
    assert snapshot.dst_shift == 0


@pytest.mark.parametrize("valid_clock", [True, False])
async def test_time_cluster_status(valid_clock, app_mock):
    ep = MagicMock()
    ep.device.application = app_mock
    cluster = Time(ep)
    now = datetime(2026 if valid_clock else 1999, 7, 15, tzinfo=UTC)
    with patch("zigpy.zcl.clusters.general.datetime", wraps=datetime) as clock:
        clock.now.return_value = now
        response = await read_attributes(cluster, [0, 1, 3, 4, 5])
    values = {record.attrid: record.value.value for record in response.status_records}
    assert values[1] == (Time.TimeStatus.Master if valid_clock else 0)
    assert values[3] == values[4] == INVALID_TIME
    assert values[5] == 0


def test_time_cluster_direct_handler_uses_time_service(app_mock):
    endpoint = MagicMock()
    endpoint.device.application = app_mock
    app_mock.local_timezone = UTC
    cluster = Time(endpoint)
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)

    with (
        patch("zigpy.zcl.clusters.general.datetime", wraps=datetime) as clock,
        patch.object(
            app_mock._time_service,
            "snapshot",
            wraps=app_mock._time_service.snapshot,
        ) as snapshot,
    ):
        clock.now.return_value = now
        value = cluster.handle_read_attribute_time()

    snapshot.assert_called_once_with(now)
    assert value == zigbee_time(now)
    assert cluster._read_snapshot is None


def test_time_service_unbounded_dst():
    class PermanentDST(tzinfo):
        def utcoffset(self, value):
            return timedelta(hours=2)

        def dst(self, value):
            return timedelta(hours=1)

    snapshot = TimeService(PermanentDST()).snapshot(datetime(2026, 7, 15, tzinfo=UTC))
    assert snapshot.authoritative
    assert snapshot.dst_start == 0
    assert snapshot.dst_end == MAX_TIME
    assert snapshot.dst_shift == 3600


async def test_time_service_concurrent_reads():
    zone = ZoneInfo("Europe/Berlin")
    main_thread = threading.get_ident()

    service = TimeService(zone)
    original_scan = service._scan_periods

    def scan(*args, **kwargs):
        assert threading.get_ident() != main_thread
        return original_scan(*args, **kwargs)

    now = datetime(2026, 7, 15, tzinfo=UTC)
    with patch.object(TimeService, "_scan_periods", side_effect=scan) as scan_mock:
        results = await asyncio.gather(
            *(service.async_snapshot(now) for index in range(5))
        )
    assert all(result == results[0] for result in results)
    assert scan_mock.call_count == 1


@pytest.mark.parametrize("zone", [None, UTC, ZoneInfo("Europe/Berlin")])
async def test_time_service_cached_reads_stay_on_loop(zone):
    service = TimeService(zone)
    now = datetime(2026, 7, 15, tzinfo=UTC)
    expected = service.snapshot(now)
    loop = asyncio.get_running_loop()
    with patch.object(loop, "run_in_executor") as executor:
        assert await service.async_snapshot(now) == expected
    executor.assert_not_called()


async def test_time_service_cancelled_discovery():
    zone = ZoneInfo("Europe/Berlin")
    service = TimeService(zone)
    now = datetime(2026, 7, 15, tzinfo=UTC)
    periods = service._discover_periods(zone, now)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    submitted = asyncio.Event()

    def submit(*args):
        submitted.set()
        return future

    with patch.object(loop, "run_in_executor", side_effect=submit) as executor:
        reader = asyncio.create_task(service.async_snapshot(now))
        await asyncio.wait_for(submitted.wait(), timeout=1)
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        assert not future.cancelled()
        assert service._cache is None
        future.set_result(periods)
        result = await service.async_snapshot(now)
    assert result.dst_shift == 3600
    assert executor.call_count == 1


async def test_time_service_invalidation_during_discovery():
    zone = ZoneInfo("Europe/Berlin")
    service = TimeService(zone)
    now = datetime(2026, 7, 15, tzinfo=UTC)
    periods = service._discover_periods(zone, now)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    submitted = asyncio.Event()

    def submit(*args):
        submitted.set()
        return future

    with patch.object(loop, "run_in_executor", side_effect=submit):
        reader = asyncio.create_task(service.async_snapshot(now))
        await asyncio.wait_for(submitted.wait(), timeout=1)
        service.timezone = ZoneInfo("Asia/Tokyo")
        future.set_result(periods)
        old = await reader
    assert old.time_zone == 3600
    assert service._cache is None
    current = await service.async_snapshot(now)
    assert current.time_zone == 32400
    assert current.dst_shift == 0


async def test_time_cluster_shared_service(app_mock):
    zone = ZoneInfo("Europe/Berlin")
    app_mock.local_timezone = zone
    endpoints = [MagicMock(), MagicMock()]
    for endpoint in endpoints:
        endpoint.device.application = app_mock
        endpoint.reply = AsyncMock()
    clusters = [Time(endpoint) for endpoint in endpoints]
    with patch.object(
        TimeService,
        "_scan_periods",
        wraps=app_mock._time_service._scan_periods,
    ) as scan:
        responses = await asyncio.gather(
            *(read_attributes(cluster, [3, 4, 5]) for cluster in clusters)
        )
    assert scan.call_count == 1
    assert responses[0] == responses[1]
    serialized = responses[0].serialize()
    assert type(responses[0]).deserialize(serialized) == (responses[0], b"")


async def test_time_cluster_snapshot_cleanup(app_mock):
    ep = MagicMock()
    ep.device.application = app_mock
    cluster = Time(ep)
    header = foundation.ZCLHeader.general(1, foundation.GeneralCommand.Read_Attributes)
    with patch.object(
        cluster, "handle_read_attribute_time", side_effect=RuntimeError("read failed")
    ):
        with pytest.raises(RuntimeError, match="read failed"):
            await cluster._handle_time_read(header, MagicMock(attribute_ids=[0]), None)
    assert cluster._read_snapshot is None


async def test_time_cluster_other_commands():
    cluster = Time(MagicMock())
    header = foundation.ZCLHeader.general(1, foundation.GeneralCommand.Default_Response)
    with patch.object(zcl.Cluster, "handle_cluster_general_request") as handler:
        cluster.handle_cluster_general_request(header, [])
    handler.assert_called_once_with(header, [], dst_addressing=None)


@pytest.fixture
def dev(monkeypatch, app_mock):
    monkeypatch.setattr(device, "APS_REPLY_TIMEOUT_EXTENDED", 0.1)
    ieee = types.EUI64(map(types.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))

    dev = device.Device(app_mock, ieee, 65535)
    node_desc = zdo_t.NodeDescriptor(1, 1, 1, 4, 5, 6, 7, 8)
    with patch.object(
        dev.zdo, "Node_Desc_req", new=AsyncMock(return_value=(0, 0xFFFF, node_desc))
    ):
        yield dev


@pytest.fixture
def ota_cluster(dev):
    ep = dev.add_endpoint(1)

    cluster = zcl.Cluster._registry[0x0019](ep)
    ep.in_clusters[cluster.cluster_id] = cluster

    with (
        patch.object(cluster, "reply", AsyncMock()),
        patch.object(cluster, "request", AsyncMock()),
    ):
        yield cluster


async def test_ota_handle_cluster_req_wrapper(ota_cluster, caplog):
    ota_cluster._handle_query_next_image = AsyncMock()

    hdr = zigpy.zcl.foundation.ZCLHeader.cluster(123, 0x01)
    ota_cluster.handle_cluster_request(hdr, [sentinel.args])
    assert ota_cluster._handle_query_next_image.call_count == 1
    assert ota_cluster._handle_query_next_image.mock_calls[0].args == (
        hdr,
        [sentinel.args],
    )
    ota_cluster._handle_query_next_image.reset_mock()

    # This command isn't currently handled
    hdr.command_id = 0x08
    ota_cluster.handle_cluster_request(hdr, [sentinel.just_args])
    assert ota_cluster._handle_query_next_image.call_count == 0


async def test_ota_handle_query_next_image(ota_cluster):
    dev = ota_cluster.endpoint.device

    ota_cluster.query_next_image_response = AsyncMock()
    dev.ota_in_progress = False

    # TODO: get rid of `sentinel` and mock the actual command
    hdr = zigpy.zcl.foundation.ZCLHeader.cluster(
        tsn=0x12, command_id=Ota.ServerCommandDefs.query_next_image.id
    )
    cmd = MagicMock()

    cache_events = []
    ota_cluster.on_event(OtaQueryCacheUpdatedEvent.event_type, cache_events.append)

    image_events = []
    ota_cluster.on_event(OtaImageAvailableEvent.event_type, image_events.append)

    # Use the real check_cluster_for_ota so it emits OtaImageAvailableEvent
    ota = dev.application.ota
    ota.check_cluster_for_ota = lambda c: OTA.check_cluster_for_ota(ota, c)

    # No image is available
    ota.get_ota_images = AsyncMock(
        return_value=OtaImagesResult(upgrades=(), downgrades=())
    )
    ota_cluster.handle_cluster_request(hdr, cmd)
    await asyncio.sleep(0)

    assert ota_cluster.query_next_image_response.mock_calls == [
        call(zcl.foundation.Status.NO_IMAGE_AVAILABLE, tsn=hdr.tsn)
    ]
    assert len(image_events) == 1
    assert isinstance(image_events[0], OtaImageAvailableEvent)
    assert image_events[0].images_result == OtaImagesResult(upgrades=(), downgrades=())
    assert image_events[0].query_cmd is cmd
    assert ota_cluster.last_query_cmd is cmd
    assert len(cache_events) == 1
    assert isinstance(cache_events[0], OtaQueryCacheUpdatedEvent)

    ota_cluster.query_next_image_response.reset_mock()
    image_events.clear()

    # Now one is available
    img = MagicMock()
    ota.get_ota_images = AsyncMock(
        return_value=OtaImagesResult(upgrades=(img,), downgrades=())
    )
    ota_cluster.handle_cluster_request(hdr, cmd)
    await asyncio.sleep(0)

    assert ota_cluster.query_next_image_response.mock_calls == [
        call(zcl.foundation.Status.NO_IMAGE_AVAILABLE, tsn=hdr.tsn)
    ]
    assert len(image_events) == 1
    assert image_events[0].images_result == OtaImagesResult(
        upgrades=(img,), downgrades=()
    )
    assert image_events[0].query_cmd is cmd


async def test_ota_handle_image_block_req(ota_cluster):
    dev = ota_cluster.endpoint.device

    ota_cluster.image_block_response = AsyncMock()
    dev.ota_in_progress = False

    hdr = zigpy.zcl.foundation.ZCLHeader.cluster(
        tsn=0x12, command_id=Ota.ServerCommandDefs.image_block.id
    )
    cmd = MagicMock()

    # Stop the upgrade, none is in progress
    ota_cluster.handle_cluster_request(hdr, cmd)
    await asyncio.sleep(0)

    assert ota_cluster.image_block_response.mock_calls == [
        call(zcl.foundation.Status.ABORT, tsn=hdr.tsn)
    ]

    ota_cluster.image_block_response.reset_mock()

    # If we flip the progress flag, send nothing
    dev.ota_in_progress = True
    ota_cluster.handle_cluster_request(hdr, cmd)
    await asyncio.sleep(0)

    assert ota_cluster.image_block_response.mock_calls == []


def test_ias_zone_type():
    extra = b"\xaa\x55"
    zone, rest = sec.IasZone.ZoneType.deserialize(b"\x0d\x00" + extra)
    assert rest == extra
    assert zone is sec.IasZone.ZoneType.Motion_Sensor

    zone, rest = sec.IasZone.ZoneType.deserialize(b"\x81\x81" + extra)
    assert rest == extra
    assert zone.name.startswith("manufacturer_specific")
    assert zone.value == 0x8181


def test_ias_ace_audible_notification():
    extra = b"\xaa\x55"
    notification_type, rest = sec.IasAce.AudibleNotification.deserialize(
        b"\x00" + extra
    )
    assert rest == extra
    assert notification_type is sec.IasAce.AudibleNotification.Mute

    notification_type, rest = sec.IasAce.AudibleNotification.deserialize(
        b"\x81" + extra
    )
    assert rest == extra
    assert notification_type.name.startswith("manufacturer_specific")
    assert notification_type.value == 0x81


def test_basic_cluster_power_source():
    extra = b"The rest of the owl\xaa\x55"
    pwr_src, rest = zcl.clusters.general.Basic.PowerSource.deserialize(b"\x81" + extra)

    assert rest == extra
    assert pwr_src == zcl.clusters.general.Basic.PowerSource.Mains_single_phase
    assert pwr_src == 0x01
    assert pwr_src.value == 0x01
    assert pwr_src.battery_backup


@pytest.mark.parametrize(
    ("raw", "mode", "name"),
    [
        (0x00, 0, "Stop"),
        (0x01, 0, "Stop"),
        (0x02, 0, "Stop"),
        (0x03, 0, "Stop"),
        (0x30, 3, "Emergency"),
        (0x31, 3, "Emergency"),
        (0x32, 3, "Emergency"),
        (0x33, 3, "Emergency"),
    ],
)
def test_security_iaswd_warning_mode(raw, mode, name):
    """Test warning command class of IasWD cluster."""

    def _test(warning, data):
        assert warning.serialize() == data
        assert warning == raw
        assert warning.mode == mode
        assert warning.mode.name == name
        warning.mode = mode
        assert warning.serialize() == data
        assert warning.mode == mode

    data = types.uint8_t(raw).serialize()
    _test(sec.IasWd.Warning(raw), data)

    extra = b"The rest of the owl\xaa\x55"
    warn, rest = sec.IasWd.Warning.deserialize(data + extra)
    assert rest == extra
    _test(warn, data)
    repr(warn)


def test_security_iaswd_warning_mode_2():
    """Test warning command class of IasWD cluster."""

    def _test(data, raw, mode, name):
        warning, _ = sec.IasWd.Warning.deserialize(data)
        assert warning.serialize() == data
        assert warning == raw
        assert warning.mode == mode
        assert warning.mode.name == name
        warning.mode = mode
        assert warning.serialize() == data
        assert warning.mode == mode

    for mode in sec.IasWd.Warning.WarningMode:
        for other in range(16):
            raw = mode << 4 | other
            data = types.uint8_t(raw).serialize()
            _test(data, raw, mode.value, mode.name)


def test_security_iaswd_warning_strobe():
    """Test strobe of warning command class of IasWD cluster."""

    for strobe in sec.IasWd.Warning.Strobe:
        for mode in range(16):
            for siren in range(4):
                raw = mode << 4 | siren
                raw |= strobe.value << 2
                data = types.uint8_t(raw).serialize()
                warning, _ = sec.IasWd.Warning.deserialize(data)
                assert warning.serialize() == data
                assert warning == raw
                assert warning.strobe == strobe.value
                assert warning.strobe.name == strobe.name
                warning.strobe = strobe
                assert warning.serialize() == data
                assert warning.strobe == strobe.value


def test_security_iaswd_warning_siren():
    """Test siren of warning command class of IasWD cluster."""

    for siren in sec.IasWd.Warning.SirenLevel:
        for mode in range(16):
            for strobe in range(4):
                raw = mode << 4 | (strobe << 2)
                raw |= siren.value
                data = types.uint8_t(raw).serialize()
                warning, _ = sec.IasWd.Warning.deserialize(data)
                assert warning.serialize() == data
                assert warning == raw
                assert warning.level == siren.value
                assert warning.level.name == siren.name
                warning.level = siren
                assert warning.serialize() == data
                assert warning.level == siren.value


@pytest.mark.parametrize(
    ("raw", "mode", "name"),
    [
        (0x00, 0, "Armed"),
        (0x01, 0, "Armed"),
        (0x02, 0, "Armed"),
        (0x03, 0, "Armed"),
        (0x10, 1, "Disarmed"),
        (0x11, 1, "Disarmed"),
        (0x12, 1, "Disarmed"),
        (0x13, 1, "Disarmed"),
    ],
)
def test_security_iaswd_squawk_mode(raw, mode, name):
    """Test squawk command class of IasWD cluster."""

    def _test(squawk, data):
        assert squawk.serialize() == data
        assert squawk == raw
        assert squawk.mode == mode
        assert squawk.mode.name == name
        squawk.mode = mode
        assert squawk.serialize() == data
        assert squawk.mode == mode

    data = types.uint8_t(raw).serialize()
    _test(sec.IasWd.Squawk(raw), data)

    extra = b"The rest of the owl\xaa\x55"
    squawk, rest = sec.IasWd.Squawk.deserialize(data + extra)
    assert rest == extra
    _test(squawk, data)
    repr(squawk)


def test_security_iaswd_squawk_strobe():
    """Test strobe of squawk command class of IasWD cluster."""

    for strobe in sec.IasWd.Squawk.Strobe:
        for mode in range(16):
            for level in range(4):
                raw = mode << 4 | level
                raw |= strobe.value << 3
                data = types.uint8_t(raw).serialize()
                squawk, _ = sec.IasWd.Squawk.deserialize(data)
                assert squawk.serialize() == data
                assert squawk == raw
                assert squawk.strobe == strobe.value
                assert squawk.strobe == strobe
                assert squawk.strobe.name == strobe.name
                squawk.strobe = strobe
                assert squawk.serialize() == data
                assert squawk.strobe == strobe


def test_security_iaswd_squawk_level():
    """Test level of squawk command class of IasWD cluster."""

    for level in sec.IasWd.Squawk.SquawkLevel:
        for other in range(64):
            raw = other << 2 | level.value
            data = types.uint8_t(raw).serialize()
            squawk, _ = sec.IasWd.Squawk.deserialize(data)
            assert squawk.serialize() == data
            assert squawk == raw
            assert squawk.level == level.value
            assert squawk.level == level
            assert squawk.level.name == level.name
            squawk.level = level
            assert squawk.serialize() == data
            assert squawk.level == level


def test_hvac_thermostat_system_type():
    """Test system_type class."""

    hvac = zcl.clusters.hvac
    sys_type = hvac.Thermostat.SystemType(0x00)
    assert sys_type.cooling_system_stage == hvac.CoolingSystemStage.Cool_Stage_1
    assert sys_type.heating_system_stage == hvac.HeatingSystemStage.Heat_Stage_1
    assert sys_type.heating_fuel_source == hvac.HeatingFuelSource.Electric
    assert sys_type.heating_system_type == hvac.HeatingSystemType.Conventional

    sys_type = hvac.Thermostat.SystemType(0x35)
    assert sys_type.cooling_system_stage == hvac.CoolingSystemStage.Cool_Stage_2
    assert sys_type.heating_system_stage == hvac.HeatingSystemStage.Heat_Stage_2
    assert sys_type.heating_fuel_source == hvac.HeatingFuelSource.Gas
    assert sys_type.heating_system_type == hvac.HeatingSystemType.Heat_Pump


@patch("zigpy.zcl.Cluster.send_default_rsp")
async def test_ias_zone(send_rsp_mock):
    """Test sending default response on zone status notification."""

    ep = MagicMock()
    ep.reply = AsyncMock()
    t = zcl.Cluster._registry[sec.IasZone.cluster_id](ep, is_server=False)

    # suppress default response
    hdr, args = t.deserialize(b"\tK\x00&\x00\x00\x00\x00\x00")
    hdr.frame_control = hdr.frame_control.replace(disable_default_response=True)
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 0
    send_rsp_mock.reset_mock()

    # this should generate a default response
    hdr.frame_control = hdr.frame_control.replace(disable_default_response=False)
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 1
    send_rsp_mock.reset_mock()

    t = zcl.Cluster._registry[sec.IasZone.cluster_id](ep, is_server=True)

    # suppress default response
    hdr, args = t.deserialize(b"\tK\x00&\x00\x00\x00\x00\x00")
    hdr.frame_control = hdr.frame_control.replace(disable_default_response=True)
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 0
    send_rsp_mock.reset_mock()

    # this should generate a default response
    hdr.frame_control = hdr.frame_control.replace(disable_default_response=False)
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 1
    send_rsp_mock.reset_mock()


def test_ota_image_block_field_control():
    """Test OTA image_block with field control deserializes properly."""
    data = bytes.fromhex("01d403020b101d01001f000100000000400000")

    ep = MagicMock()
    cluster = zcl.clusters.general.Ota(ep)

    hdr, response = cluster.deserialize(data)
    assert hdr.serialize() + response.serialize() == data

    image_block = cluster.commands_by_name["image_block"].schema

    assert response == image_block(
        field_control=image_block.FieldControl.MinimumBlockPeriod,
        manufacturer_code=4107,
        image_type=285,
        file_version=0x01001F00,
        file_offset=0,
        maximum_data_size=64,
        minimum_block_period=0,
    )

    assert response.request_node_addr is None


def test_general_analog_in_application_type():
    """Test AnalogInput General Cluster, Application Type Attribute."""
    app_type = zcl.clusters.general_const.ApplicationType(
        0x00_01_0007
    )  # Group 0x00, Type 0x01, Application 0x0007

    assert app_type.group == 0x00
    assert (
        app_type.type
        == zcl.clusters.general_const.AnalogInputType.Relative_Humidity_Percent
    )
    assert (
        app_type.index
        == zcl.clusters.general_const.RelativeHumidityPercent.Space_Humidity
    )


def test_ias_zone_enum_subclass_zcl_type():
    """Test `IasZone.zone_type` is an enum16, not a uint16."""

    assert sec.IasZone.AttributeDefs.zone_type.zcl_type == foundation.DataTypeId.enum16
