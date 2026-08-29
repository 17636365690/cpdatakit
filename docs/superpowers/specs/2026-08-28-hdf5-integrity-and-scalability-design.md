# HDF5 Integrity and Scalable Reads Design

**Date:** 2026-08-28  
**Status:** Approved in chat; implementation pending

## Goal

Make CPDataKit HDF5 files trustworthy at the read and write boundaries, add a scalable
read path for larger files, and close the highest-risk test and documentation gaps from
the v0.2.0 maintenance review without changing the default `load_dataset(path)` workflow.

## Scope

This change covers:

1. Strict validation of the CPDataKit HDF5 envelope and metadata.
2. Explicit refusal to write a failed `ValidationResult`, with an opt-in escape hatch.
3. Atomic HDF5 output replacement and temporary-file cleanup.
4. Field/range reads and lazy chunk iteration for CPDataKit HDF5.
5. Immutable `FieldSchema` collection fields while keeping JSON output compatible.
6. Regression tests for I/O, schema, normalization, CLI failures, adapters, and nested data.
7. A small synthetic HDF5 read benchmark and user-facing documentation.
8. Cleanup of GitHub Issues #2, #3, #5, and #7 after the implementation evidence is
   available; Issues #4 and #6 remain open until their separate work is complete.

The core design keeps solver-specific integrations, schema evolution, storage evolution, and
release work behind their documented boundaries.

## Design

### HDF5 envelope validation

`src/cpdatakit/io/__init__.py` will use a single metadata-reading helper for both full and
partial reads. The helper will require these root attributes:

- `format == "CPDataKit"`
- `format_version == "1.0"`
- a supported `profile`
- `schema_version == "1.0"`
- `units_json`
- `field_mapping_json`
- `provenance_json`
- `validation_summary_json`

Text attributes may be HDF5 strings or UTF-8 bytes. Version, marker, profile, and JSON
attributes will be type-checked; each JSON attribute must decode to an object. Missing,
malformed, unsupported, or structurally inconsistent metadata will raise `DataReadError`
with the input path context. The data group must still contain at least one non-scalar
dataset, and every field must have the same non-zero record count.

### Safe writing

`write_hdf5()` will gain `allow_invalid: bool = False`. When the supplied
`ValidationResult` is invalid and the flag is false, it raises a new expected CPDataKit
exception before creating output. Passing `allow_invalid=True` writes the file and records
the failed validation summary explicitly.

The writer will create a uniquely named temporary file in the target directory, close the
HDF5 handle, and atomically replace the target with `os.replace()`. Any exception removes
the temporary file. Existing output remains protected by the current `force` behavior;
the API and CLI will not silently opt into invalid output.

### Scalable reads

The existing `load_dataset(path)` signature and full-read behavior remain unchanged. The
I/O module will add:

```python
def load_hdf5(
    path: str | Path,
    *,
    fields: Iterable[str] | None = None,
    start: int | None = None,
    stop: int | None = None,
) -> Dataset

def iter_hdf5_chunks(
    path: str | Path,
    *,
    fields: Iterable[str] | None = None,
    chunk_size: int = 10_000,
) -> Iterator[Dataset]
```

`load_dataset()` will delegate HDF5 paths to `load_hdf5()`. Field selection preserves the
requested order and rejects unknown or empty selections. `start`/`stop` are non-negative,
half-open record bounds; invalid ranges raise `DataReadError`. `iter_hdf5_chunks()` validates
the envelope before yielding, determines the record count from dataset shapes, and reads
only `[start:stop]` slices for each chunk. Each returned `Dataset` carries the same parsed
metadata and source path. Non-HDF5 loaders do not gain ambiguous partial-read semantics.

### Schema immutability

`FieldSchema.shape`, `FieldSchema.components`, and `FieldSchema.aliases` will be normalized
to tuples during construction, including direct dataclass construction. Validators will
accept the tuple representation. `schema_to_dict()` will continue converting them to JSON
lists, so schema files and their wire format remain unchanged. `ProfileSchema.fields` stays
a tuple; no broader mapping or conventions immutability change is introduced in this scope.

### Adapter and maintenance contract

`docs/adapter-guide.md` will turn the existing guidance into an explicit acceptance checklist:
official format evidence, license/redistribution review, supported upstream versions, a
synthetic or approved fixture, explicit units/conventions, deterministic offline tests,
failure behavior for ambiguity, with solver/runtime dependencies kept in their documented
integration boundary. Tests will verify the abstract `DatasetAdapter` contract alongside the
documented adapter guidance.

## Error handling

- Read-time envelope and data-shape failures: `DataReadError`.
- Failed validation passed to the writer: a dedicated `DataValidationError` under
  `CPDataKitError`, so CLI callers can handle it consistently.
- Existing output without `force=True`: `OutputExistsError`.
- Temporary-file cleanup must happen for HDF5 serialization errors, including inconsistent
  shaped values.

## Test strategy

Tests will be written before each production change and run in focused red/green cycles.
The regression set will include:

- every required HDF5 attribute missing, wrong type, wrong version, malformed JSON, and bad
  JSON object shape;
- invalid write rejection, `allow_invalid=True`, atomic replacement, and cleanup after a
  serialization failure;
- selected fields, bounded reads, chunk sizes, metadata preservation, empty/unknown fields,
  invalid bounds, and empty files;
- tuple-backed schema collections, direct construction, validation, and JSON round-trip;
- CLI error return paths, unit-conversion failure, malformed mappings, adapter abstraction,
  and nested-array validation/property boundaries.

The benchmark script will generate deterministic HDF5 data under a caller-selected temporary
or output directory, then report elapsed time and process RSS for full, selected-field, and
chunked reads. It will not run as part of the normal unit-test suite.

## Documentation and GitHub actions

Update `docs/data-format.md`, `docs/quickstart.md`, `docs/adapter-guide.md`,
`docs/roadmap.md`, and `CHANGELOG.md` with the new API and safety semantics. After local
verification, add concise implementation comments to Issues #2, #3, #5, and #7 and close
them through the authenticated GitHub CLI. Issue #4 will reference the new chunk-read
implementation but remain open for broader performance work; Issue #6 will remain open for
an actual optional adapter contribution.

## Alternatives considered

1. **Add optional `fields/start/stop/chunk_size` arguments to `load_dataset()`.** Rejected:
   mixing a materialized return value with iterator behavior makes the stable API harder to
   reason about and creates unclear behavior for CSV/JSON.
2. **Introduce a reader class.** Rejected for now: it adds lifecycle and resource-management
   surface without a current consumer requiring persistent sessions.
3. **Use separate `load_hdf5()` and `iter_hdf5_chunks()` APIs.** Selected: explicit semantics,
   compatibility with existing callers, and a small implementation boundary that can grow
   later without overloading the generic loader.
