# P1 fidelity and input boundaries implementation plan

**Goal:** Fix audit R01/R02/R03 without modifying source files or weakening validation.

**Architecture:** Parse text values before pandas promotion, preserve exact integer columns including nullable values, and reject unsafe mixed numeric promotion. Unit mapping must preserve identity conversions and reject nonrepresentable results. All HDF5 readers inspect container links/storage before dereferencing data.

**Tech stack:** Existing Python 3.12+, pandas, NumPy, Pint, h5py, FastAPI and pytest. No new runtime dependency.

**Spec:** Approved F1/F2 in the 2026-10-02 CPDataKit audit and implementation proposal. The user authorized repair of the recommended first phase. Other audit findings and new features remain outside this change.

## Global constraints

- Base main: f26a97584e6dc8eee415580847a7281ce76c7508. Isolated branch; preserve sibling worktrees.
- No commit, push, release, version change, external file upload or large benchmark.
- Test with synthetic fixtures; never overwrite original input. Keep red/green evidence under ignored `.artifacts/p1-fixes/`.
- Follow test-driven-development: real regression fails before the corresponding production edit; literal independent expectations, not values computed by the implementation.
- Ordinary CSV retains its documented comma/UTF-8/default missing-token inference. Lexical identifiers and customized dialects use explicit CSV confirmation. Document the boundary rather than silently changing all existing text semantics.
- For mixed numeric values, an explicit diagnostic is acceptable when the existing storage contract cannot preserve them; silent integer rounding or nonzero underflow is not.

## Task 1: Safe CSV/JSON values before DataFrame construction

**Files:** `src/cpdatakit/io/_tabular_text.py`, `io/__init__.py`, `tests/test_p1_text_fidelity.py`, `tests/test_p1_ingestion_workflows.py`.

**Interface:** `read_csv_frame(path: Path) -> pd.DataFrame`; `read_json_frame(path: Path) -> pd.DataFrame`. Both raise DataReadError for malformed or unsafe numeric data. Existing `load_dataset(path)` remains the public entry point.

- [ ] Write and run failing tests for CSV/JSON `9007199254740993` with a missing row, uint64 bounds, int/float promotion, nonzero underflow, source preservation and nested JSON arrays.
- [ ] Preserve tokens until each column's representation is chosen. Integral columns use int64/uint64 or pandas nullable equivalents as needed. Mixed numeric columns compare original Python integers without NumPy coercing the comparison; reject value changes with field/record context.
- [ ] Retain normal curve/string/missing-value behavior and correct float parsing; use the same helpers via public load_dataset so CLI, application and Web follow one route.
- [ ] Run targeted reader, validation, scientific conversion and entry-point tests, including unsupported nullable export failing without an output file.

Literal regression expectation:

```python
loaded = load_dataset(source)
assert int(loaded.data["id"].iloc[0]) == 9007199254740993
assert pd.isna(loaded.data["id"].iloc[1])
assert source.read_bytes() == original
```

## Task 2: Precision-safe unit mapping

**Files:** `normalization.py`, shared numeric safety helper if needed, `application/csv_intake.py` for location-preserving errors, `tests/test_p1_unit_precision.py`.

**Interface:** Existing `normalize_dataset(dataset, schema, mappings, drop_unmapped=False)` remains unchanged. Identity/equivalent-unit conversion preserves values and dtype; unsafe nonidentity conversion raises NormalizationError containing field/record.

- [ ] Run red tests showing N→N changes 2^53+1, and 1e-300 ym→m silently becomes zero.
- [ ] Validate shape and unit declarations before conversion; preserve exact identity values, avoid Series construction repromoting nullable integers, and detect nonrepresentable casts/overflow/underflow before publishing a result.
- [ ] Test ordinary scale/offset units, tensors, nullable values, schema validation, and CSV import diagnostics; no unrequested performance redesign.

```python
mapped = normalize_dataset(dataset, schema, [FieldMapping("x", "x", "N", "N")])
assert int(mapped.data["x"].iloc[0]) == 9007199254740993
assert mapped.data["x"].dtype == dataset.data["x"].dtype
```

## Task 3: Self-contained HDF5 inputs

**Files:** `_hdf5_safety.py`, `inspection.py`, `io/__init__.py`, `io/hdf5_v2.py`, `adapters/damask_dadf5.py`, HDF5-backed `formats/netcdf.py`, `tests/test_p1_hdf5_safety.py`.

**Interface:** `assert_self_contained_hdf5(handle: h5py.File) -> None` raises DataReadError before external payload access. Default rejects ExternalLink, external raw storage, VDS and SoftLink; safe HardLinks remain supported and cycles are visited only once.

- [ ] Record red tests using local synthetic external links, group links, raw storage and VDS. Include missing targets so rejection cannot depend on successfully opening the target.
- [ ] Traverse link metadata before object access, track hardlink object identities, inspect storage properties without reading payload.
- [ ] Integrate immediately after file open, including `_prepare_hdf5_read` before any data lookup; cover inspect, full/selected/chunked/v2, DAMASK and HDF5-backed NetCDF.
- [ ] Test valid self-contained files and hardlinks/cycles, blocked input upload with no catalog record/residue, and API/CLI errors; record explicit SoftLink compatibility boundary.

## Task 4: Integration, documentation and independent validation

**Files:** Current format/security/application docs as needed; local verification report under `.artifacts/p1-fixes/`.

- [ ] Run all newly added regressions and affected existing tests after integrating agent changes; inspect each failure before fixing.
- [ ] Run repository-required pytest with coverage, Ruff, formatting and build checks. No claim of remote CI or multi-OS validation.
- [ ] Build wheel/sdist, install the wheel in a clean separate environment, run original audit cases and the installed-browser smoke scripts with synthetic data. Browser testing dependencies stay outside the runtime installation.
- [ ] Independently review both contract satisfaction and implementation hazards; correct actionable findings and rerun affected validation.
- [ ] Confirm original worktree states and source fixture bytes remain unchanged; report final diff, tests and remaining audit scope. Do not commit or publish.

Execution uses the available collaboration tools for independent bounded subtasks; no new user-owned chat or unavailable execution skill is required.
