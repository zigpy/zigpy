from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime
import logging
from pathlib import Path

import pytest

from zigpy.appdb import sqlite3
import zigpy.device_scanner
import zigpy.endpoint
import zigpy.exceptions
from zigpy.profiles import zha
import zigpy.types as t
from zigpy.zcl import ClusterType, foundation
from zigpy.zcl.clusters.general import Basic, OnOff
from zigpy.zdo import types as zdo_t

from .async_mock import AsyncMock, call, patch
from .conftest import make_node_desc
from .test_appdb import make_app_with_db


def test_device_scanner_public_contract_types():
    summary_fields = [
        field.name
        for field in dataclasses.fields(zigpy.device_scanner.DeviceScanSummary)
    ]
    assert summary_fields == [
        "ieee",
        "completed",
        "outcome",
        "used_resume",
        "force_full",
        "descriptor_refresh_performed",
        "last_finished",
        "error_code",
        "last_error",
    ]

    snapshot_fields = [
        field.name
        for field in dataclasses.fields(zigpy.device_scanner.DeviceScanSnapshot)
    ]
    assert snapshot_fields == [
        "ieee",
        "raw_node_descriptor",
        "last_snapshot_at",
        "endpoints",
    ]

    event_fields = [
        field.name
        for field in dataclasses.fields(zigpy.device_scanner.DeviceScanProgressEvent)
    ]
    assert event_fields == [
        "ieee",
        "status",
        "outcome",
        "step",
        "endpoint_id",
        "cluster_id",
        "cluster_type",
        "scope_kind",
        "manufacturer_code_scope",
        "error_code",
        "error",
    ]


def test_device_scanner_public_error_types():
    for error_type in (
        zigpy.device_scanner.InvalidScanOptionsError,
        zigpy.device_scanner.ScanInProgressError,
        zigpy.device_scanner.DeviceScanTargetMissingError,
        zigpy.device_scanner.DeviceScanSnapshotNotFoundError,
    ):
        assert issubclass(error_type, Exception)


def test_device_scanner_vocabulary_is_fixed():
    assert zigpy.device_scanner.SCAN_EVENT_NAMES == (
        "scan_queued",
        "scan_started",
        "step_started",
        "step_finished",
        "scan_finished",
    )
    assert zigpy.device_scanner.SCAN_STATUSES == (
        "queued",
        "started",
        "success",
        "failed",
        "skipped",
    )
    assert zigpy.device_scanner.SCAN_OUTCOMES == (
        "success",
        "partial",
        "failed",
    )
    assert zigpy.device_scanner.SCAN_ERROR_CODES == (
        "invalid_scan_options",
        "scan_in_progress",
        "device_scan_target_missing",
        "descriptor_refresh_failed",
        "scan_deadline_exceeded",
        "unsupported_discovery_command",
        "transport_failure",
        "attribute_unsupported",
        "missing_raw_manufacturer_code",
    )


async def test_device_scanner_invalid_scan_options(app):
    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")

    with pytest.raises(zigpy.device_scanner.InvalidScanOptionsError):
        await app.device_scanner.scan(ieee, resume=True, force_full=True)


def test_device_scanner_progress_events_emit_on_scanner(app):
    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:44")
    events = []

    class Listener:
        def scan_finished(self, event):
            events.append(event)

    app.device_scanner.add_listener(Listener())

    event = app.device_scanner._emit_progress(
        "scan_finished",
        ieee=ieee,
        status="failed",
        outcome="failed",
        error_code="scan_deadline_exceeded",
        error="deadline exceeded",
    )

    assert isinstance(event, zigpy.device_scanner.DeviceScanProgressEvent)
    assert events == [event]


@pytest.mark.parametrize(
    ("event_name", "payload", "expected_error"),
    [
        ("bogus", {"status": "queued"}, "Unknown device scan event name"),
        ("scan_started", {"status": "bogus"}, "Unknown device scan status"),
        (
            "scan_finished",
            {"status": "success", "outcome": "bogus"},
            "Unknown device scan outcome",
        ),
        (
            "scan_finished",
            {"status": "failed", "error_code": "bogus"},
            "Unknown device scan error code",
        ),
    ],
)
def test_device_scanner_emit_progress_rejects_unknown_vocabulary(
    app, event_name, payload, expected_error
):
    with pytest.raises(ValueError, match=expected_error):
        app.device_scanner._emit_progress(
            event_name,
            ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:44"),
            **payload,
        )


def test_device_scanner_get_dblistener_requires_initialized_listener(app):
    app._dblistener = None

    with pytest.raises(
        RuntimeError, match="DeviceScanner requires an initialized database listener"
    ):
        app.device_scanner._get_dblistener()


async def test_device_scanner_noop_action_is_awaitable(app):
    await app.device_scanner._noop_action()


async def test_device_scanner_scan_raises_when_active_request_is_missing_task(app):
    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:45")
    app.device_scanner._active_scans[ieee] = zigpy.device_scanner._SharedScanRequest(
        ieee=ieee,
        resume=True,
        force_full=False,
    )

    with pytest.raises(RuntimeError, match="missing its task"):
        await app.device_scanner.scan(ieee)


async def test_device_scanner_run_shared_scan_converts_internal_scan_failures(
    tmp_path: Path,
):
    app, dev, _ = await _make_basic_scan_target(tmp_path)
    request = zigpy.device_scanner._SharedScanRequest(
        ieee=dev.ieee,
        resume=False,
        force_full=False,
    )

    class FakeTimeout:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def expired(self) -> bool:
            return False

    with (
        patch(
            "zigpy.device_scanner.asyncio_timeout",
            return_value=FakeTimeout(),
        ),
        patch.object(
            app.device_scanner,
            "_run_scan_body",
            new=AsyncMock(
                side_effect=zigpy.device_scanner._ScanFailure(
                    "scan broke", error_code="transport_failure"
                )
            ),
        ),
    ):
        summary = await app.device_scanner._run_shared_scan(request)

    assert summary.outcome == "failed"
    assert summary.error_code == "transport_failure"
    assert summary.last_error == "scan broke"

    await app.shutdown()


async def test_device_scanner_run_shared_scan_nonexpired_timeout_is_not_deadline(
    tmp_path: Path,
):
    app, dev, _ = await _make_basic_scan_target(tmp_path)
    request = zigpy.device_scanner._SharedScanRequest(
        ieee=dev.ieee,
        resume=False,
        force_full=False,
    )

    class FakeTimeout:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def expired(self) -> bool:
            return False

    with (
        patch(
            "zigpy.device_scanner.asyncio_timeout",
            return_value=FakeTimeout(),
        ),
        patch.object(
            app.device_scanner,
            "_run_scan_body",
            new=AsyncMock(side_effect=TimeoutError()),
        ),
    ):
        with pytest.raises(TimeoutError):
            await app.device_scanner._run_shared_scan(request)

    await app.shutdown()


async def test_device_scanner_run_shared_scan_uses_exception_scan_error_code(
    tmp_path: Path,
):
    app, dev, _ = await _make_basic_scan_target(tmp_path)
    request = zigpy.device_scanner._SharedScanRequest(
        ieee=dev.ieee,
        resume=False,
        force_full=False,
    )

    class FakeTimeout:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def expired(self) -> bool:
            return False

    exc = RuntimeError("boom")
    exc.device_scan_error_code = "transport_failure"

    with (
        patch(
            "zigpy.device_scanner.asyncio_timeout",
            return_value=FakeTimeout(),
        ),
        patch.object(
            app.device_scanner,
            "_run_scan_body",
            new=AsyncMock(side_effect=exc),
        ),
    ):
        summary = await app.device_scanner._run_shared_scan(request)

    assert summary.outcome == "failed"
    assert summary.error_code == "transport_failure"
    assert summary.last_error == "boom"

    await app.shutdown()


async def test_device_scanner_run_scope_step_reraises_unexpected_exception(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)

    with pytest.raises(RuntimeError, match="boom"):
        await app.device_scanner._run_scope_step(
            target,
            step=zigpy.device_scanner.SCAN_STEPS[1],
            action=AsyncMock(side_effect=RuntimeError("boom")),
        )

    await app.shutdown()


async def test_device_scanner_run_scope_step_reraises_timeout_when_deadline_expired(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)

    with patch.object(app.device_scanner, "_scan_deadline_expired", return_value=True):
        with pytest.raises(TimeoutError):
            await app.device_scanner._run_scope_step(
                target,
                step=zigpy.device_scanner.SCAN_STEPS[1],
                action=AsyncMock(side_effect=TimeoutError()),
            )

    await app.shutdown()


def test_device_scanner_snapshot_helpers_cover_status_variants(app):
    scanner = app.device_scanner

    assert scanner._to_datetime(None) is None

    pending_row = zigpy.appdb.DeviceScanProgressRow(
        ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:46"),
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=False,
        attr_discovery_next_id=0,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    failed_row = pending_row._replace(
        last_error_code="transport_failure",
        last_error="timeout",
    )
    success_row = pending_row._replace(
        attr_discovery_complete=True,
        attr_reads_complete=True,
        cmd_rx_complete=True,
        cmd_tx_complete=True,
    )

    assert (
        scanner._make_snapshot_progress(pending_row, synthetic_skipped=False).status
        == "pending"
    )
    assert (
        scanner._make_snapshot_progress(failed_row, synthetic_skipped=False).status
        == "failed"
    )
    assert (
        scanner._make_snapshot_progress(success_row, synthetic_skipped=False).status
        == "success"
    )


def test_device_scanner_decode_attribute_value_returns_none_on_decode_failure(app):
    class BrokenDeserializer:
        @classmethod
        def deserialize(cls, data: bytes):
            raise ValueError("bad value")

    assert (
        app.device_scanner._decode_attribute_value(
            datatype=int(foundation.DataTypeId.uint8),
            raw_value=b"\x01",
            decode_cache={int(foundation.DataTypeId.uint8): BrokenDeserializer},
        )
        is None
    )


def test_device_scanner_coerce_device_type_variants(app):
    scanner = app.device_scanner

    assert scanner._coerce_device_type(zha.PROFILE_ID, None) is None
    assert (
        scanner._coerce_device_type(
            zigpy.profiles.zll.PROFILE_ID,
            zigpy.profiles.zll.DeviceType.COLOR_LIGHT,
        )
        == zigpy.profiles.zll.DeviceType.COLOR_LIGHT
    )
    assert scanner._coerce_device_type(0xA1E0, 0x0061) == 0x0061


def test_device_scanner_make_ephemeral_cluster_adds_server_cluster(app):
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:11:22:33:47"),
    )
    ep = zigpy.endpoint.Endpoint(dev, 1)

    cluster = app.device_scanner._make_ephemeral_cluster(
        ep,
        cluster_id=Basic.cluster_id,
        cluster_type=ClusterType.Server,
    )

    assert ep.in_clusters[Basic.cluster_id] is cluster
    assert getattr(ep, cluster.ep_attribute) is cluster


def test_device_scanner_canonicalize_attribute_value_handles_arrays(app):
    array_value = foundation.Array(
        type=foundation.DataTypeId.octstr,
        value=t.LVList[t.LVBytes, t.uint16_t]([b"\x00\x01"]),
    )

    datatype, raw = app.device_scanner._canonicalize_attribute_value(array_value)

    assert datatype == int(
        foundation.DataType.from_python_type(type(array_value)).type_id
    )
    assert raw == array_value.serialize()


async def test_device_scanner_translate_discovery_failure_variants(tmp_path: Path):
    app, _, _ = await _make_basic_scan_target(tmp_path)

    unsupported = app.device_scanner._translate_discovery_failure(
        zigpy.exceptions.DeliveryError(
            "unsupported",
            status=int(foundation.Status.UNSUP_GENERAL_COMMAND),
        )
    )
    unknown_status = app.device_scanner._translate_discovery_failure(
        zigpy.exceptions.DeliveryError("plain failure", status=999)
    )
    unsupported_text = app.device_scanner._translate_discovery_failure(
        zigpy.exceptions.DeliveryError("feature not supported")
    )
    unrelated = app.device_scanner._translate_discovery_failure(
        zigpy.exceptions.DeliveryError("boom")
    )

    assert unsupported is not None
    assert unsupported.error_code == "unsupported_discovery_command"
    assert unknown_status is None
    assert unsupported_text is not None
    assert unsupported_text.error_code == "unsupported_discovery_command"
    assert unrelated is None

    await app.shutdown()


