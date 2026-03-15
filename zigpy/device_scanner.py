from __future__ import annotations

import asyncio
import collections
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import functools
import logging
import typing

import zigpy.datastructures
import zigpy.device
import zigpy.endpoint
import zigpy.exceptions
import zigpy.profiles
import zigpy.types as t
import zigpy.util
import zigpy.zcl
from zigpy.zcl import ClusterType, foundation
import zigpy.zdo.types as zdo_t

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Mapping

    import zigpy.appdb
    import zigpy.application
    from zigpy.zcl import Cluster

    asyncio_timeout: typing.Callable[[float | None], asyncio.Timeout]
else:
    from asyncio import timeout as asyncio_timeout


LOGGER = logging.getLogger(__name__)


ScopeEventPayload: typing.TypeAlias = dict[str, int | ClusterType | None]
SnapshotRowValue: typing.TypeAlias = t.EUI64 | int | float | str | bytes | None
_DefaultResponseTuple: typing.TypeAlias = tuple[
    foundation.GeneralCommand, foundation.Status | int
]
_DefaultResponseResult: typing.TypeAlias = (
    foundation.DefaultResponse | _DefaultResponseTuple
)


class _AttributeValueDeserializer(typing.Protocol):
    @classmethod
    def deserialize(cls, data: bytes) -> tuple[object, bytes]: ...


class _StandardAttributeDiscoveryResponse(typing.Protocol):
    discovery_complete: bool
    attribute_info: list[foundation.DiscoverAttributesResponseRecord]


class _ExtendedAttributeDiscoveryResponse(typing.Protocol):
    discovery_complete: bool
    extended_attr_info: list[foundation.DiscoverAttributesExtendedResponseRecord]


_AttributeDiscoveryResponse: typing.TypeAlias = (
    _StandardAttributeDiscoveryResponse | _ExtendedAttributeDiscoveryResponse
)


class _CommandDiscoveryResponse(typing.Protocol):
    discovery_complete: bool
    command_ids: list[t.uint8_t]


class _ReadAttributesRawResponse(typing.Protocol):
    status_records: list[foundation.ReadAttributeRecord]


class _DiscoverCommandsCallable(typing.Protocol):
    def __call__(
        self,
        start_command_id: int,
        max_command_ids: int,
        *,
        manufacturer: int | None = None,
    ) -> Awaitable[_CommandDiscoveryResponse | _DefaultResponseResult]: ...


SCAN_EVENT_NAMES = (
    "scan_queued",
    "scan_started",
    "step_started",
    "step_finished",
    "scan_finished",
)

SCAN_EVENT_QUEUED = SCAN_EVENT_NAMES[0]
SCAN_EVENT_STARTED = SCAN_EVENT_NAMES[1]
SCAN_EVENT_STEP_STARTED = SCAN_EVENT_NAMES[2]
SCAN_EVENT_STEP_FINISHED = SCAN_EVENT_NAMES[3]
SCAN_EVENT_FINISHED = SCAN_EVENT_NAMES[4]

SCAN_STATUSES = (
    "queued",
    "started",
    "success",
    "failed",
    "skipped",
)

SCAN_STATUS_QUEUED = SCAN_STATUSES[0]
SCAN_STATUS_STARTED = SCAN_STATUSES[1]
SCAN_STATUS_SUCCESS = SCAN_STATUSES[2]
SCAN_STATUS_FAILED = SCAN_STATUSES[3]
SCAN_STATUS_SKIPPED = SCAN_STATUSES[4]

SCAN_OUTCOMES = (
    "success",
    "partial",
    "failed",
)

SCAN_OUTCOME_SUCCESS = SCAN_OUTCOMES[0]
SCAN_OUTCOME_PARTIAL = SCAN_OUTCOMES[1]
SCAN_OUTCOME_FAILED = SCAN_OUTCOMES[2]

SCAN_STEPS = (
    "descriptor_refresh",
    "attribute_discovery",
    "attribute_reads",
    "command_discovery_received",
    "command_discovery_generated",
)

SCAN_STEP_DESCRIPTOR_REFRESH = SCAN_STEPS[0]

STEP_STATUSES = SCAN_STATUSES

