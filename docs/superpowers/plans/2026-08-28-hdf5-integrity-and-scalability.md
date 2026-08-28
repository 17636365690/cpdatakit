# HDF5 Integrity and Scalable Reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden CPDataKit HDF5 boundaries, add explicit partial/chunk reads, make FieldSchema collection fields immutable, and close the validated v0.2.0 maintenance gaps.

**Architecture:** Keep load_dataset(path) as the stable full-read entry point and move HDF5-specific selection into load_hdf5() plus iter_hdf5_chunks(). Share one strict metadata parser between all HDF5 read paths, and make the writer use a same-directory temporary file followed by atomic replacement. Keep schema JSON wire output unchanged while freezing in-memory collection fields.

**Tech Stack:** Python 3.10+, h5py, NumPy, pandas, pytest, Hypothesis, Ruff, Hatchling, GitHub CLI.

**Spec:** docs/superpowers/specs/2026-08-28-hdf5-integrity-and-scalability-design.md

## Global Constraints

- HDF5 readers require format, format_version, profile, schema_version, units_json, field_mapping_json, provenance_json, and validation_summary_json.
- format_version and schema_version must equal 1.0; unsupported or malformed metadata raises DataReadError.
- write_hdf5() defaults to allow_invalid=False; invalid output requires explicit allow_invalid=True.
- Existing load_dataset(path) full-read behavior remains unchanged.
- New partial reads use load_hdf5() and iter_hdf5_chunks(); CSV and JSON do not receive ambiguous partial-read arguments.
- FieldSchema.shape, components, and aliases are tuples in memory and lists in serialized JSON.
- HDF5 writes are atomic and clean their temporary file on every serialization failure.
- No solver-specific adapter, ODB/DADF5 support, schema migration, scientific inference, new storage format, or release/version bump is introduced.
- Core dependencies remain unchanged.

---

### Task 1: Add strict HDF5 envelope validation

**Files:**
- Modify: src/cpdatakit/io/__init__.py
- Test: tests/test_io.py

**Interfaces:**
- Produces private helper _read_hdf5_metadata(handle: h5py.File, path: Path) -> dict[str, Any].
- Keeps load_dataset(path) as the public full-read entry point.

- [ ] **Step 1: Write failing tests for missing and malformed metadata**

Add a helper that writes a two-row data/step dataset plus the complete metadata set, then remove or corrupt one attribute:

~~~python
def _write_minimal_cpdatakit_hdf5(path: Path, attrs: dict[str, object] | None = None) -> None:
    defaults = {
        "format": "CPDataKit",
        "format_version": "1.0",
        "profile": "curve",
        "schema_version": "1.0",
        "units_json": "{}",
        "field_mapping_json": "{}",
        "provenance_json": "{}",
        "validation_summary_json": '{"valid": true, "error_count": 0, "warning_count": 0}',
    }
    defaults.update(attrs or {})
    with h5py.File(path, "w") as handle:
        for name, value in defaults.items():
            handle.attrs[name] = value
        handle.create_group("data").create_dataset("step", data=[0, 1])


@pytest.mark.parametrize(
    "attribute",
    [
        "format_version",
        "profile",
        "schema_version",
        "units_json",
        "field_mapping_json",
        "provenance_json",
        "validation_summary_json",
    ],
)
def test_hdf5_requires_complete_metadata(tmp_path: Path, attribute: str) -> None:
    path = tmp_path / f"missing-{attribute}.h5"
    _write_minimal_cpdatakit_hdf5(path)
    with h5py.File(path, "r+") as handle:
        del handle.attrs[attribute]
    with pytest.raises(DataReadError, match="metadata"):
        load_dataset(path)


@pytest.mark.parametrize(
    "attrs",
    [
        {"format_version": "2.0"},
        {"schema_version": "2.0"},
        {"profile": "unknown"},
        {"units_json": "[]"},
        {"field_mapping_json": "not-json"},
        {"provenance_json": 7},
    ],
)
def test_hdf5_rejects_invalid_metadata(tmp_path: Path, attrs: dict[str, object]) -> None:
    path = tmp_path / "invalid-metadata.h5"
    _write_minimal_cpdatakit_hdf5(path, attrs)
    with pytest.raises(DataReadError, match="metadata"):
        load_dataset(path)