def test_device_scanner_extract_default_response_status_handles_invalid_status(app):
    assert (
        app.device_scanner._extract_default_response_status(
            (foundation.GeneralCommand.Default_Response, 999)
        )
        is None
    )


async def test_device_scanner_skip_unsupported_command_discovery_persists_empty_page(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)

    with patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()):
        await app.device_scanner._skip_unsupported_command_discovery(
            target,
            direction="received",
            start_command_id=4,
            status=foundation.Status.UNSUP_GENERAL_COMMAND,
        )

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.commands == []
    assert rows.progress[0].cmd_rx_complete is True
    assert rows.progress[0].cmd_rx_next_id == 4

    await app.shutdown()


async def _make_basic_scan_target(tmp_path: Path):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11"),
    )
    dev.node_desc = make_node_desc()

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)

    target = next(
        target
        for target in await app.device_scanner._build_raw_scan_targets(dev)
        if target.endpoint_id == 1
        and target.cluster.cluster_type == ClusterType.Server
        and target.cluster.cluster_id == Basic.cluster_id
    )
    return app, dev, target


async def _seed_scan_progress(app, target):
    await app._dblistener.upsert_device_scan_progress(
        ieee=target.endpoint.device.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=target.scope.manufacturer_code_scope,
        attr_discovery_complete=False,
        attr_discovery_next_id=0,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )


async def _seed_discovered_attribute(
    app,
    target,
    *,
    attr_id: int,
    attribute_name: str | None,
    datatype: int,
    access: int | None,
    read_complete: bool = False,
    read_status: str | None = None,
    value: bytes | None = None,
    last_error_code: str | None = None,
):
    await app._dblistener.upsert_device_scan_attribute(
        ieee=target.endpoint.device.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=target.scope.manufacturer_code_scope,
        attr_id=attr_id,
        attribute_name=attribute_name,
        datatype=datatype,
        access=access,
        discovered_at=1.0,
        read_complete=read_complete,
        read_status=read_status,
        value=value,
        last_read=None,
        last_error_code=last_error_code,
        last_error=None,
    )


async def _make_onoff_scan_targets(tmp_path: Path):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:22"),
    )
    dev.node_desc = make_node_desc()

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(OnOff.cluster_id)
    ep1.add_output_cluster(OnOff.cluster_id)

    await app._dblistener._save_device(dev)

    targets = await app.device_scanner._build_raw_scan_targets(dev)
    server_target = next(
        target
        for target in targets
        if target.cluster.cluster_type == ClusterType.Server
        and target.cluster.cluster_id == OnOff.cluster_id
    )
    client_target = next(
        target
        for target in targets
        if target.cluster.cluster_type == ClusterType.Client
        and target.cluster.cluster_id == OnOff.cluster_id
    )
    return app, dev, server_target, client_target


def _make_scan_summary(
    ieee: t.EUI64,
    *,
    outcome: str = "success",
    error_code: str | None = None,
    last_error: str | None = None,
) -> zigpy.device_scanner.DeviceScanSummary:
    return zigpy.device_scanner.DeviceScanSummary(
        ieee=ieee,
        completed=True,
        outcome=outcome,
        used_resume=True,
        force_full=False,
        descriptor_refresh_performed=True,
        last_finished=None,
        error_code=error_code,
        last_error=last_error,
    )


async def test_device_scanner_descriptor_refresh_does_not_mutate_live_runtime_dictionaries(
    app,
):
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11"),
    )
    dev.node_desc = make_node_desc()

    live_ep = dev.add_endpoint(1)
    live_ep.status = zigpy.endpoint.Status.ZDO_INIT
    live_ep.profile_id = zha.PROFILE_ID
    live_ep.device_type = zha.DeviceType.PUMP
    live_ep.add_input_cluster(Basic.cluster_id)

    original_endpoints = set(dev.endpoints)
    original_input_clusters = dict(live_ep.in_clusters)

    async def mock_active_ep_req(nwk):
        assert nwk == dev.nwk
        return [zdo_t.Status.SUCCESS, None, [1, 2]]

    async def mock_simple_desc_req(nwk, endpoint_id):
        assert nwk == dev.nwk

        sd = zdo_t.SimpleDescriptor()
        sd.endpoint = endpoint_id
        sd.profile = zha.PROFILE_ID
        sd.device_type = zha.DeviceType.PUMP

        if endpoint_id == 1:
            sd.input_clusters = [Basic.cluster_id]
        else:
            sd.input_clusters = [OnOff.cluster_id]

        sd.output_clusters = []
        return [zdo_t.Status.SUCCESS, None, sd]

    dev.zdo.Node_Desc_req = AsyncMock(
        return_value=(zdo_t.Status.SUCCESS, dev.nwk, dev.node_desc)
    )
    dev.zdo.Active_EP_req = AsyncMock(side_effect=mock_active_ep_req)
    dev.zdo.Simple_Desc_req = AsyncMock(side_effect=mock_simple_desc_req)

    result = await app.device_scanner._discover_raw_descriptors(dev)

    assert set(dev.endpoints) == original_endpoints
    assert 2 not in dev.endpoints
    assert dict(live_ep.in_clusters) == original_input_clusters
    assert {descriptor.endpoint_id for descriptor in result.endpoints} == {1, 2}


async def test_device_scanner_refresh_replaces_raw_rows_and_cleans_removed_scan_scopes(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=0x1111)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)
    ep1.add_input_cluster(OnOff.cluster_id)

    ep2 = dev.add_endpoint(2)
    ep2.status = zigpy.endpoint.Status.ZDO_INIT
    ep2.profile_id = zha.PROFILE_ID
    ep2.device_type = zha.DeviceType.PUMP
    ep2.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=OnOff.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=False,
        attr_discovery_next_id=0,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=1.0,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=2,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=False,
        attr_discovery_next_id=0,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=1.0,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )

    events = []

    class Listener:
        def step_started(self, event):
            events.append(("step_started", event))

        def step_finished(self, event):
            events.append(("step_finished", event))

    app.device_scanner.add_listener(Listener())

    refreshed_node_desc = make_node_desc(manufacturer_code=0x2222)

    async def mock_active_ep_req(nwk):
        assert nwk == dev.nwk
        return [zdo_t.Status.SUCCESS, None, [1]]

    async def mock_simple_desc_req(nwk, endpoint_id):
        assert nwk == dev.nwk
        assert endpoint_id == 1

        sd = zdo_t.SimpleDescriptor()
        sd.endpoint = endpoint_id
        sd.profile = zha.PROFILE_ID
        sd.device_type = zha.DeviceType.PUMP
        sd.input_clusters = [Basic.cluster_id]
        sd.output_clusters = [OnOff.cluster_id]
        return [zdo_t.Status.SUCCESS, None, sd]

    dev.zdo.Node_Desc_req = AsyncMock(
        return_value=(zdo_t.Status.SUCCESS, dev.nwk, refreshed_node_desc)
    )
    dev.zdo.Active_EP_req = AsyncMock(side_effect=mock_active_ep_req)
    dev.zdo.Simple_Desc_req = AsyncMock(side_effect=mock_simple_desc_req)

    await app.device_scanner._refresh_raw_descriptors(dev)

    with sqlite3.connect(tmp_path / "test.db") as conn:
        endpoint_rows = conn.execute(
            "SELECT endpoint_id, profile_id, device_type, status"
            " FROM endpoints_v15 WHERE ieee = ? ORDER BY endpoint_id",
            (str(dev.ieee),),
        ).fetchall()
        cluster_rows = conn.execute(
            "SELECT endpoint_id, cluster_type, cluster_id"
            " FROM clusters_v15 WHERE ieee = ? ORDER BY endpoint_id, cluster_type, cluster_id",
            (str(dev.ieee),),
        ).fetchall()
        node_desc_row = conn.execute(
            "SELECT manufacturer_code FROM node_descriptors_v15 WHERE ieee = ?",
            (str(dev.ieee),),
        ).fetchone()

    assert endpoint_rows == [
        (1, zha.PROFILE_ID, zha.DeviceType.PUMP, zigpy.endpoint.Status.ZDO_INIT)
    ]
    assert cluster_rows == [
        (1, ClusterType.Server, Basic.cluster_id),
        (1, ClusterType.Client, OnOff.cluster_id),
    ]
    assert node_desc_row == (0x2222,)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.progress == []

    assert [name for name, _ in events] == ["step_started", "step_finished"]
    assert events[0][1].step == "descriptor_refresh"
    assert events[0][1].endpoint_id is None
    assert events[1][1].status == "success"
    assert events[1][1].step == "descriptor_refresh"

    await app.shutdown()


async def test_device_scanner_refresh_preserves_group_memberships_for_kept_endpoints(
    tmp_path: Path,
):
    db_path = tmp_path / "test.db"
    app = await make_app_with_db(db_path)
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:12"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=0x1111)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO groups_v15 (group_id, name) VALUES (?, ?)",
            (0x1234, "kitchen"),
        )
        conn.execute(
            "INSERT INTO group_members_v15 (group_id, ieee, endpoint_id)"
            " VALUES (?, ?, ?)",
            (0x1234, str(dev.ieee), 1),
        )
        conn.commit()

    async def mock_active_ep_req(nwk):
        assert nwk == dev.nwk
        return [zdo_t.Status.SUCCESS, None, [1]]

    async def mock_simple_desc_req(nwk, endpoint_id):
        assert nwk == dev.nwk
        assert endpoint_id == 1

        sd = zdo_t.SimpleDescriptor()
        sd.endpoint = endpoint_id
        sd.profile = zha.PROFILE_ID
        sd.device_type = zha.DeviceType.PUMP
        sd.input_clusters = [Basic.cluster_id]
        sd.output_clusters = []
        return [zdo_t.Status.SUCCESS, None, sd]

    dev.zdo.Node_Desc_req = AsyncMock(
        return_value=(zdo_t.Status.SUCCESS, dev.nwk, dev.node_desc)
    )
    dev.zdo.Active_EP_req = AsyncMock(side_effect=mock_active_ep_req)
    dev.zdo.Simple_Desc_req = AsyncMock(side_effect=mock_simple_desc_req)

    await app.device_scanner._refresh_raw_descriptors(dev)

    with sqlite3.connect(db_path) as conn:
        group_members = conn.execute(
            "SELECT group_id, ieee, endpoint_id FROM group_members_v15 WHERE ieee = ?",
            (str(dev.ieee),),
        ).fetchall()

    assert group_members == [(0x1234, str(dev.ieee), 1)]

    await app.shutdown()


async def test_device_scanner_refresh_failure_keeps_prior_raw_rows_and_emits_failed_step(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=0x1111)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)

    events = []

    class Listener:
        def step_started(self, event):
            events.append(("step_started", event))

        def step_finished(self, event):
            events.append(("step_finished", event))

    app.device_scanner.add_listener(Listener())

    dev.zdo.Node_Desc_req = AsyncMock(
        return_value=(
            zdo_t.Status.SUCCESS,
            dev.nwk,
            make_node_desc(manufacturer_code=0x2222),
        )
    )
    dev.zdo.Active_EP_req = AsyncMock(return_value=(zdo_t.Status.NOT_ACTIVE, None, []))

    with pytest.raises(zigpy.exceptions.InvalidResponse):
        await app.device_scanner._refresh_raw_descriptors(dev)

    with sqlite3.connect(tmp_path / "test.db") as conn:
        endpoint_rows = conn.execute(
            "SELECT endpoint_id FROM endpoints_v15 WHERE ieee = ? ORDER BY endpoint_id",
            (str(dev.ieee),),
        ).fetchall()
        node_desc_row = conn.execute(
            "SELECT manufacturer_code FROM node_descriptors_v15 WHERE ieee = ?",
            (str(dev.ieee),),
        ).fetchone()

    assert endpoint_rows == [(1,)]
    assert node_desc_row == (0x1111,)
    assert [name for name, _ in events] == ["step_started", "step_finished"]
    assert events[1][1].status == "failed"
    assert events[1][1].error_code == "descriptor_refresh_failed"

    await app.shutdown()


