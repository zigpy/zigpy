# Raw Device Scan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an on-demand raw on-wire device scan service to zigpy that persists resumable scan state and inventory in the database without mutating live runtime state.

**Architecture:** Add a `DeviceScanner` service on `ControllerApplication` that refreshes raw descriptors first, then scans refreshed raw endpoint and cluster rows using ephemeral scan-only endpoint and cluster objects backed by the live device transport. Extract the raw descriptor walk into shared init-time and scan-time helper logic, persist scan inventory plus checkpoints in new appdb tables, use one canonical stored attribute value representation, and expose a DB-backed snapshot API with explicit error codes, deadline behavior, and manufacturer-scope skip visibility.

**Tech Stack:** Python, asyncio, zigpy ZDO/ZCL APIs, SQLite via `aiosqlite`, pytest

---

### Task 1: Add schema, migration, and runtime persistence wiring

**Files:**
- Create: `zigpy/zigpy/appdb_schemas/schema_v15.sql`
- Modify: `zigpy/zigpy/appdb.py`
- Modify: `zigpy/tests/test_appdb.py`
- Modify: `zigpy/tests/test_appdb_migration.py`
- Test: `zigpy/tests/test_appdb.py`
- Test: `zigpy/tests/test_appdb_migration.py`

**Step 1: Write the failing tests**

Add runtime-persistence tests that assert:

- progress rows preserve `last_error_code` separately from `last_error`
- attribute rows preserve standard and manufacturer-scoped duplicates
- attribute rows persist one canonical raw value field plus datatype metadata
- command rows persist direction separately
- the pending-read index includes `attr_id` in its ordered key shape

Add migration tests that assert:

- `PRAGMA user_version` is incremented
- all new scan tables, columns, the final NULL-safe manufacturer-scope index shape, and exact named secondary indexes exist

**Step 2: Run the tests to verify they fail**

Run: `pytest zigpy/tests/test_appdb.py zigpy/tests/test_appdb_migration.py -k "device_scan or raw_scan" -v`
Expected: FAIL because schema v15 and runtime helpers are not fully wired.

**Step 3: Implement schema v15 and DB helpers**

Add:

- `device_scan_progress_v15`
- `device_scan_attributes_v15`
- `device_scan_commands_v15`

Use the same NULL-safe manufacturer code uniqueness pattern already used by `attributes_cache_v14`; do not add a generated `manufacturer_code_scope_idx` column unless implementation proves the existing pattern is insufficient.

Define these exact secondary indexes:

- `idx_device_scan_progress_v15_ieee`
- `idx_device_scan_attributes_v15_ieee`
- `idx_device_scan_attributes_v15_pending_reads` using the final NULL-safe manufacturer-scope key shape with ordered `(ieee, endpoint_id, cluster_type, cluster_id, read_complete, attr_id)` lookup for pending-readable attributes
- `idx_device_scan_commands_v15_ieee`

Update `zigpy.appdb`:

- bump `DB_VERSION`
- add migration handling
- add explicit async helpers for writing and clearing scan rows
- add explicit helpers for DB-backed snapshot reads using bulk per-table queries for one device
- persist `last_error_code` alongside `last_error`
- store one canonical raw attribute value field instead of parallel raw and normalized columns

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_appdb.py zigpy/tests/test_appdb_migration.py -k "device_scan or raw_scan" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/appdb.py zigpy/zigpy/appdb_schemas/schema_v15.sql zigpy/tests/test_appdb.py zigpy/tests/test_appdb_migration.py
git -C zigpy commit -m "feat: add raw device scan schema"
```

### Task 2: Add failing scanner API tests

**Files:**
- Modify: `zigpy/tests/test_application.py`
- Create: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/zigpy/application.py`
- Create: `zigpy/zigpy/device_scanner.py`

**Step 1: Write the failing tests**

Add tests that assert:

- `ControllerApplication` exposes `device_scanner`
- scans are explicit and not started automatically
- `scan(ieee, resume=True, force_full=True)` fails fast before queue classification
- public contract types exist: `DeviceScanSummary`, `DeviceScanSnapshot`, and `DeviceScanProgressEvent`
- public error types exist: `InvalidScanOptionsError`, `ScanInProgressError`, `DeviceScanTargetMissingError`, and `DeviceScanSnapshotNotFoundError`
- scan progress events use the fixed event names and payload shape
- summary and event payloads include stable `error_code`
- scan progress listeners attach to `app.device_scanner`

**Step 2: Run the tests to verify they fail**

Run: `pytest zigpy/tests/test_application.py zigpy/tests/test_device_scanner.py -k "device_scanner" -v`
Expected: FAIL because `device_scanner` does not exist.

