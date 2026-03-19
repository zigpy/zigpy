# Raw On-Wire Device Scan Design

**Date:** 2026-03-15

**Goal:** Add an on-demand zigpy device scan that performs a full raw on-wire inventory of a device, stores the results durably in zigpy's database, can resume from the last completed scan step, and never mutates live runtime cache or event state.

## Requirements

- On-demand only. This is not part of `Device.initialize()` or normal rejoin flow.
- Persist the full scan inventory durably in the database.
- Store the raw on-wire view, not the quirked view.
- Keep the first iteration non-invasive at runtime.
- Scan surface for v1:
  - raw descriptors
  - discovered attributes via `Discover_Attribute_Extended`, falling back to `Discover_Attributes` when needed
  - readable attribute values
  - discovered received/generated commands
- Preserve progress and resume from the last completed scan step.
- Default behavior is `resume`; `force_full` is explicit.
- Reject `resume=True` plus `force_full=True` as invalid input before queue classification.
- Use one fixed internal scan deadline in v1. It is not configurable.
- Use stable `error_code` values alongside human-readable error text.
- Store one canonical persisted attribute value representation plus datatype metadata.
- Keep manufacturer-specific scanning raw-only. If raw manufacturer code is absent, expose an explicit skipped reason instead of silently omitting that scope.

## Research Summary

### zha-toolkit behavior

The reference implementation in `zha-toolkit` is an active diagnostic walker:

- It walks all endpoints except endpoint `0`.
- It skips endpoint `242`.
- It scans input and output clusters.
- It discovers attributes with `discover_attributes_extended()` in pages of 16, falling back to `discover_attributes()` when the extended command is unsupported.
- It reads readable attributes in chunks of 4.
- It optionally does a second manufacturer-scoped attribute pass using `ep.manufacturer_id`.
- It discovers received/generated commands in pages of 16.
- It writes a JSON artifact, not durable normalized state.

The useful ideas are the paging model, small read batches, and best-effort retry behavior.

The parts zigpy should not copy directly are:

- It uses `cluster.read_attributes()`, which updates cache/events and cannot read unknown discovered attribute IDs safely in current zigpy.
- It does not persist normalized, resumable state.
- It does not do manufacturer-scoped command discovery.
- It appears to pass `is_server=True` even for output clusters, which makes command direction handling unreliable.

### zigpy behavior

zigpy already has strong primitives, but not a complete device scanner:

- `Device._initialize()` discovers node descriptor, active endpoints, simple descriptors, model/manufacturer, and an OTA attribute.
- `ControllerApplication.device_initialized()` persists the raw device view before quirks are applied.
- `PersistingListener` already stores:
  - devices
  - endpoints
  - clusters
  - node descriptors
  - attribute cache
  - unsupported attributes
- `Topology` is still a useful service-pattern reference for:
  - task ownership
  - retries
  - request pacing
  - explicit scan API

The key gaps are:

- No on-demand device scan orchestrator.
- No database model for discovered command inventory, attribute metadata, scan checkpoints, or partial completion.
- No non-invasive raw read path that persists scan results separately from `attributes_cache`.
- No DB-backed read model for scan snapshots.

## Architectural Choice

Use a dedicated on-demand raw scan service.

Rejected alternatives:

1. Extend normal init and reuse live clusters plus `attributes_cache`.
   This violates the non-invasive and raw-view requirements.

2. Scan through a detached raw `Device` clone.
   This is incorrect in zigpy because request/response matching is attached to the live device instance used by the application.

Chosen approach:

- Add a `DeviceScanner` service owned by `ControllerApplication`.
- Use the live device only as the transport anchor for request/response matching.
- Extract a shared raw descriptor discovery helper from normal init and reuse it for scanner refresh instead of duplicating descriptor walk logic.
- Treat refreshed raw descriptor tables in the database as the canonical scan-plan source.
- Persist scan inventory and scan progress in dedicated database tables.
- Never write scan results into the live runtime attribute cache in v1.

The shared descriptor helper is intentionally not local to `device_scanner.py`. This design expects the extraction to touch existing init code in `zigpy.device` and `zigpy.endpoint` so join-time descriptor behavior and scan-time descriptor behavior cannot drift apart.