async def test_device_scanner_descriptor_refresh_applies_request_pacing(app):
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11"),
    )

    async def mock_active_ep_req(nwk):
        return [zdo_t.Status.SUCCESS, None, [1]]

    async def mock_simple_desc_req(nwk, endpoint_id):
        sd = zdo_t.SimpleDescriptor()
        sd.endpoint = endpoint_id
        sd.profile = zha.PROFILE_ID
        sd.device_type = zha.DeviceType.PUMP
        sd.input_clusters = [Basic.cluster_id]
        sd.output_clusters = []
        return [zdo_t.Status.SUCCESS, None, sd]

    dev.zdo.Node_Desc_req = AsyncMock(
        return_value=(zdo_t.Status.SUCCESS, dev.nwk, make_node_desc())
    )
    dev.zdo.Active_EP_req = AsyncMock(side_effect=mock_active_ep_req)
    dev.zdo.Simple_Desc_req = AsyncMock(side_effect=mock_simple_desc_req)

    with patch("zigpy.device_scanner.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        await app.device_scanner._discover_raw_descriptors(dev)

    assert sleep_mock.await_count == 3


async def test_device_scanner_builds_targets_from_raw_db_rows_with_output_cluster_role(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:11"),
    )
    dev.node_desc = make_node_desc()

    raw_ep = dev.add_endpoint(1)
    raw_ep.status = zigpy.endpoint.Status.ZDO_INIT
    raw_ep.profile_id = zha.PROFILE_ID
    raw_ep.device_type = zha.DeviceType.PUMP
    raw_ep.add_input_cluster(Basic.cluster_id)
    raw_ep.add_output_cluster(OnOff.cluster_id)

    await app._dblistener._save_device(dev)

    quirk_ep = dev.add_endpoint(99)
    quirk_ep.status = zigpy.endpoint.Status.ZDO_INIT
    quirk_ep.profile_id = zha.PROFILE_ID
    quirk_ep.device_type = zha.DeviceType.PUMP
    quirk_ep.add_input_cluster(0xFC00)

    targets = await app.device_scanner._build_raw_scan_targets(dev)

    assert {
        (target.endpoint_id, target.cluster.cluster_type, target.cluster.cluster_id)
        for target in targets
    } == {
        (1, ClusterType.Server, Basic.cluster_id),
        (1, ClusterType.Client, OnOff.cluster_id),
    }
    onoff_target = next(
        target for target in targets if target.cluster.cluster_id == OnOff.cluster_id
    )
    assert onoff_target.cluster.is_client is True
    assert onoff_target.cluster.is_server is False
    assert onoff_target.endpoint.endpoint_id == 1
    assert onoff_target.endpoint is not dev.endpoints[1]
    assert 99 not in {target.endpoint_id for target in targets}

    await app.shutdown()


async def test_device_scanner_build_raw_scan_targets_skips_endpoint_242(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:33"),
    )
    dev.node_desc = make_node_desc()

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    ep242 = dev.add_endpoint(242)
    ep242.status = zigpy.endpoint.Status.ZDO_INIT
    ep242.profile_id = 0xA1E0
    ep242.device_type = 0x0061
    ep242.add_output_cluster(0x0021)

    await app._dblistener._save_device(dev)

    targets = await app.device_scanner._build_raw_scan_targets(dev)

    assert {
        (target.endpoint_id, target.cluster.cluster_type, target.cluster.cluster_id)
        for target in targets
    } == {
        (1, ClusterType.Server, Basic.cluster_id),
    }

    await app.shutdown()


async def test_device_scanner_attribute_discovery_persists_pages_and_progress(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)

    discover_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Attribute_Extended_rsp
    ].schema
    target.cluster.discover_attributes_extended = AsyncMock(
        side_effect=[
            discover_rsp(
                discovery_complete=False,
                extended_attr_info=[
                    foundation.DiscoverAttributesExtendedResponseRecord(
                        attrid=0x0000,
                        datatype=foundation.DataTypeId.uint8,
                        acl=foundation.AttributeAccessControl.READ,
                    ),
                    foundation.DiscoverAttributesExtendedResponseRecord(
                        attrid=0x0001,
                        datatype=foundation.DataTypeId.uint8,
                        acl=foundation.AttributeAccessControl.READ
                        | foundation.AttributeAccessControl.WRITE,
                    ),
                ],
            ),
            discover_rsp(
                discovery_complete=True,
                extended_attr_info=[
                    foundation.DiscoverAttributesExtendedResponseRecord(
                        attrid=0x0002,
                        datatype=foundation.DataTypeId.uint8,
                        acl=foundation.AttributeAccessControl.READ,
                    )
                ],
            ),
        ]
    )

    await app.device_scanner._discover_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert [row.attr_id for row in rows.attributes] == [0x0000, 0x0001, 0x0002]
    assert [row.datatype for row in rows.attributes] == [
        foundation.DataTypeId.uint8,
        foundation.DataTypeId.uint8,
        foundation.DataTypeId.uint8,
    ]
    assert [row.access for row in rows.attributes] == [
        foundation.AttributeAccessControl.READ,
        foundation.AttributeAccessControl.READ
        | foundation.AttributeAccessControl.WRITE,
        foundation.AttributeAccessControl.READ,
    ]
    assert all(row.read_complete is False for row in rows.attributes)
    assert all(row.read_status is None for row in rows.attributes)
    assert all(row.last_error_code is None for row in rows.attributes)
    assert all(row.value is None for row in rows.attributes)

    assert len(rows.progress) == 1
    progress = rows.progress[0]
    assert progress.endpoint_id == 1
    assert progress.cluster_type == ClusterType.Server
    assert progress.cluster_id == Basic.cluster_id
    assert progress.attr_discovery_complete is True
    assert progress.attr_discovery_next_id == 3

    assert target.cluster.discover_attributes_extended.await_args_list[0].args == (
        0,
        16,
    )
    assert target.cluster.discover_attributes_extended.await_args_list[0].kwargs == {
        "manufacturer": None
    }
    assert target.cluster.discover_attributes_extended.await_args_list[1].args == (
        2,
        16,
    )
    assert target.cluster.discover_attributes_extended.await_args_list[1].kwargs == {
        "manufacturer": None
    }

    await app.shutdown()


async def test_device_scanner_attribute_discovery_falls_back_to_standard_on_unsupported_extended_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    discover_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Attributes_rsp
    ].schema
    target.cluster.discover_attributes_extended = AsyncMock(
        return_value=(
            foundation.GeneralCommand.Default_Response,
            foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )
    target.cluster.discover_attributes = AsyncMock(
        return_value=discover_rsp(
            discovery_complete=True,
            attribute_info=[
                foundation.DiscoverAttributesResponseRecord(
                    attrid=0x0000,
                    datatype=foundation.DataTypeId.uint8,
                )
            ],
        )
    )
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")
    with (
        patch.object(
            app._dblistener,
            "persist_device_scan_attribute_discovery_page",
            new=AsyncMock(
                wraps=app._dblistener.persist_device_scan_attribute_discovery_page
            ),
        ) as persist_page,
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()) as pace,
    ):
        await app.device_scanner._discover_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert [row.attr_id for row in rows.attributes] == [0x0000]
    assert [row.access for row in rows.attributes] == [None]
    assert rows.progress[0].attr_discovery_complete is True
    target.cluster.discover_attributes_extended.assert_awaited_once()
    target.cluster.discover_attributes.assert_awaited_once()
    assert pace.await_count == 2
    assert persist_page.await_count == 1
    assert persist_page.await_args.kwargs["reset_scope"] is True
    assert "falling back to discover_attributes" in caplog.text.lower()

    await app.shutdown()


async def test_device_scanner_attribute_discovery_continues_when_both_discovery_commands_are_unsupported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    unsupported_response = (
        foundation.GeneralCommand.Default_Response,
        foundation.Status.UNSUP_GENERAL_COMMAND,
    )
    target.cluster.discover_attributes_extended = AsyncMock(
        return_value=unsupported_response
    )
    target.cluster.discover_attributes = AsyncMock(return_value=unsupported_response)
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")

    await app.device_scanner._discover_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.attributes == []
    assert rows.progress[0].attr_discovery_complete is True
    assert rows.progress[0].attr_discovery_next_id == 0
    assert rows.progress[0].last_error_code is None
    assert "extended attribute discovery unsupported" in caplog.text.lower()
    assert "standard attribute discovery unsupported" in caplog.text.lower()

    await app.shutdown()


async def test_device_scanner_attribute_discovery_continues_when_both_default_response_objects_are_unsupported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_attributes_extended = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Attribute_Extended,
            status=foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )
    target.cluster.discover_attributes = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Attributes,
            status=foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")

    await app.device_scanner._discover_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.attributes == []
    assert rows.progress[0].attr_discovery_complete is True
    assert rows.progress[0].attr_discovery_next_id == 0
    assert rows.progress[0].last_error_code is None
    assert "extended attribute discovery unsupported" in caplog.text.lower()
    assert "standard attribute discovery unsupported" in caplog.text.lower()

    await app.shutdown()


async def test_device_scanner_manufacturer_attribute_discovery_continues_when_both_default_response_objects_are_manufacturer_unsupported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, _ = await _make_basic_scan_target(tmp_path)
    targets = await app.device_scanner._build_scan_targets_for_node_descriptor(
        dev, dev.node_desc
    )
    manufacturer_target = next(
        target
        for target in targets
        if target.cluster.cluster_id == Basic.cluster_id
        and target.scope.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )

    manufacturer_target.cluster.discover_attributes_extended = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Attribute_Extended,
            status=foundation.Status.UNSUP_MANUF_GENERAL_COMMAND,
        )
    )
    manufacturer_target.cluster.discover_attributes = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Attributes,
            status=foundation.Status.UNSUP_MANUF_GENERAL_COMMAND,
        )
    )
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")

    await app.device_scanner._discover_attributes_for_target(manufacturer_target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.attributes == []
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == manufacturer_target.endpoint_id
        and row.cluster_type == manufacturer_target.cluster.cluster_type
        and row.cluster_id == manufacturer_target.cluster.cluster_id
        and row.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )
    assert progress.attr_discovery_complete is True
    assert progress.attr_discovery_next_id == 0
    assert progress.last_error_code is None
    assert "extended attribute discovery unsupported" in caplog.text.lower()
    assert "standard attribute discovery unsupported" in caplog.text.lower()

    await app.shutdown()


async def test_device_scanner_attribute_discovery_non_unsupported_default_response_is_terminal(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_attributes_extended = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Attribute_Extended,
            status=foundation.Status.FAILURE,
        )
    )

    with pytest.raises(zigpy.device_scanner._TerminalStepFailure) as exc_info:
        await app.device_scanner._discover_attributes_for_target(target)

    assert (
        exc_info.value.error_code
        == zigpy.device_scanner.ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND
    )
    assert "failure" in str(exc_info.value).lower()

    await app.shutdown()


async def test_device_scanner_attribute_reads_use_raw_reads_and_preserve_live_cache(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await _seed_scan_progress(app, target)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    live_cluster = dev.endpoints[1].in_clusters[Basic.cluster_id]
    live_cluster._update_attribute(Basic.AttributeDefs.zcl_version.id, 9)

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        assert manufacturer is None
        assert list(attributes) == [
            Basic.AttributeDefs.zcl_version.id,
            Basic.AttributeDefs.app_version.id,
        ]
        return read_rsp(
            status_records=[
                foundation.ReadAttributeRecord(
                    attrid=Basic.AttributeDefs.zcl_version.id,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(3),
                    ),
                ),
                foundation.ReadAttributeRecord(
                    attrid=Basic.AttributeDefs.app_version.id,
                    status=foundation.Status.UNSUPPORTED_ATTRIBUTE,
                ),
            ]
        )

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)
    await app.device_scanner._read_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_complete is True
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_status == "success"
    assert attrs[Basic.AttributeDefs.zcl_version.id].last_error_code is None
    assert attrs[Basic.AttributeDefs.zcl_version.id].value == b"\x03"
    assert attrs[Basic.AttributeDefs.app_version.id].read_complete is True
    assert (
        attrs[Basic.AttributeDefs.app_version.id].read_status == "unsupported_attribute"
    )
    assert (
        attrs[Basic.AttributeDefs.app_version.id].last_error_code
        == "attribute_unsupported"
    )
    assert attrs[Basic.AttributeDefs.app_version.id].value is None
    assert rows.progress[0].attr_reads_complete is True
    assert target.cluster.read_attributes_raw.await_args.kwargs["manufacturer"] is None
    assert live_cluster._attr_cache.get_value(Basic.AttributeDefs.zcl_version) == 9

    await app.shutdown()