**Step 3: Implement minimal service wiring**

Add:

- wire a `DeviceScanner` placeholder into `ControllerApplication.__init__`
- define `DeviceScanSummary`, `DeviceScanSnapshot`, and `DeviceScanProgressEvent`
- define `InvalidScanOptionsError`, `ScanInProgressError`, `DeviceScanTargetMissingError`, and `DeviceScanSnapshotNotFoundError`
- define one centralized vocabulary for scan event names, statuses, outcomes, steps, and error codes
- define one shared internal step-status vocabulary
- define one private `_emit_progress(...)` helper
- validate `resume` plus `force_full` before queue classification

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_application.py zigpy/tests/test_device_scanner.py -k "device_scanner" -v`
Expected: PASS for wiring tests, FAIL for actual scan behavior tests.

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/application.py zigpy/zigpy/device_scanner.py zigpy/tests/test_application.py zigpy/tests/test_device_scanner.py
git -C zigpy commit -m "feat: add device scanner service wiring"
```

### Task 3: Extract shared raw descriptor helper logic

**Files:**
- Modify: `zigpy/zigpy/device.py`
- Modify: `zigpy/zigpy/endpoint.py`
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/tests/test_device.py`
- Modify: `zigpy/tests/test_device_scanner.py`

**Step 1: Write the failing tests**

Cover:

- scan refresh uses the same raw descriptor walk semantics as normal init
- inactive endpoints keep the same behavior under init and scan refresh
- profile and device-type coercion match between init and scan refresh
- scan refresh does not mutate live runtime endpoint or cluster dictionaries

**Step 2: Run the tests**

Run: `pytest zigpy/tests/test_device.py zigpy/tests/test_device_scanner.py -k "raw_descriptor or descriptor_parity" -v`
Expected: FAIL because the shared raw descriptor helper does not exist yet.

**Step 3: Extract the shared helper**

Implement:

- one shared raw descriptor discovery helper and result shape reused by normal init and scanner refresh
- init-time application of the shared result to live endpoints and clusters
- scan-time reuse of the shared result without mutating live runtime dictionaries

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_device.py zigpy/tests/test_device_scanner.py -k "raw_descriptor or descriptor_parity" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/device.py zigpy/zigpy/endpoint.py zigpy/zigpy/device_scanner.py zigpy/tests/test_device.py zigpy/tests/test_device_scanner.py
git -C zigpy commit -m "refactor: share raw descriptor discovery"
```

### Task 4: Add descriptor refresh, replacement, and raw target building

**Files:**
- Modify: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/zigpy/appdb.py`

**Step 1: Write the failing tests**

Cover:

- scan performs `Node_Desc_req`, `Active_EP_req`, and `Simple_Desc_req` before inventory
- descriptor refresh replaces raw descriptor rows atomically
- removed endpoint and cluster scan scopes are cleared when refresh removes them
- descriptor refresh failure aborts before attribute or command inventory
- descriptor refresh emits the expected step events with `started` then `success` or `failed`
- the shared internal pacing rule is applied between descriptor refresh requests
- raw scan targets are built from refreshed raw DB rows, not live quirked topology
- endpoint `242` is excluded from raw scan targets
- quirk-added endpoints and clusters are ignored
- ephemeral scan objects are not attached to live endpoint dictionaries
- output clusters use the proper cluster role when building scan objects

**Step 2: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "descriptor_refresh or raw_topology or scan_builder" -v`
Expected: FAIL because descriptor refresh and DB-backed target building are not implemented.

**Step 3: Implement descriptor refresh and target building**

Add:

