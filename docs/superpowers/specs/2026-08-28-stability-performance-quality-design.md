# Stability, HDF5 Performance, and Quality Gates Design

**Date:** 2026-08-28
**Status:** Approved in chat; implementation pending

## Goal

Build the next maintenance iteration on top of PR #20: make copied datasets and schemas
safe from hidden mutation, improve HDF5 storage for large sequential reads, enforce the current
quality level in CI, and prepare the project for a v0.3.0 release without adding solver-specific
runtime dependencies.

## Current baseline

- PR #20 is open and all its CI and CodeQL checks pass, but it is blocked on one required review.
- The PR adds strict HDF5 metadata validation, atomic writes, bounded/chunked reads, immutable
  FieldSchema collection fields, a benchmark, and documentation.
- The local PR branch has 101 passing tests and 87% total coverage, with lower module coverage
  in schema, normalization, and validation.
- Dataset.copy() still shallow-copies metadata, while ProfileSchema.conventions is a mutable dict.
- Issues #4 and #6 remain open for broader HDF5 performance work and an actual optional adapter.

## Scope

This iteration covers:

1. Deep defensive copying of Dataset metadata.
2. Recursive immutable representation of ProfileSchema.conventions with unchanged JSON output.
3. Optional HDF5 writer chunking, benchmark reporting at larger sizes, and performance tests.
4. A CI coverage gate and clean-wheel smoke coverage for the new public HDF5 APIs.
5. Documentation, roadmap, and changelog updates.
6. A stacked implementation branch/PR based on PR #20; PR #20 remains subject to its required review.
7. Post-merge release preparation for v0.3.0, without bumping the version before the required
   review and merge.

Out of scope: solver-specific adapters, ODB/DADF5 support, automatic scientific inference,
distributed processing, 3D interactive graphics, schema migration, and direct self-approval or
self-merging of protected GitHub changes.

## Design

### Dataset copy isolation

Dataset.copy() will use copy.deepcopy() for metadata while continuing to deep-copy the
DataFrame and preserve the source Path. A mutation to nested metadata in the copied Dataset
must never affect the original Dataset. This fixes normalization and future adapter code at
the existing trust boundary without changing the Dataset constructor or metadata schema.

### Immutable schema conventions

ProfileSchema.conventions will be annotated as a Mapping and normalized in __post_init__().
A small recursive freezer will convert mappings to MappingProxyType, lists/tuples to tuples, and
sets to frozensets; scalar values will be copied defensively. schema_to_dict() will recursively
thaw these values back to JSON-compatible dictionaries and lists. Existing built-in schemas
contain strings and remain byte-for-byte equivalent after JSON serialization.

The validator will accept any Mapping at the in-memory boundary but will continue rejecting
non-object schema conventions during construction/loading. The fields tuple and the existing
immutable FieldSchema collections remain unchanged.

### HDF5 writer chunking and benchmark

write_hdf5() will gain an optional hdf5_chunk_size: int | None = None. The default None
preserves the current output behavior. When set to a positive integer, each non-empty record
dataset is created with a first-axis chunk length of min(hdf5_chunk_size, record_count), while
trailing dimensions remain unchanged. Invalid sizes are rejected before creating a temporary
file. Existing atomic replacement and allow_invalid behavior remain in force.

scripts/benchmark_hdf5_read.py will accept hdf5_chunk_size and include it in its JSON report.
The benchmark will continue comparing full, selected-field, and chunked reads, and will be run
at 100,000 and 1,000,000 records during verification. The benchmark is diagnostic, not a
timing-based CI gate; the acceptance criterion is that chunked record counts are exact and
chunked memory does not grow linearly with total record count for a fixed chunk size.

### CI quality gate

The existing Ubuntu quality-and-build job will run one coverage command after installation:

~~~text
pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85
~~~

The existing Python/OS test matrix remains unchanged. The clean wheel smoke test will import
load_hdf5 and iter_hdf5_chunks in addition to the existing version and CLI checks. Ruff,
CodeQL, reproducible builds, Twine checks, and the supported-Python matrix remain required.

### Release and backlog handling

No version file changes occur before PR #20 is reviewed and merged. After merge, the public
HDF5 APIs and storage option should be released as v0.3.0, with pyproject.toml, CHANGELOG.md,
CITATION.cff, GitHub Release, and PyPI contents updated together.

Issue #4 will be split or retitled so the implemented bounded/chunked API is distinct from
remaining large-file performance and storage-layout work. Issue #6 will remain open for the
first real optional adapter; the checklist itself is documented but is not an adapter
implementation.

## Error handling

- Nested metadata changes in a Dataset copy are isolated by defensive deep copy.
- Schema convention mutation attempts raise TypeError from immutable mapping/sequence values.
- Invalid hdf5_chunk_size values raise ValueError before a temporary output is created.
- Existing DataReadError, DataValidationError, and OutputExistsError semantics are unchanged.
- CI coverage below 85% fails the quality-and-build job.
- Protected PRs remain blocked until an independent required review is present.

## Test strategy

Tests will follow red-green-refactor for production behavior:

- Dataset.copy() nested metadata isolation and source/DataFrame independence.
- ProfileSchema convention defensive copying, top-level and nested mutation rejection, and
  JSON round-trip compatibility.
- HDF5 chunk-size validation, dataset chunk layout, vector/tensor trailing shape preservation,
  and full/selected/chunked read equivalence.
- Benchmark smoke execution at 100,000 records and a larger local run at 1,000,000 records.
- CI workflow text contains the coverage gate and clean-wheel imports for both new APIs.
- Full pytest, coverage, Ruff, build, reproducible-build, and wheel smoke checks.

## Alternatives considered

1. **Deep-copy Dataset metadata but leave ProfileSchema conventions mutable.** Rejected because
   callers could still mutate an accepted schema contract after validation.
2. **Use only a top-level MappingProxyType.** Rejected because nested lists/dicts would remain
   mutable and violate the same trust-boundary principle.
3. **Always chunk every HDF5 dataset.** Rejected because it changes existing file layout and
   write performance for small files; the opt-in writer option preserves compatibility.
4. **Run coverage in every OS/Python matrix job.** Rejected because it duplicates work; one
   Ubuntu quality job is sufficient for the project-wide threshold.