~~~

- [ ] **Step 2: Run the focused tests and verify the expected red state**

Run:

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py -k "complete_metadata or invalid_metadata" -q
~~~

Expected: FAIL because the current reader supplies defaults for missing JSON attributes and does not validate versions, profiles, attribute types, or decoded JSON object shape.

- [ ] **Step 3: Implement one strict metadata parser**

In src/cpdatakit/io/__init__.py:

1. Import SUPPORTED_SCHEMA_VERSION and SUPPORTED_PROFILES from schema.py.
2. Add _required_text_attr(handle, name, path) that checks attribute presence, accepts str or UTF-8 bytes, and raises DataReadError for other types or decode failures.
3. Add _required_json_object(handle, name, path) that parses the required text attribute with json.loads() and requires a dict result.
4. Add _read_hdf5_metadata() that validates the exact marker and versions, validates profile against SUPPORTED_PROFILES, parses all four JSON objects, and returns the existing metadata keys.
5. Replace the current .get(..., default) metadata block in _read_hdf5() with the helper.

The helper must preserve the current public metadata shape: profile, schema_version, units, field_mapping, provenance, and validation_summary.

- [ ] **Step 4: Run the focused and existing I/O tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py -q
~~~

Expected: all I/O tests pass, including the new metadata cases.

- [ ] **Step 5: Commit the strict-reader change**

~~~powershell
git add src/cpdatakit/io/__init__.py tests/test_io.py
git commit -m "fix: validate CPDataKit HDF5 metadata"
~~~

### Task 2: Add explicit field, range, and chunked HDF5 reads

**Files:**
- Modify: src/cpdatakit/io/__init__.py
- Modify: src/cpdatakit/__init__.py
- Test: tests/test_io.py

**Interfaces:**
- Produces load_hdf5(path, *, fields=None, start=None, stop=None) -> Dataset.
- Produces iter_hdf5_chunks(path, *, fields=None, chunk_size=10_000) -> Iterator[Dataset].
- load_dataset(path) delegates .h5 and .hdf5 paths to load_hdf5(path).

- [ ] **Step 1: Write failing tests for selection, slicing, and lazy chunks**

Create a valid five-row HDF5 fixture through write_hdf5(), then add this helper and the tests:

~~~python
def _make_test_hdf5(tmp_path: Path, rows: int) -> Path:
    schema = load_schema("curve")
    dataset = Dataset(
        pd.DataFrame(
            {
                "step": list(range(rows)),
                "strain": [index / 100 for index in range(rows)],
                "stress": [index * 10.0 for index in range(rows)],
            }
        ),
        {"units": {"step": "1", "strain": "1", "stress": "MPa"}},
    )
    output = tmp_path / "read-fixture.h5"
    write_hdf5(dataset, output, schema, validate_dataset(dataset, schema))
    return output
~~~

~~~python
def test_load_hdf5_selects_fields_and_half_open_range(tmp_path: Path) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    selected = load_hdf5(path, fields=["stress", "step"], start=1, stop=4)
    assert list(selected.data.columns) == ["stress", "step"]
    assert selected.data["step"].tolist() == [1, 2, 3]
    assert selected.metadata["profile"] == "curve"


def test_iter_hdf5_chunks_reads_each_chunk_with_metadata(tmp_path: Path) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    chunks = list(iter_hdf5_chunks(path, fields=["step"], chunk_size=2))
    assert [len(chunk.data) for chunk in chunks] == [2, 2, 1]
    assert [chunk.data["step"].tolist() for chunk in chunks] == [[0, 1], [2, 3], [4]]
    assert all(chunk.metadata["profile"] == "curve" for chunk in chunks)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fields": []},
        {"fields": ["missing"]},
        {"start": -1},
        {"start": 4, "stop": 3},
        {"stop": 6},
    ],
)
def test_hdf5_read_rejects_invalid_selection(tmp_path: Path, kwargs: dict[str, object]) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    with pytest.raises(DataReadError):
        load_hdf5(path, **kwargs)