- atomic raw descriptor replacement helpers in `zigpy.appdb`
- removed-scope cleanup for scan rows and progress rows
- fail-closed behavior when descriptor refresh does not complete
- raw scan target extraction from refreshed raw descriptor rows
- exclusion of endpoint `242` from scan target materialization
- a private helper that creates ephemeral scan-only endpoint and cluster objects
- no named proxy classes
- inline ASCII diagrams in `device_scanner.py` and `appdb.py` when the queue and replacement code is non-obvious

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "descriptor_refresh or raw_topology or scan_builder" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/device_scanner.py zigpy/zigpy/appdb.py zigpy/tests/test_device_scanner.py
git -C zigpy commit -m "feat: refresh raw descriptors and build scan targets"
```

### Task 5: Add failing attribute discovery and raw read tests

**Files:**
- Modify: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/tests/test_appdb.py`
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/zigpy/appdb.py`

**Step 1: Write the failing tests**

Cover:

- `Discover_Attribute_Extended` pages persist immediately when supported
- tuple and decoded `foundation.DefaultResponse` unsupported replies are normalized the same way
- `Discover_Attribute_Extended` falls back to `Discover_Attributes` on default-response `UNSUP_GENERAL_COMMAND`
- manufacturer-scoped `Discover_Attribute_Extended` falls back to `Discover_Attributes` on default-response `UNSUP_MANUF_GENERAL_COMMAND`
- if both attribute discovery commands return default-response `UNSUP_GENERAL_COMMAND`, the scan continues with an empty completed discovery step
- if both manufacturer-scoped attribute discovery commands return default-response `UNSUP_MANUF_GENERAL_COMMAND`, the scan continues with an empty completed discovery step
- any other discovery default-response status becomes a terminal scope failure instead of falling through to page parsing
- output-cluster response frames with the wrong ZCL direction bit still resolve the pending request instead of becoming false transport timeouts
- wrong-direction non-response traffic does not resolve pending requests just because the TSN matches
- per-request reply timeouts become scope-local `transport_failure`, not `scan_deadline_exceeded`
- progress cursor advances only after a successful page write
- standard and manufacturer-scoped attribute rows can coexist
- manufacturer scope is skipped when the refreshed raw node descriptor has `None`, even if the live device has manufacturer values or overrides
- shared paging semantics match command discovery semantics
- readable attributes are read with `read_attributes_raw()` in fixed batches of 3
- live attribute cache is unchanged after the scan
- batch transport failure falls back using deterministic binary split semantics
- tuple and decoded `foundation.DefaultResponse` raw-read replies are normalized the same way
- malformed `ReadAttributesResponse` payloads that omit requested attribute IDs are logged, retried one-by-one for only the missing attributes, then persisted as retryable `transport_failure` rows only for any attributes still missing after the one-by-one retry
- split-and-retry operates from an in-memory per-scope target set instead of re-querying every fallback
- per-attribute progress resumes correctly
- deadline expiry during raw reads preserves already committed rows
- attribute read failures report stable `error_code` values
- attribute-read rows keep `read_status`, `last_error_code`, and derived `read_complete` consistent for success, terminal unsupported, and retryable transport failure
- only one canonical raw value field is persisted for reads

**Step 2: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py zigpy/tests/test_appdb.py -k "attribute_discovery or raw_read or device_scan_value" -v`
Expected: FAIL because discovery and raw read persistence are not implemented.

**Step 3: Implement attribute discovery and raw reads**

Implement:

- paged attribute discovery through the shared private page-runner helper
- `Discover_Attribute_Extended` first, then `Discover_Attributes` fallback on default-response `UNSUP_GENERAL_COMMAND`
- manufacturer-scoped discovery uses the same fallback semantics for default-response `UNSUP_MANUF_GENERAL_COMMAND`
- empty completed attribute-discovery persistence when both discovery commands are unsupported
- tuple and decoded `foundation.DefaultResponse` unsupported replies share the same fallback/continue behavior
- non-`UNSUP_GENERAL_COMMAND` discovery default responses take the terminal scope-failure path
- output-cluster compatibility for wrong-direction response frames so request/reply matching does not false-time out
- wrong-direction non-response traffic cannot satisfy pending requests
- discovery request timeouts take the scope-local `transport_failure` path
- shared internal pacing reused for discovery pages
- progress row upserts committed in the same transaction as each successful page
- resolved attribute name only when safe
- read target selection from persisted ACL rows, with standard-discovery fallback rows treated as readable when ACL is unknown
- canonical raw value persistence plus datatype metadata
- tuple and decoded `foundation.DefaultResponse` raw-read replies share the same terminal-read mapping
- deterministic binary split fallback after whole-batch transport failure
- one-by-one retry for only the attribute IDs omitted from an otherwise valid read response
- per-batch transactions for successful persistence
- deadline-aware partial-persistence behavior
- stable `error_code` reporting for read failures
- explicit mapping between `read_status`, `last_error_code`, and derived `read_complete`

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py zigpy/tests/test_appdb.py -k "attribute_discovery or raw_read or device_scan_value" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/device_scanner.py zigpy/zigpy/appdb.py zigpy/tests/test_device_scanner.py zigpy/tests/test_appdb.py
git -C zigpy commit -m "feat: persist raw attribute discovery and reads"
```

### Task 6: Add failing command discovery tests

**Files:**
- Modify: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/zigpy/appdb.py`

**Step 1: Write the failing tests**

Cover:

- received and generated command discovery persists direction correctly
- output clusters use the proper client role
- manufacturer-scoped command discovery runs when a manufacturer code is available
- manufacturer-scoped command discovery is skipped when the refreshed raw node descriptor from this scan has `None`
- the manufacturer-scope skipped reason is visible in progress events
- default-response `UNSUP_GENERAL_COMMAND` during command discovery is logged, persisted as an empty completed page, and does not make the scan partial
- default-response `UNSUP_MANUF_GENERAL_COMMAND` during manufacturer-scoped command discovery is logged, persisted as an empty completed page, and does not make the scan partial
- tuple and decoded `foundation.DefaultResponse` unsupported replies take the same command-discovery path
- non-`UNSUP_GENERAL_COMMAND` command-discovery default responses are terminal scope failures
- manufacturer-scoped command-discovery timeouts retry the same page once with short backoff before surfacing `transport_failure`
- shared paging semantics match attribute discovery semantics

**Step 2: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "command_discovery or output_cluster" -v`
Expected: FAIL because command discovery is incomplete.

**Step 3: Implement command discovery steps**

Implement:

- paged received command discovery through the shared private page-runner helper
- paged generated command discovery through the shared private page-runner helper
- shared internal pacing reused for command discovery pages
- direction-aware persistence
- per-page transactions for rows and progress updates
- default-response `UNSUP_GENERAL_COMMAND` handling that logs and completes the command-discovery direction with no commands
- tuple and decoded `foundation.DefaultResponse` unsupported replies share the same command-discovery skip path
- non-`UNSUP_GENERAL_COMMAND` command-discovery default responses share the same terminal failure path across tuple and decoded forms
- one short retry for manufacturer-scoped command-discovery timeouts before terminal transport failure
- skipped manufacturer-scope event emission with `error_code="missing_raw_manufacturer_code"`

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "command_discovery or output_cluster" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/device_scanner.py zigpy/zigpy/appdb.py zigpy/tests/test_device_scanner.py
git -C zigpy commit -m "feat: persist raw command discovery"
```

### Task 7: Add failing resume and deadline tests

**Files:**
- Modify: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/zigpy/appdb.py`

**Step 1: Write the failing tests**

Cover:

- completed steps are skipped on resume
- incomplete steps resume from stored cursors
- `force_full` clears all scan rows for the device
- duplicate same-device requests reuse the existing task
- conflicting same-device requests raise `ScanInProgressError`
- different-device requests wait in FIFO order for the single global slot
- queued same-device duplicate and conflict behavior matches running-task behavior
- queued scans whose device disappears before execution raise `DeviceScanTargetMissingError`
- caller cancellation detaches the caller wait without cancelling shared queued or running scan work
- deadline expiry before any new scan rows are committed returns `failed`
- deadline expiry after new scan rows are committed returns `partial`
- queue, start, and finish progress events are emitted on `app.device_scanner` in the expected order
- `scan_finished` carries terminal `outcome=success|partial|failed` matching the summary result
- descriptor refresh step events have no scope fields and inventory step events are per-scope
- resumed, partial, or failed scans still return the fixed summary type with correct `outcome` and `error_code`

**Step 2: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "resume or force_full or deadline or device_scanner" -v`
Expected: FAIL because resume and deadline semantics are incomplete.

**Step 3: Implement resume and deadline behavior**

Add:

- device-wide reset helpers
- progress row evaluation
- per-device task dedupe
- conflicting request rejection
- global FIFO queue handling
- missing-device-at-execution failure handling via `DeviceScanTargetMissingError`
- shared task ownership with caller-cancellation detachment
- scan-level deadline wrapper
- fixed internal scan deadline set to 120 seconds
- underlying zigpy per-request reply timeouts are separate from the scan deadline wrapper
- `scan_deadline_exceeded` summary and event reporting
- timeout outcome selection based on whether the timed-out run committed new scan rows

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "resume or force_full or deadline or device_scanner" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/device_scanner.py zigpy/zigpy/appdb.py zigpy/tests/test_device_scanner.py
git -C zigpy commit -m "feat: add resumable raw device scans and deadline handling"
```

### Task 8: Add snapshot retrieval API tests

**Files:**
- Modify: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/zigpy/appdb.py`

**Step 1: Write the failing tests**

Cover:

