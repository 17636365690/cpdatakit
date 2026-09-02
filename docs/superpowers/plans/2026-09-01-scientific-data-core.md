# CPDataKit v0.5 Scientific Data Core Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with strict red-green-refactor TDD. Steps
> use checkbox (`- [ ]`) syntax for tracking. The maintainer has required inline execution and has
> prohibited automatic commits, pushes, and pull requests.

**Goal:** Generalize CPDataKit's existing schema-first table contract into a scientific/engineering
data core while preserving crystal plasticity as the first compatible vertical.

**Architecture:** Keep `Dataset`, schema 1.0, and CPDataKit HDF5 1.0 unchanged. Separate bundled
profile lookup from external profile validity, require verified embedded schemas for non-built-in
HDF5 profiles, make generic analysis profile-neutral, and add narrow x-y plotting and adapter
registration seams while retaining all CP-facing functions and commands.

**Tech Stack:** Python 3.10+, pandas, NumPy, Pint, h5py, Matplotlib, argparse, pytest, Hypothesis,
Ruff, Hatchling/build.

**Spec:** `docs/superpowers/specs/2026-09-01-scientific-data-core-design.md`

## Global Constraints

- Preserve every pre-existing tracked and untracked working-tree change as maintainer-owned work.
- Do not run `git reset`, `git checkout`, `git clean`, destructive deletion, commit, push, tag, or PR
  creation.
- Preserve `Dataset`, `DatasetAdapter.load()`, `curve`, `point`, `field2d`, existing CLI syntax and
  exit codes, CPDataKit HDF5 `format_version=1.0`, legacy built-in HDF5 reads, DAMASK behavior, and
  the `cpdatakit` import path.
- Validation reports only declared structural conformance and never physical correctness.
- Do not add xarray, mesh models, new bulk formats, GUI/cloud/database features, physical inference,
  AI interpretation, Abaqus runtime support, solver execution, or dynamic plugin discovery.
- Every behavior change follows RED (expected failure), GREEN (minimal implementation), and focused
  regression verification before the next behavior.
- Replace each template commit step with `git diff --check` and a scoped `git status`; no commits.

---

### Task 1: External profile names and canonical compatibility

**Files:**
- Modify: `src/cpdatakit/schema.py`
- Test: `tests/test_schema.py`
- Test: `tests/test_validation.py`

**Interfaces:**
- Produces: `BUILTIN_PROFILES`, compatibility alias `SUPPORTED_PROFILES`, and `SchemaInput`.
- Preserves: `load_schema()`, `validate_schema()`, `make_profile_schema()`, canonical JSON, and hash
  signatures.

- [ ] Add tests that load a JSON schema whose profile is `thermal-cycle`, validate fully declared
  fields, reject an undeclared field, and assert the three audited built-in SHA-256 literals.
- [ ] Run the new tests and confirm failure is caused by `Unsupported profile 'thermal-cycle'`.
- [ ] Replace profile validity checking with a non-empty-string check; use `BUILTIN_PROFILES` only
  for resource lookup and retain `SUPPORTED_PROFILES` as an alias.
- [ ] Add `Mapping` support to `load_schema()` and align schema-aware annotations through
  `SchemaInput` without removing accepted argument forms.
- [ ] Run schema and validation tests, then `git diff --check`.

### Task 2: Custom-profile HDF5 1.0 with safe legacy behavior

**Files:**
- Modify: `src/cpdatakit/io/__init__.py`
- Test: `tests/test_io.py`

**Interfaces:**
- Consumes: `BUILTIN_PROFILES` and arbitrary validated `ProfileSchema.profile` values.
- Produces: custom-profile HDF5 round trips using the existing `schema_json`/`schema_sha256` pair.

- [ ] Add tests for a `thermal-cycle` HDF5 round trip, rejection of a custom root profile without a
  snapshot, and continued reading of a legacy built-in file without a snapshot.
- [ ] Run those tests and confirm the round trip fails at the root profile whitelist.
- [ ] Require non-empty root profile text; after snapshot verification require a snapshot only when
  the profile is outside `BUILTIN_PROFILES`.
- [ ] Run all I/O, inspection, reporting, and nested-property tests, then `git diff --check`.

### Task 3: Generic statistics with explicit CP compatibility enrichment

**Files:**
- Create: `src/cpdatakit/domains/__init__.py`
- Create: `src/cpdatakit/domains/crystal_plasticity.py`
- Modify: `src/cpdatakit/statistics.py`
- Test: `tests/test_normalization_statistics.py`

**Interfaces:**
- Produces: `summarize_cp_identifiers(dataset: Dataset) -> dict[str, int | str]`.
- Preserves: top-level `unique_grains` and `unique_phases` for built-in profiles only.

- [ ] Add tests showing a custom profile summary has generic scalar statistics but no grain/phase
  keys, a shaped numeric field is not flattened into scalar statistics, and built-in `curve` keeps
  both compatibility keys.
- [ ] Run the tests and confirm the custom summary currently leaks CP keys.
- [ ] Move grain/phase counting to the CP domain helper; merge it only for built-in profiles and
  explicitly mark shaped numeric scalar statistics unavailable.
- [ ] Run normalization/statistics, reporting, comparison, and DAMASK tests, then diff-check.

### Task 4: Schema-driven x-y plotting and CLI

**Files:**
- Modify: `src/cpdatakit/plotting.py`
- Modify: `src/cpdatakit/cli.py`
- Test: `tests/test_plotting.py`
- Test: `tests/test_cli_api_samples.py`

