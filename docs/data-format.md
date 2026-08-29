# CPDataKit data format 1.0

CPDataKit defines its own solver-neutral contract. It is not DAMASK DADF5 or Abaqus ODB.

## Profiles

`curve` represents rows ordered by a unique non-negative `step`; built-in scalar strain and stress
are dimensionless and MPa in the example contract. `point` requires a unique non-negative
`point_id` and may declare `grain_id`, `phase_id`, and Cartesian coordinates. `field2d` requires
`x`, `y`, and scalar `value`, with optional grain and phase identifiers.

The bundled JSON schemas under `src/cpdatakit/schemas` are normative for version 1.0. A field
entry contains `name`, `aliases`, `required`, `dtype`, per-record `shape`, `role`, `unit`,
`allow_missing`, range/index constraints, and a description. A profile also carries conventions
and an extension prefix. Schema version other than `1.0` is rejected.

Aliases are documentation, not automatic guesses. An alias is only applied through an explicit
`FieldMapping`. Custom fields must be fully declared in a custom schema or begin with `user_`.

## Tensor-valued tabular encoding

JSON records and CPDataKit HDF5 represent a vector or tensor as one value per record. The value
must match the declared `shape`; a schema may also declare `components` in row-major order so the
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

The JSON representation is a nested array such as `[[1.0, 0.0], [0.0, 1.0]]`; the HDF5
representation is a dataset with shape `(record_count, 2, 2)`. CPDataKit never infers component
order from field names. CSV inputs should use scalar columns or be converted to JSON/HDF5 by an
explicit producer because CSV has no portable nested-array representation.

Schema version `1.0` accepts the optional `components` declaration for migration-safe contracts.
A future schema version may make tensor roles and component vocabularies normative; readers reject
unsupported versions instead of guessing a migration.

## Unit and convention rules

CSV and JSON take units from the selected schema. A `Dataset` or CPDataKit HDF5 may carry explicit
per-field units, which must be dimensionally compatible with schema units. Pint performs only
declared conversions, including both scale and offset for affine units such as degrees Celsius.
When a mapping targets a declared vector, matrix, or tensor field, Pint converts each numeric
element while preserving the complete per-record shape and trailing dimensions. Ragged arrays,
wrong shapes, booleans, strings, complex values, and incompatible units are rejected. The mapping
still must explicitly declare both input and output units; CPDataKit does not infer stress/strain
measures, tensor component order, orientation representation, or identifier semantics.
Producers must declare stress measure, strain measure, tensor component order, orientation
representation, and identifier semantics when relevant.

## In-memory stability

`Dataset.copy()` deep-copies the DataFrame and the complete nested `metadata` mapping while
preserving the optional source path. Mutating a nested mapping or list through a copied dataset
therefore cannot change the original dataset. This isolation is part of the safe normalization
boundary; callers should use `copy()` when a transformation needs an independent working value.

`ProfileSchema.conventions` is recursively immutable in memory. Nested mappings are read-only,
sequences are represented as tuples, sets as frozensets, and other values are defensively copied.
This prevents a caller from changing a schema through a nested value after construction. The
serialization boundary remains JSON-friendly: `schema_to_dict()` and `schema_to_json()` thaw
conventions back to JSON objects and lists, so the on-disk schema representation does not expose
the tuple-backed in-memory form.

## HDF5 layout

Every CPDataKit HDF5 file must contain all eight root attributes: `format=CPDataKit`,
`format_version=1.0`, `profile`, `schema_version=1.0`, `units_json`, `field_mapping_json`,
`provenance_json`, and `validation_summary_json`. The format and schema version markers must be
present and exactly `1.0`; missing or unsupported markers are rejected. The profile must be
supported, and each JSON attribute must decode to an object. Missing, wrong-type, malformed, or
structurally inconsistent metadata raises `DataReadError` instead of being replaced with
defaults.

Normalized columns are non-scalar datasets under `/data`, all with the same non-zero record count.
Provenance includes source description, basename, SHA-256 (never an absolute source path), UTC
conversion timestamp, package/Python versions, and operation log. Readers reject missing
markers/groups, empty or inconsistent tables, and corrupt files. HDF5 field and range reads use
the first dataset axis as the record axis; shaped values retain their trailing dimensions.

`write_hdf5()` refuses to write a failed validation result by default. To create an HDF5 file that
records an invalid validation result, callers must explicitly pass `allow_invalid=True`. HDF5
writes use a same-directory temporary file and replace the target only after serialization
finishes, removing the temporary file if serialization fails.

For larger files, `load_hdf5()` supports explicit field selection and half-open record ranges,
while `iter_hdf5_chunks()` yields bounded reads. `load_dataset(path)` remains the stable full-read
entry point for existing workflows.

Storage chunking is opt-in through `write_hdf5(..., hdf5_chunk_size=N)`, where `N` is a positive
integer. The default `None` keeps the existing layout for small files and existing producers. When
configured, `N` applies to the record axis: a field with values shaped `(record_count, *tail_shape)`
is stored with chunks `(min(N, record_count), *tail_shape)`. Vector and tensor trailing dimensions
are therefore retained rather than flattened. `hdf5_chunk_size` controls the HDF5 storage layout;
the `chunk_size` argument to `iter_hdf5_chunks()` controls the number of records returned per
reader iteration. Full, field-selected, and bounded/chunked reads preserve the same logical values.

## Inspection and validation reports

`inspect_dataset()` returns a JSON-compatible structure with `file`, ordered `fields`,
`record_count`, `hdf5`, `provenance`, `adapter`, and `risks`. A field record carries its name, dtype,
full shape, per-record shape, declared unit, missing-value count, optional description, and HDF5
chunks when they exist. `inspect_hdf5_structure()` reads native HDF5 attrs and dataset metadata with
h5py, then counts missing values from bounded slices. It never calls `load_dataset()` to materialize
the whole HDF5 table. DAMASK DADF5 detection stays read-only and follows the adapter's explicit
selection rules.

`build_report()` adds the selected schema profile/version, `validation.errors`,
`validation.warnings`, descriptive statistics, provenance, adapter information, HDF5 chunk details,
and a scope note saying that validation conformance does not establish physical or scientific
correctness. JSON uses sorted keys. Markdown keeps fixed headings and field order. HTML is static,
escaped, and ready for offline printing. Reports contain aggregate metadata and no raw records.
Provenance keeps a basename and may include a digest, never an absolute path. Credential-like values
are redacted.

The CLI forms are:

```text
cpdatakit inspect INPUT [--schema SCHEMA] [--format text|json] [--output PATH] [--force]
cpdatakit report INPUT --schema SCHEMA --output PATH [--format html|markdown|json] [--force]
```

Existing outputs are protected by default. Exit status `0` means no validation errors, `1` means
data findings, and `2` means a parameter, schema, input, metadata, or output failure.

## Validation meaning

A report contains `valid`, `errors`, `warnings`, codes, field names, messages, affected counts,
and optional suggestions. Checks cover declared fields/types/shapes/ranges, missing and non-finite
values, empty strings, duplicates, index validity, unit compatibility, extensions, and schema
version. Numeric fields reject booleans, complex values, datetimes, and numeric-looking strings;
boolean fields accept only boolean values. Range and integer checks apply elementwise to shaped
numeric fields. `valid=true` means only that declared structural checks passed.