@pytest.mark.parametrize("chunk_size", [0, -1, True])
def test_hdf5_chunk_size_must_be_positive_integer(tmp_path: Path, chunk_size: object) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    with pytest.raises(DataReadError):
        list(iter_hdf5_chunks(path, chunk_size=chunk_size))
~~~

- [ ] **Step 2: Run the new tests and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py -k "load_hdf5 or iter_hdf5 or selection or chunk_size" -q
~~~

Expected: FAIL because neither HDF5-specific function exists.

- [ ] **Step 3: Implement shared bounded HDF5 reading**

In src/cpdatakit/io/__init__.py:

1. Import Iterable and Iterator from collections.abc.
2. Add _normalize_hdf5_fields(group, fields) that preserves caller order, rejects a string passed as the iterable itself, rejects empty selections, and raises DataReadError for unknown names.
3. Add _resolve_hdf5_bounds(record_count, start, stop) that rejects booleans and non-integers, enforces 0 <= start <= stop <= record_count, and returns a half-open pair.
4. Refactor field conversion into _read_hdf5_columns(group, names, start, stop); every dataset must be non-scalar and is read with item[start:stop], never item[()]. Decode byte strings and preserve shaped per-record values.
5. Add load_hdf5() that calls _ensure_readable(), opens the file, calls _read_hdf5_metadata(), validates the data group and record counts, resolves fields and bounds, builds a DataFrame, and returns Dataset(frame, metadata, path).
6. Add iter_hdf5_chunks() as a generator. It keeps the file open only during iteration, parses metadata once, resolves selection and total count before the first yield, and yields Dataset chunks for offset:min(offset + chunk_size, stop).
7. Make _read_hdf5() a compatibility wrapper around load_hdf5(path), or remove it after all references are updated.
8. Export load_hdf5 and iter_hdf5_chunks from src/cpdatakit/__init__.py.

- [ ] **Step 4: Run focused and complete tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py tests/test_cli_api_samples.py -q
& .\.venv\Scripts\python.exe -m pytest -q
~~~

Expected: all tests pass and existing load_dataset() callers remain unchanged.

- [ ] **Step 5: Commit the read API**

~~~powershell
git add src/cpdatakit/io/__init__.py src/cpdatakit/__init__.py tests/test_io.py
git commit -m "feat: add bounded and chunked HDF5 reads"
~~~

### Task 3: Reject invalid output and make HDF5 writes atomic

**Files:**
- Modify: src/cpdatakit/exceptions.py
- Modify: src/cpdatakit/io/__init__.py
- Test: tests/test_io.py

**Interfaces:**
- Produces DataValidationError(CPDataKitError).
- Extends write_hdf5(..., allow_invalid: bool = False) -> Path.

- [ ] **Step 1: Write failing tests for invalid-output policy and cleanup**

Add tests with an invalid ValidationResult:

~~~python
def test_write_hdf5_rejects_invalid_validation_by_default(curve_csv: Path, tmp_path: Path) -> None:
    dataset = load_dataset(curve_csv)
    schema = load_schema("curve")
    result = validate_dataset(dataset.data.drop(columns=["stress"]), schema)
    output = tmp_path / "invalid.h5"
    with pytest.raises(DataValidationError):
        write_hdf5(dataset, output, schema, result)
    assert not output.exists()


def test_write_hdf5_allows_explicit_invalid_output(curve_csv: Path, tmp_path: Path) -> None:
    dataset = load_dataset(curve_csv)
    schema = load_schema("curve")
    result = validate_dataset(dataset.data.drop(columns=["stress"]), schema)
    output = tmp_path / "invalid-allowed.h5"
    write_hdf5(dataset, output, schema, result, allow_invalid=True)
    assert load_dataset(output).metadata["validation_summary"]["valid"] is False


