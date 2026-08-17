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

## Unit and convention rules

CSV and JSON take units from the selected schema. A `Dataset` or CPDataKit HDF5 may carry explicit
per-field units, which must be dimensionally compatible with schema units. Pint performs only
declared conversions, including both scale and offset for affine units such as degrees Celsius.
Producers must declare stress measure, strain measure, tensor component order, orientation
representation, and identifier semantics when relevant.

## HDF5 layout

Root attributes: `format=CPDataKit`, `format_version=1.0`, `profile`, `schema_version`,
`units_json`, `field_mapping_json`, `provenance_json`, and `validation_summary_json`.
Normalized columns are non-scalar datasets under `/data`, all with the same non-zero record count.
Provenance includes source description, basename, SHA-256 (never an absolute source path), UTC
conversion timestamp, package/Python versions, and operation log. Readers reject missing
markers/groups, empty or inconsistent tables, and corrupt files.

## Validation meaning

A report contains `valid`, `errors`, `warnings`, codes, field names, messages, affected counts,
and optional suggestions. Checks cover declared fields/types/shapes/ranges, missing and non-finite
values, empty strings, duplicates, index validity, unit compatibility, extensions, and schema
version. Numeric fields reject booleans, complex values, datetimes, and numeric-looking strings;
boolean fields accept only boolean values. Range and integer checks apply elementwise to shaped
numeric fields. `valid=true` means only that declared structural checks passed.

