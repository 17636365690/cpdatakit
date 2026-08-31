# Comparison and Report Bundle Design

**Date:** 2026-08-31
**Status:** Proposed for v0.4.0; implementation starts only after maintainer review

## Goal

Produce a deterministic, shareable comparison artifact for two CPDataKit validation reports while
reusing the existing inspection/report payload and keeping raw records, absolute paths, and
credential-like values out of the bundle.

## v0.4.0 first slice

The first slice compares two already-built aggregate report payloads. It does not claim physical
equivalence, does not compare raw tensor values, and does not make timing or statistical
significance claims. A later large-file path can compare bounded dataset summaries after an explicit
performance design.

The proposed public function is:

```python
def compare_reports(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic aggregate comparison of two report payloads."""
```

The result has this exact top-level order before JSON sorting:

```text
{
  "format": "CPDataKit comparison 1.0",
  "left": {"file": object, "schema": object, "record_count": int | str},
  "right": {"file": object, "schema": object, "record_count": int | str},
  "schema": {"classification": str, "diff": object},
  "structure": {
    "fields_added": [str],
    "fields_removed": [str],
    "fields_changed": [{"name": str, "changes": [str]}]
  },
  "validation": {"left": object, "right": object},
  "statistics": {"changed": [object], "unavailable": [object]},
  "scope_note": str
}
```

Statistics comparisons are limited to existing scalar `numeric_fields` values and record counts.
Each changed entry names the field and metric and contains `left`, `right`, and `delta` when both
values are finite numbers. Shaped-field statistics and unavailable values appear under
`unavailable`; they are never flattened or silently compared.

## Bundle format

The proposed bundle writer is:

```python
def write_comparison_bundle(
    comparison: Mapping[str, Any],
    output: str | Path,
    *,
    force: bool = False,
) -> Path:
    """Write a directory bundle with deterministic JSON, Markdown, and HTML members."""
```

The output directory contains exactly:

```text
manifest.json
comparison.json
comparison.md
comparison.html
```

`manifest.json` records the bundle format, member names, UTF-8 SHA-256 digest for every member,
left/right input basenames and hashes when available, and schema hashes. The manifest contains no
raw records. All members are generated from one canonical comparison mapping; HTML is static,
escaped, offline, and has no JavaScript, external resources, or network calls.

## CLI proposal

```text
cpdatakit compare LEFT_REPORT RIGHT_REPORT --output DIRECTORY [--force]
```

The initial command consumes JSON reports created by `cpdatakit report --format json`. A future
dataset mode must call `build_report()` first and must document its materialization and memory
behavior. Existing report renderers, redaction helpers, overwrite protection, and status mapping
are reused rather than forked.

## Comparison semantics and safety

- Schema comparison delegates to the approved `diff_schemas()` contract; a breaking schema diff is
  reported as comparison content, not hidden.
- Validation is shown side by side; a report with validation errors remains comparable.
- File names are basenames, absolute paths are redacted, and credential-like keys/values are
  redacted before canonicalization.
- JSON uses sorted keys, compact member metadata, `allow_nan=False`, and one final newline.
- The bundle writer checks the target before creating it and requires `force=True` to replace an
  existing directory. Partial member writes are cleaned up on failure.
- The scope note states that the bundle compares declared structure, validation, and descriptive
  aggregates only; it is not a physical or scientific correctness certificate.

## Testing and compatibility

Tests must cover identical/changed/breaking schemas, validation findings on either side, missing and
shaped statistics, deterministic member hashes, overwrite protection, cleanup after a member-write
failure, path/credential redaction, and HTML escaping. Existing `build_report()` output and HDF5
format-1.0 behavior remain compatible.