def test_write_hdf5_removes_temp_file_after_serialization_failure(tmp_path: Path) -> None:
    schema = load_schema("point")
    dataset = Dataset(pd.DataFrame({"point_id": [0, 1], "vector": [[1.0, 2.0], [3.0]]}))
    result = validate_dataset(dataset, schema)
    output = tmp_path / "broken.h5"
    with pytest.raises(DataReadError, match="inconsistent array shapes"):
        write_hdf5(dataset, output, schema, result, allow_invalid=True)
    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.*")) == []
~~~

- [ ] **Step 2: Run the focused tests and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py -k "invalid_output or temp_file or explicit_invalid" -q
~~~

Expected: FAIL because the writer currently writes invalid results and writes directly to the target path.

- [ ] **Step 3: Implement the exception and atomic writer**

1. Add this exception in src/cpdatakit/exceptions.py:

~~~python
class DataValidationError(CPDataKitError):
    """Raised when invalid data is passed to a protected output operation."""
~~~

2. Add allow_invalid=False after force in write_hdf5() and reject an invalid result before creating a temporary file:

~~~python
if not validation.valid and not allow_invalid:
    raise DataValidationError(
        "Cannot write a dataset with validation errors; pass allow_invalid=True explicitly"
    )
~~~

3. Create the target parent, call tempfile.mkstemp(prefix=f".{target.name}.", suffix=target.suffix, dir=target.parent), close the descriptor, write the complete HDF5 file to that temporary path, close h5py, then call os.replace(temp_path, target).
4. Wrap the temporary path lifecycle in try/except BaseException; call Path.unlink(missing_ok=True) if the temporary path still exists, then re-raise.
5. Keep the current force check before creating the temporary file and preserve all existing metadata and dataset serialization behavior.

- [ ] **Step 4: Run I/O, CLI, and failure-path tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py tests/test_cli_api_samples.py tests/test_cli_mapping.py -q
~~~

Expected: all tests pass, including overwrite protection and atomic-output cases.

- [ ] **Step 5: Commit the safe writer**

~~~powershell
git add src/cpdatakit/exceptions.py src/cpdatakit/io/__init__.py tests/test_io.py
git commit -m "fix: protect HDF5 output integrity"
~~~

### Task 4: Make FieldSchema collection fields immutable

**Files:**
- Modify: src/cpdatakit/schema.py
- Modify: tests/test_schema.py
- Modify: tests/test_io.py

- [ ] **Step 1: Write failing immutability and serialization tests**

Add:

~~~python
def test_field_schema_normalizes_collection_fields_to_tuples() -> None:
    field = FieldSchema(
        "stress",
        "float",
        shape=[2],
        components=["x", "y"],
        aliases=["sigma"],
        unit="MPa",
    )
    assert field.shape == (2,)
    assert field.components == ("x", "y")
    assert field.aliases == ("sigma",)
    with pytest.raises(AttributeError):
        field.shape += (3,)
    with pytest.raises(AttributeError):
        field.components.append("z")


def test_schema_json_keeps_collection_fields_as_lists() -> None:
    schema = make_profile_schema(
        "point",
        [make_field_schema("vector", "float", shape=[2], components=["x", "y"], unit="MPa")],
    )
    payload = schema_to_dict(schema)
    assert payload["fields"][0]["shape"] == [2]
    assert payload["fields"][0]["components"] == ["x", "y"]
~~~

Update any existing test that compares a loaded component collection to a list so it asserts the tuple-backed in-memory value while retaining list assertions for serialized JSON.

- [ ] **Step 2: Run the new tests and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_schema.py -k "tuple or collection_fields" -q
~~~

Expected: FAIL because direct FieldSchema construction currently preserves mutable lists.

- [ ] **Step 3: Implement tuple normalization without changing the JSON contract**

