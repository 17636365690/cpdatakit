# CPDataKit data format 1.0

CPDataKit defines an independent, solver-neutral contract alongside DAMASK DADF5 and Abaqus ODB.

## Profiles

`curve` represents rows ordered by a unique non-negative `step`. Built-in scalar strain and stress
are dimensionless and MPa in the example contract. `point` requires a unique non-negative
`point_id` and may declare `grain_id`, `phase_id`, and Cartesian coordinates. `field2d` requires
`x`, `y`, and scalar `value`, with optional grain and phase identifiers.

The bundled JSON schemas under `src/cpdatakit/schemas` are normative for version 1.0. A field
entry contains `name`, `aliases`, `required`, `dtype`, per-record `shape`, `role`, `unit`,
`allow_missing`, range/index constraints, and a description. A profile also carries conventions
and an extension prefix. Readers support schema version `1.0`.

An external JSON schema may use any non-empty profile name. Bare names such as `curve` resolve
bundled schemas; pass a JSON path for an external profile. Fields are declared explicitly or use
the schema's extension prefix. Numeric fields declare units and shapes; schemas and mappings
record the scientific conventions used by the workflow.

Aliases document accepted source names and take effect through an explicit `FieldMapping`. Custom
fields are fully declared in a custom schema or begin with `user_`.

## Text input and numeric precision

The ordinary `load_dataset` CSV path uses comma-separated UTF-8 input and the existing pandas
missing-token and header conventions. For example, `001` is inferred as integer `1`, `NA` is
missing, and duplicate headers receive suffixes. Use the CSV confirmation workflow with explicit
string declarations when these tokens are identifiers or literal text, or when a file uses a
different encoding, delimiter, decimal mark, header row or unit row. Ordinary inferred input and
explicit lexical input are distinct contracts.

CSV and JSON numeric values are checked before DataFrame construction. Integer columns use
signed or unsigned 64-bit storage, including nullable integer storage when records are missing.
An integer such as `9007199254740993` must not pass through a float column merely because another
record is empty. Floating values use round-trip float64 parsing; binary floating rounding of
nonintegral decimal values remains part of that representation. An unrepresentable integer/float
mixture, a nonzero value underflowing to zero, or numeric overflow produces a `DataReadError`
with field and record context. Integers outside a compatible 64-bit range are rejected.

Nullable integer input does not imply every output format can encode it. A writer that cannot
preserve the values and missingness rejects conversion without publishing a partial output.
The original source remains unchanged. Explicit infinity values remain subject to schema
validation, rather than being treated as overflow caused by parsing a finite number.

## Tensor-valued tabular encoding

JSON records and CPDataKit HDF5 represent a vector or tensor as one value per record. The value
must match the declared `shape`. A schema may also declare `components` in row-major order so the
component names are explicit and stable. For example:

```json
{
  "name": "stress",
  "dtype": "float",
  "shape": [2, 2],
  "components": ["xx", "xy", "yx", "yy"],
  "unit": "MPa",
  "required": true
}
```

The JSON representation is a nested array such as `[[1.0, 0.0], [0.0, 1.0]]`. The HDF5
representation is a dataset with shape `(record_count, 2, 2)`. Component order comes from the
schema declaration. CSV inputs use scalar columns. Producers can convert tensor data to JSON or
HDF5, which carry nested arrays.

Schema version `1.0` accepts the optional `components` declaration for migration-safe contracts.
A future schema version may make tensor roles and component vocabularies normative. Callers can
migrate newer versions through an explicit schema update.

## Unit and convention rules

CSV and JSON use schema units as assumptions when source units are absent. Validation adds a
`unit_not_declared` warning for each such field and keeps `valid=True` when there are no errors.
A `Dataset` or CPDataKit HDF5 may carry explicit per-field units, which must be dimensionally
compatible with schema units. The effective unit stays with its original numeric values. Pint applies the
conversions declared in the schema and mapping, including both scale and offset for affine units
such as degrees Celsius.
For a declared vector, matrix, or tensor, an explicit mapping applies Pint to each numeric element
and keeps the per-record shape and trailing dimensions. Ragged arrays, wrong shapes, booleans,
strings, complex values, and incompatible units are rejected. Mappings include both input and
output units. Producers declare stress/strain measures, tensor component order,
orientation representation, and identifier semantics through the schema and mapping when relevant.