async def test_device_scanner_attribute_reads_include_unknown_access_rows(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await _seed_scan_progress(app, target)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=1,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=None,
    )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema
    target.cluster.read_attributes_raw = AsyncMock(
        return_value=read_rsp(
            status_records=[
                foundation.ReadAttributeRecord(
                    attrid=Basic.AttributeDefs.zcl_version.id,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(3),
                    ),
                )
            ]
        )
    )

    await app.device_scanner._read_attributes_for_target(target)

    target.cluster.read_attributes_raw.assert_awaited_once()
    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attr_row = next(row for row in rows.attributes if row.attr_id == 0x0000)
    assert attr_row.read_complete is True
    assert attr_row.read_status == "success"

    await app.shutdown()


async def test_device_scanner_attribute_reads_batch_in_groups_of_three(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await _seed_scan_progress(app, target)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=4,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    for attr_def in (
        Basic.AttributeDefs.zcl_version,
        Basic.AttributeDefs.app_version,
        Basic.AttributeDefs.stack_version,
        Basic.AttributeDefs.hw_version,
    ):
        await _seed_discovered_attribute(
            app,
            target,
            attr_id=attr_def.id,
            attribute_name=attr_def.name,
            datatype=foundation.DataTypeId.uint8,
            access=foundation.AttributeAccessControl.READ,
        )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        assert manufacturer is None

        if list(attributes) == [0, 1, 2]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=0,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(3),
                        ),
                    ),
                    foundation.ReadAttributeRecord(
                        attrid=1,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(4),
                        ),
                    ),
                    foundation.ReadAttributeRecord(
                        attrid=2,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(5),
                        ),
                    ),
                ]
            )

        if list(attributes) == [3]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=3,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(6),
                        ),
                    )
                ]
            )

        raise AssertionError(f"Unexpected attribute batch: {attributes!r}")

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    await app.device_scanner._read_attributes_for_target(target)

    assert [
        list(call.args[0])
        for call in target.cluster.read_attributes_raw.await_args_list
    ] == [[0, 1, 2], [3]]

    await app.shutdown()


async def test_device_scanner_attribute_reads_missing_status_records_are_logged_and_do_not_abort_batches(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await _seed_scan_progress(app, target)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=4,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    for attr_def in (
        Basic.AttributeDefs.zcl_version,
        Basic.AttributeDefs.app_version,
        Basic.AttributeDefs.stack_version,
        Basic.AttributeDefs.hw_version,
    ):
        await _seed_discovered_attribute(
            app,
            target,
            attr_id=attr_def.id,
            attribute_name=attr_def.name,
            datatype=foundation.DataTypeId.uint8,
            access=foundation.AttributeAccessControl.READ,
        )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        assert manufacturer is None

        if list(attributes) == [0, 1, 2]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=0,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(3),
                        ),
                    ),
                    foundation.ReadAttributeRecord(
                        attrid=1,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(4),
                        ),
                    ),
                ]
            )

        if list(attributes) == [3]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=3,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(6),
                        ),
                    )
                ]
            )

        if list(attributes) == [2]:
            return read_rsp(status_records=[])

        raise AssertionError(f"Unexpected attribute batch: {attributes!r}")

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(zigpy.device_scanner._TerminalStepFailure) as exc_info:
            await app.device_scanner._read_attributes_for_target(target)

    assert exc_info.value.error_code == "transport_failure"
    assert "0x0002" in str(exc_info.value)
    assert [
        list(call.args[0])
        for call in target.cluster.read_attributes_raw.await_args_list
    ] == [[0, 1, 2], [2], [3]]
    assert any(
        "missing status records" in record.message and "0x0002" in record.message
        for record in caplog.records
    )

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[0].read_complete is True
    assert attrs[0].read_status == "success"
    assert attrs[1].read_complete is True
    assert attrs[1].read_status == "success"
    assert attrs[2].read_complete is False
    assert attrs[2].read_status == "transport_failure"
    assert attrs[2].last_error_code == "transport_failure"
    assert attrs[2].value is None
    assert attrs[3].read_complete is True
    assert attrs[3].read_status == "success"
    assert rows.progress[0].attr_reads_complete is False

    await app.shutdown()


async def test_device_scanner_attribute_reads_retry_before_split(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema
    read_attempts = 0

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        nonlocal read_attempts
        read_attempts += 1
        assert manufacturer is None
        assert list(attributes) == [
            Basic.AttributeDefs.zcl_version.id,
            Basic.AttributeDefs.app_version.id,
        ]

        if read_attempts == 1:
            raise zigpy.exceptions.DeliveryError("boom")

        return read_rsp(
            status_records=[
                foundation.ReadAttributeRecord(
                    attrid=Basic.AttributeDefs.zcl_version.id,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(4),
                    ),
                ),
                foundation.ReadAttributeRecord(
                    attrid=Basic.AttributeDefs.app_version.id,
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(7),
                    ),
                ),
            ]
        )

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    await app.device_scanner._read_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_complete is True
    assert attrs[Basic.AttributeDefs.zcl_version.id].value == b"\x04"
    assert attrs[Basic.AttributeDefs.app_version.id].read_complete is True
    assert attrs[Basic.AttributeDefs.app_version.id].value == b"\x07"
    assert rows.progress[0].attr_reads_complete is True
    assert [
        list(call.args[0])
        for call in target.cluster.read_attributes_raw.await_args_list
    ] == [[0, 1], [0, 1]]

    await app.shutdown()


async def test_device_scanner_attribute_reads_treat_default_response_as_terminal_protocol_outcome(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    target.cluster.read_attributes_raw = AsyncMock(
        return_value=(
            foundation.GeneralCommand.Default_Response,
            foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )

    await app.device_scanner._read_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_complete is True
    assert (
        attrs[Basic.AttributeDefs.zcl_version.id].read_status == "unsup_general_command"
    )
    assert attrs[Basic.AttributeDefs.zcl_version.id].last_error_code is None
    assert attrs[Basic.AttributeDefs.app_version.id].read_complete is True
    assert (
        attrs[Basic.AttributeDefs.app_version.id].read_status == "unsup_general_command"
    )
    assert attrs[Basic.AttributeDefs.app_version.id].last_error_code is None
    assert rows.progress[0].attr_reads_complete is True

    await app.shutdown()


async def test_device_scanner_attribute_reads_treat_default_response_object_as_terminal_protocol_outcome(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    target.cluster.read_attributes_raw = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Read_Attributes,
            status=foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )

    await app.device_scanner._read_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_complete is True
    assert (
        attrs[Basic.AttributeDefs.zcl_version.id].read_status == "unsup_general_command"
    )
    assert attrs[Basic.AttributeDefs.zcl_version.id].last_error_code is None
    assert attrs[Basic.AttributeDefs.app_version.id].read_complete is True
    assert (
        attrs[Basic.AttributeDefs.app_version.id].read_status == "unsup_general_command"
    )
    assert attrs[Basic.AttributeDefs.app_version.id].last_error_code is None
    assert rows.progress[0].attr_reads_complete is True

    await app.shutdown()


async def test_device_scanner_attribute_reads_split_transport_failures_and_keep_retryable_rows_pending(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        if list(attributes) == [
            Basic.AttributeDefs.zcl_version.id,
            Basic.AttributeDefs.app_version.id,
        ]:
            raise zigpy.exceptions.DeliveryError("boom")
        if list(attributes) == [Basic.AttributeDefs.zcl_version.id]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=Basic.AttributeDefs.zcl_version.id,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(4),
                        ),
                    )
                ]
            )
        if list(attributes) == [Basic.AttributeDefs.app_version.id]:
            raise zigpy.exceptions.DeliveryError("still broken")
        raise AssertionError(f"Unexpected attribute batch: {attributes!r}")

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    with pytest.raises(zigpy.device_scanner._TerminalStepFailure) as exc_info:
        await app.device_scanner._read_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attrs = {row.attr_id: row for row in rows.attributes}
    assert exc_info.value.error_code == "transport_failure"
    assert str(exc_info.value) == "still broken"
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_complete is True
    assert attrs[Basic.AttributeDefs.zcl_version.id].read_status == "success"
    assert attrs[Basic.AttributeDefs.zcl_version.id].value == b"\x04"
    assert attrs[Basic.AttributeDefs.app_version.id].read_complete is False
    assert attrs[Basic.AttributeDefs.app_version.id].read_status == "transport_failure"
    assert (
        attrs[Basic.AttributeDefs.app_version.id].last_error_code == "transport_failure"
    )
    assert attrs[Basic.AttributeDefs.app_version.id].value is None
    assert rows.progress[0].attr_reads_complete is False
    assert [
        list(call.args[0])
        for call in target.cluster.read_attributes_raw.await_args_list
    ] == [[0, 1], [0, 1], [0], [1]]

    await app.shutdown()


async def test_device_scanner_attribute_discovery_raises_translated_unsupported_delivery_error(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_attributes_extended = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError(
            "unsupported",
            status=int(foundation.Status.UNSUP_GENERAL_COMMAND),
        )
    )

    with pytest.raises(zigpy.device_scanner._TerminalStepFailure) as exc_info:
        await app.device_scanner._discover_attributes_for_target(target)

    assert exc_info.value.error_code == "unsupported_discovery_command"

    await app.shutdown()


async def test_device_scanner_attribute_discovery_reraises_nonterminal_zigbee_exception(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_attributes_extended = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("boom")
    )

    with pytest.raises(zigpy.exceptions.DeliveryError, match="boom"):
        await app.device_scanner._discover_attributes_for_target(target)

    await app.shutdown()


async def test_device_scanner_scan_marks_attribute_read_transport_failures_partial(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        if list(attributes) == [
            Basic.AttributeDefs.zcl_version.id,
            Basic.AttributeDefs.app_version.id,
        ]:
            raise zigpy.exceptions.DeliveryError("boom")
        if list(attributes) == [Basic.AttributeDefs.zcl_version.id]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=Basic.AttributeDefs.zcl_version.id,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(4),
                        ),
                    )
                ]
            )
        if list(attributes) == [Basic.AttributeDefs.app_version.id]:
            raise zigpy.exceptions.DeliveryError("still broken")
        raise AssertionError(f"Unexpected attribute batch: {attributes!r}")

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ) as discover_attrs,
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ) as discover_rx,
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ) as discover_tx,
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        summary = await app.device_scanner._run_scan_body(
            dev, resume=True, force_full=False
        )

    discover_attrs.assert_not_awaited()
    discover_rx.assert_awaited_once()
    discover_tx.assert_awaited_once()
    assert summary.outcome == "partial"
    assert summary.error_code == "transport_failure"

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    failed_progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert failed_progress.attr_reads_complete is False
    assert failed_progress.last_error_code == "transport_failure"
    assert failed_progress.last_error == "still broken"

    await app.shutdown()


async def test_device_scanner_attribute_reads_mark_complete_when_no_rows_pending(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)

    await app.device_scanner._read_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.progress[0].attr_reads_complete is True

    await app.shutdown()


