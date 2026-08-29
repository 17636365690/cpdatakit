# CPDataKit Stability Follow-up Design

## Goal

Make schema validation performed by `inspect_dataset()` correct for native CPDataKit HDF5 files
read in chunks, and make the lower-bound dependency claim visible in CI.

## Problem

`inspect_dataset()` currently validates each HDF5 chunk independently. Duplicate index values or
duplicate records that straddle a chunk boundary are therefore invisible to the inspection result.
The full in-memory `validate_dataset()` path already detects these findings, so the two public
validation paths can disagree for the same file.

The existing CI matrix covers Ubuntu and Windows with the newest compatible dependencies. It does
not exercise the lower bounds declared in `pyproject.toml`.

The duplicate-row implementation also used a DataFrame-level mapping method that is not present
in pandas 2.0, even though pandas 2.0 is the declared minimum.

## Design

Keep `validate_dataset()` behavior and its public signature unchanged. Add a private streaming
validation path that reuses the existing field, unit, extension, shape, dtype, and range checks for
each chunk, while accumulating duplicate-record and unique-index counts across the complete stream.
The accumulator stores normalized keys and counts while inspection processes the HDF5 table in
bounded chunks rather than one DataFrame. At the end of the stream it emits the same issue codes, severities,
messages, and affected-record semantics as the existing full-frame validator.

`inspect_dataset()` will use this streaming path only for native CPDataKit HDF5 files. CSV, JSON,
DAMASK adapter reads, and direct `validate_dataset()` calls keep their current code paths.

Duplicate normalization will use the stable Series-level mapping API so the direct validator works
on both the pandas 2.0 floor and newer pandas releases.

CI will add a Python 3.10 lower-bound runtime job. The lower-bound job will install the minimum
declared runtime versions and the test tools needed by the suite, then install CPDataKit against
those prepared versions.

## Documentation and scope

The Unreleased changelog and maintenance checklist will record the cross-chunk validation fix and
the lower-bound CI coverage. The existing benchmark script and adapter acceptance checklist remain
the evidence path for Issue #4 and Issue #6. Benchmark timing remains diagnostic; issue closure,
package layout, release version, author metadata, and artifact publication follow their dedicated
maintainer workflows.

## Testing

Add regression tests with a deliberately small inspection chunk size so that duplicate index and
duplicate record cases cross a chunk boundary. Assert the issue code, severity bucket, and affected
record count. Add a compatibility test that exercises validation with the newer DataFrame mapping
method unavailable. Run the focused tests first, then the full pytest/coverage/Ruff/build checks and
the existing 100k/1M diagnostic benchmarks.
