# Stability, HDF5 Performance, and Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Isolate nested Dataset metadata, make ProfileSchema conventions recursively immutable, add opt-in HDF5 storage chunking, enforce an 85% coverage gate, and prepare a reviewable v0.3.0 release path on top of PR #20.

**Architecture:** Keep Dataset and schema contracts as small immutable boundaries. Add HDF5 storage chunking as an opt-in writer parameter so existing files and small-file behavior remain unchanged, while the existing bounded/chunked readers consume the same record-axis layout. Put the project-wide coverage gate in the single Ubuntu quality job and retain the full OS/Python test matrix.

**Tech Stack:** Python 3.10+, h5py, NumPy, pandas, pytest, pytest-cov, Hypothesis, Ruff, Hatchling, GitHub Actions, GitHub CLI.

**Spec:** docs/superpowers/specs/2026-08-28-stability-performance-quality-design.md

## Global Constraints

- Dataset.copy() must deep-copy nested metadata and continue deep-copying the DataFrame.
- ProfileSchema.conventions is a Mapping with recursively immutable values; schema_to_dict() still emits JSON-compatible dict/list values.
- write_hdf5() gains hdf5_chunk_size: int | None = None; None preserves current output layout.
- A positive hdf5_chunk_size uses min(hdf5_chunk_size, record_count) on the first dataset axis and preserves trailing dimensions.
- Invalid hdf5_chunk_size values raise ValueError before creating a temporary output.
- The existing allow_invalid and atomic HDF5 write behavior remains unchanged.
- The CI coverage gate is pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85 in one Ubuntu quality job.
- The clean wheel smoke test imports load_hdf5 and iter_hdf5_chunks.
- Version metadata updates follow independent review and merge of PR #20.
- Core runtime dependencies and integration boundaries remain aligned with the documented package architecture.

---

### Task 0: Prepare the stacked implementation branch

**Files:**
- No repository files; local Git branch state only.

- [ ] **Step 1: Confirm the prerequisite branch and worktree are safe**

~~~powershell
git status --short --branch
git show-ref --verify --quiet refs/remotes/origin/codex/hdf5-integrity-scalability
if ($LASTEXITCODE -ne 0) { throw 'PR #20 prerequisite branch is not available locally' }
~~~

Expected: the worktree is clean and origin/codex/hdf5-integrity-scalability exists.

- [ ] **Step 2: Create and switch to the follow-up branch before changing code**

~~~powershell
git branch --list "codex/stability-performance-quality"
git switch -c codex/stability-performance-quality origin/codex/hdf5-integrity-scalability
~~~

If the first command shows that the branch already exists, inspect it and switch to it only when it points to the current prerequisite branch; never overwrite unrelated work.

### Task 1: Isolate nested Dataset metadata

**Files:**
- Modify: src/cpdatakit/model.py
- Create: tests/test_model.py

**Interfaces:**
- Keeps Dataset(data, metadata, source) unchanged.
- Keeps Dataset.copy() -> Dataset unchanged while strengthening its isolation guarantee.

- [ ] **Step 1: Write the failing metadata-isolation test**

Create tests/test_model.py:

~~~python
from __future__ import annotations

from pathlib import Path

import pandas as pd

from cpdatakit.model import Dataset


def test_dataset_copy_isolates_nested_metadata_and_data() -> None:
    original = Dataset(
        pd.DataFrame({"value": [1.0]}),
        {"nested": {"labels": ["raw"]}},
        Path("input.csv"),
    )

    copied = original.copy()
    copied.metadata["nested"]["labels"].append("normalized")
    copied.data.loc[0, "value"] = 2.0

    assert original.metadata == {"nested": {"labels": ["raw"]}}
    assert original.data["value"].tolist() == [1.0]
    assert copied.source == original.source
~~~

- [ ] **Step 2: Run the test and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_model.py -q
~~~

Expected: FAIL because Dataset.copy() currently performs dict(self.metadata), which leaves nested dictionaries and lists shared.

- [ ] **Step 3: Implement the minimal deep-copy change**

In src/cpdatakit/model.py:

1. Import deepcopy from copy.
2. Keep self.data.copy(deep=True) and self.source unchanged.
3. Replace dict(self.metadata) with deepcopy(self.metadata):

~~~python
def copy(self) -> Dataset:
    """Return a deep-enough copy for safe normalization."""
    return Dataset(self.data.copy(deep=True), deepcopy(self.metadata), self.source)
~~~

- [ ] **Step 4: Run model and normalization tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_model.py tests/test_normalization_statistics.py -q
~~~

Expected: PASS with no change to normalization output.

- [ ] **Step 5: Commit the isolated-copy change**

~~~powershell
git add src/cpdatakit/model.py tests/test_model.py
git commit -m "fix: isolate nested dataset metadata copies"
~~~

### Task 2: Make ProfileSchema conventions recursively immutable

**Files:**
- Modify: src/cpdatakit/schema.py
- Modify: tests/test_schema.py

**Interfaces:**
- ProfileSchema.conventions becomes Mapping[str, Any] at the public in-memory boundary.
- schema_to_dict(schema)["conventions"] remains a mutable JSON-compatible dict containing lists for sequence values.

- [ ] **Step 1: Write failing convention immutability and defensive-copy tests**

Add to tests/test_schema.py:

~~~python
def test_profile_schema_conventions_are_recursively_immutable() -> None:
    source = {"nested": {"labels": ["Cauchy stress"]}}
    schema = make_profile_schema(
        "point",
        [make_field_schema("point_id", "integer", required=True, unit="1")],
        conventions=source,
    )

    source["nested"]["labels"].append("mutated outside")
    assert schema.conventions["nested"]["labels"] == ("Cauchy stress",)

    with pytest.raises(TypeError):
        schema.conventions["new"] = "value"
    with pytest.raises(TypeError):
        schema.conventions["nested"]["labels"] += ("mutated inside",)


def test_profile_schema_conventions_thaw_to_json_lists() -> None:
    schema = make_profile_schema(
        "point",
        [make_field_schema("point_id", "integer", required=True, unit="1")],
        conventions={"nested": {"labels": ["Cauchy stress"]}},
    )

    assert schema_to_dict(schema)["conventions"] == {"nested": {"labels": ["Cauchy stress"]}}
~~~

- [ ] **Step 2: Run the new tests and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_schema.py -k "conventions_are_recursively_immutable or conventions_thaw" -q
~~~

Expected: FAIL because ProfileSchema currently stores a mutable dict and nested list directly.

- [ ] **Step 3: Implement recursive freeze/thaw helpers**

In src/cpdatakit/schema.py:

1. Import deepcopy from copy and MappingProxyType from types.
2. Add private helpers with these exact behaviors:

~~~python
def _freeze_convention(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_convention(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_convention(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_convention(item) for item in value)
    return deepcopy(value)


def _thaw_convention(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_convention(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw_convention(item) for item in value]
    return deepcopy(value)
~~~

3. Change ProfileSchema.conventions to Mapping[str, Any] with a dict default.
4. Add ProfileSchema.__post_init__() that assigns _freeze_convention(self.conventions) through object.__setattr__().
5. Change _validate_profile() to accept Mapping rather than only dict.
6. In schema_to_dict(), replace dict(contract.conventions) with _thaw_convention(contract.conventions).
7. Leave JSON parsing, make_profile_schema(), built-in schema values, and FieldSchema tuple behavior compatible.

- [ ] **Step 4: Run schema, validation, and nested-field tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_schema.py tests/test_validation.py tests/test_nested_properties.py -q
~~~

Expected: PASS; built-in JSON schemas and serialized schema output remain unchanged.

- [ ] **Step 5: Commit immutable conventions**

~~~powershell
git add src/cpdatakit/schema.py tests/test_schema.py
git commit -m "fix: make schema conventions immutable"
~~~

### Task 3: Add opt-in HDF5 storage chunking

**Files:**
- Modify: src/cpdatakit/io/__init__.py
- Modify: tests/test_io.py

**Interfaces:**
- Extends write_hdf5() with keyword-only hdf5_chunk_size: int | None = None.
- None preserves the current contiguous/default dataset creation behavior.
- A positive value creates record-axis chunks without changing the reader API.

- [ ] **Step 1: Write failing chunk-layout and argument-validation tests**

Add to tests/test_io.py:

~~~python
def test_write_hdf5_can_store_record_axis_chunks(curve: Dataset, tmp_path: Path) -> None:
    schema = load_schema("curve")
    result = validate_dataset(curve, schema)
    output = tmp_path / "chunked.h5"

    write_hdf5(curve, output, schema, result, hdf5_chunk_size=2)

    with h5py.File(output, "r") as handle:
        assert handle["data"]["step"].chunks == (2,)
        assert handle["data"]["stress"].chunks == (2,)


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5, "2"])
def test_write_hdf5_rejects_invalid_storage_chunk_size(
    curve: Dataset, tmp_path: Path, chunk_size: object
) -> None:
    schema = load_schema("curve")
    result = validate_dataset(curve, schema)
    output = tmp_path / "invalid-chunk-size.h5"

    with pytest.raises(ValueError, match="hdf5_chunk_size"):
        write_hdf5(curve, output, schema, result, hdf5_chunk_size=chunk_size)

    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.*")) == []
~~~

- [ ] **Step 2: Run the new tests and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py -k "record_axis_chunks or storage_chunk_size" -q
~~~

Expected: FAIL because write_hdf5() does not accept hdf5_chunk_size.

- [ ] **Step 3: Implement validated opt-in chunks**

In src/cpdatakit/io/__init__.py:

1. Add hdf5_chunk_size: int | None = None after allow_invalid in the keyword-only writer signature.
2. Add a private validator that accepts None, rejects bool and non-integral values, rejects values <= 0, and returns int.
3. Call the validator before target/temp-file creation.
4. After converting each column to a NumPy array, compute:

~~~python
chunks = None
if resolved_chunk_size is not None and len(values):
    chunks = (min(resolved_chunk_size, len(values)), *values.shape[1:])
~~~

5. Pass chunks=chunks to group.create_dataset(name, data=values, chunks=chunks). When chunks is None, retain default HDF5 creation behavior.
6. Keep invalid-validation rejection, force protection, atomic replacement, metadata, strings, vectors, tensors, and empty-value behavior unchanged.

- [ ] **Step 4: Run I/O and full regression tests**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_io.py tests/test_nested_properties.py -q
& .\.venv\Scripts\python.exe -m pytest -q
~~~

Expected: PASS; existing full/selected/chunked reads return the same values and shapes.

- [ ] **Step 5: Commit opt-in HDF5 storage chunking**

~~~powershell
git add src/cpdatakit/io/__init__.py tests/test_io.py
git commit -m "perf: add opt-in HDF5 storage chunking"
~~~

### Task 4: Extend and verify the HDF5 scaling benchmark

**Files:**
- Modify: scripts/benchmark_hdf5_read.py
- Create: tests/test_benchmark.py

**Interfaces:**
- Adds --hdf5-chunk-size N to the existing benchmark command.
- JSON output gains hdf5_chunk_size.
- Existing full, selected_fields, and chunked result keys remain unchanged.

- [ ] **Step 1: Write the failing benchmark integration test**

Create tests/test_benchmark.py:

~~~python
from __future__ import annotations

import json
import subprocess
import sys


def test_benchmark_reports_storage_chunk_size(tmp_path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_hdf5_read.py",
            "--records",
            "100",
            "--chunk-size",
            "16",
            "--hdf5-chunk-size",
            "8",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["records"] == 100
    assert payload["chunk_size"] == 16
    assert payload["hdf5_chunk_size"] == 8
    assert payload["full"]["record_count"] == 100
    assert payload["selected_fields"]["record_count"] == 100
    assert payload["chunked"]["record_count"] == 100
~~~

- [ ] **Step 2: Run the new test and verify the expected red state**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_benchmark.py -q
~~~

Expected: FAIL because the parser does not accept --hdf5-chunk-size and the script does not pass a storage chunk size to write_hdf5().

- [ ] **Step 3: Implement the benchmark option**

In scripts/benchmark_hdf5_read.py:

1. Add parser argument --hdf5-chunk-size with the existing _positive_int type and default None.
2. Pass hdf5_chunk_size=args.hdf5_chunk_size to write_hdf5().
3. Add "hdf5_chunk_size": args.hdf5_chunk_size to the JSON report.
4. Keep the temporary-directory cleanup behavior and null peak_rss_mib behavior on Windows.
5. Keep the benchmark diagnostic rather than making timing or RSS a CI pass/fail threshold.

- [ ] **Step 4: Run smoke and scaling benchmarks**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_benchmark.py -q
& .\.venv\Scripts\python.exe scripts/benchmark_hdf5_read.py --records 100000 --chunk-size 4096 --hdf5-chunk-size 4096
& .\.venv\Scripts\python.exe scripts/benchmark_hdf5_read.py --records 1000000 --chunk-size 4096 --hdf5-chunk-size 4096
~~~

Expected: the integration test passes; both benchmark runs print valid JSON with exact full/selected/chunked record counts. Record the elapsed time and peak RSS for later comparison; do not infer a performance win from one machine or one run.

- [ ] **Step 5: Commit the benchmark extension**

~~~powershell
git add scripts/benchmark_hdf5_read.py tests/test_benchmark.py
git commit -m "perf: benchmark HDF5 storage chunking"
~~~

### Task 5: Add the CI coverage gate and clean-wheel API smoke

**Files:**
- Modify: .github/workflows/ci.yml

**Interfaces:**
- Adds one Ubuntu quality-job coverage command.
- Extends the existing clean-wheel smoke command without changing the matrix or dependency set.

- [ ] **Step 1: Write the CI contract check**

Run this before editing the workflow:

~~~powershell
$ciText = Get-Content -LiteralPath '.github/workflows/ci.yml' -Raw
if ($ciText -match '--cov-fail-under=85') { throw 'coverage gate already present' }
if ($ciText -match 'from cpdatakit import load_hdf5, iter_hdf5_chunks') { throw 'wheel API smoke already present' }
~~~

Expected: the checks exit successfully because both workflow assertions are currently absent.

- [ ] **Step 2: Add the coverage and wheel API steps**

In the quality-and-build job, immediately after editable dev installation, add:

~~~yaml
      - name: Verify test coverage
        run: pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85
~~~

In the existing wheel smoke block, after the version import check, add:

~~~bash
          wheel-env/bin/python -c "from cpdatakit import load_hdf5, iter_hdf5_chunks; print('HDF5 APIs available')"
~~~

Do not add coverage to every OS/Python matrix job, do not change the required checks, and do not modify CodeQL.

- [ ] **Step 3: Run the local equivalent**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85 -q
& .\.venv\Scripts\ruff.exe check .
& .\.venv\Scripts\ruff.exe format --check .
~~~

Expected: coverage is at least 85%, Ruff check passes, and all files including Markdown code blocks are formatted.

- [ ] **Step 4: Commit CI quality gates**

~~~powershell
git add .github/workflows/ci.yml
git commit -m "ci: enforce coverage and HDF5 API smoke checks"
~~~

### Task 6: Document the new stability and performance contract

**Files:**
- Modify: docs/data-format.md
- Modify: docs/quickstart.md
- Modify: docs/roadmap.md
- Modify: CHANGELOG.md
- Modify: docs/maintenance.md

- [ ] **Step 1: Document immutable state and storage layout**

Update docs/data-format.md to state:

- Dataset copies isolate nested metadata.
- ProfileSchema conventions are immutable in memory and are serialized back to JSON objects/lists.
- HDF5 writer chunking is opt-in through hdf5_chunk_size.
- A configured chunk size applies to the record axis and leaves tensor trailing dimensions intact.
- Full and bounded/chunked readers preserve the same logical values.

- [ ] **Step 2: Add copyable API examples**

Add to docs/quickstart.md:

~~~python
from cpdatakit.io import load_hdf5, write_hdf5
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset

schema = load_schema("curve")
result = validate_dataset(dataset, schema)
write_hdf5(dataset, "curve-chunked.h5", schema, result, hdf5_chunk_size=4096)
window = load_hdf5("curve-chunked.h5", fields=["step", "stress"], start=10, stop=20)
~~~

Explain that the storage option is useful for larger sequential reads, while the default remains compatible for small files.

- [ ] **Step 3: Update roadmap, maintenance, and changelog**

Add to docs/roadmap.md that v0.3.0 includes API isolation, opt-in HDF5 storage chunking, scaling evidence, and the 85% CI coverage gate; keep the first optional adapter as a separate evidence-gated item.

Update docs/maintenance.md with the exact release checklist: run the full supported-Python matrix, coverage gate, Ruff, two reproducible builds, wheel smoke including HDF5 API imports, the 100k/1M benchmark commands, and verify version metadata before publishing.

Add an Unreleased CHANGELOG.md entry for deep metadata copies, immutable conventions, opt-in storage chunking, scaling benchmark output, and CI coverage/API gates. Do not change pyproject.toml version or CITATION.cff in this branch.

- [ ] **Step 4: Run documentation checks**

~~~powershell
rg -n "hdf5_chunk_size|conventions|coverage|load_hdf5|iter_hdf5_chunks|v0.3.0" docs CHANGELOG.md
& .\.venv\Scripts\ruff.exe format --check .
git diff --check
~~~

Expected: all required terms are present, Ruff reports all files formatted, and diff check is clean.

- [ ] **Step 5: Commit documentation**

~~~powershell
git add docs/data-format.md docs/quickstart.md docs/roadmap.md docs/maintenance.md CHANGELOG.md
git commit -m "docs: describe stability and HDF5 scaling work"
~~~

### Task 7: Run the full verification gate

**Files:**
- Read: all changed files, the approved spec, and this plan.

- [ ] **Step 1: Run tests and quality checks from the final worktree**

~~~powershell
& .\.venv\Scripts\python.exe -m pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85 -q
& .\.venv\Scripts\ruff.exe check .
& .\.venv\Scripts\ruff.exe format --check .
& .\.venv\Scripts\python.exe -m build
git diff --check
git status --short --branch
~~~

Expected: zero test failures, coverage at least 85%, no Ruff errors, successful package build, clean diff check, and no uncommitted files.

- [ ] **Step 2: Verify two reproducible distributions**

~~~powershell
$taskReproRoot = Join-Path $env:TEMP ("cpdatakit-next-repro-" + [guid]::NewGuid().ToString("N"))
$taskFirst = Join-Path $taskReproRoot "first"
$taskSecond = Join-Path $taskReproRoot "second"
New-Item -ItemType Directory -Force -Path $taskFirst | Out-Null
New-Item -ItemType Directory -Force -Path $taskSecond | Out-Null
& .\.venv\Scripts\python.exe -m build --outdir $taskFirst
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m build --outdir $taskSecond
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe scripts/check_reproducible_build.py $taskFirst $taskSecond
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
~~~

Expected: both wheel/sdist files match byte-for-byte.

- [ ] **Step 3: Verify clean wheel imports and benchmark output**

Create a clean environment from the freshly built wheel, then run the benchmark through that environment:

~~~powershell
$taskWheelEnv = Join-Path $env:TEMP ("cpdatakit-wheel-" + [guid]::NewGuid().ToString("N"))
& .\.venv\Scripts\python.exe -m venv $taskWheelEnv
$taskWheelPython = Join-Path $taskWheelEnv "Scripts\python.exe"
$taskWheel = (Get-ChildItem dist\cpdatakit-*.whl | Select-Object -First 1).FullName
& $taskWheelPython -m pip install --no-deps $taskWheel
& $taskWheelPython -c "from cpdatakit import load_hdf5, iter_hdf5_chunks; print('HDF5 APIs available')"
& $taskWheelPython scripts/benchmark_hdf5_read.py --records 100000 --chunk-size 4096 --hdf5-chunk-size 4096
& $taskWheelPython scripts/benchmark_hdf5_read.py --records 1000000 --chunk-size 4096 --hdf5-chunk-size 4096
~~~

Expected: the wheel import succeeds and both benchmark runs print valid JSON with exact record counts for every mode.

- [ ] **Step 4: Compare the implementation against the spec**

Review the final diff line by line and confirm:

1. Nested Dataset metadata no longer aliases across copies.
2. Nested schema conventions cannot be changed through returned values.
3. JSON schema output is unchanged.
4. HDF5 chunking is opt-in and record-axis based.
5. Existing atomic write and invalid-output behavior remains intact.
6. CI has one 85% coverage gate and clean-wheel HDF5 API imports.
7. No version, solver adapter, dependency, or unrelated README change was introduced.

### Task 8: Publish the stacked PR and align the remaining GitHub backlog

**Files:**
- No repository files beyond the commits above; authenticated GitHub branch/PR and issue metadata.

- [ ] **Step 1: Push the branch prepared in Task 0**

If PR #20 is still open, push the branch created before implementation:

~~~powershell
git push --set-upstream origin codex/stability-performance-quality
~~~

If PR #20 has merged before this step, rebase the prepared branch onto origin/main, verify the complete diff, and use main as the pull-request base. Do not overwrite unrelated remote work.

- [ ] **Step 2: Create a non-merged stacked PR**

When PR #20 is still open:

~~~powershell
gh pr create --base codex/hdf5-integrity-scalability --head codex/stability-performance-quality --title "Improve API isolation and HDF5 scaling" --body "Adds deep Dataset metadata copies, recursively immutable schema conventions, opt-in HDF5 storage chunking, scaling benchmark output, and an 85% CI coverage/API smoke gate. PR #20 remains the prerequisite HDF5 integrity/read foundation. This PR is intentionally not merged by the task."
~~~

When PR #20 is already merged, use --base main and describe the merged prerequisite in the body. Do not self-approve or self-merge a protected PR.

- [ ] **Step 3: Retitle and update Issue #4**

Use the exact remaining scope:

~~~powershell
gh issue edit 4 --title "Benchmark and optimize large CPDataKit HDF5 reads"
gh issue comment 4 --body "The bounded/chunked API and opt-in storage chunking are implemented in PR #20 and the follow-up PR. This issue remains open for larger-file benchmarks, memory scaling evidence, compression/layout evaluation, and further optimization."
~~~

- [ ] **Step 4: Retitle and update Issue #6**

Keep the checklist work documented but make the remaining deliverable explicit:

~~~powershell
gh issue edit 6 --title "Contribute the first optional CPDataKit adapter"
gh issue comment 6 --body "The acceptance checklist is documented. This issue remains open for the first actual optional adapter with official format evidence, licensing review, reproducible fixtures, explicit conventions, and offline tests."
~~~

- [ ] **Step 5: Verify remote and local handoff state**

~~~powershell
gh pr checks 20
gh pr list --state open --limit 10 --json number,title,state,baseRefName,headRefName,url
gh issue list --state open --limit 20 --json number,title,url
git status --short --branch
~~~

Confirm PR #20 and the follow-up PR are not merged, all completed checks are green, Issues #4 and #6 describe only their remaining work, and the final worktree is clean.

### Task 9: Post-merge v0.3.0 release handoff

**Files:**
- No implementation files before the required PR review and merge.

- [ ] **Step 1: Record the release boundary**

Do not edit pyproject.toml, CITATION.cff, or create a tag in the follow-up implementation PR. The release starts only after PR #20 and the follow-up stability/performance PR have independent approval and are merged.

- [ ] **Step 2: Prepare the v0.3.0 release checklist**

After merge, update pyproject.toml, CHANGELOG.md, and CITATION.cff together; run the supported matrix, coverage gate, Ruff, two reproducible builds, clean-wheel smoke, benchmark commands, and Twine validation; then create the GitHub Release and publish to PyPI only after all artifacts match.

- [ ] **Step 3: Verify release consistency**

Before publishing, confirm the version reported by pyproject.toml, the installed wheel, the GitHub tag/release, and PyPI are all v0.3.0. Keep the current environment's stale editable-install metadata from being used as release evidence; verify in a fresh environment.