## Raw View Strategy

The scan must operate on the raw on-wire topology, not the quirked topology.

Important implication:

- The live device object in `app.devices` may be quirked and may add/remove/replace endpoints and clusters.
- The scan plan must therefore be built from raw descriptor data, not the live quirked endpoint graph.

Use this split:

- **Canonical raw topology source:** refreshed raw descriptor tables in the database
- **Bootstrap fallback:** `device.original_signature` only before raw tables exist
- **Transport source:** the live application device instance

This avoids the broken detached-device pattern while keeping the scan raw.

## Public API

### `ControllerApplication.device_scanner`

A new explicit-use service similar in role to `Topology`.

Responsibilities:

- option validation
- task dedupe
- global scan concurrency
- resume and `force_full`
- progress events
- persistence coordination
- DB-backed snapshot assembly

### `DeviceScanner.scan()`

```python
await app.device_scanner.scan(
    ieee,
    resume=True,
    force_full=False,
)
```

Behavior:

- default `resume=True`
- every scan refreshes raw descriptors first
- `force_full=True` clears all scan state for the device first
- `resume=True` and `force_full=True` together raise `InvalidScanOptionsError` before queue classification
- the scan deadline is a fixed internal 120 seconds and non-configurable in v1
- `scan()` returns a fixed `DeviceScanSummary` contract, not the full snapshot

### `DeviceScanSummary`

`scan()` returns a small fixed `DeviceScanSummary` type.

Fields:

- `ieee`
- `completed`
- `outcome`
- `used_resume`
- `force_full`
- `descriptor_refresh_performed`
- `last_finished`
- `error_code`
- `last_error`

Meaning:

- `completed=True` means this run reached a terminal state, not that every scope succeeded
- `outcome` is one of `success`, `partial`, or `failed`
- callers and tests must key off `error_code`, not `last_error` text

### `DeviceScanner.get_snapshot()`

```python
snapshot = await app.device_scanner.get_snapshot(ieee)
```

Behavior:

- `get_snapshot()` is a pure DB-backed read API and does not require the live device to exist
- if no persisted raw descriptor rows exist for the IEEE, raise `DeviceScanSnapshotNotFoundError`
- if persisted raw descriptor rows exist but scan rows do not, return a valid empty snapshot with materialized scopes and empty `progress`, `attributes`, and `commands`
- partial scans return partial progress, attributes, and commands without consulting live runtime objects

### `DeviceScanSnapshot`

Top-level fields:

- `ieee`
- `raw_node_descriptor`
- `last_snapshot_at`
- `endpoints`

Hierarchy:

```text
DeviceScanSnapshot
  |
  +--> ieee
  +--> raw_node_descriptor
  +--> last_snapshot_at
  `--> endpoints[]
        |
        +--> endpoint_id
        +--> profile_id
        +--> device_type
        `--> clusters[]
              |
              +--> cluster_id
              +--> cluster_type
              +--> standard
              |     +--> progress
              |     +--> attributes[]
              |     `--> commands[]
              |
              `--> manufacturer_specific
                    +--> manufacturer_code
                    +--> progress
                    +--> attributes[]
                    `--> commands[]