async def test_device_scanner_attribute_reads_report_multiple_remaining_rows(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    await app._dblistener.upsert_device_scan_progress(
        ieee=target.endpoint.device.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=target.scope.manufacturer_code_scope,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    with patch.object(
        app.device_scanner,
        "_read_attribute_rows_with_fallback",
        new=AsyncMock(return_value=()),
    ):
        with pytest.raises(zigpy.device_scanner._TerminalStepFailure) as exc_info:
            await app.device_scanner._read_attributes_for_target(target)

    assert exc_info.value.error_code == "transport_failure"
    assert "0x0000" in str(exc_info.value)
    assert "0x0001" in str(exc_info.value)

    await app.shutdown()


async def test_device_scanner_attribute_discovery_persists_standard_and_manufacturer_scopes(
    tmp_path: Path,
):
    app, dev, standard_target = await _make_basic_scan_target(tmp_path)
    targets = await app.device_scanner._build_scan_targets_for_node_descriptor(
        dev, dev.node_desc
    )
    standard_target = next(
        target
        for target in targets
        if target.cluster.cluster_id == Basic.cluster_id
        and target.scope.manufacturer_code_scope is None
    )
    manufacturer_target = next(
        target
        for target in targets
        if target.cluster.cluster_id == Basic.cluster_id
        and target.scope.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )

    discover_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Attribute_Extended_rsp
    ].schema
    manufacturers = []

    async def discover_attributes_extended(
        start_attr_id, page_size, *, manufacturer=None
    ):
        manufacturers.append(manufacturer)
        return discover_rsp(
            discovery_complete=True,
            extended_attr_info=[
                foundation.DiscoverAttributesExtendedResponseRecord(
                    attrid=Basic.AttributeDefs.zcl_version.id,
                    datatype=foundation.DataTypeId.uint8,
                    acl=foundation.AttributeAccessControl.READ,
                )
            ],
        )

    standard_target.cluster.discover_attributes_extended = AsyncMock(
        side_effect=discover_attributes_extended
    )

    await app.device_scanner._discover_attributes_for_target(standard_target)
    await app.device_scanner._discover_attributes_for_target(manufacturer_target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    attr_rows = [
        row
        for row in rows.attributes
        if row.attr_id == Basic.AttributeDefs.zcl_version.id
    ]
    assert {row.manufacturer_code_scope for row in attr_rows} == {
        None,
        dev.node_desc.manufacturer_code,
    }
    assert manufacturers == [None, dev.node_desc.manufacturer_code]

    await app.shutdown()


async def test_device_scanner_command_discovery_persists_received_and_generated_pages(
    tmp_path: Path,
):
    app, dev, server_target, _ = await _make_onoff_scan_targets(tmp_path)

    cmd_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Received_rsp
    ].schema
    server_target.cluster.discover_commands_received = AsyncMock(
        side_effect=[
            cmd_rsp(discovery_complete=False, command_ids=[0x00, 0x01]),
            cmd_rsp(discovery_complete=True, command_ids=[0x02]),
        ]
    )
    server_target.cluster.discover_commands_generated = AsyncMock(
        return_value=cmd_rsp(discovery_complete=True, command_ids=[0x00])
    )

    await app.device_scanner._discover_commands_received_for_target(server_target)
    await app.device_scanner._discover_commands_generated_for_target(server_target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    rx_rows = [row for row in rows.commands if row.direction == "received"]
    tx_rows = [row for row in rows.commands if row.direction == "generated"]
    assert [row.command_id for row in rx_rows] == [0x00, 0x01, 0x02]
    assert [row.command_id for row in tx_rows] == [0x00]
    assert rows.progress[0].cmd_rx_complete is True
    assert rows.progress[0].cmd_rx_next_id == 3
    assert rows.progress[0].cmd_tx_complete is True
    assert rows.progress[0].cmd_tx_next_id == 1
    assert server_target.cluster.discover_commands_received.await_args_list[0].args == (
        0,
        16,
    )
    assert server_target.cluster.discover_commands_generated.await_args_list[
        0
    ].args == (
        0,
        16,
    )

    await app.shutdown()


async def test_device_scanner_command_discovery_logs_and_completes_on_unsupported_default_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, target, _ = await _make_onoff_scan_targets(tmp_path)
    target.cluster.discover_commands_received = AsyncMock(
        return_value=(
            foundation.GeneralCommand.Default_Response,
            foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")

    await app.device_scanner._discover_commands_received_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert rows.commands == []
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert progress.cmd_rx_complete is True
    assert progress.cmd_rx_next_id == 0
    assert progress.last_error_code is None
    assert "unsupported command discovery response" in caplog.text

    await app.shutdown()


async def test_device_scanner_command_discovery_persists_client_role_for_output_clusters(
    tmp_path: Path,
):
    app, dev, _, client_target = await _make_onoff_scan_targets(tmp_path)

    cmd_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Generated_rsp
    ].schema
    client_target.cluster.discover_commands_generated = AsyncMock(
        return_value=cmd_rsp(discovery_complete=True, command_ids=[0x00, 0x02])
    )

    await app.device_scanner._discover_commands_generated_for_target(client_target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert [
        (row.cluster_type, row.direction, row.command_id) for row in rows.commands
    ] == [
        (ClusterType.Client, "generated", 0x00),
        (ClusterType.Client, "generated", 0x02),
    ]
    assert client_target.cluster.is_client is True
    assert client_target.cluster.is_server is False

    await app.shutdown()


async def test_device_scanner_command_discovery_persists_manufacturer_scope(
    tmp_path: Path,
):
    app, dev, server_target, _ = await _make_onoff_scan_targets(tmp_path)
    targets = await app.device_scanner._build_scan_targets_for_node_descriptor(
        dev, dev.node_desc
    )
    manufacturer_target = next(
        target
        for target in targets
        if target.cluster.cluster_id == OnOff.cluster_id
        and target.cluster.cluster_type == ClusterType.Server
        and target.scope.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )

    cmd_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Received_rsp
    ].schema
    manufacturers = []

    async def discover_commands_received(
        start_command_id, page_size, *, manufacturer=None
    ):
        manufacturers.append(manufacturer)
        return cmd_rsp(discovery_complete=True, command_ids=[0x00])

    manufacturer_target.cluster.discover_commands_received = AsyncMock(
        side_effect=discover_commands_received
    )

    await app.device_scanner._discover_commands_received_for_target(manufacturer_target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    rx_rows = [
        row
        for row in rows.commands
        if row.direction == "received"
        and row.cluster_id == OnOff.cluster_id
        and row.manufacturer_code_scope == dev.node_desc.manufacturer_code
    ]
    assert [row.command_id for row in rx_rows] == [0x00]
    assert manufacturers == [dev.node_desc.manufacturer_code]

    await app.shutdown()


async def test_device_scanner_manufacturer_command_discovery_logs_and_completes_on_manufacturer_unsupported_default_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, _, _ = await _make_onoff_scan_targets(tmp_path)
    targets = await app.device_scanner._build_scan_targets_for_node_descriptor(
        dev, dev.node_desc
    )
    manufacturer_target = next(
        target
        for target in targets
        if target.cluster.cluster_id == OnOff.cluster_id
        and target.cluster.cluster_type == ClusterType.Server
        and target.scope.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )
    manufacturer_target.cluster.discover_commands_received = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Commands_Received,
            status=foundation.Status.UNSUP_MANUF_GENERAL_COMMAND,
        )
    )
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")

    await app.device_scanner._discover_commands_received_for_target(manufacturer_target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == manufacturer_target.endpoint_id
        and row.cluster_type == manufacturer_target.cluster.cluster_type
        and row.cluster_id == manufacturer_target.cluster.cluster_id
        and row.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )
    assert progress.cmd_rx_complete is True
    assert progress.cmd_rx_next_id == 0
    assert progress.last_error_code is None
    assert "unsupported command discovery response" in caplog.text.lower()

    await app.shutdown()


async def test_device_scanner_retries_manufacturer_command_discovery_timeout_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    app, dev, _, _ = await _make_onoff_scan_targets(tmp_path)
    targets = await app.device_scanner._build_scan_targets_for_node_descriptor(
        dev, dev.node_desc
    )
    manufacturer_target = next(
        target
        for target in targets
        if target.cluster.cluster_id == OnOff.cluster_id
        and target.cluster.cluster_type == ClusterType.Server
        and target.scope.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )
    cmd_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Generated_rsp
    ].schema
    manufacturer_target.cluster.discover_commands_generated = AsyncMock(
        side_effect=[
            TimeoutError(),
            cmd_rsp(discovery_complete=True, command_ids=[0x02]),
        ]
    )
    caplog.set_level(logging.WARNING, logger="zigpy.device_scanner")

    with patch("zigpy.device_scanner.asyncio.sleep", new=AsyncMock()):
        await app.device_scanner._discover_commands_generated_for_target(
            manufacturer_target
        )

    assert manufacturer_target.cluster.discover_commands_generated.await_count == 2
    assert "Retrying manufacturer-scoped generated command discovery" in caplog.text

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == manufacturer_target.endpoint_id
        and row.cluster_type == manufacturer_target.cluster.cluster_type
        and row.cluster_id == manufacturer_target.cluster.cluster_id
        and row.manufacturer_code_scope == dev.node_desc.manufacturer_code
    )
    commands = [
        row
        for row in rows.commands
        if row.endpoint_id == manufacturer_target.endpoint_id
        and row.cluster_type == manufacturer_target.cluster.cluster_type
        and row.cluster_id == manufacturer_target.cluster.cluster_id
        and row.manufacturer_code_scope == dev.node_desc.manufacturer_code
        and row.direction == "generated"
    ]
    assert progress.cmd_tx_complete is True
    assert [row.command_id for row in commands] == [0x02]

    await app.shutdown()


