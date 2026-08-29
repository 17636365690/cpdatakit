# Inspect and Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add safe, deterministic inspect and offline report commands for CSV, JSON, CPDataKit HDF5, and the existing DAMASK DADF5 adapter without changing existing APIs, exit-code conventions, or the HDF5 1.0 layout.

**Architecture:** Keep inspection separate from rendering. inspection.py owns file-format detection, bounded HDF5 structure reads, portable metadata sanitization, and optional schema findings. reporting.py builds one canonical report mapping and renders it as JSON, Markdown, or static HTML. cli.py only parses arguments, selects a loader/renderer, protects output files, and maps expected failures.

**Tech Stack:** Python 3.10+, argparse, h5py, NumPy, pandas, existing CPDataKit schema/validation/statistics APIs, and stdlib html/json/re. No new runtime dependency.

**Spec:** docs/superpowers/specs/2026-08-29-inspection-and-reporting-design.md

## Global Constraints

- Python >= 3.10 and argparse remain the supported runtime/CLI foundations.
- Existing CSV, JSON, CPDataKit HDF5 readers, load_hdf5(), iter_hdf5_chunks(), validate_dataset(), and summarize_dataset() remain compatible.
- HDF5 inspect uses h5py attrs, dataset shape, dtype, chunks, and bounded slices; it never calls load_dataset() to materialize the entire file.
- CPDataKit HDF5 metadata remains strict and version 1.0; no HDF5 layout or version migration is added.
- DAMASK DADF5 support remains read-only and uses the existing adapter; no solver runtime is imported.
- No automatic scientific inference or automatic unit inference is added.
- JSON output uses stable structures and sort_keys=True; report JSON disallows NaN and infinity.
- New output files are protected from overwrite unless --force is passed.
- New commands map success to 0, validation/data findings to 1, and parameter/read/output failures to 2.
- HTML is fully escaped, offline, static, and free of external CDN, JavaScript, and network dependencies.
- Reports contain no raw records, absolute paths, passwords, tokens, or other sensitive metadata.
- Existing commands, public signatures, and their return-code behavior remain unchanged.
- No GitHub issue, merge, release, or publication operation is part of this work.

---

### Task 1: Establish failing inspection API tests

Files:
- Create: tests/test_inspection.py
- Modify: tests/conftest.py only if a reusable HDF5 fixture is needed after the first test

Interfaces:
- Produces the first executable contract for cpdatakit.inspection.inspect_dataset() and inspect_hdf5_structure().
- The result is a JSON-compatible mapping with file, fields, record_count, hdf5, provenance, adapter, risks, and optional schema keys.

- [ ] Step 1: Write the smallest failing CSV inspection test

Add this real-file test:

~~~python
from pathlib import Path

from cpdatakit.inspection import inspect_dataset


def test_inspect_csv_describes_fields_and_records(tmp_path: Path) -> None:
    path = tmp_path / "curve.csv"
    path.write_text("step,strain,stress\n0,0.0,0.0\n1,0.1,10.0\n", encoding="utf-8")

    result = inspect_dataset(path, schema="curve")

    assert result["file"]["format"] == "CSV"
    assert result["record_count"] == 2
    assert [field["name"] for field in result["fields"]] == ["step", "strain", "stress"]
    assert result["fields"][0]["dtype"] == "int64"
    assert result["schema"]["validation"]["valid"] is True
~~~

- [ ] Step 2: Run the test and verify the expected red state

Run:

~~~powershell
python -m pytest tests/test_inspection.py::test_inspect_csv_describes_fields_and_records -q
~~~

Expected: collection fails with ModuleNotFoundError because cpdatakit.inspection does not exist. This is the intended feature-missing failure.

- [ ] Step 3: Add the remaining inspection red tests before implementation

Cover JSON order, CPDataKit HDF5 metadata/shape/chunks, missing values, schema findings, bounded access, and corrupt metadata:

~~~python
def test_inspect_json_preserves_input_field_order(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps([{"label": "A", "value": 1.5}]), encoding="utf-8")

    result = inspect_dataset(path)

    assert result["file"]["format"] == "JSON"
    assert [field["name"] for field in result["fields"]] == ["label", "value"]
    assert result["record_count"] == 1