```

Materialization rules:

- `standard` is always materialized
- `manufacturer_specific` is always materialized so manufacturer-scope visibility is explicit
- when the refreshed raw node descriptor has a manufacturer code, `manufacturer_specific` behaves like a normal scan scope
- when the refreshed raw node descriptor has no manufacturer code:
  - `manufacturer_specific.manufacturer_code` is `None`
  - `manufacturer_specific.progress.status` is `skipped`
  - `manufacturer_specific.progress.error_code` is `missing_raw_manufacturer_code`
  - `manufacturer_specific.attributes` and `manufacturer_specific.commands` are empty
  - this skipped scope is synthesized during event and snapshot assembly from raw descriptor state; it does not require a persisted progress row

Ordering:

- endpoints ordered by `endpoint_id` ascending
- clusters ordered by `cluster_type`, then `cluster_id` ascending
- attributes ordered by `attr_id` ascending
- commands ordered by `direction`, then `command_id` ascending

Assembly rule:

- seed the endpoint and cluster hierarchy from raw descriptor rows in one pass
- attach progress, attributes, and commands from scan rows in one pass
- each snapshot attribute exposes `datatype`, the canonical stored raw value, and an optional decoded value
- decode the canonical stored attribute value into snapshot output during assembly
- resolve decode metadata once per cluster or type and reuse it while decoding attribute values in that single assembly pass
- never re-query or re-scan per cluster or scope during snapshot assembly

### Public errors

Public scanner errors are fixed named types, not message-based behavior.

- `InvalidScanOptionsError` for invalid option combinations such as `resume=True` plus `force_full=True`
- `ScanInProgressError` for conflicting queued or running same-device requests
- `DeviceScanTargetMissingError` when a queued scan reaches execution after the target device was removed
- `DeviceScanSnapshotNotFoundError` when `get_snapshot()` has no persisted raw descriptor rows to read from

## Progress Event Contract

Progress events are intentionally small.

Listeners attach to `app.device_scanner`, following the same `ListenableMixin` pattern used by `Topology`.

Event names:

- `scan_queued`
- `scan_started`
- `step_started`
- `step_finished`
- `scan_finished`

Event payload fields:

- `ieee`
- `status`
- optional `outcome`
- optional `step`
- optional scope: `endpoint_id`, `cluster_id`, `cluster_type`, `scope_kind`, `manufacturer_code_scope`
- optional `error_code`
- optional `error`

Allowed statuses:

- `queued`
- `started`
- `success`
- `failed`
- `skipped`

Cardinality:

- `scan_queued`, `scan_started`, and `scan_finished` are scan-level events
- `scan_finished` may include terminal `outcome=success|partial|failed`
- `step_started` and `step_finished` are used for both descriptor refresh and per-scope inventory work
- descriptor refresh uses `step="descriptor_refresh"` and does not include scope fields
- inventory step events are emitted per scope and include `endpoint_id`, `cluster_id`, `cluster_type`, `scope_kind`, and `manufacturer_code_scope`
- manufacturer-scope gating uses `status="skipped"`, `error_code="missing_raw_manufacturer_code"`, `scope_kind="manufacturer_specific"`, and `manufacturer_code_scope=None`

## Error-Code Vocabulary

The scanner layer defines one fixed error-code vocabulary used by summary, events, and persisted scan-state fields.

V1 error codes:

- `invalid_scan_options`
- `scan_in_progress`
- `device_scan_target_missing`
- `descriptor_refresh_failed`
- `scan_deadline_exceeded`
- `unsupported_discovery_command`
- `transport_failure`
- `attribute_unsupported`
- `missing_raw_manufacturer_code`

`error_code` is the machine-readable contract. `last_error` and event `error` remain human-readable diagnostic text only.

For attribute-read rows:

- `read_status` is the protocol or result-category field
- `last_error_code` is the scanner error-contract field
- terminal protocol outcomes may have no `last_error_code`
- transport or scanner failures must set `last_error_code`
- `read_complete` is a derived query-optimization flag and must remain consistent with `read_status`

## Scheduling And Task Ownership

V1 scheduler rules:

- only one device scan runs globally at a time
- different-device requests wait in FIFO order for the global slot
- a queued same-device request counts as in-progress for dedupe and conflict purposes
- exact duplicate same-device requests reuse the queued or running task
- conflicting same-device requests raise `ScanInProgressError`
- the shared scan task is owned by `DeviceScanner`, not any single caller
- caller cancellation detaches only that caller's wait and does not cancel shared queued or running scan work
- every shared scan task runs inside one fixed internal deadline wrapper
- deadline expiry releases the global slot and preserves already committed rows
- deadline expiry is `partial` only if the timed-out run committed new scan rows before expiry; otherwise it is `failed`

```text
caller request
  |
  +--> validate options
  |     `--> invalid -> InvalidScanOptionsError
  |
  +--> classify request
  |     +--> same-device exact duplicate -> attach to shared task
  |     +--> same-device conflict -> ScanInProgressError
  |     `--> different device -> FIFO queue
  |
  `--> run shared task with deadline
        |
        +--> success -> release slot -> wake next queued scan
        +--> failed  -> release slot -> wake next queued scan
        `--> timeout -> persist partial state -> release slot -> wake next queued scan
