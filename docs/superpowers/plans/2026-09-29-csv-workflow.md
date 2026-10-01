# Real CSV Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete the approved real CSV import, confirmation, ordered conversion and report workflow.

**Architecture:** Add an explicit bounded CSV intake service alongside existing readers, and a separate workbench route module. Store original bytes and reviewed declarations in an immutable per-import folder and register schema/data together. Reuse verified existing conversion snapshots as inputs, rather than copying caller-selected output paths.

**Tech Stack:** Python 3.12+, pandas, Pint, h5py, FastAPI, SQLite, vanilla browser modules, pytest.

**Spec:** `docs/superpowers/specs/2026-09-29-csv-workflow.md`

## Global Constraints

- Python >=3.12; retain existing dependency ranges and version 0.9.3 during development.
- No NetCDF3/datetime expansion, solver work, training, release, commit or push in this scope.
- Use the available collaboration tools and TDD workflow in this session; preserve red/green evidence under `.artifacts/csv-workflow/`.
- User approval is already given for this scope. Do not repeat permission gates or commit changes automatically.

## Task 1: Ordered HDF5

Files: `src/cpdatakit/io/__init__.py`, `tests/test_hdf5_column_order.py`.

- [x] Add a failing round-trip using columns `z,a,m,user_extra`, explicit selection and chunk reads. Assert literal column sequences and exact per-field values.
- [x] Run `.venv/Scripts/python -m pytest tests/test_hdf5_column_order.py -q`, preserve red output.
- [x] Enable native HDF5 group creation order with `handle.create_group("data", track_order=True)`; retain legacy read behavior.
- [x] Run new tests and existing HDF5 selection/fidelity tests; preserve green output.

## Task 2: Explicit CSV intake core

Files: new `src/cpdatakit/application/csv_intake.py`, `tests/test_csv_intake.py`.

Interfaces:
```python
preview_csv(payload: bytes, options: dict | None = None, *, max_bytes=67108864, max_rows=100000) -> dict
prepare_csv(payload: bytes, options: dict, columns: list[dict], *, profile="imported-csv", source_name="source.csv", source_sha256=None, max_bytes=67108864, max_rows=100000) -> CsvPrepared
# CsvPrepared.value: Dataset; .schema: ProfileSchema; .manifest: dict
```

- [x] Write tests with literal semicolon/BOM/unit-row/decimal-comma data, unnamed and duplicate headers, explicit exclusions and N→kN expectations. Add integer precision, row width, missing-unit and size-limit failures.
- [x] Run tests red before service implementation.
- [x] Parse by column index; expose bounded samples and unit suggestions only. Validate all choices and produce a normalized Dataset, reviewed schema and source manifest.
- [x] Run tests green and retain command output.

## Task 3: Verified artifacts as inputs

Files: new `src/cpdatakit/web/artifact_inputs.py`, `tests/test_artifact_inputs.py`, targeted catalog helpers in `src/cpdatakit/catalog/sqlite.py`.

Interfaces:
```python
install_artifact_inputs(app, *, require_csrf)
# POST /api/projects/{project_id}/artifacts/{artifact_id}/use-as-input
# -> {dataset_id, schema_selector, artifact_id, filename}
```

- [x] First test conversion→reuse→report against a real local app; exercise source overwrite, repeated/concurrent reuse, cross-project requests, unsupported artifact kinds, tampering and CSRF.
- [x] Preserve red output, then implement snapshot/hash/schema checks and atomic idempotent catalog binding.
- [x] Test green; do not modify browser files owned by the integrating agent.

## Task 4: CSV web transaction and confirmation table

Files: new `web/csv_workflow.py`, `web/static/csv-intake.js`, `tests/test_csv_workflow.py`; modify `web/app.py`, `web/templates/project.html`, `web/static/app.js`, `web/static/style.css`.

Interfaces:
```python
install_csv_workflow(app, *, require_csrf)
# POST /api/projects/{project_id}/csv-preview: file, options_json
# POST /api/projects/{project_id}/csv-import: file, options_json, columns_json, source_sha256, confirmed
# -> {dataset_id, schema_selector, status, operation, value, validation, provenance}
catalog.register_csv_import(project_id, *, data_path, data_sha256, schema_path, schema_sha256, schema_name, metadata)
# -> (DatasetRecord, SchemaRecord), one transaction
```

- [x] Add endpoint tests with 2 source rows: `[0,100,7,20,0]` and `[1,200,8,40,0.01]`. Confirm one exclusion, preserve raw bytes and map N→kN to `[0.1,0.2]`. Assert report values, metadata and project data registration.
- [x] Add no-confirmation, changed source hash, unresolved units, unsafe upload directory, size limits and catalog failure tests. Observe endpoint 404 red baseline before route implementation.
- [x] Save source/schema/data/manifest in a private staged folder, publish to a fresh UUID path, atomically register, retain uncertain failure evidence without exposing an incomplete success.
- [x] Build settings/preview/confirmation controls with textContent and explicit includes, names, dtypes, roles and units. Reset review on changed file/settings. Require source confirmation and a convention description; store confirmation settings.
- [x] Add result reuse buttons, refresh selected dataset and its schema, clear obsolete mapping, and explain which stored input a report uses.
- [x] Test backend green and exercise browser interactions against real uploads.

## Task 5: Acceptance, documentation and review

Files: `docs/workbench-guide.md`, `docs/quickstart.md`, `docs/verification/2026-09-29-csv-workflow.md`, relevant README/changelog only as needed.

- [x] Run targeted regression tests, then full pytest suite, lint, format and diff checks.
- [x] Run local IN718 12-file acceptance without vendoring data; independently compare rows, values, units, ordering and source hashes.
- [x] Run browser from original raw curve through confirmation and report, then conversion→reuse→report. Include missing-unit and changed-options behavior.
- [x] Independent review of schema/units, transactional safety and stale UI state; repair findings with failing tests.
- [x] Save evidence and describe remaining boundaries, including legacy HDF5 order and the deferred multidimensional milestone. Leave changes local for user review.
