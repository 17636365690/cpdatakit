# Real CSV workflow

Approved scope: the user's instruction to complete the next step after the three real-data trials.

## User outcome

A workbench user selects CSV parsing settings, previews actual columns, explicitly confirms included fields, types, roles and source/target units, then imports a validated dataset and generates its report without editing JSON. Original bytes, settings, exclusions and source hashes remain inspectable. Existing conversion artifacts can become inputs without downloading and uploading them again.

## Requirements

- Python >=3.12; retain existing dependency ranges and version 0.9.3 during development.
- CSV settings: comma/semicolon/tab delimiter, 1-based header row (0 means no header), optional separate unit row, decimal point/comma, UTF-8 with optional BOM or GB18030.
- Preview is bounded to 64 MiB and 100,000 data records by default; display at most five sample values per field. Reject ragged data explicitly rather than skipping rows.
- Field identity is source column index, including empty/duplicate names. Every column must be explicitly included or excluded. Included target names are unique. Numeric units and roles must be confirmed; do not infer physical conventions or call unknown units dimensionless.
- Preserve integer precision and apply only explicit unit conversions. Reject unsupported/lossy values with row/column guidance.
- CSV confirmation creates a project-local bundle with unchanged source.csv, schema.json, manifest.json and validated data.h5. Dataset/schema catalog records are one transaction. No existing output is replaced.
- Preserve new HDF5 1.0 data-column order, including extension fields; explicit selected-field order wins. Historical files without creation-order information retain their existing behavior.
- Reuse only verified conversion snapshots from the same project with their originating schema. Repeated reuse is idempotent, reports/comparisons are not data inputs, altered snapshots are rejected.
- UI selections and mapping state must not silently refer to prior data after import/reuse. Clearly identify current input, and distinguish mapping preview from a reportable stored result.
- No NetCDF3/datetime expansion, solver work, training, release, commit or push in this scope.

## Acceptance

Use small synthetic automated fixtures shaped like the audited IN718 files. Separately test the local licensed 12-file archive without copying it into the source repository: identify six semicolon columns, explicitly exclude the unnamed channel, declare five supported quantities, convert force N to kN, preserve 24,073 rows and column order, and compare values independently. In the browser, import one original curve through the table and generate its report; convert it and reuse that verified output for another report without uploading again. Reject missing units and malformed rows. Preserve all source hashes.