```

## Persistence Surface

Keep database writes in `zigpy.appdb.PersistingListener`, but add explicit async methods for the device scan service and low-level DB-backed snapshot read helpers.

This keeps schema ownership in one place while avoiding the normal event-driven attribute cache path.

Callers read snapshots only through `DeviceScanner`; `appdb` returns low-level scan rows and `DeviceScanner` assembles the public `DeviceScanSnapshot`.

The scanner layer also defines:

- one shared internal step and status vocabulary used by progress events, summary assembly, and snapshot assembly
- one shared internal scope identity helper used by scan execution, event emission, and snapshot assembly
- one shared raw descriptor discovery helper reused by both normal init and scanner refresh

## Database Model

Do not duplicate existing raw descriptor tables. Reuse:

- `devices_vN`
- `endpoints_vN`
- `clusters_vN`
- `node_descriptors_vN`

Add new tables:

### `device_scan_progress_v15`

Keyed by:

- `ieee`
- `endpoint_id`
- `cluster_type`
- `cluster_id`
- `manufacturer_code_scope`

Stores:

- `attr_discovery_complete`
- `attr_discovery_next_id`
- `attr_reads_complete`
- `cmd_rx_complete`
- `cmd_rx_next_id`
- `cmd_tx_complete`
- `cmd_tx_next_id`
- `last_started`
- `last_finished`
- `last_error_code`
- `last_error`
- `last_success`

Purpose:

- resumable paging
- resumable read progress
- stable machine-readable error reporting

Secondary indexes:

- `idx_device_scan_progress_v15_ieee` on `(ieee)` for per-device clears and snapshot reads

### `device_scan_attributes_v15`

Keyed by:

- `ieee`
- `endpoint_id`
- `cluster_type`
- `cluster_id`
- `manufacturer_code_scope`
- `attr_id`

Stores:

- raw attribute identifier
- optional resolved attribute name
- datatype
- ACL bitmap
- discovery timestamp
- read completion flag
- read status
- one canonical raw persisted value field
- last read timestamp
- `last_error_code`
- `last_error`

Notes:

- Keep the scope manufacturer code in the key because standard and manufacturer-scoped discovery can both surface the same attribute ID.
- Use the same NULL-safe uniqueness approach zigpy already uses for `manufacturer_code`.
- `read_complete` is a query-oriented derived flag and must stay consistent with `read_status`.
- `read_status` captures protocol or result status; `last_error_code` captures scanner failure semantics when applicable.
- Do not store both raw bytes and a normalized text or JSON rendering. Snapshot assembly derives optional decoded output from the canonical stored value.

Secondary indexes:

- `idx_device_scan_attributes_v15_ieee` on `(ieee)` for per-device clears and snapshot reads
- `idx_device_scan_attributes_v15_pending_reads` on the existing NULL-safe manufacturer-scope index shape plus `(ieee, endpoint_id, cluster_type, cluster_id, read_complete, attr_id)` ordering for pending-readable-attribute selection per scope

### `device_scan_commands_v15`

Keyed by:

- `ieee`
- `endpoint_id`
- `cluster_type`
- `cluster_id`
- `manufacturer_code_scope`
- `direction`
- `command_id`

Stores:

- raw command identifier
- direction (`received` or `generated`)
- optional resolved command name
- optional resolved schema text
- discovery timestamp

Notes:

- Name and schema are annotations from zigpy's known cluster definitions, not treated as raw on-wire truth.

Secondary indexes:

- `idx_device_scan_commands_v15_ieee` on `(ieee)` for per-device clears and snapshot reads

## Scan Algorithm

Every scan refreshes raw descriptors first, then inventories refreshed raw cluster scopes.

```text
scan request
  |
  +--> validate options
  |     `--> invalid -> InvalidScanOptionsError
  |
  +--> classify request
  |     +--> same-device exact duplicate -> reuse task
  |     +--> same-device conflict -> ScanInProgressError
  |     `--> different device -> FIFO wait
  |
  +--> emit scan_queued
  |
  `--> run shared scan task inside deadline
        |
        +--> emit scan_started
        |
        +--> refresh raw descriptors
        |     +--> step_started(descriptor_refresh)
        |     +--> shared raw descriptor discovery helper
        |     +--> atomically replace raw descriptor rows
        |     +--> clear removed scan scopes
        |     `--> step_finished(descriptor_refresh, success|failed)
        |
        +--> for each refreshed raw endpoint/cluster
        |     +--> standard scope
        |     |     +--> discover attrs
        |     |     +--> read readable attrs
        |     |     +--> discover rx commands
        |     |     `--> discover tx commands
        |     |
        |     `--> manufacturer_specific scope
        |           +--> raw manufacturer code present -> scan normally
        |           `--> raw manufacturer code absent
        |                 +--> mark scope skipped
        |                 `--> emit step_finished(..., skipped, missing_raw_manufacturer_code,
        |                                       scope_kind=manufacturer_specific,
        |                                       manufacturer_code_scope=None)
        |
        `--> emit scan_finished(success|partial|failed)
```