1. Change FieldSchema annotations/defaults to tuple[int, ...], tuple[str, ...], and tuple[str, ...].
2. Add frozen-dataclass __post_init__() using object.__setattr__() to convert list inputs for shape, components, and aliases to tuples, including direct construction.
3. Update _validate_field() to validate tuple-backed values.
4. Keep make_field_schema() iterable-friendly by materializing each iterable before construction.
5. Keep schema_to_dict() converting the tuple fields back to JSON lists.

- [ ] **Step 4: Run schema, validation, and nested-field tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_schema.py tests/test_validation.py tests/test_nested_properties.py -q
~~~

Expected: all tests pass with immutable in-memory schema collections and unchanged JSON round-trips.

- [ ] **Step 5: Commit schema immutability**

~~~powershell
git add src/cpdatakit/schema.py tests/test_schema.py tests/test_io.py
git commit -m "fix: make field schema collections immutable"
~~~

### Task 5: Fill remaining high-risk regression tests

**Files:**
- Create: tests/test_adapters.py
- Modify: tests/test_cli_mapping.py
- Modify: tests/test_validation.py
- Modify: tests/test_nested_properties.py

**Interfaces:**
- Tests only; no new production adapter is introduced.

- [ ] **Step 1: Add adapter abstraction tests**

Create tests/test_adapters.py:

~~~python
from pathlib import Path

import pandas as pd
import pytest

from cpdatakit.adapters import DatasetAdapter
from cpdatakit.model import Dataset


def test_dataset_adapter_is_abstract() -> None:
    with pytest.raises(TypeError):
        DatasetAdapter()


def test_dataset_adapter_load_contract_returns_dataset(tmp_path: Path) -> None:
    class FixtureAdapter(DatasetAdapter):
        def load(self, path: Path) -> Dataset:
            return Dataset(pd.DataFrame({"source": [path.name]}), {"units": {}})

    result = FixtureAdapter().load(tmp_path / "fixture.dat")
    assert isinstance(result, Dataset)
    assert result.data["source"].tolist() == ["fixture.dat"]
~~~

- [ ] **Step 2: Add explicit failure-path assertions**

Add these explicit failure-path tests, keeping any existing tests that cover the same behavior:

~~~python
def test_cli_returns_two_for_unit_conversion_failure(tmp_path: Path, capsys) -> None:
    data, mapping = _write_input_and_mapping(tmp_path)
    mapping.write_text(
        '{"mappings":[{"source":"stress","target":"stress",'
        '"input_unit":"meter","output_unit":"MPa"}]}',
        encoding="utf-8",
    )
    assert main(["validate", str(data), "--schema", "curve", "--mapping", str(mapping)]) == 2
    assert "Cannot convert" in capsys.readouterr().err


def test_cli_returns_one_for_invalid_data(tmp_path: Path, capsys) -> None:
    data = tmp_path / "invalid.csv"
    data.write_text("step,strain,stress\n-1,0.0,0.0\n", encoding="utf-8")
    assert main(["validate", str(data), "--schema", "curve"]) == 1
    assert "below_minimum" in capsys.readouterr().out


def test_mapping_rejects_unknown_key(tmp_path: Path, capsys) -> None:
    data, _ = _write_input_and_mapping(tmp_path)
    mapping = tmp_path / "unknown-key.json"
    mapping.write_text(
        '{"mappings":[{"source":"increment","target":"step","infer":true}]}',
        encoding="utf-8",
    )
    assert main(["validate", str(data), "--schema", "curve", "--mapping", str(mapping)]) == 2
    assert "unsupported keys" in capsys.readouterr().err


def test_invalid_schema_version_is_rejected(tmp_path: Path) -> None:
    schema = tmp_path / "unsupported.json"
    schema.write_text('{"profile":"curve","schema_version":"2.0","fields":[]}', encoding="utf-8")
    with pytest.raises(SchemaError, match="Unsupported schema version"):
        load_schema(schema)


def test_nested_schema_rejects_unsupported_dtype(tmp_path: Path) -> None:
    schema = tmp_path / "unsupported-dtype.json"
    schema.write_text(
        '{"profile":"point","schema_version":"1.0","fields":['
        '{"name":"vector","dtype":"decimal","shape":[2],"unit":"1"}]}',
        encoding="utf-8",
    )
    with pytest.raises(SchemaError, match="unsupported dtype"):
        load_schema(schema)
