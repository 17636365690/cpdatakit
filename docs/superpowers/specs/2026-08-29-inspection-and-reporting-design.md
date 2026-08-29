# Inspect and Shareable Validation Reports Design

**Goal:** Add a machine-readable `inspect` command and offline `report` command that expose the existing CPDataKit validation and descriptive statistics without changing the existing dataset APIs or HDF5 format.

**Status:** Design approved in chat on 2026-08-29; implementation follows the repository's existing Python 3.10+, argparse, h5py, pandas, and dataclass conventions.

## Scope

The feature adds two read-only presentation layers:

- `inspection.py` describes an input file and its structural risks. It accepts CSV, JSON records, CPDataKit HDF5, and the existing DAMASK DADF5 adapter boundary.
- `reporting.py` builds a stable report payload and renders that payload as JSON, Markdown, or self-contained HTML.
- `cli.py` remains orchestration-only: it parses arguments, selects the loader and renderer, protects output files, and maps existing error/validation conventions to exit statuses.

The implementation does not run a solver, infer scientific meaning, infer units, migrate schemas, add a runtime dependency, or modify the CPDataKit HDF5 version-1.0 layout.

## Public interfaces

The package exposes the following new functions:

```python
inspect_dataset(
    path: str | Path,
    *,
    schema: str | Path | ProfileSchema | Mapping[str, Any] | None = None,
) -> dict[str, Any]

inspect_hdf5_structure(path: str | Path) -> dict[str, Any]

render_report_json(report: Mapping[str, Any]) -> str
render_report_markdown(report: Mapping[str, Any]) -> str
render_report_html(report: Mapping[str, Any]) -> str
```

The inspection functions return JSON-compatible dictionaries. They use stable field order from the input representation, stable list order for validation findings, and explicit string values such as `"not available"` when a quantity cannot be obtained without inventing information.

## Inspection result

The inspection result has these top-level sections:

```text
file       file name, extension, detected kind, and format version
fields     ordered field records with name, dtype, shape, record shape, unit,
           missing count, and optional description
record_count
hdf5       CPDataKit storage chunks and relevant structural details, or an empty object
provenance sanitized portable provenance metadata
adapter    sanitized adapter metadata, or an empty object
risks      missing-value and basic structural-risk findings
schema     schema profile/version and validation result when --schema is supplied
```

For CPDataKit HDF5, `inspect_hdf5_structure()` opens the file with `h5py`, reads root attrs, checks `/data`, and reads each dataset's `dtype`, `shape`, `chunks`, and bounded record slices. It never calls `load_dataset()` and never materializes the complete HDF5 table. Missing-value counts are accumulated over bounded slices. Record counts, scalar datasets, inconsistent first axes, absent units, and absent required metadata are reported as structural risks or `DataReadError` according to the existing strict-reader contract.

For CSV and JSON, the existing `load_dataset()` path remains the source of truth. For a DAMASK DADF5 file, the root version markers are recognized before CPDataKit metadata parsing; the structure is described through h5py and analysis/reporting uses the existing `DamaskDADF5Adapter` with its explicit default selection rules. No DAMASK runtime is imported.

When `schema` is provided, the result includes the validated profile and schema version plus the existing `ValidationResult.to_dict()` shape. Schema loading errors remain read/parameter errors, while data validation errors are findings and do not prevent a report from being rendered.

## Report payload and renderers

`reporting.py` builds one canonical payload with the following sections:

```text
file, schema, record_count, fields, validation, statistics,
provenance, adapter, hdf5, scope_note
```

`schema` contains the profile, version, field contract, conventions, and extension prefix using `schema_to_dict()`. `fields` combines structural inspection with schema descriptions and declared units. `validation` is the existing errors/warnings representation. `statistics` is the existing `summarize_dataset()` output. `scope_note` explicitly states that validation conformance does not establish physical or scientific correctness.

JSON uses `json.dumps(..., indent=2, sort_keys=True, allow_nan=False)` and ends with one newline. Markdown uses fixed headings, fixed table columns, input field order, and deterministic scalar formatting. HTML uses a static stylesheet only; it has no external resources, JavaScript, or network dependency and is suitable for browser printing.

## Safety and portability

The report layer does not include raw record values. It only emits names, shapes, dtypes, units, counts, aggregate statistics, validation messages, descriptions, and declared metadata.

All user-controlled strings are sanitized before they enter the canonical payload:

- paths are represented by a basename only;
- absolute POSIX, drive-letter, and UNC path patterns are redacted from free text;
- values associated with password, token, secret, API-key, authorization, and credential-like keys are replaced with `[redacted]`;
- arbitrary metadata is reduced to the allowlisted provenance and adapter fields;
- HTML rendering applies `html.escape()` to every displayed string, including field names, descriptions, messages, and suggestions.

Output paths are never included in report content. Existing output protection is preserved: an existing destination raises an output error unless `--force` is supplied. Parent directories are created only after the overwrite check.

## CLI behavior

The commands are:

```text
cpdatakit inspect INPUT [--format text|json] [--schema SCHEMA] [--output PATH] [--force]
cpdatakit report INPUT --schema SCHEMA [--format html|markdown|json] --output PATH [--force]
```

`inspect` defaults to concise text on stdout and supports JSON output. `report` defaults to HTML and requires an output path because it is a shareable artifact. Report generation proceeds when validation finds errors or warnings; the command returns `1` after writing the report. Missing/invalid inputs, unsupported schemas, malformed metadata, unsupported formats, and output failures return `2`. A successful load with no validation errors returns `0`. Existing commands and their argument names/return codes remain unchanged.

## Test strategy

Tests are added in three layers:

- `tests/test_inspection.py` covers CSV, JSON, CPDataKit HDF5, bounded HDF5 reads, metadata failures, chunks, risks, provenance, and schema validation.
- `tests/test_reporting.py` covers canonical JSON, deterministic Markdown, offline HTML, escaping, validation errors/warnings, statistics, and sensitive/path redaction.
- `tests/test_cli_inspect_report.py` covers parser behavior, exit statuses `0/1/2`, empty/unknown/bad inputs, overwrite protection, `--force`, and DAMASK compatibility.

Each production behavior is introduced by a failing test and then implemented minimally. The final gate is the requested full pytest coverage command, Ruff checks, and `python -m build`.