async def test_device_scanner_standard_command_discovery_timeout_reraises(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_commands_received = AsyncMock(side_effect=TimeoutError())

    with pytest.raises(TimeoutError):
        await app.device_scanner._discover_commands_received_for_target(target)

    await app.shutdown()


async def test_device_scanner_command_discovery_translates_terminal_zigbee_exception(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_commands_generated = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError(
            "unsupported",
            status=foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )

    with pytest.raises(zigpy.device_scanner._TerminalStepFailure) as exc_info:
        await app.device_scanner._discover_commands_generated_for_target(target)

    assert (
        exc_info.value.error_code
        == zigpy.device_scanner.ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND
    )

    await app.shutdown()


async def test_device_scanner_command_discovery_reraises_nonterminal_zigbee_exception(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    target.cluster.discover_commands_generated = AsyncMock(
        side_effect=zigpy.exceptions.ZigbeeException("boom")
    )

    with pytest.raises(zigpy.exceptions.ZigbeeException, match="boom"):
        await app.device_scanner._discover_commands_generated_for_target(target)

    await app.shutdown()


async def test_device_scanner_scan_reuses_duplicate_requests_and_rejects_conflicts(
    tmp_path: Path,
):
    app, dev, _ = await _make_basic_scan_target(tmp_path)
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = []

    async def mock_run_scan_body(device, *, resume, force_full):
        calls.append((device.ieee, resume, force_full))
        started.set()
        await finish.wait()
        return _make_scan_summary(device.ieee)

    with patch.object(
        app.device_scanner,
        "_run_scan_body",
        new=AsyncMock(side_effect=mock_run_scan_body),
        create=True,
    ):
        first = asyncio.create_task(app.device_scanner.scan(dev.ieee))
        await asyncio.wait_for(started.wait(), timeout=0.2)

        second = asyncio.create_task(app.device_scanner.scan(dev.ieee))

        with pytest.raises(zigpy.device_scanner.ScanInProgressError):
            await app.device_scanner.scan(dev.ieee, resume=False)

        finish.set()

        assert await first == await second

    assert calls == [(dev.ieee, True, False)]

    await app.shutdown()


async def test_device_scanner_scan_waits_fifo_for_different_devices(tmp_path: Path):
    app, first_dev, _ = await _make_basic_scan_target(tmp_path)
    second_dev = app.add_device(
        nwk=0x2234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:33"),
    )
    second_dev.node_desc = make_node_desc()

    ep1 = second_dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(second_dev)

    first_started = asyncio.Event()
    allow_first_finish = asyncio.Event()
    start_order = []

    async def mock_run_scan_body(device, *, resume, force_full):
        start_order.append(device.ieee)
        if device.ieee == first_dev.ieee:
            first_started.set()
            await allow_first_finish.wait()
        return _make_scan_summary(device.ieee)

    with patch.object(
        app.device_scanner,
        "_run_scan_body",
        new=AsyncMock(side_effect=mock_run_scan_body),
        create=True,
    ):
        first = asyncio.create_task(app.device_scanner.scan(first_dev.ieee))
        await asyncio.wait_for(first_started.wait(), timeout=0.2)

        second = asyncio.create_task(app.device_scanner.scan(second_dev.ieee))
        await asyncio.sleep(0)
        assert start_order == [first_dev.ieee]

        allow_first_finish.set()
        await asyncio.gather(first, second)

    assert start_order == [first_dev.ieee, second_dev.ieee]

    await app.shutdown()


async def test_device_scanner_scan_queued_duplicate_and_conflict_match_running_behavior(
    tmp_path: Path,
):
    app, first_dev, _ = await _make_basic_scan_target(tmp_path)
    second_dev = app.add_device(
        nwk=0x3234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:99"),
    )
    second_dev.node_desc = make_node_desc()

    ep1 = second_dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(second_dev)

    first_started = asyncio.Event()
    allow_first_finish = asyncio.Event()
    second_started = asyncio.Event()
    allow_second_finish = asyncio.Event()
    calls = []

    async def mock_run_scan_body(device, *, resume, force_full):
        calls.append((device.ieee, resume, force_full))
        if device.ieee == first_dev.ieee:
            first_started.set()
            await allow_first_finish.wait()
        else:
            second_started.set()
            await allow_second_finish.wait()
        return _make_scan_summary(device.ieee)

    with patch.object(
        app.device_scanner,
        "_run_scan_body",
        new=AsyncMock(side_effect=mock_run_scan_body),
        create=True,
    ):
        first = asyncio.create_task(app.device_scanner.scan(first_dev.ieee))
        await asyncio.wait_for(first_started.wait(), timeout=0.2)

        queued = asyncio.create_task(app.device_scanner.scan(second_dev.ieee))
        duplicate = asyncio.create_task(app.device_scanner.scan(second_dev.ieee))
        await asyncio.sleep(0)

        with pytest.raises(zigpy.device_scanner.ScanInProgressError):
            await app.device_scanner.scan(second_dev.ieee, resume=False)

        allow_first_finish.set()
        await asyncio.wait_for(second_started.wait(), timeout=0.2)
        allow_second_finish.set()

        queued_summary, duplicate_summary = await asyncio.gather(queued, duplicate)
        await first

    assert queued_summary == duplicate_summary
    assert calls == [
        (first_dev.ieee, True, False),
        (second_dev.ieee, True, False),
    ]

    await app.shutdown()


async def test_device_scanner_scan_caller_cancellation_does_not_cancel_shared_work(
    tmp_path: Path,
):
    app, dev, _ = await _make_basic_scan_target(tmp_path)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def mock_run_scan_body(device, *, resume, force_full):
        started.set()
        await finish.wait()
        return _make_scan_summary(device.ieee)

    with patch.object(
        app.device_scanner,
        "_run_scan_body",
        new=AsyncMock(side_effect=mock_run_scan_body),
        create=True,
    ):
        owner = asyncio.create_task(app.device_scanner.scan(dev.ieee))
        await asyncio.wait_for(started.wait(), timeout=0.2)

        detached = asyncio.create_task(app.device_scanner.scan(dev.ieee))
        await asyncio.sleep(0)
        detached.cancel()

        with pytest.raises(asyncio.CancelledError):
            await detached

        assert not owner.done()

        finish.set()
        summary = await owner

    assert summary.outcome == "success"

    await app.shutdown()


async def test_device_scanner_scan_missing_target_before_execution_fails_cleanly(
    tmp_path: Path,
):
    app, first_dev, _ = await _make_basic_scan_target(tmp_path)
    second_dev = app.add_device(
        nwk=0x2234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:44"),
    )
    second_dev.node_desc = make_node_desc()

    ep1 = second_dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(second_dev)

    events = []

    class Listener:
        def scan_finished(self, event):
            events.append(event)

    app.device_scanner.add_listener(Listener())

    started = asyncio.Event()
    finish = asyncio.Event()

    async def mock_run_scan_body(device, *, resume, force_full):
        if device.ieee == first_dev.ieee:
            started.set()
            await finish.wait()
        return _make_scan_summary(device.ieee)

    with patch.object(
        app.device_scanner,
        "_run_scan_body",
        new=AsyncMock(side_effect=mock_run_scan_body),
        create=True,
    ):
        first = asyncio.create_task(app.device_scanner.scan(first_dev.ieee))
        await asyncio.wait_for(started.wait(), timeout=0.2)

        second = asyncio.create_task(app.device_scanner.scan(second_dev.ieee))
        await asyncio.sleep(0)
        app.devices.pop(second_dev.ieee)

        finish.set()
        await first

        with pytest.raises(zigpy.device_scanner.DeviceScanTargetMissingError):
            await second

    assert events[-1].status == "failed"
    assert events[-1].outcome == "failed"
    assert events[-1].error_code == "device_scan_target_missing"

    await app.shutdown()


async def test_device_scanner_scan_deadline_outcome_depends_on_committed_scan_rows(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)

    async def sleep_forever(*args, **kwargs):
        await asyncio.sleep(60)

    with (
        patch("zigpy.device_scanner.SCAN_DEADLINE_S", 0.01),
        patch.object(
            app.device_scanner,
            "_run_scan_body",
            new=AsyncMock(side_effect=sleep_forever),
            create=True,
        ),
    ):
        failed_summary = await app.device_scanner.scan(dev.ieee)

    assert failed_summary.outcome == "failed"
    assert failed_summary.error_code == "scan_deadline_exceeded"

    async def persist_then_sleep(device, *, resume, force_full):
        await app._dblistener.upsert_device_scan_progress(
            ieee=device.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=None,
            attr_discovery_complete=False,
            attr_discovery_next_id=1,
            attr_reads_complete=False,
            cmd_rx_complete=False,
            cmd_rx_next_id=0,
            cmd_tx_complete=False,
            cmd_tx_next_id=0,
            last_started=1.0,
            last_finished=None,
            last_error_code=None,
            last_error=None,
            last_success=None,
        )
        await asyncio.sleep(60)

    with (
        patch("zigpy.device_scanner.SCAN_DEADLINE_S", 0.01),
        patch.object(
            app.device_scanner,
            "_run_scan_body",
            new=AsyncMock(side_effect=persist_then_sleep),
            create=True,
        ),
    ):
        partial_summary = await app.device_scanner.scan(dev.ieee, force_full=False)

    assert partial_summary.outcome == "partial"
    assert partial_summary.error_code == "scan_deadline_exceeded"

    await app.shutdown()


async def test_device_scanner_scan_continues_after_terminal_scope_failure(
    tmp_path: Path,
):
    app, dev, bad_target, good_target = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(bad_target, good_target)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(
                side_effect=[
                    zigpy.device_scanner._TerminalStepFailure(
                        "unsupported discovery",
                        error_code=zigpy.device_scanner.ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND,
                    ),
                    None,
                ]
            ),
        ) as discover_attrs,
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ) as read_attrs,
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ) as discover_rx,
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ) as discover_tx,
    ):
        summary = await app.device_scanner._run_scan_body(
            dev, resume=False, force_full=False
        )

    assert discover_attrs.await_count == 2
    assert read_attrs.await_count == 1
    assert discover_rx.await_count == 1
    assert discover_tx.await_count == 1
    assert summary.outcome == "partial"
    assert summary.error_code == "unsupported_discovery_command"
    assert summary.last_error == "unsupported discovery"
    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    failed_progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == bad_target.endpoint_id
        and row.cluster_type == bad_target.cluster.cluster_type
        and row.cluster_id == bad_target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert failed_progress.last_error_code == "unsupported_discovery_command"

    await app.shutdown()


async def test_device_scanner_scan_treats_scope_timeout_as_transport_failure_not_deadline(
    tmp_path: Path,
):
    app, dev, bad_target, good_target = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(bad_target, good_target)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(side_effect=[TimeoutError(), None]),
        ) as discover_attrs,
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ) as read_attrs,
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ) as discover_rx,
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ) as discover_tx,
    ):
        summary = await app.device_scanner.scan(dev.ieee, resume=False)

    assert discover_attrs.await_count == 2
    assert read_attrs.await_count == 1
    assert discover_rx.await_count == 1
    assert discover_tx.await_count == 1
    assert summary.outcome == "partial"
    assert summary.error_code == "transport_failure"
    assert summary.last_error == "request timed out"
    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    failed_progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == bad_target.endpoint_id
        and row.cluster_type == bad_target.cluster.cluster_type
        and row.cluster_id == bad_target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert failed_progress.last_error_code == "transport_failure"
    assert failed_progress.last_error == "request timed out"

    await app.shutdown()


async def test_device_scanner_scan_continues_after_missing_attribute_read_status_records(
    tmp_path: Path,
):
    app, dev, target, _ = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )
    await _seed_scan_progress(app, target)
    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def discover_attributes_for_target(
        current_target: zigpy.device_scanner._RawScanTarget,
        *,
        start_attr_id: int,
    ) -> None:
        assert current_target is target
        assert start_attr_id == 0
        await app._dblistener.upsert_device_scan_progress(
            ieee=dev.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=target.scope.manufacturer_code_scope,
            attr_discovery_complete=True,
            attr_discovery_next_id=4,
            attr_reads_complete=False,
            cmd_rx_complete=False,
            cmd_rx_next_id=0,
            cmd_tx_complete=False,
            cmd_tx_next_id=0,
            last_started=None,
            last_finished=None,
            last_error_code=None,
            last_error=None,
            last_success=None,
        )
        for attr_def, datatype in (
            (OnOff.AttributeDefs.on_off, foundation.DataTypeId.bool_),
            (
                OnOff.AttributeDefs.global_scene_control,
                foundation.DataTypeId.bool_,
            ),
            (OnOff.AttributeDefs.on_time, foundation.DataTypeId.uint16),
            (OnOff.AttributeDefs.off_wait_time, foundation.DataTypeId.uint16),
        ):
            await _seed_discovered_attribute(
                app,
                target,
                attr_id=attr_def.id,
                attribute_name=attr_def.name,
                datatype=datatype,
                access=foundation.AttributeAccessControl.READ,
            )

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        assert manufacturer is None

        if list(attributes) == [0, 16384, 16385]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=0,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.bool_,
                            value=t.Bool.true,
                        ),
                    ),
                    foundation.ReadAttributeRecord(
                        attrid=16384,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.bool_,
                            value=t.Bool.false,
                        ),
                    ),
                ]
            )

        if list(attributes) == [16386]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=16386,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint16,
                            value=t.uint16_t(9),
                        ),
                    )
                ]
            )

        if list(attributes) == [16385]:
            return read_rsp(status_records=[])

        raise AssertionError(f"Unexpected attribute batch: {attributes!r}")

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(side_effect=discover_attributes_for_target),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ) as discover_rx,
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ) as discover_tx,
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        summary = await app.device_scanner._run_scan_body(
            dev, resume=False, force_full=False
        )

    assert summary.outcome == "partial"
    assert summary.error_code == "transport_failure"
    assert "0x4001" in (summary.last_error or "")
    discover_rx.assert_awaited_once()
    discover_tx.assert_awaited_once()

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    failed_progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert failed_progress.last_error_code == "transport_failure"
    assert "0x4001" in (failed_progress.last_error or "")

    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[0].read_complete is True
    assert attrs[0].read_status == "success"
    assert attrs[16384].read_complete is True
    assert attrs[16384].read_status == "success"
    assert attrs[16385].read_complete is False
    assert attrs[16385].read_status == "transport_failure"
    assert attrs[16385].last_error_code == "transport_failure"
    assert attrs[16386].read_complete is True
    assert attrs[16386].read_status == "success"

    await app.shutdown()