HDF5 1.0 keeps the effective units in `units_json` and adds optional `units_source_json`, a mapping
from field name to `declared` (source metadata or explicit mapping), `assumed` (schema default),
`unknown` (historical unit with no recorded origin), or `unspecified` (a field without a unit).
For example, a CSV containing `time,stage` can produce `units_json={"time":"s","stage":null}`
and `units_source_json={"time":"assumed","stage":"unspecified"}`. Re-reading and rewriting
preserve these origins. A legacy file with no origin map remains readable and uses `unknown`
for its recorded units. The extra optional attribute is backward compatible with format 1.0.
Inspection, reports, and comparisons expose field-level `unit_source` values.

String fields require a text value for every record. Missing text produces `missing_string_value`
when `allow_missing=True`, or the existing `missing_value` error when `allow_missing=False`.
Fill the missing entries or remove the incomplete records before validation and HDF5 conversion.
Numeric fields retain their schema-declared missing-value policy.

Identity or equivalent-unit mappings preserve numeric values and storage types. Nonidentity
mappings reject integer precision loss and finite-to-infinite or nonzero-to-zero underflow;
legitimate offset results such as `273.15 K -> 0 degC` are accepted. Numeric errors retain field
and record context, and CSV confirmation translates that context to source row and column.
These checks also apply to scientific-array mappings. Existing nonfinite input is still reported
by validation; a unit conversion does not make invalid input valid.

## Self-contained HDF5 input

Readers and inspection require self-contained HDF5 files, including CPDataKit v1/v2, the DAMASK
adapter and HDF5-backed NetCDF. Before reading dataset payloads, they reject ExternalLink,
external raw storage and virtual datasets (VDS), including unused branches. SoftLinks are also
rejected in this policy; internal HardLink aliases and cycles are supported. Classic NetCDF3
is unaffected. There is no implicit trusted-path exception.

A root-file hash cannot authenticate data stored in another file. To import such a source,
produce a new self-contained file using a trusted producer, explicitly choosing the source
dependencies, and retain the original files separately. CPDataKit does not follow or copy those
dependencies automatically. Errors identify the link/storage category without exposing its
external target path.

### Bounded reads and conversion receipts

Application services accept `ReadLimits` and cooperative execution contexts and pass them to
internal reader helpers. Historical public reader signatures and export identities remain unchanged.
Bounded readers inspect source
record counts and selected fixed-width storage requirements before reading payloads. A byte limit
estimates materialized array storage, not total process RSS. Simple variable-length strings use a
conservative selected-count times whole-file-size estimate, including Unicode/object overhead;
small text tables remain usable and oversized estimates are rejected before reads. Numeric,
nested and compound variable-length payloads remain unsupported under explicit memory bounds;
ordinary reads without limits retain existing support. This is not a native-parser memory sandbox.
Read checkpoints run between slabs;
complete/global schema checks are not replaced with per-slab approximations.

Conversion provenance can contain optional `lineage` version 1 with a flat list of SHA-256-linked
receipts. Writers preserve the original CSV manifest, excluded columns, source description and
ordered prior operations, then append current input/schema/mapping digests and conversion
parameters. The origin is marked `recorded_from_csv_import` only when its source digest is known
to match the first input; older/incomplete histories remain `historical_unknown`.
Each new receipt records only the mapping applied in that operation. Previously applied mappings
remain in their earlier receipts or effective dataset metadata, and are not counted as a new
mapping when a later conversion performs no mapping.

Readers verify receipt hashes, parent links and mirrored metadata before exposing the data.
The limits are 64 receipts including the origin, 1 MiB of canonical provenance JSON and nesting
depth 32. Exceeding a limit rejects the new write instead of silently dropping history. These
hashes check consistency, not authorship or authenticity. A completed output digest belongs in an
external job/catalog receipt, not inside the file whose bytes it hashes. Reports sanitize their
displayed copy for privacy; the artifact's embedded receipts are the authoritative integrity copy.

## In-memory stability

`Dataset.copy()` deep-copies the DataFrame and the complete nested `metadata` mapping while
preserving the optional source path. Changes made through a copied dataset stay isolated from the
original. Use `copy()` when a transformation needs an independent working value.

`ProfileSchema.conventions` is recursively immutable in memory. Nested mappings are read-only,
sequences are represented as tuples, sets as frozensets, and other values are defensively copied.
Callers receive immutable nested values after construction. The serialization boundary remains
JSON-friendly: `schema_to_dict()` and `schema_to_json()` thaw
conventions back to JSON objects and lists before writing the on-disk schema representation.

## HDF5 layout

Every CPDataKit HDF5 file must contain all eight root attributes: `format=CPDataKit`,
`format_version=1.0`, `profile`, `schema_version=1.0`, `units_json`, `field_mapping_json`,
`provenance_json`, and `validation_summary_json`. The format and schema version markers must equal
`1.0`. Readers require a supported profile and JSON objects for each JSON attribute. Missing,
wrong-type, malformed, or structurally inconsistent metadata raises `DataReadError`.