- `app.device_scanner.get_snapshot(...)` returns a fixed `DeviceScanSnapshot`
- `app.device_scanner.get_snapshot(...)` raises `DeviceScanSnapshotNotFoundError` when no persisted raw descriptor rows exist
- `app.device_scanner.get_snapshot(...)` returns a valid empty snapshot when raw descriptor rows exist but scan rows do not
- the snapshot has stable top-level fields: `ieee`, `raw_node_descriptor`, `last_snapshot_at`, and `endpoints`
- the snapshot hierarchy is `endpoints -> clusters -> standard / manufacturer_specific`
- each scope embeds `progress`, `attributes`, and `commands`
- `standard` is always materialized and `manufacturer_specific` is also materialized when raw manufacturer scope is explicitly skipped
- `last_snapshot_at` is the max persisted timestamp among included rows
- snapshots do not require loading scan tables into live runtime objects
- partial snapshot reads reflect persisted incomplete DB state, not live runtime objects
- snapshot retrieval is a public `DeviceScanner` API rather than a caller-facing `appdb` surface
- progress event scope metadata maps to the same hierarchical snapshot location
- snapshot output ordering is deterministic for endpoints, clusters, attributes, and commands
- snapshot attributes expose `datatype`, canonical raw value, and decoded value when decoding is possible
- skipped manufacturer scope includes `manufacturer_code=None`, `progress.status="skipped"`, `progress.error_code="missing_raw_manufacturer_code"`, and empty `attributes` and `commands`

**Step 2: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "snapshot" -v`
Expected: FAIL because snapshot retrieval is missing.

**Step 3: Implement snapshot getter**

Add a public `DeviceScanner` snapshot API backed by a DB read path that assembles a fixed hierarchical `DeviceScanSnapshot` from:

- raw device identifiers
- raw endpoints and clusters
- discovered attributes
- discovered commands
- per-scope progress state

Use:

- one bulk query per relevant table for the target IEEE
- low-level per-table scan rows from `appdb`
- seed the endpoint and cluster hierarchy from raw rows in one pass
- then attach progress, attributes, and commands from scan rows in one pass
- the shared internal scope identity helper to place rows under the correct endpoint, cluster, and scope
- in-memory assembly of the merged hierarchical snapshot in `DeviceScanner`
- canonical ordering for endpoints, clusters, attributes, and commands
- single-pass decode of canonical stored attribute values during assembly with reused metadata per cluster or type
- synthesized skipped manufacturer scope materialization from raw descriptor state instead of silent omission or persisted skipped progress rows

**Step 4: Run the tests**

Run: `pytest zigpy/tests/test_device_scanner.py -k "snapshot" -v`
Expected: PASS

**Step 5: Commit**

```bash
git -C zigpy add zigpy/zigpy/device_scanner.py zigpy/zigpy/appdb.py zigpy/tests/test_device_scanner.py
git -C zigpy commit -m "feat: add raw device scan snapshot retrieval"
```

### Task 9: Run focused verification and polish

**Files:**
- Modify: `zigpy/zigpy/device_scanner.py`
- Modify: `zigpy/zigpy/appdb.py`
- Modify: `zigpy/zigpy/device.py`
- Modify: `zigpy/zigpy/endpoint.py`
- Modify: `zigpy/tests/test_device_scanner.py`
- Modify: `zigpy/tests/test_appdb.py`
- Modify: `zigpy/tests/test_appdb_migration.py`
- Modify: `zigpy/tests/test_application.py`
- Modify: `zigpy/tests/test_device.py`

**Step 1: Run the focused suites**

Run:

```bash
pytest zigpy/tests/test_device_scanner.py -v
pytest zigpy/tests/test_appdb.py -k "device_scan or raw_scan" -v
pytest zigpy/tests/test_appdb_migration.py -k "device_scan or raw_scan" -v
pytest zigpy/tests/test_application.py -k "device_scanner" -v
pytest zigpy/tests/test_device.py -k "raw_descriptor or device_scanner" -v
```

Expected: PASS

**Step 2: Fix any failures with minimal changes**

Prefer:

- small test corrections only when behavior is clearly correct
- minimal production changes
- no extra options or abstractions not required by the design
- tests that assert `error_code` rather than human-readable message text
- preserving the single canonical value-storage rule

**Step 3: Run a broader regression pass**

Run:

```bash
pytest zigpy/tests/test_appdb.py zigpy/tests/test_appdb_migration.py zigpy/tests/test_application.py zigpy/tests/test_device.py zigpy/tests/test_endpoint.py zigpy/tests/test_device_scanner.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git -C zigpy add zigpy/zigpy/device_scanner.py zigpy/zigpy/application.py zigpy/zigpy/device.py zigpy/zigpy/endpoint.py zigpy/zigpy/appdb.py zigpy/zigpy/appdb_schemas/schema_v15.sql zigpy/tests/test_device_scanner.py zigpy/tests/test_appdb.py zigpy/tests/test_appdb_migration.py zigpy/tests/test_application.py zigpy/tests/test_device.py
git -C zigpy commit -m "feat: add resumable raw device scan service"
```
