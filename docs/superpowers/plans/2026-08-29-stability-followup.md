# CPDataKit Stability Follow-up Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with a test-first cycle and keep the working tree changes available for review. Release operations follow the maintenance workflow after local verification.

**Goal:** Make native HDF5 inspection preserve duplicate validation across chunk boundaries and verify lower-bound dependency support in CI.

**Architecture:** Keep the public `validate_dataset()` API unchanged. Add a private chunk-stream validator that performs existing per-chunk structural checks and a global duplicate tracker, then make native HDF5 inspection use it. Expand CI and release-maintenance documentation without changing package version or external GitHub state.

**Tech Stack:** Python 3.10+, pandas, NumPy, h5py, pytest, GitHub Actions YAML, Markdown.

**Spec:** `docs/superpowers/specs/2026-08-29-stability-followup-design.md`

## Global Constraints

- Preserve the CPDataKit HDF5 1.0 layout and all existing public function signatures.
- Never load the complete HDF5 table into one DataFrame during inspection.
- Preserve `duplicate_record` as a warning and `duplicate_index` as an error.
- Keep `pyproject.toml` and `CITATION.cff` aligned with the authorized release workflow; artifact and GitHub operations follow their dedicated process.
- Keep benchmark execution diagnostic, with machine-independent evidence rather than timing thresholds.

---

### Task 1: Reproduce the cross-chunk validation bug

**Files:**
- Modify: `tests/test_inspection.py`

**Interfaces:**
- Consumes: `Dataset`, `write_hdf5()`, `inspect_dataset()`, and the existing `curve` schema.
- Produces: Regression tests proving that duplicate index and duplicate record findings survive HDF5 chunk boundaries.

- [ ] **Step 1: Write the failing duplicate-index test**

  Add a test that changes the third `curve` row's `step` to `0`, writes an invalid file with
  `hdf5_chunk_size=2`, monkeypatches `cpdatakit.inspection._INSPECTION_CHUNK_SIZE` to `2`, and
  asserts that schema validation reports `duplicate_index` with `affected_records == 2`.

- [ ] **Step 2: Write the failing duplicate-record test**

  Add a separate test that copies the first `curve` row into the third row, writes it with the same
  two-record boundary, and asserts that schema validation contains a `duplicate_record` warning
  with `affected_records == 2`.

- [ ] **Step 3: Run the focused tests and verify the expected failure**

  Run:

  ```powershell
  $env:PYTHONPATH='src;.venv\Lib\site-packages'
  python -m pytest tests/test_inspection.py -k 'duplicate' -q
  ```

  Expected: the new tests fail because the current chunk-by-chunk inspection returns no global
  duplicate finding.

---

### Task 2: Implement streaming duplicate tracking

**Files:**
- Modify: `src/cpdatakit/validation.py`
- Modify: `src/cpdatakit/inspection.py`
- Test: `tests/test_inspection.py`

**Interfaces:**
- Consumes: the existing field/unit/extension validation helpers and `iter_hdf5_chunks()`.
- Produces: a private chunk validation helper used only by native HDF5 inspection while the public API remains unchanged.

- [ ] **Step 1: Extract shared per-frame validation**

  Move the existing field, unit, and undeclared-field checks behind a private helper that accepts a
  validated `Dataset`, `ProfileSchema`, and `ValidationResult`. Keep `validate_dataset()` calling
  this helper so direct validation retains its current behavior.

- [ ] **Step 2: Add a private duplicate accumulator**

  Track normalized full-row keys and non-missing values for every `index=True, unique=True` field.
  Count keys across all chunks, then append one `duplicate_record` warning for keys occurring more
  than once and one `duplicate_index` error per affected field. Use the same messages, suggestions,
  severities, and affected-record counts as `validate_dataset()`.

- [ ] **Step 3: Add the private chunk-stream validation function**

  Load the schema once, run shared structural checks for each yielded chunk, feed each chunk to the
  accumulator, and finalize duplicate findings after the iterator is exhausted. Do not call the
  public full-frame duplicate logic for each chunk.

- [ ] **Step 4: Route native HDF5 inspection through the helper**

  Replace the per-chunk `validate_dataset()` loop in `_validate_native_hdf5()` with the new private
  stream helper while preserving issue merging and existing CSV/JSON/DADF5 paths.

- [ ] **Step 5: Run the focused tests and verify green**

  Run the same focused pytest command from Task 1. Expected: both new tests pass and existing
  inspection tests remain green.

- [ ] **Step 6: Preserve the pandas 2.0 compatibility floor**

  Keep duplicate normalization implemented through the stable Series-level mapping API and retain
  the compatibility regression test in `tests/test_validation.py`; do not rely on the newer
  DataFrame-level mapping method.

---

### Task 3: Add lower-bound dependency coverage

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the existing `test` matrix and project dependency floors in `pyproject.toml`.
- Produces: a Python 3.10 lower-bound runtime job.

- [ ] **Step 1: Add a lower-bound dependency job**

  On `ubuntu-latest` with Python 3.10, install `numpy>=1.24,<1.25`, `pandas>=2.0,<2.1`,
  `h5py>=3.8,<3.9`, `matplotlib>=3.7,<3.8`, `pint>=0.22,<0.23`, `pytest>=7.4,<8`, and
  `hypothesis>=6.100,<7`, then install the project with `python -m pip install -e . --no-deps`
  and run `pytest`.

- [ ] **Step 2: Validate the workflow syntax and local test command**

  Run the repository's available YAML/quality checks and `pytest` locally. Do not claim remote CI
  success until GitHub executes the changed workflow.

---

### Task 4: Record the remaining acceptance work

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/maintenance.md`

**Interfaces:**
- Consumes: the completed regression fix, CI matrix, existing benchmark script, and adapter guide.
- Produces: release-maintenance notes that are explicit about what is fixed and what remains open.

- [ ] **Step 1: Add an Unreleased changelog entry**

  Record the cross-chunk duplicate validation fix, pandas 2.0 compatibility fix, and lower-bound CI coverage under the
  existing Unreleased sections without changing the 0.2.0 version heading.

- [ ] **Step 2: Update the maintenance checklist**

  Identify the lower-bound dependency job and retain the 100k/1M benchmark commands as diagnostic
  evidence rather than pass/fail timing gates.

- [ ] **Step 3: Check adapter and performance boundaries**

  Confirm the adapter acceptance checklist remains the source of truth for Issue #6 and the
  benchmark commands remain the source of truth for Issue #4. Do not close either issue or claim
  that a first external adapter or broad large-file optimization has been delivered.

---

### Task 5: Verify the complete change

**Files:**
- No additional files.

**Interfaces:**
- Consumes: all changes from Tasks 1-4.
- Produces: fresh local evidence for tests, coverage, lint, build, package boundaries, and benchmark output.

- [ ] **Step 1: Run the full test and quality gates**

  Run the project test suite with the 85% coverage gate, Ruff check, and Ruff format check.

- [ ] **Step 2: Run build and package-boundary checks**

  Build reproducible distributions, verify metadata and Twine checks, and run the clean-wheel smoke
  commands already documented in `docs/maintenance.md`.

- [ ] **Step 3: Run both HDF5 benchmark sizes**

  Run the existing benchmark at 100,000 and 1,000,000 records with a 4096 reader/storage chunk
  size. Confirm valid JSON and exact record counts for full, selected-field, and chunked reads.

- [ ] **Step 4: Inspect the final diff and status**

  Confirm only the approved source, test, CI, changelog, maintenance, spec, and plan files changed;
  leave PRs, releases, version metadata, and external GitHub state untouched.