SCAN_ERROR_CODES = (
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

ERROR_CODE_INVALID_SCAN_OPTIONS = SCAN_ERROR_CODES[0]
ERROR_CODE_SCAN_IN_PROGRESS = SCAN_ERROR_CODES[1]
ERROR_CODE_DEVICE_SCAN_TARGET_MISSING = SCAN_ERROR_CODES[2]
ERROR_CODE_DESCRIPTOR_REFRESH_FAILED = SCAN_ERROR_CODES[3]
ERROR_CODE_SCAN_DEADLINE_EXCEEDED = SCAN_ERROR_CODES[4]
ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND = SCAN_ERROR_CODES[5]
ERROR_CODE_TRANSPORT_FAILURE = SCAN_ERROR_CODES[6]
ERROR_CODE_ATTRIBUTE_UNSUPPORTED = SCAN_ERROR_CODES[7]
ERROR_CODE_MISSING_RAW_MANUFACTURER_CODE = SCAN_ERROR_CODES[8]

REQUEST_PACING_DELAY_S = 0.01
SCAN_DEADLINE_S = 120.0
ATTRIBUTE_DISCOVERY_PAGE_SIZE = 16
ATTRIBUTE_READ_BATCH_SIZE = 3
ATTRIBUTE_READ_RETRY_BACKOFF_S = 0.05
COMMAND_DISCOVERY_RETRY_BACKOFF_S = 0.05
UTC_TZ = timezone(timedelta(0))

ATTRIBUTE_READ_STATUS_SUCCESS = "success"
ATTRIBUTE_READ_STATUS_UNSUPPORTED = "unsupported_attribute"
ATTRIBUTE_READ_STATUS_TRANSPORT_FAILURE = "transport_failure"

COMMAND_DISCOVERY_DIRECTION_RECEIVED = "received"
COMMAND_DISCOVERY_DIRECTION_GENERATED = "generated"


class InvalidScanOptionsError(ValueError):
    """Raised when scan options are invalid."""


class ScanInProgressError(RuntimeError):
    """Raised when a conflicting scan is already queued or running."""


class DeviceScanTargetMissingError(LookupError):
    """Raised when a queued scan target no longer exists at execution time."""


class DeviceScanSnapshotNotFoundError(LookupError):
    """Raised when no persisted raw rows exist for a snapshot read."""


@dataclass(frozen=True, slots=True)
class DeviceScanSummary:
    ieee: t.EUI64
    completed: bool
    outcome: str
    used_resume: bool
    force_full: bool
    descriptor_refresh_performed: bool
    last_finished: datetime | None
    error_code: str | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshot:
    ieee: t.EUI64
    raw_node_descriptor: zdo_t.NodeDescriptor | None
    last_snapshot_at: datetime | None
    endpoints: list[DeviceScanSnapshotEndpoint]


@dataclass(frozen=True, slots=True)
class DeviceScanProgressEvent:
    ieee: t.EUI64
    status: str
    outcome: str | None = None
    step: str | None = None
    endpoint_id: int | None = None
    cluster_id: int | None = None
    cluster_type: ClusterType | None = None
    manufacturer_code_scope: int | None = None
    error_code: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshotCommand:
    direction: str
    command_id: int
    command_name: str | None
    command_schema: str | None


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshotAttribute:
    attr_id: int
    attribute_name: str | None
    datatype: int | None
    raw_value: bytes | None
    decoded_value: object
    read_complete: bool
    read_status: str | None
    last_error_code: str | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshotProgress:
    status: str
    error_code: str | None
    error: str | None
    last_started: datetime | None
    last_finished: datetime | None
    last_success: datetime | None
    attr_discovery_complete: bool
    attr_discovery_next_id: int
    attr_reads_complete: bool
    cmd_rx_complete: bool
    cmd_rx_next_id: int
    cmd_tx_complete: bool
    cmd_tx_next_id: int


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshotScope:
    manufacturer_code: int | None
    progress: DeviceScanSnapshotProgress
    attributes: list[DeviceScanSnapshotAttribute]
    commands: list[DeviceScanSnapshotCommand]


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshotCluster:
    cluster_id: int
    cluster_type: ClusterType
    standard: DeviceScanSnapshotScope
    manufacturer_specific: DeviceScanSnapshotScope


@dataclass(frozen=True, slots=True)
class DeviceScanSnapshotEndpoint:
    endpoint_id: int
    profile_id: int
    device_type: int | None
    status: int
    clusters: list[DeviceScanSnapshotCluster]


@dataclass(frozen=True, slots=True)
class _RawDeviceDescriptors:
    node_descriptor: zdo_t.NodeDescriptor
    endpoints: tuple[zigpy.endpoint.DiscoveredEndpointDescriptor, ...]


@dataclass(frozen=True, slots=True)
class _ScanScopeKey:
    endpoint_id: int
    cluster_type: ClusterType
    cluster_id: int
    manufacturer_code_scope: int | None = None


@dataclass(frozen=True, slots=True)
class _RawScanTarget:
    endpoint: zigpy.endpoint.Endpoint
    cluster: Cluster
    scope: _ScanScopeKey

    @property
    def endpoint_id(self) -> int:
        return self.scope.endpoint_id


@dataclass(slots=True)
class _SharedScanRequest:
    ieee: t.EUI64
    resume: bool
    force_full: bool
    task: asyncio.Task[DeviceScanSummary] | None = None


class _ScanFailure(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None):
        super().__init__(message)
        self.error_code = error_code


class _TerminalStepFailure(_ScanFailure):
    """A known scope-local failure that should not abort the whole scan."""


@dataclass(frozen=True, slots=True)
class _StepResult:
    status: str
    error_code: str | None = None
    error: str | None = None


class DeviceScanner(zigpy.util.ListenableMixin):
    """On-demand raw device scan service."""

    def __init__(self, app: zigpy.application.ControllerApplication) -> None:
        super().__init__()
        self._app = app
        self._active_scans: dict[t.EUI64, _SharedScanRequest] = {}
        self._scan_slot_limiter = zigpy.datastructures.RequestLimiter(
            max_concurrency=1, capacities={0: 1}
        )
        self._current_scan_deadline: asyncio.Timeout | None = None

    def _emit_progress(self, event_name: str, **payload) -> DeviceScanProgressEvent:
        if event_name not in SCAN_EVENT_NAMES:
            raise ValueError(f"Unknown device scan event name: {event_name!r}")

        status = payload.get("status")
        if status not in SCAN_STATUSES:
            raise ValueError(f"Unknown device scan status: {status!r}")

        outcome = payload.get("outcome")
        if outcome is not None and outcome not in SCAN_OUTCOMES:
            raise ValueError(f"Unknown device scan outcome: {outcome!r}")

        error_code = payload.get("error_code")
        if error_code is not None and error_code not in SCAN_ERROR_CODES:
            raise ValueError(f"Unknown device scan error code: {error_code!r}")

        event = DeviceScanProgressEvent(**payload)
        self.listener_event(event_name, event)
        return event

    def _get_dblistener(self) -> zigpy.appdb.PersistingListener:
        dblistener = self._app._dblistener
        if dblistener is None:
            raise RuntimeError(
                "DeviceScanner requires an initialized database listener"
            )
        return dblistener

    def _scan_deadline_expired(self) -> bool:
        return bool(
            self._current_scan_deadline is not None
            and self._current_scan_deadline.expired()
        )

    async def _noop_action(self) -> None:
        await asyncio.sleep(0)

    async def scan(
        self,
        ieee: t.EUI64,
        *,
        resume: bool = True,
        force_full: bool = False,
    ) -> DeviceScanSummary:
        if resume and force_full:
            raise InvalidScanOptionsError(
                "resume=True and force_full=True is invalid "
                f"({ERROR_CODE_INVALID_SCAN_OPTIONS})"
            )
        existing = self._active_scans.get(ieee)
        if existing is not None:
            if existing.resume == resume and existing.force_full == force_full:
                existing_task = existing.task
                if existing_task is None:
                    raise RuntimeError("Active device scan request is missing its task")
                return await asyncio.shield(existing_task)

            raise ScanInProgressError(
                f"Conflicting scan already queued or running ({ERROR_CODE_SCAN_IN_PROGRESS})"
            )

        request = _SharedScanRequest(ieee=ieee, resume=resume, force_full=force_full)
        self._active_scans[ieee] = request
        self._emit_progress(
            SCAN_EVENT_QUEUED,
            ieee=ieee,
            status=SCAN_STATUS_QUEUED,
        )

        task = self._app.create_task(
            self._run_shared_scan(request),
            name=f"device-scanner:{ieee}",
        )
        request.task = task

        def _remove_active_scan(_task: asyncio.Task[DeviceScanSummary]) -> None:
            self._active_scans.pop(ieee, None)

        task.add_done_callback(_remove_active_scan)

        return await asyncio.shield(task)

    async def get_snapshot(self, ieee: t.EUI64) -> DeviceScanSnapshot:
        dblistener = self._get_dblistener()
        topology = await dblistener.get_raw_topology_rows(ieee)

        if (
            topology.node_descriptor is None
            and not topology.endpoints
            and not topology.clusters
        ):
            raise DeviceScanSnapshotNotFoundError(
                f"No persisted raw descriptor rows for {ieee}"
            )

        rows = await dblistener.get_device_scan_rows(ieee)
        return self._assemble_snapshot(ieee, topology, rows)

    def _scope_event_payload(self, target: _RawScanTarget) -> ScopeEventPayload:
        return {
            "endpoint_id": target.scope.endpoint_id,
            "cluster_id": target.scope.cluster_id,
            "cluster_type": target.scope.cluster_type,
            "manufacturer_code_scope": target.scope.manufacturer_code_scope,
        }

    def _progress_row_key(
        self,
        row: (
            zigpy.appdb.DeviceScanProgressRow
            | zigpy.appdb.DeviceScanAttributeRow
            | zigpy.appdb.DeviceScanCommandRow
        ),
    ) -> _ScanScopeKey:
        return _ScanScopeKey(
            endpoint_id=row.endpoint_id,
            cluster_type=ClusterType(row.cluster_type),
            cluster_id=row.cluster_id,
            manufacturer_code_scope=row.manufacturer_code_scope,
        )

    async def _load_progress_by_scope(
        self, ieee: t.EUI64
    ) -> dict[_ScanScopeKey, zigpy.appdb.DeviceScanProgressRow]:
        rows = await self._get_dblistener().get_device_scan_rows(ieee)
        return {self._progress_row_key(row): row for row in rows.progress}

    def _rows_snapshot(
        self, rows: zigpy.appdb.DeviceScanRows
    ) -> set[tuple[str, tuple[SnapshotRowValue, ...]]]:
        return (
            {("progress", tuple(row)) for row in rows.progress}
            | {("attribute", tuple(row)) for row in rows.attributes}
            | {("command", tuple(row)) for row in rows.commands}
        )

    def _scan_rows_have_new_commits(
        self,
        before: zigpy.appdb.DeviceScanRows,
        after: zigpy.appdb.DeviceScanRows,
    ) -> bool:
        return bool(self._rows_snapshot(after) - self._rows_snapshot(before))

    async def _run_shared_scan(self, request: _SharedScanRequest) -> DeviceScanSummary:
        dblistener = self._get_dblistener()
        before_rows = await dblistener.get_device_scan_rows(request.ieee)

        async with self._scan_slot_limiter(priority=0):
            try:
                device = self._app.get_device(ieee=request.ieee)
            except KeyError as exc:
                error = DeviceScanTargetMissingError(
                    f"Queued scan target disappeared before execution ({ERROR_CODE_DEVICE_SCAN_TARGET_MISSING})"
                )
                self._emit_progress(
                    SCAN_EVENT_FINISHED,
                    ieee=request.ieee,
                    status=SCAN_STATUS_FAILED,
                    outcome=SCAN_OUTCOME_FAILED,
                    error_code=ERROR_CODE_DEVICE_SCAN_TARGET_MISSING,
                    error=str(error),
                )
                raise error from exc

            self._emit_progress(
                SCAN_EVENT_STARTED,
                ieee=device.ieee,
                status=SCAN_STATUS_STARTED,
            )

            deadline = asyncio_timeout(SCAN_DEADLINE_S)
            self._current_scan_deadline = deadline

            try:
                try:
                    async with deadline:
                        summary = await self._run_scan_body(
                            device,
                            resume=request.resume,
                            force_full=request.force_full,
                        )
                except TimeoutError:
                    if not deadline.expired():
                        raise

                    after_rows = await dblistener.get_device_scan_rows(device.ieee)
                    outcome = (
                        SCAN_OUTCOME_PARTIAL
                        if self._scan_rows_have_new_commits(before_rows, after_rows)
                        else SCAN_OUTCOME_FAILED
                    )
                    summary = DeviceScanSummary(
                        ieee=device.ieee,
                        completed=True,
                        outcome=outcome,
                        used_resume=request.resume,
                        force_full=request.force_full,
                        descriptor_refresh_performed=True,
                        last_finished=datetime.now(UTC_TZ),
                        error_code=ERROR_CODE_SCAN_DEADLINE_EXCEEDED,
                        last_error="scan deadline exceeded",
                    )
                except _ScanFailure as exc:
                    summary = DeviceScanSummary(
                        ieee=device.ieee,
                        completed=True,
                        outcome=SCAN_OUTCOME_FAILED,
                        used_resume=request.resume,
                        force_full=request.force_full,
                        descriptor_refresh_performed=True,
                        last_finished=datetime.now(UTC_TZ),
                        error_code=exc.error_code,
                        last_error=str(exc),
                    )
                except Exception as exc:  # noqa: BLE001
                    summary = DeviceScanSummary(
                        ieee=device.ieee,
                        completed=True,
                        outcome=SCAN_OUTCOME_FAILED,
                        used_resume=request.resume,
                        force_full=request.force_full,
                        descriptor_refresh_performed=True,
                        last_finished=datetime.now(UTC_TZ),
                        error_code=getattr(exc, "device_scan_error_code", None),
                        last_error=str(exc),
                    )
            finally:
                if self._current_scan_deadline is deadline:
                    self._current_scan_deadline = None
            self._emit_progress(
                SCAN_EVENT_FINISHED,
                ieee=summary.ieee,
                status=(
                    SCAN_STATUS_SUCCESS
                    if summary.outcome == SCAN_OUTCOME_SUCCESS
                    else SCAN_STATUS_FAILED
                ),
                outcome=summary.outcome,
                error_code=summary.error_code,
                error=summary.last_error,
            )
            return summary

    async def _run_scope_step(
        self,
        target: _RawScanTarget,
        *,
        step: str,
        action: typing.Callable[[], typing.Awaitable[None]],
        skipped: bool = False,
        error_code: str | None = None,
    ) -> _StepResult:
        payload = self._scope_event_payload(target)

        if skipped:
            self._emit_progress(
                SCAN_EVENT_STEP_FINISHED,
                ieee=target.endpoint.device.ieee,
                status=SCAN_STATUS_SKIPPED,
                step=step,
                error_code=error_code,
                **payload,
            )
            return _StepResult(status=SCAN_STATUS_SKIPPED, error_code=error_code)

        self._emit_progress(
            SCAN_EVENT_STEP_STARTED,
            ieee=target.endpoint.device.ieee,
            status=SCAN_STATUS_STARTED,
            step=step,
            **payload,
        )

        try:
            await action()
        except _TerminalStepFailure as exc:
            await self._get_dblistener().set_device_scan_progress_error(
                ieee=target.endpoint.device.ieee,
                endpoint_id=target.endpoint_id,
                cluster_type=target.cluster.cluster_type,
                cluster_id=target.cluster.cluster_id,
                manufacturer_code_scope=target.scope.manufacturer_code_scope,
                error_code=exc.error_code or ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND,
                error=str(exc),
            )
            self._emit_progress(
                SCAN_EVENT_STEP_FINISHED,
                ieee=target.endpoint.device.ieee,
                status=SCAN_STATUS_FAILED,
                step=step,
                error_code=exc.error_code,
                error=str(exc),
                **payload,
            )
            return _StepResult(
                status=SCAN_STATUS_FAILED,
                error_code=exc.error_code,
                error=str(exc),
            )
        except TimeoutError as exc:
            if self._scan_deadline_expired():
                raise

            error = str(exc) or "request timed out"
            await self._get_dblistener().set_device_scan_progress_error(
                ieee=target.endpoint.device.ieee,
                endpoint_id=target.endpoint_id,
                cluster_type=target.cluster.cluster_type,
                cluster_id=target.cluster.cluster_id,
                manufacturer_code_scope=target.scope.manufacturer_code_scope,
                error_code=ERROR_CODE_TRANSPORT_FAILURE,
                error=error,
            )
            self._emit_progress(
                SCAN_EVENT_STEP_FINISHED,
                ieee=target.endpoint.device.ieee,
                status=SCAN_STATUS_FAILED,
                step=step,
                error_code=ERROR_CODE_TRANSPORT_FAILURE,
                error=error,
                **payload,
            )
            return _StepResult(
                status=SCAN_STATUS_FAILED,
                error_code=ERROR_CODE_TRANSPORT_FAILURE,
                error=error,
            )
        except Exception as exc:  # noqa: BLE001
            self._emit_progress(
                SCAN_EVENT_STEP_FINISHED,
                ieee=target.endpoint.device.ieee,
                status=SCAN_STATUS_FAILED,
                step=step,
                error=str(exc),
                **payload,
            )
            raise

        self._emit_progress(
            SCAN_EVENT_STEP_FINISHED,
            ieee=target.endpoint.device.ieee,
            status=SCAN_STATUS_SUCCESS,
            step=step,
            **payload,
        )
        return _StepResult(status=SCAN_STATUS_SUCCESS)

    async def _build_scan_targets_for_node_descriptor(
        self,
        device: zigpy.device.Device,
        node_descriptor: zdo_t.NodeDescriptor,
    ) -> tuple[_RawScanTarget, ...]:
        raw_targets = await self._build_raw_scan_targets(device)
        targets = list(raw_targets)

        if node_descriptor.manufacturer_code is not None:
            targets.extend(
                _RawScanTarget(
                    endpoint=target.endpoint,
                    cluster=target.cluster,
                    scope=_ScanScopeKey(
                        endpoint_id=target.scope.endpoint_id,
                        cluster_type=target.scope.cluster_type,
                        cluster_id=target.scope.cluster_id,
                        manufacturer_code_scope=node_descriptor.manufacturer_code,
                    ),
                )
                for target in raw_targets
            )

        return tuple(targets)

    async def _run_scan_body(
        self,
        device: zigpy.device.Device,
        *,
        resume: bool,
        force_full: bool,
    ) -> DeviceScanSummary:
        dblistener = self._get_dblistener()

        if force_full:
            await dblistener.clear_device_scan_data(device.ieee)

        raw_descriptors = await self._refresh_raw_descriptors(device)
        targets = await self._build_scan_targets_for_node_descriptor(
            device, raw_descriptors.node_descriptor
        )
        has_manufacturer_scope = (
            raw_descriptors.node_descriptor.manufacturer_code is not None
        )
        progress_by_scope = await self._load_progress_by_scope(device.ieee)
        outcome = SCAN_OUTCOME_SUCCESS
        summary_error_code: str | None = None
        summary_error: str | None = None

        def record_scope_failure(step_result: _StepResult) -> None:
            nonlocal outcome, summary_error_code, summary_error

            if step_result.status != SCAN_STATUS_FAILED:
                return

            outcome = SCAN_OUTCOME_PARTIAL
            if summary_error_code is None:
                summary_error_code = step_result.error_code
            if summary_error is None:
                summary_error = step_result.error

        for target in targets:
            progress = progress_by_scope.get(target.scope)
            attr_start_id = (
                0
                if progress is None or not resume or progress.attr_discovery_complete
                else progress.attr_discovery_next_id
            )
            cmd_rx_start_id = (
                0
                if progress is None or not resume or progress.cmd_rx_complete
                else progress.cmd_rx_next_id
            )
            cmd_tx_start_id = (
                0
                if progress is None or not resume or progress.cmd_tx_complete
                else progress.cmd_tx_next_id
            )
            scope_terminal_failure = False

            attr_discovery_result = await self._run_scope_step(
                target,
                step=SCAN_STEPS[1],
                skipped=bool(resume and progress and progress.attr_discovery_complete),
                action=functools.partial(
                    self._discover_attributes_for_target,
                    target,
                    start_attr_id=attr_start_id,
                ),
            )
            record_scope_failure(attr_discovery_result)
            scope_terminal_failure = attr_discovery_result.status == SCAN_STATUS_FAILED

            if not scope_terminal_failure:
                progress_by_scope = await self._load_progress_by_scope(device.ieee)
                progress = progress_by_scope.get(target.scope)

                attr_reads_result = await self._run_scope_step(
                    target,
                    step=SCAN_STEPS[2],
                    skipped=bool(resume and progress and progress.attr_reads_complete),
                    action=functools.partial(self._read_attributes_for_target, target),
                )
                record_scope_failure(attr_reads_result)

                progress_by_scope = await self._load_progress_by_scope(device.ieee)
                progress = progress_by_scope.get(target.scope)

                cmd_rx_result = await self._run_scope_step(
                    target,
                    step=SCAN_STEPS[3],
                    skipped=bool(resume and progress and progress.cmd_rx_complete),
                    action=functools.partial(
                        self._discover_commands_received_for_target,
                        target,
                        start_command_id=cmd_rx_start_id,
                    ),
                )
                record_scope_failure(cmd_rx_result)
                scope_terminal_failure = cmd_rx_result.status == SCAN_STATUS_FAILED

            if not scope_terminal_failure:
                progress_by_scope = await self._load_progress_by_scope(device.ieee)
                progress = progress_by_scope.get(target.scope)

                cmd_tx_result = await self._run_scope_step(
                    target,
                    step=SCAN_STEPS[4],
                    skipped=bool(resume and progress and progress.cmd_tx_complete),
                    action=functools.partial(
                        self._discover_commands_generated_for_target,
                        target,
                        start_command_id=cmd_tx_start_id,
                    ),
                )
                record_scope_failure(cmd_tx_result)

            if (
                not has_manufacturer_scope
                and target.scope.manufacturer_code_scope is None
            ):
                for step in SCAN_STEPS[1:]:
                    await self._run_scope_step(
                        target,
                        step=step,
                        skipped=True,
                        error_code=ERROR_CODE_MISSING_RAW_MANUFACTURER_CODE,
                        action=self._noop_action,
                    )

        return DeviceScanSummary(
            ieee=device.ieee,
            completed=True,
            outcome=outcome,
            used_resume=resume,
            force_full=force_full,
            descriptor_refresh_performed=True,
            last_finished=datetime.now(UTC_TZ),
            error_code=summary_error_code,
            last_error=summary_error,
        )

    def _to_datetime(self, timestamp: float | None) -> datetime | None:
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp, UTC_TZ)

    def _decode_attribute_value(
        self,
        *,
        datatype: int | None,
        raw_value: bytes | None,
        decode_cache: dict[int, type[_AttributeValueDeserializer]],
    ) -> object:
        if datatype is None or raw_value is None:
            return None

        try:
            python_type = decode_cache.get(datatype)
            if python_type is None:
                python_type = foundation.DataType.from_type_id(
                    foundation.DataTypeId(datatype)
                ).python_type
                decode_cache[datatype] = python_type

            value, _ = python_type.deserialize(raw_value)
            return int(value) if isinstance(value, int) else value
        except Exception:  # noqa: BLE001
            return None

    def _make_snapshot_progress(
        self,
        row: zigpy.appdb.DeviceScanProgressRow | None,
        *,
        synthetic_skipped: bool,
    ) -> DeviceScanSnapshotProgress:
        if synthetic_skipped:
            return DeviceScanSnapshotProgress(
                status="skipped",
                error_code=ERROR_CODE_MISSING_RAW_MANUFACTURER_CODE,
                error=None,
                last_started=None,
                last_finished=None,
                last_success=None,
                attr_discovery_complete=False,
                attr_discovery_next_id=0,
                attr_reads_complete=False,
                cmd_rx_complete=False,
                cmd_rx_next_id=0,
                cmd_tx_complete=False,
                cmd_tx_next_id=0,
            )

        if row is None:
            return DeviceScanSnapshotProgress(
                status="pending",
                error_code=None,
                error=None,
                last_started=None,
                last_finished=None,
                last_success=None,
                attr_discovery_complete=False,
                attr_discovery_next_id=0,
                attr_reads_complete=False,
                cmd_rx_complete=False,
                cmd_rx_next_id=0,
                cmd_tx_complete=False,
                cmd_tx_next_id=0,
            )

        if (
            row.attr_discovery_complete
            and row.attr_reads_complete
            and row.cmd_rx_complete
            and row.cmd_tx_complete
        ):
            status = "success"
        elif row.last_error_code is not None:
            status = "failed"
        elif row.last_started is not None or row.last_finished is not None:
            status = "started"
        else:
            status = "pending"

        return DeviceScanSnapshotProgress(
            status=status,
            error_code=row.last_error_code,
            error=row.last_error,
            last_started=self._to_datetime(row.last_started),
            last_finished=self._to_datetime(row.last_finished),
            last_success=self._to_datetime(row.last_success),
            attr_discovery_complete=row.attr_discovery_complete,
            attr_discovery_next_id=row.attr_discovery_next_id,
            attr_reads_complete=row.attr_reads_complete,
            cmd_rx_complete=row.cmd_rx_complete,
            cmd_rx_next_id=row.cmd_rx_next_id,
            cmd_tx_complete=row.cmd_tx_complete,
            cmd_tx_next_id=row.cmd_tx_next_id,
        )

    def _assemble_snapshot(
        self,
        ieee: t.EUI64,
        topology: zigpy.appdb.RawTopologyRows,
        rows: zigpy.appdb.DeviceScanRows,
    ) -> DeviceScanSnapshot:
        progress_by_scope = {self._progress_row_key(row): row for row in rows.progress}
        attrs_by_scope: dict[_ScanScopeKey, list[DeviceScanSnapshotAttribute]] = (
            collections.defaultdict(list)
        )
        commands_by_scope: dict[_ScanScopeKey, list[DeviceScanSnapshotCommand]] = (
            collections.defaultdict(list)
        )
        decode_cache: dict[int, type[_AttributeValueDeserializer]] = {}
        timestamps: list[float] = []

        for row in rows.progress:
            timestamps.extend(
                ts
                for ts in (row.last_started, row.last_finished, row.last_success)
                if ts is not None
            )

        for attribute_row in rows.attributes:
            attrs_by_scope[self._progress_row_key(attribute_row)].append(
                DeviceScanSnapshotAttribute(
                    attr_id=attribute_row.attr_id,
                    attribute_name=attribute_row.attribute_name,
                    datatype=attribute_row.datatype,
                    raw_value=attribute_row.value,
                    decoded_value=self._decode_attribute_value(
                        datatype=attribute_row.datatype,
                        raw_value=attribute_row.value,
                        decode_cache=decode_cache,
                    ),
                    read_complete=attribute_row.read_complete,
                    read_status=attribute_row.read_status,
                    last_error_code=attribute_row.last_error_code,
                    last_error=attribute_row.last_error,
                )
            )
            timestamps.extend(
                ts
                for ts in (attribute_row.discovered_at, attribute_row.last_read)
                if ts is not None
            )

        for command_row in rows.commands:
            commands_by_scope[self._progress_row_key(command_row)].append(
                DeviceScanSnapshotCommand(
                    direction=command_row.direction,
                    command_id=command_row.command_id,
                    command_name=command_row.command_name,
                    command_schema=command_row.command_schema,
                )
            )
            timestamps.append(command_row.discovered_at)

        clusters_by_endpoint: dict[int, list[zigpy.appdb.RawClusterRow]] = (
            collections.defaultdict(list)
        )
        for cluster_row in topology.clusters:
            clusters_by_endpoint[cluster_row.endpoint_id].append(cluster_row)

        endpoints: list[DeviceScanSnapshotEndpoint] = []
        manufacturer_code = (
            None
            if topology.node_descriptor is None
            else topology.node_descriptor.manufacturer_code
        )

        for endpoint_row in topology.endpoints:
            if endpoint_row.endpoint_id in (0, 242):
                continue

            clusters: list[DeviceScanSnapshotCluster] = []
            for cluster_row in clusters_by_endpoint.get(endpoint_row.endpoint_id, ()):
                cluster_type = ClusterType(cluster_row.cluster_type)
                standard_scope_key = _ScanScopeKey(
                    endpoint_id=endpoint_row.endpoint_id,
                    cluster_type=cluster_type,
                    cluster_id=cluster_row.cluster_id,
                    manufacturer_code_scope=None,
                )
                manufacturer_scope_key = _ScanScopeKey(
                    endpoint_id=endpoint_row.endpoint_id,
                    cluster_type=cluster_type,
                    cluster_id=cluster_row.cluster_id,
                    manufacturer_code_scope=manufacturer_code,
                )
                synthetic_skipped = manufacturer_code is None

                clusters.append(
                    DeviceScanSnapshotCluster(
                        cluster_id=cluster_row.cluster_id,
                        cluster_type=cluster_type,
                        standard=DeviceScanSnapshotScope(
                            manufacturer_code=None,
                            progress=self._make_snapshot_progress(
                                progress_by_scope.get(standard_scope_key),
                                synthetic_skipped=False,
                            ),
                            attributes=attrs_by_scope.get(standard_scope_key, []),
                            commands=commands_by_scope.get(standard_scope_key, []),
                        ),
                        manufacturer_specific=DeviceScanSnapshotScope(
                            manufacturer_code=manufacturer_code,
                            progress=self._make_snapshot_progress(
                                progress_by_scope.get(manufacturer_scope_key),
                                synthetic_skipped=synthetic_skipped,
                            ),
                            attributes=(
                                []
                                if synthetic_skipped
                                else attrs_by_scope.get(manufacturer_scope_key, [])
                            ),
                            commands=(
                                []
                                if synthetic_skipped
                                else commands_by_scope.get(manufacturer_scope_key, [])
                            ),
                        ),
                    )
                )

            endpoints.append(
                DeviceScanSnapshotEndpoint(
                    endpoint_id=endpoint_row.endpoint_id,
                    profile_id=endpoint_row.profile_id,
                    device_type=self._coerce_device_type(
                        endpoint_row.profile_id, endpoint_row.device_type
                    ),
                    status=endpoint_row.status,
                    clusters=clusters,
                )
            )

        last_snapshot_at = (
            None if not timestamps else self._to_datetime(max(timestamps))
        )

        return DeviceScanSnapshot(
            ieee=ieee,
            raw_node_descriptor=topology.node_descriptor,
            last_snapshot_at=last_snapshot_at,
            endpoints=endpoints,
        )

    async def _pace_requests(self) -> None:
        await asyncio.sleep(REQUEST_PACING_DELAY_S)

    async def _discover_raw_descriptors(
        self, device: zigpy.device.Device
    ) -> _RawDeviceDescriptors:
        node_descriptor = await device.discover_node_descriptor(refresh=True)
        await self._pace_requests()

        endpoint_ids = await device.discover_active_endpoints(refresh=True)
        await self._pace_requests()

        endpoints = []

        for endpoint_id in endpoint_ids:
            ephemeral_endpoint = zigpy.endpoint.Endpoint(device, endpoint_id)
            endpoints.append(await ephemeral_endpoint.discover_descriptor(refresh=True))
            await self._pace_requests()

        return _RawDeviceDescriptors(
            node_descriptor=node_descriptor,
            endpoints=tuple(endpoints),
        )

    async def _refresh_raw_descriptors(
        self, device: zigpy.device.Device
    ) -> _RawDeviceDescriptors:
        self._emit_progress(
            SCAN_EVENT_STEP_STARTED,
            ieee=device.ieee,
            status=SCAN_STATUS_STARTED,
            step=SCAN_STEP_DESCRIPTOR_REFRESH,
        )

        try:
            raw_descriptors = await self._discover_raw_descriptors(device)
            await self._get_dblistener().replace_device_raw_descriptors(
                device,
                node_descriptor=raw_descriptors.node_descriptor,
                endpoints=raw_descriptors.endpoints,
            )
        except Exception as exc:  # noqa: BLE001
            setattr(exc, "device_scan_error_code", ERROR_CODE_DESCRIPTOR_REFRESH_FAILED)
            self._emit_progress(
                SCAN_EVENT_STEP_FINISHED,
                ieee=device.ieee,
                status=SCAN_STATUS_FAILED,
                step=SCAN_STEP_DESCRIPTOR_REFRESH,
                error_code=ERROR_CODE_DESCRIPTOR_REFRESH_FAILED,
                error=str(exc),
            )
            raise

        self._emit_progress(
            SCAN_EVENT_STEP_FINISHED,
            ieee=device.ieee,
            status=SCAN_STATUS_SUCCESS,
            step=SCAN_STEP_DESCRIPTOR_REFRESH,
        )
        return raw_descriptors

    def _coerce_device_type(
        self, profile_id: int | None, device_type: int | None
    ) -> zigpy.profiles.zha.DeviceType | zigpy.profiles.zll.DeviceType | int | None:
        if device_type is None:
            return None

        if profile_id == zigpy.profiles.zha.PROFILE_ID:
            return zigpy.profiles.zha.DeviceType(device_type)
        if profile_id == zigpy.profiles.zll.PROFILE_ID:
            return zigpy.profiles.zll.DeviceType(device_type)
        return device_type

    def _make_ephemeral_cluster(
        self,
        endpoint: zigpy.endpoint.Endpoint,
        *,
        cluster_id: int,
        cluster_type: ClusterType,
    ) -> Cluster:
        cluster = zigpy.zcl.Cluster.from_id(
            endpoint,
            cluster_id,
            is_server=cluster_type == ClusterType.Server,
        )

        if cluster_type == ClusterType.Server:
            endpoint.in_clusters[cluster_id] = cluster
        else:
            endpoint.out_clusters[cluster_id] = cluster

        if cluster.ep_attribute is not None:
            endpoint._cluster_attr[cluster.ep_attribute] = cluster

        return cluster

    async def _build_raw_scan_targets(
        self, device: zigpy.device.Device
    ) -> tuple[_RawScanTarget, ...]:
        topology = await self._get_dblistener().get_raw_topology_rows(device.ieee)
        clusters_by_endpoint: dict[int, list[zigpy.appdb.RawClusterRow]] = (
            collections.defaultdict(list)
        )

        for cluster_row in topology.clusters:
            clusters_by_endpoint[cluster_row.endpoint_id].append(cluster_row)

        targets = []

        for endpoint_row in topology.endpoints:
            # Match the reference diagnostic walker and avoid Green Power false timeouts.
            if endpoint_row.endpoint_id in (0, 242):
                continue

            endpoint = zigpy.endpoint.Endpoint(device, endpoint_row.endpoint_id)
            endpoint.status = zigpy.endpoint.Status(endpoint_row.status)
            endpoint.profile_id = endpoint_row.profile_id
            endpoint.device_type = self._coerce_device_type(
                endpoint_row.profile_id, endpoint_row.device_type
            )

            for cluster_row in clusters_by_endpoint.get(endpoint_row.endpoint_id, ()):
                cluster_type = ClusterType(cluster_row.cluster_type)
                cluster = self._make_ephemeral_cluster(
                    endpoint,
                    cluster_id=cluster_row.cluster_id,
                    cluster_type=cluster_type,
                )

                targets.append(
                    _RawScanTarget(
                        endpoint=endpoint,
                        cluster=cluster,
                        scope=_ScanScopeKey(
                            endpoint_id=endpoint_row.endpoint_id,
                            cluster_type=cluster.cluster_type,
                            cluster_id=cluster.cluster_id,
                        ),
                    )
                )

        return tuple(targets)

    def _resolve_attribute_name(
        self, target: _RawScanTarget, attr_id: int
    ) -> str | None:
        try:
            return target.cluster.find_attribute(
                attr_id,
                manufacturer_code=target.scope.manufacturer_code_scope,
            ).name
        except KeyError:
            return None

    def _canonicalize_attribute_value(
        self,
        value: foundation.TypeValue
        | foundation.Array
        | foundation.Bag
        | foundation.Set,
    ) -> tuple[int, bytes]:
        if isinstance(value, foundation.Array | foundation.Bag | foundation.Set):
            datatype = int(foundation.DataType.from_python_type(type(value)).type_id)
            return datatype, value.serialize()

        datatype = int(value.type)
        python_type = foundation.DataType.from_type_id(
            foundation.DataTypeId(datatype)
        ).python_type
        return datatype, python_type(value.value).serialize()

    def _translate_discovery_failure(
        self, exc: Exception
    ) -> _TerminalStepFailure | None:
        unsupported_statuses = {
            foundation.Status.UNSUP_CLUSTER_COMMAND,
            foundation.Status.UNSUP_GENERAL_COMMAND,
            foundation.Status.UNSUP_MANUF_CLUSTER_COMMAND,
            foundation.Status.UNSUP_MANUF_GENERAL_COMMAND,
            foundation.Status.UNSUPPORTED_CLUSTER,
        }

        if isinstance(exc, zigpy.exceptions.DeliveryError) and exc.status is not None:
            try:
                status = foundation.Status(exc.status)
            except ValueError:
                status = None

            if status in unsupported_statuses:
                return _TerminalStepFailure(
                    str(exc),
                    error_code=ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND,
                )

        lowered_error = str(exc).lower()
        if "unsupported" in lowered_error or "not supported" in lowered_error:
            return _TerminalStepFailure(
                str(exc),
                error_code=ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND,
            )

        return None

    def _translate_discovery_response_failure(
        self,
        response: (
            _AttributeDiscoveryResponse
            | _CommandDiscoveryResponse
            | _DefaultResponseResult
        ),
    ) -> _TerminalStepFailure | None:
        status = self._extract_default_response_status(response)

        if status is None:
            return None

        return _TerminalStepFailure(
            f"discovery command rejected with {status.name.lower()}",
            error_code=ERROR_CODE_UNSUPPORTED_DISCOVERY_COMMAND,
        )

    def _extract_default_response_status(
        self,
        response: (
            _AttributeDiscoveryResponse
            | _CommandDiscoveryResponse
            | _ReadAttributesRawResponse
            | _DefaultResponseResult
        ),
    ) -> foundation.Status | None:
        status: foundation.Status | int

        if isinstance(response, foundation.DefaultResponse):
            status = response.status
        elif (
            isinstance(response, tuple)
            and len(response) == 2
            and response[0] == foundation.GeneralCommand.Default_Response
        ):
            status = response[1]
        else:
            return None

        try:
            return foundation.Status(status)
        except ValueError:
            return None

    def _normalize_attribute_read_status_records(
        self,
        response: _ReadAttributesRawResponse | _DefaultResponseResult,
        attr_ids: list[int],
    ) -> list[foundation.ReadAttributeRecord]:
        status = self._extract_default_response_status(response)

        if status is None:
            raw_response = typing.cast(_ReadAttributesRawResponse, response)
            return list(raw_response.status_records)

        return [
            foundation.ReadAttributeRecord(attrid=t.uint16_t(attr_id), status=status)
            for attr_id in attr_ids
        ]

    def _get_unsupported_discovery_status(
        self,
        response: (
            _StandardAttributeDiscoveryResponse
            | _ExtendedAttributeDiscoveryResponse
            | _CommandDiscoveryResponse
            | _DefaultResponseResult
        ),
    ) -> foundation.Status | None:
        status = self._extract_default_response_status(response)

        if status not in (
            foundation.Status.UNSUP_GENERAL_COMMAND,
            foundation.Status.UNSUP_MANUF_GENERAL_COMMAND,
        ):
            return None

        return status

    def _extract_discovered_attributes(
        self,
        target: _RawScanTarget,
        response: _AttributeDiscoveryResponse,
        *,
        start_attr_id: int,
    ) -> tuple[list[tuple[int, str | None, int, int | None]], int]:
        if hasattr(response, "extended_attr_info"):
            extended_response = typing.cast(
                _ExtendedAttributeDiscoveryResponse, response
            )
            discovered_attributes: list[tuple[int, str | None, int, int | None]] = [
                (
                    int(attribute_info.attrid),
                    self._resolve_attribute_name(target, int(attribute_info.attrid)),
                    int(attribute_info.datatype),
                    int(attribute_info.acl),
                )
                for attribute_info in extended_response.extended_attr_info
            ]
            next_attr_id = (
                start_attr_id
                if not extended_response.extended_attr_info
                else int(extended_response.extended_attr_info[-1].attrid) + 1
            )
            return discovered_attributes, next_attr_id

        standard_response = typing.cast(_StandardAttributeDiscoveryResponse, response)
        discovered_attributes = [
            (
                int(attribute_info.attrid),
                self._resolve_attribute_name(target, int(attribute_info.attrid)),
                int(attribute_info.datatype),
                None,
            )
            for attribute_info in standard_response.attribute_info
        ]
        next_attr_id = (
            start_attr_id
            if not standard_response.attribute_info
            else int(standard_response.attribute_info[-1].attrid) + 1
        )
        return discovered_attributes, next_attr_id

    async def _skip_unsupported_command_discovery(
        self,
        target: _RawScanTarget,
        *,
        direction: str,
        start_command_id: int,
        status: foundation.Status,
    ) -> None:
        LOGGER.warning(
            "Skipping %s command discovery for %s endpoint %s cluster 0x%04x (%s): unsupported command discovery response %s",
            direction,
            target.endpoint.device.ieee,
            target.endpoint_id,
            target.cluster.cluster_id,
            target.cluster.cluster_type.name.lower(),
            status.name,
        )
        await self._pace_requests()
        await self._get_dblistener().persist_device_scan_command_discovery_page(
            ieee=target.endpoint.device.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=target.scope.manufacturer_code_scope,
            direction=direction,
            commands=[],
            next_command_id=start_command_id,
            complete=True,
        )

    async def _discover_attributes_for_target(
        self, target: _RawScanTarget, *, start_attr_id: int = 0
    ) -> None:
        use_extended_discovery = True

        while True:
            try:
                if use_extended_discovery:
                    response: (
                        _AttributeDiscoveryResponse | _DefaultResponseResult
                    ) = await target.cluster.discover_attributes_extended(
                        start_attr_id,
                        ATTRIBUTE_DISCOVERY_PAGE_SIZE,
                        manufacturer=target.scope.manufacturer_code_scope,
                    )
                else:
                    response = await target.cluster.discover_attributes(
                        start_attr_id,
                        ATTRIBUTE_DISCOVERY_PAGE_SIZE,
                        manufacturer=target.scope.manufacturer_code_scope,
                    )
            except (TimeoutError, zigpy.exceptions.ZigbeeException) as exc:
                terminal_failure = self._translate_discovery_failure(exc)

                if terminal_failure is not None:
                    raise terminal_failure from exc

                raise
            unsupported_status = self._get_unsupported_discovery_status(response)

            if unsupported_status is not None:
                if use_extended_discovery:
                    LOGGER.warning(
                        "Extended attribute discovery unsupported for %s endpoint %s cluster 0x%04x (%s): %s; falling back to discover_attributes",
                        target.endpoint.device.ieee,
                        target.endpoint_id,
                        target.cluster.cluster_id,
                        target.cluster.cluster_type.name.lower(),
                        unsupported_status.name,
                    )
                    use_extended_discovery = False
                    continue

                LOGGER.warning(
                    "Standard attribute discovery unsupported for %s endpoint %s cluster 0x%04x (%s): %s; continuing scan without attribute discovery",
                    target.endpoint.device.ieee,
                    target.endpoint_id,
                    target.cluster.cluster_id,
                    target.cluster.cluster_type.name.lower(),
                    unsupported_status.name,
                )
                await self._pace_requests()
                await (
                    self._get_dblistener().persist_device_scan_attribute_discovery_page(
                        ieee=target.endpoint.device.ieee,
                        endpoint_id=target.endpoint_id,
                        cluster_type=target.cluster.cluster_type,
                        cluster_id=target.cluster.cluster_id,
                        manufacturer_code_scope=target.scope.manufacturer_code_scope,
                        attributes=[],
                        next_attr_id=start_attr_id,
                        complete=True,
                    )
                )
                return

            terminal_failure = self._translate_discovery_response_failure(response)

            if terminal_failure is not None:
                raise terminal_failure

            await self._pace_requests()
            attribute_response = typing.cast(_AttributeDiscoveryResponse, response)
            discovered_attributes, next_attr_id = self._extract_discovered_attributes(
                target,
                attribute_response,
                start_attr_id=start_attr_id,
            )

            await self._get_dblistener().persist_device_scan_attribute_discovery_page(
                ieee=target.endpoint.device.ieee,
                endpoint_id=target.endpoint_id,
                cluster_type=target.cluster.cluster_type,
                cluster_id=target.cluster.cluster_id,
                manufacturer_code_scope=target.scope.manufacturer_code_scope,
                attributes=discovered_attributes,
                next_attr_id=next_attr_id,
                complete=bool(attribute_response.discovery_complete),
            )

            if attribute_response.discovery_complete:
                return

            start_attr_id = next_attr_id

    async def _persist_attribute_read_transport_failure(
        self,
        target: _RawScanTarget,
        attr_id: int,
        exc: Exception,
    ) -> None:
        await self._get_dblistener().persist_device_scan_attribute_read_results(
            ieee=target.endpoint.device.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=target.scope.manufacturer_code_scope,
            results=[
                (
                    attr_id,
                    None,
                    False,
                    ATTRIBUTE_READ_STATUS_TRANSPORT_FAILURE,
                    None,
                    None,
                    ERROR_CODE_TRANSPORT_FAILURE,
                    str(exc),
                )
            ],
        )

    async def _read_attribute_rows_with_fallback(
        self,
        target: _RawScanTarget,
        attr_rows: list[zigpy.appdb.DeviceScanAttributeRow],
        *,
        retried: bool = False,
    ) -> tuple[int, ...]:
        attr_ids = [row.attr_id for row in attr_rows]

        try:
            response = await target.cluster.read_attributes_raw(
                attr_ids,
                manufacturer=target.scope.manufacturer_code_scope,
            )
        except (TimeoutError, zigpy.exceptions.ZigbeeException) as exc:
            if not retried and len(attr_rows) > 1:
                await asyncio.sleep(ATTRIBUTE_READ_RETRY_BACKOFF_S)
                return await self._read_attribute_rows_with_fallback(
                    target,
                    attr_rows,
                    retried=True,
                )

            if len(attr_rows) == 1:
                await self._persist_attribute_read_transport_failure(
                    target, attr_rows[0].attr_id, exc
                )
                await self._pace_requests()
                return ()

            midpoint = len(attr_rows) // 2
            lower_missing_attr_ids = await self._read_attribute_rows_with_fallback(
                target, attr_rows[:midpoint]
            )
            upper_missing_attr_ids = await self._read_attribute_rows_with_fallback(
                target, attr_rows[midpoint:]
            )
            return lower_missing_attr_ids + upper_missing_attr_ids

        await self._pace_requests()
        records_by_attr_id = {
            int(status_record.attrid): status_record
            for status_record in self._normalize_attribute_read_status_records(
                response, attr_ids
            )
        }
        missing_attr_ids = [
            row.attr_id for row in attr_rows if row.attr_id not in records_by_attr_id
        ]
        missing_attr_ids_text = ", ".join(
            f"0x{attr_id:04x}" for attr_id in missing_attr_ids
        )
        if missing_attr_ids:
            response_attr_ids_text = ", ".join(
                f"0x{attr_id:04x}" for attr_id in sorted(records_by_attr_id)
            )
            LOGGER.warning(
                "Read_Attributes response missing status records for %s endpoint %s cluster 0x%04x (%s) manufacturer %s: missing %s; response contained %s",
                target.endpoint.device.ieee,
                target.endpoint_id,
                target.cluster.cluster_id,
                target.cluster.cluster_type.name.lower(),
                target.scope.manufacturer_code_scope,
                missing_attr_ids_text,
                response_attr_ids_text or "(none)",
            )
        last_read = datetime.now(UTC_TZ).timestamp()
        results: list[
            tuple[
                int,
                int | None,
                bool,
                str | None,
                bytes | None,
                float | None,
                str | None,
                str | None,
            ]
        ] = []
        missing_rows: list[zigpy.appdb.DeviceScanAttributeRow] = []

        for row in attr_rows:
            record = records_by_attr_id.get(row.attr_id)

            if record is None:
                missing_rows.append(row)

                if len(attr_rows) > 1:
                    continue

                results.append(
                    (
                        row.attr_id,
                        None,
                        False,
                        ATTRIBUTE_READ_STATUS_TRANSPORT_FAILURE,
                        None,
                        None,
                        ERROR_CODE_TRANSPORT_FAILURE,
                        f"missing read response records for attributes {missing_attr_ids_text}",
                    )
                )
                continue

            if record.status == foundation.Status.SUCCESS:
                attribute_value = typing.cast(
                    foundation.TypeValue
                    | foundation.Array
                    | foundation.Bag
                    | foundation.Set,
                    record.value,
                )
                datatype, value = self._canonicalize_attribute_value(attribute_value)
                results.append(
                    (
                        row.attr_id,
                        datatype,
                        True,
                        ATTRIBUTE_READ_STATUS_SUCCESS,
                        value,
                        last_read,
                        None,
                        None,
                    )
                )
            elif record.status == foundation.Status.UNSUPPORTED_ATTRIBUTE:
                results.append(
                    (
                        row.attr_id,
                        None,
                        True,
                        ATTRIBUTE_READ_STATUS_UNSUPPORTED,
                        None,
                        last_read,
                        ERROR_CODE_ATTRIBUTE_UNSUPPORTED,
                        None,
                    )
                )
            else:
                results.append(
                    (
                        row.attr_id,
                        None,
                        True,
                        record.status.name.lower(),
                        None,
                        last_read,
                        None,
                        None,
                    )
                )

        if results:
            await self._get_dblistener().persist_device_scan_attribute_read_results(
                ieee=target.endpoint.device.ieee,
                endpoint_id=target.endpoint_id,
                cluster_type=target.cluster.cluster_type,
                cluster_id=target.cluster.cluster_id,
                manufacturer_code_scope=target.scope.manufacturer_code_scope,
                results=results,
            )

        if len(attr_rows) > 1 and missing_rows:
            retried_missing_attr_ids: list[int] = []

            for missing_row in missing_rows:
                retried_missing_attr_ids.extend(
                    await self._read_attribute_rows_with_fallback(
                        target,
                        [missing_row],
                        retried=True,
                    )
                )

            return tuple(retried_missing_attr_ids)

        return tuple(missing_attr_ids)

    async def _read_attributes_for_target(self, target: _RawScanTarget) -> None:
        dblistener = self._get_dblistener()
        pending_rows = await dblistener.get_pending_device_scan_attributes(
            ieee=target.endpoint.device.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=target.scope.manufacturer_code_scope,
        )

        if not pending_rows:
            await dblistener.set_device_scan_attr_reads_complete(
                ieee=target.endpoint.device.ieee,
                endpoint_id=target.endpoint_id,
                cluster_type=target.cluster.cluster_type,
                cluster_id=target.cluster.cluster_id,
                manufacturer_code_scope=target.scope.manufacturer_code_scope,
                complete=True,
            )
            return

        missing_attr_ids: list[int] = []
        for index in range(0, len(pending_rows), ATTRIBUTE_READ_BATCH_SIZE):
            batch = pending_rows[index : index + ATTRIBUTE_READ_BATCH_SIZE]
            missing_attr_ids.extend(
                await self._read_attribute_rows_with_fallback(target, batch)
            )

        remaining_rows = await dblistener.get_pending_device_scan_attributes(
            ieee=target.endpoint.device.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=target.scope.manufacturer_code_scope,
        )
        if missing_attr_ids:
            missing_attr_ids_text = ", ".join(
                f"0x{attr_id:04x}" for attr_id in sorted(set(missing_attr_ids))
            )
            raise _TerminalStepFailure(
                f"missing read response records for attributes {missing_attr_ids_text}",
                error_code=ERROR_CODE_TRANSPORT_FAILURE,
            )
        if remaining_rows:
            if len(remaining_rows) == 1 and remaining_rows[0].last_error:
                error = remaining_rows[0].last_error
            else:
                remaining_attr_ids_text = ", ".join(
                    f"0x{row.attr_id:04x}" for row in remaining_rows
                )
                error = f"request timed out for attributes {remaining_attr_ids_text}"

            raise _TerminalStepFailure(
                error,
                error_code=ERROR_CODE_TRANSPORT_FAILURE,
            )

        await dblistener.set_device_scan_attr_reads_complete(
            ieee=target.endpoint.device.ieee,
            endpoint_id=target.endpoint_id,
            cluster_type=target.cluster.cluster_type,
            cluster_id=target.cluster.cluster_id,
            manufacturer_code_scope=target.scope.manufacturer_code_scope,
            complete=True,
        )

    def _get_command_definitions(
        self, target: _RawScanTarget, direction: str
    ) -> Mapping[int, foundation.ZCLCommandDef]:
        if direction == COMMAND_DISCOVERY_DIRECTION_RECEIVED:
            return (
                target.cluster.server_commands
                if target.cluster.is_server
                else target.cluster.client_commands
            )

        return (
            target.cluster.client_commands
            if target.cluster.is_server
            else target.cluster.server_commands
        )

    def _resolve_command_name(
        self, target: _RawScanTarget, direction: str, command_id: int
    ) -> str | None:
        command_def = self._get_command_definitions(target, direction).get(command_id)
        return None if command_def is None else command_def.name

    async def _discover_commands_for_target(
        self,
        target: _RawScanTarget,
        *,
        direction: str,
        discover_commands: _DiscoverCommandsCallable,
        start_command_id: int = 0,
    ) -> None:
        while True:
            retried_timeout = False

            while True:
                try:
                    response = await discover_commands(
                        start_command_id,
                        ATTRIBUTE_DISCOVERY_PAGE_SIZE,
                        manufacturer=target.scope.manufacturer_code_scope,
                    )
                except TimeoutError:
                    if (
                        target.scope.manufacturer_code_scope is not None
                        and not retried_timeout
                    ):
                        LOGGER.warning(
                            "Retrying manufacturer-scoped %s command discovery for %s endpoint %s cluster 0x%04x (%s) after timeout",
                            direction,
                            target.endpoint.device.ieee,
                            target.endpoint_id,
                            target.cluster.cluster_id,
                            target.cluster.cluster_type.name.lower(),
                        )
                        retried_timeout = True
                        await asyncio.sleep(COMMAND_DISCOVERY_RETRY_BACKOFF_S)
                        continue

                    raise
                except zigpy.exceptions.ZigbeeException as exc:
                    terminal_failure = self._translate_discovery_failure(exc)

                    if terminal_failure is not None:
                        raise terminal_failure from exc

                    raise

                break
            unsupported_status = self._get_unsupported_discovery_status(response)

            if unsupported_status is not None:
                await self._skip_unsupported_command_discovery(
                    target,
                    direction=direction,
                    start_command_id=start_command_id,
                    status=unsupported_status,
                )
                return

            terminal_failure = self._translate_discovery_response_failure(response)

            if terminal_failure is not None:
                raise terminal_failure

            await self._pace_requests()
            command_response = typing.cast(_CommandDiscoveryResponse, response)

            commands: list[tuple[int, str | None, str | None]] = [
                (
                    int(command_id),
                    self._resolve_command_name(target, direction, int(command_id)),
                    None,
                )
                for command_id in command_response.command_ids
            ]
            next_command_id = (
                start_command_id
                if not command_response.command_ids
                else int(command_response.command_ids[-1]) + 1
            )

            await self._get_dblistener().persist_device_scan_command_discovery_page(
                ieee=target.endpoint.device.ieee,
                endpoint_id=target.endpoint_id,
                cluster_type=target.cluster.cluster_type,
                cluster_id=target.cluster.cluster_id,
                manufacturer_code_scope=target.scope.manufacturer_code_scope,
                direction=direction,
                commands=commands,
                next_command_id=next_command_id,
                complete=bool(command_response.discovery_complete),
            )

            if command_response.discovery_complete:
                return

            start_command_id = next_command_id

    async def _discover_commands_received_for_target(
        self, target: _RawScanTarget, *, start_command_id: int = 0
    ) -> None:
        await self._discover_commands_for_target(
            target,
            direction=COMMAND_DISCOVERY_DIRECTION_RECEIVED,
            discover_commands=target.cluster.discover_commands_received,
            start_command_id=start_command_id,
        )

    async def _discover_commands_generated_for_target(
        self, target: _RawScanTarget, *, start_command_id: int = 0
    ) -> None:
        await self._discover_commands_for_target(
            target,
            direction=COMMAND_DISCOVERY_DIRECTION_GENERATED,
            discover_commands=target.cluster.discover_commands_generated,
            start_command_id=start_command_id,
        )