~~~

- [ ] **Step 3: Run targeted coverage tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_adapters.py tests/test_cli_mapping.py tests/test_validation.py tests/test_nested_properties.py -q
~~~

Expected: PASS with the high-risk branches covered.

- [ ] **Step 4: Commit the regression suite**

~~~powershell
git add tests/test_adapters.py tests/test_cli_mapping.py tests/test_validation.py tests/test_nested_properties.py
git commit -m "test: cover high-risk validation and adapter paths"
~~~

### Task 6: Add the deterministic HDF5 read benchmark

**Files:**
- Create: scripts/benchmark_hdf5_read.py

**Interfaces:**
- CLI command: python scripts/benchmark_hdf5_read.py --records N --chunk-size N --output-dir PATH.
- Generates deterministic HDF5 data, measures full/selected/chunked reads, and prints elapsed seconds plus peak RSS in MiB.

- [ ] **Step 1: Write the benchmark smoke-test command**

Run before implementation:

~~~powershell
& .\.venv\Scripts\python.exe scripts/benchmark_hdf5_read.py --help
~~~

Expected: FAIL because the script does not exist.

- [ ] **Step 2: Implement the benchmark script**

Use argparse, tempfile.TemporaryDirectory when output-dir is omitted, NumPy default_rng(0), time.perf_counter(), and resource where available. Generate a valid curve Dataset through the public writer, then measure:

~~~python
load_hdf5(path)
load_hdf5(path, fields=["step", "stress"])
list(iter_hdf5_chunks(path, fields=["step", "stress"], chunk_size=args.chunk_size))
~~~

Print JSON with records, chunk_size, and one result object per mode. If resource is unavailable on Windows, print peak_rss_mib: null. Do not add a runtime dependency or run the script from normal pytest.

- [ ] **Step 3: Run the smoke benchmark**

~~~powershell
& .\.venv\Scripts\python.exe scripts/benchmark_hdf5_read.py --records 10000 --chunk-size 1024
~~~

Expected: valid JSON, matching record counts, and no leftover temporary file.

- [ ] **Step 4: Commit the benchmark**

~~~powershell
git add scripts/benchmark_hdf5_read.py
git commit -m "perf: add HDF5 read benchmark"
~~~

### Task 7: Update user documentation and changelog

**Files:**
- Modify: docs/data-format.md
- Modify: docs/quickstart.md
- Modify: docs/adapter-guide.md
- Modify: docs/roadmap.md
- Modify: CHANGELOG.md

- [ ] **Step 1: Document strict metadata and writer policy**

State that all eight root attributes are required, JSON attributes must be objects, 1.0 markers are rejected when missing or unsupported, and invalid validation results are not written unless allow_invalid=True is explicit.

- [ ] **Step 2: Document the new read APIs**

Add this quickstart example:

~~~python
from cpdatakit.io import iter_hdf5_chunks, load_hdf5

window = load_hdf5("curve.h5", fields=["step", "stress"], start=10, stop=20)
for chunk in iter_hdf5_chunks("curve.h5", fields=["step", "stress"], chunk_size=4096):
    consume(chunk.data)
~~~

Explain that each chunk is a Dataset, metadata is preserved, and HDF5 reads are sliced along the record axis.

- [ ] **Step 3: Turn the adapter guide into an acceptance checklist**

Add checkboxes for official format evidence, license and redistribution review, upstream version coverage, synthetic/approved fixtures, explicit units and conventions, deterministic offline tests, ambiguity failure behavior, and keeping solver runtimes out of core dependencies.

- [ ] **Step 4: Update roadmap and changelog**

Add an Unreleased changelog entry for strict metadata, safe writes, partial/chunk reads, immutable schema fields, regression coverage, benchmark, and the adapter checklist. Keep Issue #4 open for broader performance work. Do not change the package version.