**Interfaces:**
- Produces: `plot_xy(dataset, schema, x, y) -> tuple[Figure, Axes]` in
  `cpdatakit.plotting` and CLI kind `xy` with `--x`/`--y`.
- Preserves: every existing plot kind and output/exit behavior.

- [ ] Add API tests for declared scalar numeric x/y fields, unit-labelled axes, and rejection of
  undeclared, shaped, and non-numeric fields.
- [ ] Add CLI tests for successful PNG output and exit 2 when `--x` or `--y` is missing.
- [ ] Run the focused tests and confirm `plot_xy`/`xy` are absent.
- [ ] Implement paired finite-value extraction, deterministic line plotting, parser options, and
  dispatch with concise `CPDataKitError` failures.
- [ ] Run plotting and all CLI tests, then diff-check.

### Task 5: Backward-compatible adapter descriptors, detection, and registry

**Files:**
- Modify: `src/cpdatakit/adapters/base.py`
- Create: `src/cpdatakit/adapters/registry.py`
- Modify: `src/cpdatakit/adapters/damask_dadf5.py`
- Modify: `src/cpdatakit/adapters/__init__.py`
- Modify: `src/cpdatakit/inspection.py`
- Modify: `src/cpdatakit/reporting.py`
- Test: `tests/test_adapters.py`
- Test: `tests/test_damask_adapter.py`
- Test: `tests/test_inspection.py`

**Interfaces:**
- Produces: immutable `AdapterInfo`, defaulted `DatasetAdapter.info()`/`detect()`,
  `AdapterRegistry.register/get/describe/detect`, and `DEFAULT_ADAPTER_REGISTRY`.
- Preserves: subclasses implementing only `load(path)` and all DAMASK constructor/load behavior.

- [ ] Add tests for an old-style subclass, descriptor defaults, registration/list/lookup/detection,
  duplicate rejection, and DAMASK header detection without implicit loading.
- [ ] Run focused tests and confirm descriptor/registry APIs are absent.
- [ ] Implement the base defaults and isolated registry; register DAMASK and add its non-throwing
  header detector.
- [ ] Route HDF5 format detection and report adapter lookup through the registry while keeping the
  existing DAMASK-specific structural reader and ambiguity errors.
- [ ] Run adapter, DAMASK, inspection, reporting, and CLI report tests, then diff-check.

### Task 6: Reproducible non-CP thermal-cycle example and E2E coverage

**Files:**
- Create: `examples/thermal-cycle/README.md`
- Create: `examples/thermal-cycle/schema/thermal-cycle.json`
- Create: `examples/thermal-cycle/input/thermal-cycle.csv`
- Create: `examples/thermal-cycle/mappings/thermal-cycle.json`
- Create: `tests/test_scientific_data_core.py`
- Create: `tests/test_cli_scientific_example.py`

**Interfaces:**
- Consumes: custom profiles, mapping, HDF5, generic statistics, inspect/report/compare, and xy plot.
- Produces: a checked-in end-to-end scientific/engineering example with no CP fields.

- [ ] Add deterministic schema/input/mapping fixtures and tests that run validate, summary,
  convert, inspect, two JSON reports, compare, and xy plot in `tmp_path`.
- [ ] Run the E2E tests; after Tasks 1–5 they must pass without production changes. If a test fails,
  use the systematic-debugging workflow to identify the owning boundary, add a focused regression
  test for that boundary, observe RED, and fix that boundary before rerunning the E2E test.
- [ ] Run both new E2E tests plus all existing CP CLI, HDF5, DAMASK, and Surfalex tests.

### Task 7: Positioning, architecture, authoring, roadmap, and CI smoke

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/architecture.md`
- Modify: `docs/data-format.md`
- Modify: `docs/adapter-guide.md`
- Modify: `docs/schema-authoring.md`
- Modify: `docs/roadmap.md`
- Modify: `CHANGELOG.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Documents: scientific/engineering schema-first core, CP first vertical, HDF5 snapshot rule,
  adapter registry, thermal-cycle commands, validation scope, and explicit non-goals.

- [ ] Update project description and keywords without changing package name or version.
- [ ] Update English/Chinese positioning while retaining the existing CP quickstart.
- [ ] Document the core/vertical boundary, custom schemas/HDF5, registry semantics, v0.5 roadmap,
  and Unreleased changes without overwriting the in-progress v0.4 content.
- [ ] Add clean-wheel CI smoke commands for custom validation/conversion/xy plotting.
- [ ] Run example E2E tests and metadata tests; run `ruff check .` and `ruff format --check .` and
  report any inherited baseline failure exactly.

### Task 8: Full verification and clean-wheel smoke

**Files:**
- Verify all changed and created files; do not create committed artifacts.

**Interfaces:**
- Produces: real command results for final handoff.

- [ ] Run `pytest`.
- [ ] Run `pytest --cov=cpdatakit` and record total coverage.
- [ ] Run `ruff check .`.
- [ ] Run `ruff format --check .`.
- [ ] Run `python -m build`.
- [ ] Create an isolated temporary virtual environment outside the source tree, install the newly
  built wheel, and execute imports plus existing CP and thermal-cycle validate/convert/inspect/
  report/compare/xy smoke commands.
- [ ] Run `git diff --check`, inspect `git status --short`, enumerate task-owned files, and verify no
  user-owned file was deleted or reverted.
- [ ] Report implemented capability, deferred design, real command output, compatibility risks, and
  v0.6 recommendations without committing or pushing.