async def test_device_scanner_attribute_reads_retry_missing_records_individually(
    tmp_path: Path,
):
    app, _, target = await _make_basic_scan_target(tmp_path)
    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    await _seed_scan_progress(app, target)
    for attr_def, datatype in (
        (Basic.AttributeDefs.zcl_version, foundation.DataTypeId.uint8),
        (Basic.AttributeDefs.app_version, foundation.DataTypeId.uint8),
        (Basic.AttributeDefs.stack_version, foundation.DataTypeId.uint8),
        (Basic.AttributeDefs.hw_version, foundation.DataTypeId.uint8),
    ):
        await _seed_discovered_attribute(
            app,
            target,
            attr_id=attr_def.id,
            attribute_name=attr_def.name,
            datatype=datatype,
            access=foundation.AttributeAccessControl.READ,
        )

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer=None,
        **kwargs,
    ):
        assert manufacturer is None

        if list(attributes) == [0, 1, 2]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=0,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(1),
                        ),
                    ),
                    foundation.ReadAttributeRecord(
                        attrid=1,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(2),
                        ),
                    ),
                ]
            )

        if list(attributes) == [2]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=2,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(3),
                        ),
                    )
                ]
            )

        if list(attributes) == [3]:
            return read_rsp(
                status_records=[
                    foundation.ReadAttributeRecord(
                        attrid=3,
                        status=foundation.Status.SUCCESS,
                        value=foundation.TypeValue(
                            type=foundation.DataTypeId.uint8,
                            value=t.uint8_t(4),
                        ),
                    )
                ]
            )

        raise AssertionError(f"Unexpected attribute batch: {attributes!r}")

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    with patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()):
        await app.device_scanner._read_attributes_for_target(target)

    assert target.cluster.read_attributes_raw.await_args_list == [
        call([0, 1, 2], manufacturer=None),
        call([2], manufacturer=None),
        call([3], manufacturer=None),
    ]

    rows = await app._dblistener.get_device_scan_rows(target.endpoint.device.ieee)
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert progress.attr_reads_complete is True
    attrs = {row.attr_id: row for row in rows.attributes}
    assert attrs[0].read_status == "success"
    assert attrs[1].read_status == "success"
    assert attrs[2].read_status == "success"
    assert attrs[3].read_status == "success"

    await app.shutdown()


async def test_device_scanner_scan_ignores_unsupported_command_discovery_response(
    tmp_path: Path,
):
    app, dev, target, _ = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )
    cmd_tx_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Generated_rsp
    ].schema

    target.cluster.discover_commands_received = AsyncMock(
        return_value=(
            foundation.GeneralCommand.Default_Response,
            foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )
    target.cluster.discover_commands_generated = AsyncMock(
        return_value=cmd_tx_rsp(discovery_complete=True, command_ids=[0x00])
    )

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        summary = await app.device_scanner._run_scan_body(
            dev, resume=False, force_full=False
        )

    assert summary.outcome == "success"
    assert summary.error_code is None
    target.cluster.discover_commands_generated.assert_awaited_once()
    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert progress.cmd_rx_complete is True
    assert progress.cmd_tx_complete is True
    assert progress.last_error_code is None

    await app.shutdown()


async def test_device_scanner_scan_ignores_unsupported_command_discovery_default_response_object(
    tmp_path: Path,
):
    app, dev, target, _ = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )
    cmd_tx_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Generated_rsp
    ].schema

    target.cluster.discover_commands_received = AsyncMock(
        return_value=foundation.DefaultResponse(
            command_id=foundation.GeneralCommand.Discover_Commands_Received,
            status=foundation.Status.UNSUP_GENERAL_COMMAND,
        )
    )
    target.cluster.discover_commands_generated = AsyncMock(
        return_value=cmd_tx_rsp(discovery_complete=True, command_ids=[0x00])
    )

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        summary = await app.device_scanner._run_scan_body(
            dev, resume=False, force_full=False
        )

    assert summary.outcome == "success"
    assert summary.error_code is None
    target.cluster.discover_commands_generated.assert_awaited_once()
    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert progress.cmd_rx_complete is True
    assert progress.cmd_tx_complete is True
    assert progress.last_error_code is None

    await app.shutdown()


async def test_device_scanner_scan_treats_non_unsupported_command_discovery_default_response_as_terminal(
    tmp_path: Path,
):
    app, dev, target, _ = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )

    target.cluster.discover_commands_received = AsyncMock(
        return_value=(
            foundation.GeneralCommand.Default_Response,
            foundation.Status.FAILURE,
        )
    )
    target.cluster.discover_commands_generated = AsyncMock()

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        summary = await app.device_scanner._run_scan_body(
            dev, resume=False, force_full=False
        )

    assert summary.outcome == "partial"
    assert summary.error_code == "unsupported_discovery_command"
    assert "failure" in (summary.last_error or "").lower()
    target.cluster.discover_commands_generated.assert_not_awaited()
    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    progress = next(
        row
        for row in rows.progress
        if row.endpoint_id == target.endpoint_id
        and row.cluster_type == target.cluster.cluster_type
        and row.cluster_id == target.cluster.cluster_id
        and row.manufacturer_code_scope is None
    )
    assert progress.last_error_code == "unsupported_discovery_command"

    await app.shutdown()


async def test_device_scanner_scan_resume_skips_completed_steps_and_force_full_restarts(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )

    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=3,
        attr_reads_complete=True,
        cmd_rx_complete=True,
        cmd_rx_next_id=2,
        cmd_tx_complete=True,
        cmd_tx_next_id=1,
        last_started=1.0,
        last_finished=2.0,
        last_error_code=None,
        last_error=None,
        last_success=2.0,
    )

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
            create=True,
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ) as discover_attrs,
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ) as read_attrs,
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ) as discover_rx,
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ) as discover_tx,
    ):
        resume_summary = await app.device_scanner.scan(dev.ieee, resume=True)
        assert resume_summary.used_resume is True
        discover_attrs.assert_not_awaited()
        read_attrs.assert_not_awaited()
        discover_rx.assert_not_awaited()
        discover_tx.assert_not_awaited()

        force_summary = await app.device_scanner.scan(
            dev.ieee, resume=False, force_full=True
        )
        assert force_summary.force_full is True
        assert discover_attrs.await_count == 1
        assert read_attrs.await_count == 1
        assert discover_rx.await_count == 1
        assert discover_tx.await_count == 1

    await app.shutdown()


async def test_device_scanner_force_full_clears_existing_scan_rows_before_rerun(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )

    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=int(foundation.AttributeAccessControl.READ),
        read_complete=True,
        read_status="success",
        value=b"\x04",
    )

    async def check_rows_cleared(*args, **kwargs):
        rows = await app._dblistener.get_device_scan_rows(dev.ieee)
        assert rows.attributes == []

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(side_effect=check_rows_cleared),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ),
    ):
        await app.device_scanner.scan(dev.ieee, resume=False, force_full=True)

    await app.shutdown()


async def test_device_scanner_get_snapshot_raises_when_raw_rows_are_missing(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    ieee = t.EUI64.convert("aa:bb:cc:dd:11:22:33:55")

    with pytest.raises(zigpy.device_scanner.DeviceScanSnapshotNotFoundError):
        await app.device_scanner.get_snapshot(ieee)

    await app.shutdown()


async def test_device_scanner_scan_preserves_error_code_from_scan_failure(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:67"),
    )
    dev.node_desc = make_node_desc()
    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)
    await app._dblistener._save_device(dev)

    with patch.object(
        app.device_scanner,
        "_run_scan_body",
        new=AsyncMock(
            side_effect=zigpy.device_scanner._ScanFailure(
                "descriptor refresh failed",
                error_code=zigpy.device_scanner.ERROR_CODE_DESCRIPTOR_REFRESH_FAILED,
            )
        ),
    ):
        summary = await app.device_scanner.scan(dev.ieee)

    assert summary.outcome == "failed"
    assert summary.error_code == "descriptor_refresh_failed"
    assert summary.last_error == "descriptor refresh failed"

    await app.shutdown()


async def test_device_scanner_get_snapshot_returns_valid_empty_hierarchy(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:66"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=None)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)

    snapshot = await app.device_scanner.get_snapshot(dev.ieee)

    assert isinstance(snapshot, zigpy.device_scanner.DeviceScanSnapshot)
    assert snapshot.ieee == dev.ieee
    assert snapshot.raw_node_descriptor == dev.node_desc
    assert len(snapshot.endpoints) == 1

    endpoint = snapshot.endpoints[0]
    assert endpoint.endpoint_id == 1
    assert len(endpoint.clusters) == 1

    cluster = endpoint.clusters[0]
    assert cluster.cluster_id == Basic.cluster_id
    assert cluster.standard.progress.status == "pending"
    assert cluster.standard.attributes == []
    assert cluster.standard.commands == []
    assert cluster.manufacturer_specific.progress.status == "skipped"
    assert (
        cluster.manufacturer_specific.progress.error_code
        == "missing_raw_manufacturer_code"
    )
    assert cluster.manufacturer_specific.manufacturer_code is None

    await app.shutdown()


async def test_device_scanner_get_snapshot_skips_endpoint_242(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:67"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=0x1234)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    ep242 = dev.add_endpoint(242)
    ep242.status = zigpy.endpoint.Status.ZDO_INIT
    ep242.profile_id = 0xA1E0
    ep242.device_type = 0x0061
    ep242.add_output_cluster(0x0021)

    await app._dblistener._save_device(dev)

    snapshot = await app.device_scanner.get_snapshot(dev.ieee)

    assert [endpoint.endpoint_id for endpoint in snapshot.endpoints] == [1]

    await app.shutdown()


async def test_device_scanner_get_snapshot_exposes_raw_and_decoded_values_and_ordering(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)

    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=True,
        cmd_rx_complete=True,
        cmd_rx_next_id=1,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=2.0,
        last_finished=4.0,
        last_error_code=None,
        last_error=None,
        last_success=4.0,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name="zcl_version",
        datatype=foundation.DataTypeId.uint8,
        access=int(foundation.AttributeAccessControl.READ),
        read_complete=True,
        read_status="success",
        value=b"\x04",
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name="app_version",
        datatype=foundation.DataTypeId.uint8,
        access=int(foundation.AttributeAccessControl.READ),
        read_complete=True,
        read_status="unsupported_attribute",
        value=None,
        last_error_code="attribute_unsupported",
    )
    await app._dblistener.upsert_device_scan_command(
        ieee=dev.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=None,
        direction="received",
        command_id=1,
        command_name="reset_to_factory_defaults",
        command_schema=None,
        discovered_at=3.0,
    )

    snapshot = await app.device_scanner.get_snapshot(dev.ieee)

    cluster = snapshot.endpoints[0].clusters[0]
    attrs = cluster.standard.attributes
    assert [attr.attr_id for attr in attrs] == [
        Basic.AttributeDefs.zcl_version.id,
        Basic.AttributeDefs.app_version.id,
    ]
    assert attrs[0].datatype == foundation.DataTypeId.uint8
    assert attrs[0].raw_value == b"\x04"
    assert attrs[0].decoded_value == 4
    assert attrs[1].raw_value is None
    assert attrs[1].decoded_value is None
    assert attrs[1].last_error_code == "attribute_unsupported"
    assert cluster.standard.commands[0].direction == "received"
    assert snapshot.last_snapshot_at is not None

    await app.shutdown()


async def test_device_scanner_get_snapshot_uses_max_persisted_timestamp_and_skipped_scope_is_empty(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:aa"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=None)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)
    target = next(
        target
        for target in await app.device_scanner._build_raw_scan_targets(dev)
        if target.cluster.cluster_id == Basic.cluster_id
    )
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=1,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=2.0,
        last_finished=4.0,
        last_error_code=None,
        last_error=None,
        last_success=4.0,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name="zcl_version",
        datatype=foundation.DataTypeId.uint8,
        access=int(foundation.AttributeAccessControl.READ),
        read_complete=True,
        read_status="success",
        value=b"\x04",
    )

    snapshot = await app.device_scanner.get_snapshot(dev.ieee)

    assert snapshot.last_snapshot_at == datetime.fromtimestamp(4.0, UTC)
    skipped_scope = snapshot.endpoints[0].clusters[0].manufacturer_specific
    assert skipped_scope.attributes == []
    assert skipped_scope.commands == []

    await app.shutdown()


async def test_device_scanner_snapshot_marks_partial_discovery_as_started(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)

    with patch("zigpy.appdb.datetime") as datetime_mock:
        now = datetime(2026, 3, 15, tzinfo=UTC)
        datetime_mock.now.return_value = now
        datetime_mock.fromtimestamp.side_effect = datetime.fromtimestamp

        await app._dblistener.persist_device_scan_attribute_discovery_page(
            ieee=dev.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=None,
            attributes=[],
            next_attr_id=5,
            complete=False,
        )

    snapshot = await app.device_scanner.get_snapshot(dev.ieee)
    progress = snapshot.endpoints[0].clusters[0].standard.progress

    assert progress.status == "started"
    assert progress.last_finished == now
    assert progress.last_success == now
    assert snapshot.last_snapshot_at == now

    await app.shutdown()


async def test_device_scanner_resume_uses_stored_discovery_cursors(tmp_path: Path):
    app, dev, target, _ = await _make_onoff_scan_targets(tmp_path)
    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )

    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=False,
        attr_discovery_next_id=3,
        attr_reads_complete=True,
        cmd_rx_complete=False,
        cmd_rx_next_id=7,
        cmd_tx_complete=False,
        cmd_tx_next_id=9,
        last_started=1.0,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )

    discover_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Attribute_Extended_rsp
    ].schema
    cmd_rx_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Received_rsp
    ].schema
    cmd_tx_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Commands_Generated_rsp
    ].schema

    target.cluster.discover_attributes_extended = AsyncMock(
        return_value=discover_rsp(discovery_complete=True, extended_attr_info=[])
    )
    target.cluster.discover_commands_received = AsyncMock(
        return_value=cmd_rx_rsp(discovery_complete=True, command_ids=[])
    )
    target.cluster.discover_commands_generated = AsyncMock(
        return_value=cmd_tx_rsp(discovery_complete=True, command_ids=[])
    )

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        await app.device_scanner._run_scan_body(dev, resume=True, force_full=False)

    assert target.cluster.discover_attributes_extended.await_args_list[0].args == (
        3,
        16,
    )
    assert target.cluster.discover_commands_received.await_args_list[0].args == (7, 16)
    assert target.cluster.discover_commands_generated.await_args_list[0].args == (9, 16)

    await app.shutdown()