### Step 0: refresh raw descriptors

- Always request the node descriptor first.
- Request active endpoints with `Active_EP_req`.
- Request each endpoint's simple descriptor with `Simple_Desc_req`.
- Build the refreshed raw descriptor set in memory first.
- Replace the device's raw descriptor rows atomically only after the full refresh succeeds.
- Clear scan rows and progress rows for scopes that disappeared from the refreshed raw topology.
- If descriptor refresh fails, abort the scan before attribute or command inventory begins and leave the prior canonical raw rows untouched.

### Step 1: choose scan scopes

Only materialize scan scopes for refreshed raw endpoints other than endpoint `0` and endpoint `242`.

For every refreshed raw cluster:

1. Materialize the `standard` scope with `manufacturer_code_scope = NULL`
2. Materialize the `manufacturer_specific` scope
   - if refreshed raw node descriptor has a non-`None` manufacturer code, scan it normally
   - otherwise synthesize it as `skipped` with `error_code = missing_raw_manufacturer_code` and no persisted scan rows

### Step 2: discover attributes

- Use one shared private page runner for all page-driven discovery steps.
- Page in batches of 16, matching the reference behavior.
- Try `Discover_Attribute_Extended` first so ACL metadata is preserved when the device supports it.
- Discovery default responses may arrive either as the legacy `(GeneralCommand.Default_Response, status)` tuple or as a decoded `foundation.DefaultResponse` object; normalize both forms before making control-flow decisions.
- Some devices reply to output-cluster requests with the wrong ZCL direction bit; request/response matching must still treat those actual response frames as replies instead of letting them fall through to transport timeouts.
- Wrong-direction non-response traffic must not satisfy pending requests just because the TSN matches.
- If the device replies to `Discover_Attribute_Extended` with default-response `UNSUP_GENERAL_COMMAND`, log it and retry the same page with `Discover_Attributes`.
- If the manufacturer-scoped pass replies with default-response `UNSUP_MANUF_GENERAL_COMMAND`, treat it as the manufacturer-specific analogue of unsupported discovery: log it and retry the same page with `Discover_Attributes`.
- Apply the baseline pacing delay before issuing that fallback `Discover_Attributes` request.
- If `Discover_Attributes` also replies with default-response `UNSUP_GENERAL_COMMAND`, log it, persist an empty completed page for the scope, and continue the scan.
- If the manufacturer-scoped fallback also replies with default-response `UNSUP_MANUF_GENERAL_COMMAND`, log it, persist an empty completed page for the scope, and continue the scan.
- Any other discovery default-response status is terminal for that scope and produces the normal partial-scan failure path.
- Per-request transport timeouts still use zigpy's normal reply timeouts and surface as scope-local `transport_failure`, not `scan_deadline_exceeded`.
- Persist each successful page and its progress cursor update in the same transaction.
- Advance the stored cursor only after the page rows are committed.
- Mark the step complete only after the terminating page is processed.
- Persist ACL metadata only when extended discovery succeeds; standard discovery pages leave ACL as `NULL`.
- When a scope restarts from attribute-discovery page `0` on a non-resume scan, replace that scope's previously persisted progress, attribute rows, and command rows on the first committed page so stale inventory does not survive a fresh scan.