def test_inspect_cpdatakit_hdf5_reports_shape_dtype_units_and_chunks(
    curve: Dataset, tmp_path: Path
) -> None:
    output = tmp_path / "curve.h5"
    schema = load_schema("curve")
    write_hdf5(curve, output, schema, validate_dataset(curve, schema), hdf5_chunk_size=2)

    result = inspect_dataset(output)

    assert result["file"]["format"] == "CPDataKit HDF5"
    assert result["file"]["format_version"] == "1.0"
    assert result["record_count"] == 3
    assert result["fields"][0]["shape"] == [3]
    assert result["fields"][0]["chunks"] == [2]
    assert result["fields"][2]["unit"] == "MPa"
    assert result["hdf5"]["chunks"]["step"] == [2]


def test_inspect_hdf5_reads_bounded_slices_without_load_dataset(
    curve: Dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "curve.h5"
    schema = load_schema("curve")
    write_hdf5(curve, output, schema, validate_dataset(curve, schema), hdf5_chunk_size=1)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("inspect must not call load_dataset")

    monkeypatch.setattr("cpdatakit.inspection.load_dataset", fail)
    result = inspect_hdf5_structure(output)

    assert result["record_count"] == 3
    assert result["fields"][0]["missing_count"] == 0


def test_inspect_reports_missing_values_and_schema_errors(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text("step,strain,stress\n0,,0.0\n0,0.1,NaN\n", encoding="utf-8")

    result = inspect_dataset(path, schema="curve")

    assert result["fields"][1]["missing_count"] == 1
    assert result["risks"]["missing_values"][0]["field"] == "strain"
    assert result["schema"]["validation"]["valid"] is False
    assert {item["code"] for item in result["schema"]["validation"]["errors"]} >= {
        "missing_value",
        "duplicate_index",
    }


@pytest.mark.parametrize("attribute", ["format_version", "units_json", "provenance_json"])
def test_inspect_rejects_missing_cpdatakit_metadata(tmp_path: Path, attribute: str) -> None:
    path = tmp_path / "broken.h5"
    _write_minimal_cpdatakit_hdf5(path)
    with h5py.File(path, "r+") as handle:
        del handle.attrs[attribute]

    with pytest.raises(DataReadError, match="metadata"):
        inspect_hdf5_structure(path)
~~~

- [ ] Step 4: Run all inspection tests to record the red state

Run:

~~~powershell
python -m pytest tests/test_inspection.py -q
~~~

Expected: all new tests fail at import or missing-function boundaries, while existing tests remain untouched.

- [ ] Step 5: Commit only the failing inspection tests

~~~powershell
git add tests/test_inspection.py
git commit -m "test: specify dataset inspection behavior"
~~~

### Task 2: Implement safe inspection and bounded HDF5 structure reads

Files:
- Create: src/cpdatakit/inspection.py
- Modify: src/cpdatakit/__init__.py
- Test: tests/test_inspection.py

Interfaces:
- Implements inspect_dataset(path, *, schema=None) -> dict[str, Any].
- Implements inspect_hdf5_structure(path) -> dict[str, Any].
- Implements render_inspection_text(result) -> str and write_inspection(result, output, force=False) -> Path for CLI use.
- CSV/JSON use load_dataset(); CPDataKit HDF5 uses h5py; DADF5 detection uses root markers and h5py structure.

- [ ] Step 1: Implement only enough for the first CSV test

Create inspection.py with suffix dispatch, ordered pandas field records, file metadata, empty hdf5/adapter mappings, and schema_to_dict()/validate_dataset() integration. Use Path(path).name for the file name and str(series.dtype) for scalar dtype.

- [ ] Step 2: Run the first inspection test and verify green

~~~powershell
python -m pytest tests/test_inspection.py::test_inspect_csv_describes_fields_and_records -q
~~~

Expected: PASS.

- [ ] Step 3: Add field, risk, metadata, and sanitization helpers

Implement these helpers in inspection.py:

~~~python
def _safe_text(value: object, *, key: str | None = None) -> str:
    """Redact credential-like keys and absolute paths from free text."""


def _safe_metadata(value: object, *, key: str | None = None) -> object:
    """Recursively return JSON-compatible, portable metadata."""


def _missing_count(values: object) -> int:
    """Count missing scalar/array elements in one bounded slice."""


def _series_field_info(series: pd.Series, unit: str, description: str) -> dict[str, Any]:
    """Return stable name, dtype, shape, record_shape, unit, missing_count, description."""
~~~

Use an allowlist for embedded provenance and adapter keys. Preserve no source/output path except the input basename. Treat field order as dataframe order and HDF5 group order. Do not emit raw record values.

- [ ] Step 4: Implement native CPDataKit HDF5 inspection in h5py

Open with h5py.File(path, "r"), reuse the existing strict metadata contract or an exact internal helper for root attrs, require /data, check all first-axis lengths, and build each field record from dataset.dtype, dataset.shape, dataset.chunks. Accumulate missing values only through bounded slices:

~~~python
for offset in range(0, record_count, 10_000):
    stop = min(offset + 10_000, record_count)
    values = dataset[offset:stop]
    missing_count += _missing_count(values)
~~~

Return hdf5["chunks"] as a field-to-list-or-null mapping. Keep strict metadata failures as DataReadError.

- [ ] Step 5: Implement DADF5 recognition and structural inspection

Recognize DADF5 from DADF5_version_major and DADF5_version_minor, validate the documented structure through DamaskDADF5Adapter rules, select the sole label when unambiguous, and describe datasets beneath the selected increment/kind/label/field using h5py shape/dtype/chunks and bounded slices. Set file.format to DAMASK DADF5 and adapter.name to DamaskDADF5Adapter. Preserve only portable selection/version values. Keep adapter ambiguity as an expected AdapterError.

- [ ] Step 6: Add schema-validation aggregation for native HDF5 without full materialization

Use iter_hdf5_chunks() to validate bounded frames and merge equivalent ValidationIssue values by severity, code, field, message, and suggestion, adding affected counts. Validate required fields, units, shape, dtype, and ranges per chunk. Add lightweight sets for declared unique index fields and row fingerprints so duplicates spanning chunks are still reported. Never call load_dataset() or concatenate all chunks.

- [ ] Step 7: Export public inspection functions and run focused tests

Update src/cpdatakit/__init__.py and run:

~~~powershell
python -m pytest tests/test_inspection.py -q
~~~

Expected: all inspection tests pass. Add a focused regression test before correcting any unexpected branch.

- [ ] Step 8: Commit the inspection implementation

~~~powershell
git add src/cpdatakit/inspection.py src/cpdatakit/__init__.py tests/test_inspection.py
git commit -m "feat: add bounded dataset inspection"
~~~

### Task 3: Establish failing report renderer and payload tests

Files:
- Create: tests/test_reporting.py

Interfaces:
- Defines build_report(path, schema), render_report_json(report), render_report_markdown(report), and render_report_html(report).
- Reports contain file, schema, record_count, fields, validation, statistics, provenance, adapter, hdf5, and scope_note.

- [ ] Step 1: Write failing JSON and Markdown tests

Use a small explicit mapping for renderer tests and a real Dataset fixture for payload tests:

~~~python
def test_report_json_is_sorted_and_newline_terminated() -> None:
    report = {"z": 1, "a": {"message": "safe"}}

    rendered = render_report_json(report)

    assert rendered == '{\n  "a": {\n    "message": "safe"\n  },\n  "z": 1\n}\n'


def test_report_markdown_has_stable_sections_and_field_order(curve: Dataset) -> None:
    report = build_report_from_dataset(curve, load_schema("curve"))

    rendered = render_report_markdown(report)

    assert rendered.index("## Fields") < rendered.index("## Validation")
    assert rendered.index("| step |") < rendered.index("| strain |")
    assert "Validation conformance does not establish physical or scientific correctness." in rendered
~~~

The test helper build_report_from_dataset() is test-only and should assemble the same canonical sections expected from build_report().

- [ ] Step 2: Run report tests and verify the expected red state

~~~powershell
python -m pytest tests/test_reporting.py -q
~~~

Expected: import or missing-function failures because reporting.py and its renderers do not exist.

- [ ] Step 3: Add failing HTML, content, and escaping tests

~~~python
def test_report_html_escapes_user_strings() -> None:
    report = {
        "file": {"format": "CSV"},
        "fields": [{"name": "<field>", "description": "<script>alert(1)</script>"}],
        "validation": {"errors": [{"message": "bad <value>", "field": "<field>"}], "warnings": []},
        "scope_note": "<not trusted>",
    }

    rendered = render_report_html(report)

    assert "&lt;field&gt;" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered
    assert "<script" not in rendered.lower()
    assert "http://" not in rendered


def test_report_contains_errors_warnings_statistics_and_metadata(
    curve: Dataset, tmp_path: Path
) -> None:
    path = tmp_path / "curve.csv"
    curve.data.to_csv(path, index=False)

    report = build_report(path, "curve")

    assert report["validation"]["errors"] == []
    assert "warnings" in report["validation"]
    assert "numeric_fields" in report["statistics"]
    assert report["provenance"]["input_filename"] == "curve.csv"
    assert "scope_note" in report
~~~

- [ ] Step 4: Add failing redaction and deterministic-output tests

~~~python
def test_report_redacts_paths_and_credentials() -> None:
    report = {
        "provenance": {
            "input_filename": r"C:\secret\input.h5",
            "source_description": "password=super-secret /home/user/private/input.h5",
            "api_token": "token-value",
        }
    }

    rendered = render_report_json(report)

    assert r"C:\secret" not in rendered
    assert "/home/user/private" not in rendered
    assert "super-secret" not in rendered
    assert "token-value" not in rendered


def test_report_markdown_is_deterministic(curve: Dataset) -> None:
    report = build_report_from_dataset(curve, load_schema("curve"))

    assert render_report_markdown(report) == render_report_markdown(report)
~~~

- [ ] Step 5: Run all report tests and record red state

~~~powershell
python -m pytest tests/test_reporting.py -q
~~~

Expected: every new report test fails because production renderers are not implemented.

- [ ] Step 6: Commit only the failing report tests

~~~powershell
git add tests/test_reporting.py
git commit -m "test: specify offline validation reports"
~~~

### Task 4: Implement report payload and deterministic renderers

Files:
- Create: src/cpdatakit/reporting.py
- Modify: src/cpdatakit/__init__.py
- Test: tests/test_reporting.py

Interfaces:
- Implements build_report(path, schema) -> dict[str, Any].
- Implements render_report_json(report), render_report_markdown(report), and render_report_html(report).
- Implements write_report(report, output, format, force=False) -> Path.

- [ ] Step 1: Implement JSON rendering only

Use:

~~~python
json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
~~~

Keep the renderer pure. Run the JSON renderer test and make it pass before adding other formats.

- [ ] Step 2: Implement canonical report assembly

build_report() must load and validate the requested schema, use inspect_dataset(path, schema=contract) for file and structure details, load CSV/JSON through load_dataset(), load native HDF5 through its existing reader, and load DADF5 through DamaskDADF5Adapter(). It then runs validate_dataset(dataset, contract) and summarize_dataset(dataset, contract, validation=result). Put result.to_dict() under validation, schema_to_dict(contract) under schema, and the summary under statistics. Keep the exact scope note: Validation conformance does not establish physical or scientific correctness. Build the report even when validation is invalid.

- [ ] Step 3: Run JSON payload tests and verify green

~~~powershell
python -m pytest tests/test_reporting.py::test_report_json_is_sorted_and_newline_terminated tests/test_reporting.py::test_report_contains_errors_warnings_statistics_and_metadata -q
~~~

Expected: PASS.

- [ ] Step 4: Implement deterministic Markdown

Use fixed headings in this order: # CPDataKit Validation Report, ## File and Format, ## Schema, ## Fields, ## Validation, ## Descriptive Statistics, ## Provenance, ## Adapter, ## HDF5 Storage, and ## Scope. Use fixed field columns Field | Dtype | Shape | Unit | Missing | Description, preserve input field order, escape pipe/newline characters, and represent mappings/lists with sorted-key JSON. Do not include absolute paths or raw values.

- [ ] Step 5: Implement static, fully escaped HTML

Build a complete document with a small embedded CSS block for print-friendly tables and headings. Render every value through html.escape(str(value), quote=True) or escaped JSON. Do not interpolate user strings into raw HTML. Do not add script tags, external links, image URLs, fonts, CDN references, or network calls. Render errors and warnings in separate tables and show a visible scope note.

- [ ] Step 6: Implement protected report output

write_report() selects a renderer by exact format, checks target.exists() before parent creation, raises OutputExistsError unless force=True, writes UTF-8 text with one final newline, and converts OSError to CPDataKitError for CLI status 2.

- [ ] Step 7: Export report APIs and run focused tests

Update src/cpdatakit/__init__.py and run:

~~~powershell
python -m pytest tests/test_reporting.py -q
~~~

Expected: all report tests pass.

- [ ] Step 8: Commit the report implementation

~~~powershell
git add src/cpdatakit/reporting.py src/cpdatakit/__init__.py tests/test_reporting.py
git commit -m "feat: add offline validation report renderers"
~~~

### Task 5: Establish failing CLI tests for inspect and report

Files:
- Create: tests/test_cli_inspect_report.py

Interfaces:
- Defines argparse forms, stdout/file output, overwrite protection, --force, and status mapping for both commands.

- [ ] Step 1: Write failing CLI happy-path tests

~~~python
def test_cli_inspect_json_writes_stable_output(curve_csv: Path, tmp_path: Path) -> None:
    output = tmp_path / "inspect.json"

    status = main([
        "inspect", str(curve_csv), "--schema", "curve", "--format", "json",
        "--output", str(output),
    ])

    assert status == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["file"]["format"] == "CSV"
    assert payload["schema"]["validation"]["valid"] is True


def test_cli_report_html_and_markdown_write_offline_artifacts(
    curve_csv: Path, tmp_path: Path
) -> None:
    html = tmp_path / "report.html"
    markdown = tmp_path / "report.md"

    assert main(["report", str(curve_csv), "--schema", "curve", "--output", str(html)]) == 0
    assert main([
        "report", str(curve_csv), "--schema", "curve", "--format", "markdown",
        "--output", str(markdown),
    ]) == 0
    assert "<html" in html.read_text(encoding="utf-8")
    assert markdown.read_text(encoding="utf-8").startswith("# CPDataKit Validation Report")
~~~

- [ ] Step 2: Run CLI tests and verify expected red state

~~~powershell
python -m pytest tests/test_cli_inspect_report.py -q
~~~

Expected: argparse rejects inspect/report because the subcommands are not implemented.

- [ ] Step 3: Add failing status and overwrite tests

Cover status 1 for invalid schema data, status 2 for missing/bad input and unknown schema, existing output rejection, --force replacement, empty CSV, report JSON output, a native HDF5 fixture, and a one-label DADF5 fixture. Assert that new-command error output does not contain an absolute input path.

- [ ] Step 4: Commit the failing CLI tests

~~~powershell
git add tests/test_cli_inspect_report.py
git commit -m "test: specify inspect and report CLI behavior"
~~~

### Task 6: Add thin CLI orchestration and preserve existing commands

Files:
- Modify: src/cpdatakit/cli.py
- Test: tests/test_cli_inspect_report.py

Interfaces:
- Adds inspect with optional --schema, --format {text,json}, optional --output, and --force.
- Adds report with required --schema, required --output, --format {html,markdown,json} defaulting to html, and --force.
- Leaves validate, summary, convert, and plot parser forms and behavior intact.

- [ ] Step 1: Add parser definitions and dispatch before the existing common schema/data path

Implement these parser arguments:

~~~python
inspect = commands.add_parser("inspect", help="Inspect file structure and optional schema conformance")
inspect.add_argument("data", type=Path)
inspect.add_argument("--schema")
inspect.add_argument("--format", choices=["text", "json"], default="text")
inspect.add_argument("--output", type=Path)
inspect.add_argument("--force", action="store_true")

report = commands.add_parser("report", help="Write an offline validation report")
report.add_argument("data", type=Path)
report.add_argument("--schema", required=True)
report.add_argument("--format", choices=["html", "markdown", "json"], default="html")
report.add_argument("--output", required=True, type=Path)
report.add_argument("--force", action="store_true")
~~~

Dispatch to _run_inspect() and _run_report() before the existing common schema/mapping path. Keep table construction out of cli.py.

- [ ] Step 2: Implement status handling and protected output

_run_inspect() writes text or JSON through write_inspection(), returns 1 only when optional schema validation has errors or structural/missing-value risks are present, otherwise 0. _run_report() calls build_report(), writes through write_report(), and returns 0 when report["validation"]["valid"] is true and 1 otherwise. Expected CPDataKitError failures reach the existing top-level handler and return 2.

For new commands only, sanitize exception text with the inspection redaction helper before printing so input errors cannot reveal absolute paths or credentials. Existing command error output remains unchanged.

- [ ] Step 3: Run CLI focused tests and regression tests

~~~powershell
python -m pytest tests/test_cli_inspect_report.py tests/test_cli_mapping.py -q
python -m pytest -q
~~~

Expected: all new CLI tests and all existing tests pass.

- [ ] Step 4: Commit the CLI integration

~~~powershell
git add src/cpdatakit/cli.py tests/test_cli_inspect_report.py
git commit -m "feat: add inspect and report commands"
~~~

### Task 7: Update user documentation and release notes

Files:
- Modify: README.md
- Modify: README.zh-CN.md
- Modify: docs/quickstart.md
- Modify: docs/data-format.md
- Modify: docs/architecture.md
- Modify: CHANGELOG.md

- [ ] Step 1: Add exact copyable examples to both READMEs

Include these exact commands:

~~~text
cpdatakit inspect curve.h5 --format json --output inspect.json
cpdatakit report curve.h5 --schema curve --output report.html
~~~

Explain inspect schema optionality, report format choices, --force, and statuses 0/1/2.

- [ ] Step 2: Extend quickstart

Add a conversion-to-inspection/report flow, including that reports open without network access and validation conformance does not certify physical or scientific correctness.

- [ ] Step 3: Document data-format and architecture boundaries

In docs/data-format.md, document stable inspection/report sections, HDF5 bounded reads/chunk fields, basename-only provenance/redaction, and no raw record values. In docs/architecture.md, place inspection/reporting between readers/validation and CLI and state that HTML is static/offline.

- [ ] Step 4: Add a changelog entry

Describe both commands, formats, overwrite protection, DADF5 compatibility, and unchanged HDF5 1.0 format. Do not claim release publication.

- [ ] Step 5: Verify documentation and commit

~~~powershell
rg -n "cpdatakit inspect curve\.h5 --format json --output inspect\.json|cpdatakit report curve\.h5 --schema curve --output report\.html|scientific correctness|offline" README.md README.zh-CN.md docs/quickstart.md docs/data-format.md docs/architecture.md CHANGELOG.md
git diff --check
git add README.md README.zh-CN.md docs/quickstart.md docs/data-format.md docs/architecture.md CHANGELOG.md
git commit -m "docs: document inspection and validation reports"
~~~

### Task 8: Full regression, quality gates, and completion audit

Files:
- Modify only files required by failing verification evidence; otherwise no additional files.

- [ ] Step 1: Run focused feature tests

~~~powershell
python -m pytest tests/test_inspection.py tests/test_reporting.py tests/test_cli_inspect_report.py -q
~~~

Expected: all feature tests pass.

- [ ] Step 2: Run the requested coverage gate

~~~powershell
python -m pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85
~~~

Expected: zero failures and total coverage at least 85%. Add behavior-focused tests for uncovered branches before changing production code.

- [ ] Step 3: Run lint, format, and build gates

~~~powershell
ruff check .
ruff format --check .
python -m build
~~~

Expected: Ruff reports no errors, format check passes, and wheel/sdist build successfully.

- [ ] Step 4: Audit the final diff and compatibility

~~~powershell
git diff --check
git status --short
git diff HEAD~8..HEAD --stat
rg -n "dependencies|DADF5|format_version|load_dataset|sort_keys|force|scientific correctness" src/cpdatakit README.md README.zh-CN.md docs CHANGELOG.md
~~~

Confirm no runtime dependency was added, no solver/scientific/unit inference was introduced, HDF5 metadata/layout remains version 1.0, new outputs contain no absolute paths or sensitive values, and no GitHub/merge/release action occurred.

- [ ] Step 5: Report only verified results

List changed files, public API/CLI usage, exact test count and coverage from fresh commands, build result, and unresolved limitations. Do not claim a gate passed unless its command exited successfully.