async def test_device_scanner_attribute_discovery_keeps_first_page_when_later_page_write_fails(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    discover_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Discover_Attribute_Extended_rsp
    ].schema
    target.cluster.discover_attributes_extended = AsyncMock(
        side_effect=[
            discover_rsp(
                discovery_complete=False,
                extended_attr_info=[
                    foundation.DiscoverAttributesExtendedResponseRecord(
                        attrid=0x0000,
                        datatype=foundation.DataTypeId.uint8,
                        acl=foundation.AttributeAccessControl.READ,
                    )
                ],
            ),
            discover_rsp(
                discovery_complete=True,
                extended_attr_info=[
                    foundation.DiscoverAttributesExtendedResponseRecord(
                        attrid=0x0001,
                        datatype=foundation.DataTypeId.uint8,
                        acl=foundation.AttributeAccessControl.READ,
                    )
                ],
            ),
        ]
    )

    original_persist = app._dblistener.persist_device_scan_attribute_discovery_page
    calls = 0

    async def persist_then_fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("page write failed")
        return await original_persist(*args, **kwargs)

    with patch.object(
        app._dblistener,
        "persist_device_scan_attribute_discovery_page",
        new=AsyncMock(side_effect=persist_then_fail),
    ):
        with pytest.raises(RuntimeError):
            await app.device_scanner._discover_attributes_for_target(target)

    rows = await app._dblistener.get_device_scan_rows(dev.ieee)
    assert [row.attr_id for row in rows.attributes] == [0x0000]
    assert rows.progress[0].attr_discovery_next_id == 1
    assert rows.progress[0].attr_discovery_complete is False

    await app.shutdown()


async def test_device_scanner_attribute_reads_do_not_requery_pending_rows_during_split_fallback(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    await app._dblistener.upsert_device_scan_progress(
        ieee=dev.ieee,
        endpoint_id=1,
        cluster_type=ClusterType.Server,
        cluster_id=Basic.cluster_id,
        manufacturer_code_scope=None,
        attr_discovery_complete=True,
        attr_discovery_next_id=2,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=None,
        last_finished=None,
        last_error_code=None,
        last_error=None,
        last_success=None,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.zcl_version.id,
        attribute_name=Basic.AttributeDefs.zcl_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )
    await _seed_discovered_attribute(
        app,
        target,
        attr_id=Basic.AttributeDefs.app_version.id,
        attribute_name=Basic.AttributeDefs.app_version.name,
        datatype=foundation.DataTypeId.uint8,
        access=foundation.AttributeAccessControl.READ,
    )

    read_rsp = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Read_Attributes_rsp
    ].schema

    async def read_attributes_raw(attributes, *args, manufacturer=None, **kwargs):
        if list(attributes) == [0, 1]:
            raise zigpy.exceptions.DeliveryError("boom")
        return read_rsp(
            status_records=[
                foundation.ReadAttributeRecord(
                    attrid=attributes[0],
                    status=foundation.Status.SUCCESS,
                    value=foundation.TypeValue(
                        type=foundation.DataTypeId.uint8,
                        value=t.uint8_t(4),
                    ),
                )
            ]
        )

    target.cluster.read_attributes_raw = AsyncMock(side_effect=read_attributes_raw)

    original_get_pending = app._dblistener.get_pending_device_scan_attributes

    with patch.object(
        app._dblistener,
        "get_pending_device_scan_attributes",
        new=AsyncMock(wraps=original_get_pending),
    ) as get_pending:
        await app.device_scanner._read_attributes_for_target(target)

    assert get_pending.await_count == 2

    await app.shutdown()


async def test_device_scanner_scan_emits_step_cardinality_and_missing_manufacturer_skip(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:77"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=None)

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)

    events = []

    class Listener:
        def scan_queued(self, event):
            events.append(("scan_queued", event))

        def scan_started(self, event):
            events.append(("scan_started", event))

        def step_started(self, event):
            events.append(("step_started", event))

        def step_finished(self, event):
            events.append(("step_finished", event))

        def scan_finished(self, event):
            events.append(("scan_finished", event))

    app.device_scanner.add_listener(Listener())

    async def mock_active_ep_req(nwk):
        return [zdo_t.Status.SUCCESS, None, [1]]

    async def mock_simple_desc_req(nwk, endpoint_id):
        sd = zdo_t.SimpleDescriptor()
        sd.endpoint = endpoint_id
        sd.profile = zha.PROFILE_ID
        sd.device_type = zha.DeviceType.PUMP
        sd.input_clusters = [Basic.cluster_id]
        sd.output_clusters = []
        return [zdo_t.Status.SUCCESS, None, sd]

    dev.zdo.Node_Desc_req = AsyncMock(
        return_value=(
            zdo_t.Status.SUCCESS,
            dev.nwk,
            make_node_desc(manufacturer_code=None),
        )
    )
    dev.zdo.Active_EP_req = AsyncMock(side_effect=mock_active_ep_req)
    dev.zdo.Simple_Desc_req = AsyncMock(side_effect=mock_simple_desc_req)

    with (
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ),
        patch.object(app.device_scanner, "_pace_requests", new=AsyncMock()),
    ):
        summary = await app.device_scanner.scan(dev.ieee, resume=False)

    assert [name for name, _ in events[:2]] == ["scan_queued", "scan_started"]
    assert events[-1][0] == "scan_finished"
    assert events[-1][1].outcome == "success"
    assert summary.outcome == "success"

    descriptor_events = [
        event for _, event in events if event.step == "descriptor_refresh"
    ]
    assert descriptor_events
    assert all(event.endpoint_id is None for event in descriptor_events)
    assert all(event.cluster_id is None for event in descriptor_events)

    attr_events = [event for _, event in events if event.step == "attribute_discovery"]
    assert any(
        event.status == "started"
        and event.endpoint_id == 1
        and event.scope_kind == "standard"
        for event in attr_events
    )
    assert any(
        event.status == "skipped"
        and event.error_code == "missing_raw_manufacturer_code"
        and event.scope_kind == "manufacturer_specific"
        and event.manufacturer_code_scope is None
        for event in attr_events
    )
    assert not any(
        event.status == "skipped" and event.scope_kind == "standard"
        for event in attr_events
    )

    await app.shutdown()


async def test_device_scanner_scan_ignores_live_manufacturer_override_when_raw_code_missing(
    tmp_path: Path,
):
    app = await make_app_with_db(tmp_path / "test.db")
    dev = app.add_device(
        nwk=0x1234,
        ieee=t.EUI64.convert("aa:bb:cc:dd:ee:ff:00:88"),
    )
    dev.node_desc = make_node_desc(manufacturer_code=None)
    dev.manufacturer_id_override = 0x9999

    ep1 = dev.add_endpoint(1)
    ep1.status = zigpy.endpoint.Status.ZDO_INIT
    ep1.profile_id = zha.PROFILE_ID
    ep1.device_type = zha.DeviceType.PUMP
    ep1.add_input_cluster(Basic.cluster_id)

    await app._dblistener._save_device(dev)

    raw_descriptors = zigpy.device_scanner._RawDeviceDescriptors(
        node_descriptor=dev.node_desc,
        endpoints=(),
    )
    target = next(
        target
        for target in await app.device_scanner._build_raw_scan_targets(dev)
        if target.cluster.cluster_id == Basic.cluster_id
    )
    events = []

    class Listener:
        def step_finished(self, event):
            events.append(event)

    app.device_scanner.add_listener(Listener())

    with (
        patch.object(
            app.device_scanner,
            "_refresh_raw_descriptors",
            new=AsyncMock(return_value=raw_descriptors),
        ),
        patch.object(
            app.device_scanner,
            "_build_scan_targets_for_node_descriptor",
            new=AsyncMock(return_value=(target,)),
        ),
        patch.object(
            app.device_scanner,
            "_discover_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_read_attributes_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_received_for_target",
            new=AsyncMock(),
        ),
        patch.object(
            app.device_scanner,
            "_discover_commands_generated_for_target",
            new=AsyncMock(),
        ),
    ):
        await app.device_scanner._run_scan_body(dev, resume=False, force_full=False)

    assert any(
        event.status == "skipped"
        and event.error_code == "missing_raw_manufacturer_code"
        and event.scope_kind == "manufacturer_specific"
        and event.manufacturer_code_scope is None
        for event in events
    )
    assert not any(
        event.status == "skipped" and event.scope_kind == "standard" for event in events
    )

    await app.shutdown()


async def test_device_scanner_load_progress_by_scope_uses_progress_rows_query(
    tmp_path: Path,
):
    app, dev, target = await _make_basic_scan_target(tmp_path)
    progress_row = zigpy.appdb.DeviceScanProgressRow(
        ieee=dev.ieee,
        endpoint_id=target.endpoint_id,
        cluster_type=target.cluster.cluster_type,
        cluster_id=target.cluster.cluster_id,
        manufacturer_code_scope=target.scope.manufacturer_code_scope,
        attr_discovery_complete=True,
        attr_discovery_next_id=1,
        attr_reads_complete=False,
        cmd_rx_complete=False,
        cmd_rx_next_id=0,
        cmd_tx_complete=False,
        cmd_tx_next_id=0,
        last_started=1.0,
        last_finished=2.0,
        last_error_code=None,
        last_error=None,
        last_success=2.0,
    )

    with (
        patch.object(
            app._dblistener,
            "get_device_scan_progress_rows",
            new=AsyncMock(return_value=[progress_row]),
        ) as get_progress_rows,
        patch.object(
            app._dblistener,
            "get_device_scan_rows",
            new=AsyncMock(side_effect=AssertionError("unexpected full row load")),
        ),
    ):
        progress_by_scope = await app.device_scanner._load_progress_by_scope(dev.ieee)

    assert progress_by_scope == {target.scope: progress_row}
    get_progress_rows.assert_awaited_once_with(dev.ieee)

    await app.shutdown()