### Step 3: read readable attributes

- Load the pending readable target set from stored attribute rows once per cluster scope after discovery completes.
- Use `read_attributes_raw()`, never `read_attributes()`.
- Default read batch size is fixed at 3 in v1.
- `read_attributes_raw()` default-response failures may arrive either as the legacy tuple form or as a decoded `foundation.DefaultResponse` object; normalize both forms before mapping terminal per-attribute statuses.
- If a `ReadAttributesResponse` omits one or more requested attribute IDs, log the missing IDs, retry only the missing IDs one-by-one, then persist retryable `transport_failure` rows only for any IDs that are still missing after the one-by-one retry. Continue the remaining read batches for the scope and surface the scope as a partial transport failure instead of aborting the scan.
- On whole-batch transport failure:
  - retry with backoff
  - split the batch into lower and upper halves
  - continue binary splitting until single-attribute reads
- Drive split-and-retry from the in-memory target set for the current scope instead of re-querying the database for every fallback.
- Persist each successful read batch in its own transaction.
- Terminal device responses such as unsupported attribute are marked complete for that attribute and use the fixed `attribute_unsupported` error code where appropriate.
- Transport failures remain retryable and do not mark the attribute complete.

### Request pacing

- Apply a small fixed internal pacing delay between outbound scan requests in v1.
- Reuse the same pacing rule for descriptor refresh, discovery pages, and raw reads.
- Keep pacing internal and non-configurable in v1.
- Retry-time backoff is in addition to the baseline pacing rule.

### Step 4 and 5: discover commands

- Use the same shared private page runner used by attribute discovery.
- Page in batches of 16.
- Persist each successful page and its progress cursor update in the same transaction.
- Track separate cursors for received and generated directions.
- Use correct cluster role handling for output clusters.
- Output-cluster response frames with the wrong ZCL direction bit must still resolve the pending request so command discovery does not false-time out, but wrong-direction non-response traffic must not.
- Support manufacturer-scoped discovery only when the refreshed raw node descriptor from this scan provides a non-`None` manufacturer code.
- If manufacturer code is absent, represent the skipped scope explicitly rather than silently omitting it.
- If received or generated command discovery replies with default-response `UNSUP_GENERAL_COMMAND`, in either tuple or decoded `foundation.DefaultResponse` form, log it, persist an empty completed page for that direction, and continue the scan.
- If manufacturer-scoped command discovery replies with default-response `UNSUP_MANUF_GENERAL_COMMAND`, in either tuple or decoded `foundation.DefaultResponse` form, log it, persist an empty completed page for that direction, and continue the scan.
- Any other command-discovery default-response status is terminal for that scope and does not fall through to normal page parsing.
- If a manufacturer-scoped command-discovery page times out, retry that same page once with a short backoff before surfacing the normal scope-local `transport_failure`.

## Resume, `force_full`, And Deadlines

Default resume behavior:

- if a cluster scope has completed a step, skip that step
- if attribute discovery completed but attribute reads did not, resume reads only
- if command discovery partially completed, continue from the stored cursor
- `resume=False` reruns each scope from zero; the first committed attribute-discovery page replaces any previously persisted inventory for that scope

`force_full` behavior:

- clear all scan rows and progress rows for the device first
- keep the current raw descriptor rows until descriptor refresh succeeds
- refresh descriptors and rescan from zero

Deadline behavior:

- the deadline wraps the whole shared scan task, not just individual requests
- the fixed deadline is 120 seconds in v1
- underlying per-request reply timeouts are independent of the 120-second scan wrapper and do not imply deadline expiry
- deadline expiry preserves already committed rows
- deadline expiry releases the global queue slot
- deadline expiry returns `partial` only if the timed-out run committed new scan rows before expiry; otherwise it returns `failed`
- deadline expiry returns a terminal summary with `error_code=scan_deadline_exceeded` and human-readable `last_error`

