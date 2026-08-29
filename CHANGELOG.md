# Changelog

All notable changes follow Keep a Changelog; versions follow Semantic Versioning.

## [Unreleased]

### Added

- Explicit `load_hdf5()` field/range reads and `iter_hdf5_chunks()` lazy chunk iteration, with
  metadata-preserving `Dataset` results and record-axis slicing.
- Opt-in record-axis HDF5 storage chunking through `write_hdf5(..., hdf5_chunk_size=N)`; the
  default layout remains unchanged when the option is omitted.
- A deterministic HDF5 read benchmark covering full, selected-field, and chunked reads.
- 100k- and 1M-record benchmark commands that report storage chunk size, exact record counts,
  elapsed time, and peak RSS where available.
- An adapter contribution acceptance checklist covering format evidence, licensing, fixtures,
  conventions, offline tests, ambiguity handling, and dependency boundaries.
- A read-only DAMASK DADF5 adapter for explicit increment/branch/dataset selections, with source
  metadata and no DAMASK runtime dependency.
- Added `inspect` for CSV, JSON, CPDataKit HDF5, and clear DAMASK DADF5 selections. It reads HDF5
  metadata and missing values in bounded slices, then shows chunks, provenance, adapter details, and
  optional schema findings.
- Added offline `report` output in HTML, Markdown, and canonical JSON. Reports include the schema,
  validation errors and warnings, descriptive statistics, sanitized provenance, and overwrite
  protection. The CPDataKit HDF5 1.0 format and existing CLI commands stay unchanged.
- Added helpers for canonical schema JSON and SHA-256 hashes. New HDF5 files now carry the schema
  snapshot, with an optional `schema_uri` that is recorded but never fetched.

### Fixed

- Require all eight CPDataKit HDF5 root attributes, exact supported version markers, and JSON
  metadata objects; reject missing, unsupported, malformed, or inconsistent envelopes.
- Refuse invalid HDF5 validation results unless `allow_invalid=True` is explicit, and make writes
  atomic with temporary-file cleanup after serialization failures.
- Fixed unit conversion for declared vector, matrix, and tensor fields. Values keep their
  per-record shape, and malformed shaped values report the record that failed.
- Check embedded HDF5 schema JSON, profile/version matches, and hashes while keeping legacy
  format-1.0 files without snapshots readable.

### Changed

- Make `Dataset.copy()` isolate nested metadata so copied working datasets cannot mutate the
  original metadata tree.
- Make `ProfileSchema.conventions` recursively immutable in memory while keeping
  `schema_to_dict()` and `schema_to_json()` output as JSON objects and lists.
- Keep `FieldSchema` collection fields immutable in memory while preserving list-shaped schema JSON
  output.
- Enforce an 85% project coverage gate in CI and smoke-test `load_hdf5` and `iter_hdf5_chunks` from
  a clean wheel installation.
- Expand regression coverage for HDF5 metadata, bounded reads, safe writes, schema immutability,
  nested fields, CLI failures, and the adapter abstraction.

## [0.2.0] - 2026-08-24

### Added

- Public schema-authoring helpers for constructing, validating, serializing, writing, and
  documenting external JSON contracts.
- Optional tensor component-order declarations for vector and matrix fields.
- Strict JSON mapping files for CLI validation, summaries, conversion, and plots.
- Hypothesis property coverage for malformed nested shapes, non-finite values, dtype boundaries,
  and tensor HDF5 round trips.
- Add CodeQL v4 scanning for Python code on pushes, pull requests, and a weekly schedule.

### Fixed

- Keep explicit field mappings and unit conversions auditable in CLI-produced HDF5 metadata.
- Reject unsupported mapping keys and malformed schema component declarations before processing data.

### Changed

- Pin Hatchling and normalize the tagged commit timestamp for reproducible distributions.
- Build distributions twice in CI and reject byte-level differences before packaging.

## [0.1.1] - 2026-08-17

### Fixed

- Enforce custom-schema dtype, shape, bounds, alias, and option declarations at load time.
- Validate boolean and shaped numeric fields without accepting unrelated coercible values.
- Handle nested custom values safely during duplicate-record detection.
- Apply affine unit conversions with both scale and offset.
- Reject malformed CPDataKit HDF5 tables with consistent `DataReadError` failures.
- Reject shaped or non-numeric histogram fields with a concise domain error.

### Added

- PyPI Trusted Publishing workflow with tagged, inspected distributions and OIDC authentication.
- Five-minute synthetic-data quickstart and a scientifically scoped repository social-preview asset.
- Release metadata and semantic-version tag consistency checks.

### Changed

- The README now offers a one-command GitHub Release installation for non-contributors.
- Repository-relative README links are absolute so they work correctly on PyPI.
- Publishing documentation and workflow now target the complete v0.1.1 distribution.

## [0.1.0] - 2026-08-12

### Added

- Versioned `curve`, `point`, and `field2d` schemas.
- CSV, JSON records, and CPDataKit HDF5 I/O with provenance.
- Structured validation, explicit normalization, descriptive summaries, plotting, CLI, and API.
- Deterministic synthetic datasets, tests, documentation, and cross-platform CI.