- [ ] **Step 5: Check documentation links and formatting**

~~~powershell
rg -n "load_hdf5|iter_hdf5_chunks|allow_invalid|format_version|adapter" docs CHANGELOG.md
git diff --check
~~~

- [ ] **Step 6: Commit documentation**

~~~powershell
git add docs/data-format.md docs/quickstart.md docs/adapter-guide.md docs/roadmap.md CHANGELOG.md
git commit -m "docs: describe safe and scalable HDF5 workflows"
~~~

### Task 8: Run the full verification gate

**Files:**
- Read: all changed files and the approved spec/plan.

- [ ] **Step 1: Run the complete test and quality suite**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\ruff.exe check src tests scripts
& .\.venv\Scripts\ruff.exe format --check src tests scripts
& .\.venv\Scripts\python.exe -m build
& .\.venv\Scripts\python.exe scripts/check_reproducible_build.py
git diff --check
~~~

Record the exit code and failure count for every command. If any command fails, add a focused failing test, fix the implementation, and rerun the complete gate.

- [ ] **Step 2: Verify requirements against the spec**

Check each of the eight scope items against the actual diff, test output, and documentation. Confirm no version bump, solver adapter, new dependency, or unrelated refactor was introduced.

- [ ] **Step 3: Inspect final repository state**

~~~powershell
git status --short
git log --oneline -12
~~~

Only create a final fix commit after all tests and quality checks are green.

### Task 9: Publish evidence and clean up GitHub Issues

**Files:**
- No repository files; authenticated GitHub issue and pull-request state.

- [ ] **Step 1: Create a dedicated publish branch if needed**

Use a codex/-prefixed branch based on the verified local commits:

~~~powershell
git switch -c codex/hdf5-integrity-scalability
git push --set-upstream origin codex/hdf5-integrity-scalability
~~~

If the branch already exists, inspect it before choosing another name; do not overwrite unrelated remote work.

- [ ] **Step 2: Create a non-merged pull request**

~~~powershell
gh pr create --base main --head codex/hdf5-integrity-scalability --title "Harden HDF5 integrity and add scalable reads" --body "Implements strict HDF5 metadata validation, protected/atomic writes, bounded and chunked reads, immutable FieldSchema collections, regression coverage, benchmark, and documentation. Full local pytest, Ruff, build, and reproducible-build checks are attached in the task summary. "
~~~

Do not merge the pull request in this task.

- [ ] **Step 3: Comment on and close completed issues**

After the PR URL is known, comment with exact evidence and close Issues #2, #3, #5, and #7:

~~~powershell
gh issue comment 2 --body "Implemented and covered: schema authoring and validation helpers are present in v0.2.0; regression coverage is green."
gh issue close 2 --reason completed
gh issue comment 3 --body "Implemented in v0.2.0 and covered by tensor round-trip and nested validation tests."
gh issue close 3 --reason completed
gh issue comment 5 --body "Implemented in v0.2.0: explicit JSON CLI mappings, unit conversion, conflict checks, and error-path tests are present."
gh issue close 5 --reason completed
gh issue comment 7 --body "Expanded malformed nested-field and schema immutability coverage in the current PR."
gh issue close 7 --reason completed
~~~

- [ ] **Step 4: Update still-open roadmap issues without closing them**

~~~powershell
gh issue comment 4 --body "The current PR adds load_hdf5() and iter_hdf5_chunks() with field/range selection and regression tests. This issue remains open for larger-file benchmarking and further performance work."
gh issue comment 6 --body "The adapter guide now contains the acceptance checklist for format evidence, licensing, fixtures, conventions, and offline tests. This issue remains open until an actual optional adapter is contributed."
~~~

- [ ] **Step 5: Verify final remote state**

~~~powershell
gh issue list --state all --limit 20 --json number,state,title,url
gh pr view --json number,state,isDraft,url,checks
~~~

Confirm #2, #3, #5, and #7 are closed, #4 and #6 remain open, and the PR is not merged.