## Runtime Side Effects

The first iteration is intentionally non-invasive.

Must not:

- update live `attributes_cache`
- emit normal attribute read or update events
- overwrite live model, manufacturer, or other runtime device state
- overwrite the live device endpoint or cluster dictionaries during scan execution

Allowed:

- sending active ZDO and ZCL requests for scanning
- emitting only the fixed scan-specific progress events described above

Fast polling is not required for v1. It can be added later as an explicit scan option if needed.

## Snapshot Materialization Diagram

```text
raw cluster row
  |
  +--> standard scope
  |     +--> progress from progress rows
  |     +--> attributes from attribute rows
  |     `--> commands from command rows
  |
  `--> manufacturer_specific scope
        |
        +--> raw manufacturer code present
        |     +--> manufacturer_code=<value>
        |     +--> progress from progress rows
        |     +--> attributes from attribute rows
        |     `--> commands from command rows
        |
        `--> raw manufacturer code absent
              +--> manufacturer_code=None
              +--> progress.status=skipped
              +--> progress.error_code=missing_raw_manufacturer_code
              +--> attributes=[]
              `--> commands=[]
```

## Testing Strategy

Minimum required tests:

- progress listeners attach to `app.device_scanner`, not `ControllerApplication`
- invalid `resume=True` plus `force_full=True` fails fast before queueing
- scan performs descriptor refresh with `Node_Desc_req`, `Active_EP_req`, and `Simple_Desc_req`
- descriptor refresh uses the same raw descriptor helper as normal init
- descriptor refresh parity covers edge cases such as inactive endpoints and profile or device-type coercion
- descriptor refresh failure aborts before attribute or command inventory
- refreshed raw descriptor replacement clears removed endpoint and cluster scan scopes
- scan uses refreshed raw database topology, not quirked live topology
- output cluster command directions are correct
- raw scan reads do not touch live `attributes_cache`
- standard and manufacturer-scoped rows coexist for the same attribute ID
- manufacturer-scoped inventory is skipped when the refreshed raw node descriptor has `None`, even if live manufacturer values or overrides exist
- the manufacturer-scope skipped reason is visible in both progress events and snapshot output
- attribute discovery resume continues from the stored cursor
- partial attribute read resume skips completed rows
- raw attribute reads use deterministic binary split fallback after transport failure
- ordered pending-read selection uses the final pending-read index shape
- unsupported extended attribute discovery falls back to standard discovery
- if both attribute discovery commands are unsupported, the scope completes discovery with no attributes and the scan continues
- tuple and decoded `foundation.DefaultResponse` `UNSUP_GENERAL_COMMAND` replies take the same control-flow path
- command discovery `UNSUP_GENERAL_COMMAND` replies are logged and treated as completed empty pages, not terminal scope failures
- `force_full` resets all scan state for the device
- duplicate requests for the same device reuse the existing scan task
- conflicting same-device requests raise `ScanInProgressError`
- different-device requests wait in FIFO order for the single global slot
- queued same-device duplicate and conflict behavior matches running-task behavior
- queued scans whose device disappears before execution raise `DeviceScanTargetMissingError`, not raw `KeyError`
- caller cancellation does not cancel the shared queued or running scan task
- scan-level deadline returns `failed` when the timed-out run committed no new scan rows
- scan-level deadline returns `partial` when the timed-out run committed new scan rows before expiry
- progress events use the fixed event names, statuses, payload shape, and terminal `scan_finished.outcome`
- summary and lower-level scan-state outputs expose stable `error_code` values
- attribute-read rows keep `read_status`, `last_error_code`, and derived `read_complete` consistent for success, terminal unsupported, and retryable transport failure
- descriptor refresh `step_*` events have no scope fields while inventory `step_*` events are per-scope
- `get_snapshot()` raises `DeviceScanSnapshotNotFoundError` when no persisted raw descriptor rows exist
- `get_snapshot()` returns a valid empty snapshot when raw descriptor rows exist but scan rows do not
- snapshot reads are DB-backed and reflect partial persisted state, not live runtime objects
- snapshot reads use bulk per-table queries rather than per-scope N+1 queries
- snapshot assembly seeds the hierarchy from raw rows once, then attaches scan rows in one pass
- snapshot output ordering is deterministic for endpoints, clusters, attributes, and commands
- snapshot attributes expose `datatype`, canonical raw value, and decoded value when decoding is possible
- skipped manufacturer scope is synthesized with full shape: `manufacturer_code=None`, `progress.status=skipped`, `progress.error_code=missing_raw_manufacturer_code`, and empty `attributes` and `commands`
- snapshot decoding from the canonical stored attribute value representation is correct for standard and manufacturer-scoped rows
- scan applies the fixed internal pacing rule between outbound requests

## Test Diagram

```text
[NEW] app.device_scanner.scan(ieee, resume, force_full)
  |
  +--> validate request args
  |     `--> invalid resume+force_full -> InvalidScanOptionsError
  |
  +--> classify request
  |     +--> exact duplicate same-device -> reuse task
  |     +--> same-device conflict -> ScanInProgressError
  |     `--> different device -> FIFO queue
  |
  +--> scan-level deadline wrapper
  |     +--> timeout before new rows commit -> failed summary + slot release
  |     `--> timeout after new rows commit -> partial summary + slot release
  |
  +--> descriptor refresh via shared helper
  |     +--> Node_Desc_req / Active_EP_req / Simple_Desc_req
  |     +--> atomic raw-row replacement
  |     `--> failure aborts inventory
  |
  +--> build ephemeral raw targets from DB rows
  |
  +--> per refreshed cluster
  |     +--> standard scope -> discovery / reads / command discovery
  |     `--> manufacturer_specific scope
  |           +--> raw manufacturer code present -> normal scan
  |           `--> raw manufacturer code absent -> synthesized skipped scope + missing_raw_manufacturer_code
  |
  `--> summary emission
        +--> success / partial / failed
        `--> stable error_code + human-readable error