Normalized columns are non-scalar datasets under `/data`, all with the same non-zero record count.
Provenance includes source description, basename, SHA-256, UTC
conversion timestamp, package/Python versions, and operation log. Readers require the documented
markers and groups, a non-empty consistent table, and valid file contents. HDF5 field and range reads use
the first dataset axis as the record axis. Shaped values retain their trailing dimensions.

Files produced by the current writer also carry `schema_json`, the compact canonical JSON for the
validated schema, and `schema_sha256`, its lowercase SHA-256 digest over UTF-8 bytes. An optional
`schema_uri` records an external reference for caller-managed access. Readers check the embedded
schema, its exact canonical JSON representation, profile/version, and digest. Legacy format-1.0
files that lack these additive attributes remain readable. A snapshot must contain all of its paired
attributes. The writer rejects empty datasets because the HDF5 table contract requires a non-zero
record count and the current reader refuses empty tables.

A legacy HDF5 1.0 file using built-in `curve`, `point`, or `field2d` may omit the schema snapshot.
A custom profile includes verified canonical `schema_json` and matching `schema_sha256`.
Both cases retain `format_version=1.0`.

`write_hdf5()` writes validated results by default. To record an invalid validation result, pass
`allow_invalid=True`. HDF5 writes use a same-directory temporary file and replace the target after
serialization finishes. A serialization failure removes the temporary file.

For larger files, `load_hdf5()` supports explicit field selection and half-open record ranges,
while `iter_hdf5_chunks()` yields bounded reads. `load_dataset(path)` remains the stable full-read
entry point for existing workflows.
Storage chunking is opt-in through `write_hdf5(..., hdf5_chunk_size=N)`, where `N` is a positive
integer. Leave the option as `None` to keep the existing layout for small files and existing producers. When
configured, `N` applies to the record axis: a field with values shaped `(record_count, *tail_shape)`
is stored with chunks `(min(N, record_count), *tail_shape)`. Vector and tensor trailing dimensions
stay intact. `hdf5_chunk_size` controls the HDF5 storage layout.
the `chunk_size` argument to `iter_hdf5_chunks()` controls the number of records returned per
reader iteration. Full, field-selected, and bounded/chunked reads preserve the same logical values.

## Inspection and validation reports

`inspect_dataset()` returns a JSON-compatible structure with `file`, ordered `fields`,
`record_count`, `hdf5`, `provenance`, `adapter`, and `risks`. A field record carries its name, dtype,
full shape, per-record shape, declared unit, missing-value count, optional description, and HDF5
chunks when they exist. `inspect_hdf5_structure()` reads native HDF5 attrs and dataset metadata with
h5py, then counts missing values from bounded slices. Native HDF5 inspection keeps reads bounded
throughout the process. DAMASK DADF5 detection reads according to the adapter's explicit selection
rules.

`build_report()` adds the selected schema profile/version, `validation.errors`,
`validation.warnings`, descriptive statistics, provenance, adapter information, HDF5 chunk details,
and a description of the checks performed. JSON uses sorted keys. Markdown keeps fixed headings
and field order. HTML is static, escaped, and ready for offline printing. Reports contain aggregate
metadata while source records remain in the source dataset. Provenance keeps a basename and may
include a digest. Credential-like values are redacted.

The CLI forms are:

```text
cpdatakit inspect INPUT [--schema SCHEMA] [--format text|json] [--output PATH] [--force]
cpdatakit report INPUT --schema SCHEMA --output PATH [--format html|markdown|json] [--force]
```

Existing outputs stay protected by default. Pass `--force` when a command should replace one. For
`validate`, `summary`, and `report`, status `0` means processing succeeded with zero validation
errors and status `1` means validation errors. For `inspect`, status `1` also covers declared
structural or missing-value risks; warning-only findings are reported but do not invalidate the
result. Status `2` means a parameter, schema, input, metadata, or output failure.

## Validation meaning

A report contains `valid`, `errors`, `warnings`, codes, field names, messages, affected counts,
and optional suggestions. Checks cover declared fields/types/shapes/ranges, missing and non-finite
values, empty strings, duplicates, index validity, unit compatibility, extensions, and schema
version. Numeric fields reject booleans, complex values, datetimes, and numeric-looking strings.
boolean fields require boolean values. Range and integer checks apply elementwise to shaped
numeric fields. `valid=true` means that the declared structural checks passed. It reports schema
conformance.