[NEW] app.device_scanner.get_snapshot(ieee)
  |
  +--> no raw descriptor rows -> DeviceScanSnapshotNotFoundError
  +--> raw rows but no scan rows -> empty materialized snapshot
  `--> partial/full scan rows -> assembled snapshot
        +--> deterministic ordering
        +--> canonical-value decode
        `--> explicit manufacturer-scope skip visibility
```

## Non-Goals

- automatic scanning during init or rejoin
- endpoint-scoped public scan APIs
- caller override APIs for manufacturer-specific scanning
- using scan results as live runtime cache
- cancel-scan API
- historical snapshot retention or diffing
- quirk-aware scan persistence

## Recommended File Shape

- `zigpy/zigpy/device_scanner.py`
- `zigpy/zigpy/application.py`
- `zigpy/zigpy/device.py`
- `zigpy/zigpy/endpoint.py`
- `zigpy/zigpy/appdb.py`
- `zigpy/zigpy/appdb_schemas/schema_v15.sql`
- `zigpy/tests/test_device_scanner.py`
- `zigpy/tests/test_device.py`
- `zigpy/tests/test_appdb.py`
- `zigpy/tests/test_appdb_migration.py`

## Inline ASCII Diagram Candidates

- `zigpy/zigpy/device_scanner.py`: queue ownership, deadline release, and scan pipeline
- `zigpy/zigpy/appdb.py`: raw descriptor replacement transaction and removed-scope cleanup
- `zigpy/tests/test_device_scanner.py`: descriptor refresh fixture shape when the setup is non-obvious

## Summary

The tight design is:

- on-demand only
- raw on-wire only
- non-invasive at runtime
- descriptor-refresh-first
- shared descriptor discovery logic with normal init
- normalized DB schema
- resumable per cluster scope and per attribute read
- transport via live device, topology via refreshed raw database tables
- explicit machine-readable error codes
- explicit skipped manufacturer-scope visibility

That gives zigpy a proper core device scan instead of a JSON dump helper while keeping the v1 contract explicit and testable.
