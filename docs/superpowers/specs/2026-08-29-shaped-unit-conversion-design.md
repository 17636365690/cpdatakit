# Shaped Field Unit Conversion Design

**Date:** 2026-08-29  
**Status:** Approved in chat; implementation in progress

## Goal

Make explicit `FieldMapping` unit conversions work for scalar and per-record shaped numeric
fields without changing the public normalization API or introducing scientific inference.

## Scope

This change covers:

1. Scalar, vector, matrix, and higher-rank tensor unit conversion in `normalize_dataset()`.
2. Shape-preserving numeric coercion driven by the target `FieldSchema`.
3. Clear failures for ragged arrays, wrong shapes, non-numeric values, and incompatible units.
4. Preservation of existing metadata, field mapping logs, source immutability, and no-conversion
   rename behavior.
5. Regression tests and documentation for scalar/vector/matrix/tensor conversions.

Out of scope: schema inference, automatic tensor component ordering, flattening shaped values,
HDF5 format changes, schema snapshots, solver adapters, and changes to the public `FieldMapping`
constructor.

## Design

`FieldMapping` remains the explicit source-to-target and input-unit-to-output-unit contract.
`normalize_dataset()` loads the validated target schema and uses the target field's declared
`shape` as the only shape contract. A scalar target requires one numeric value per record. A
shaped target requires one nested numeric array per record whose complete shape equals the
declared shape. Values are never flattened and no shape or scientific convention is guessed.

Conversion is performed on a defensive `Dataset.copy()`. For scalar fields, the converter checks
that values are real numeric scalars and converts the column with Pint. For shaped fields, it
coerces each non-missing record to a numeric NumPy array, checks its shape, converts every array
element with Pint, and stores one float-valued array per record. A missing scalar record remains
missing so the schema's existing `allow_missing` and validation rules decide whether it is valid;
NaN elements inside an otherwise shaped array remain visible to validation as non-finite values.

Ragged nested arrays, arrays with a different shape, booleans, strings, complex values, and other
non-numeric values raise `NormalizationError` before the result is returned. Pint dimensionality,
undefined-unit, and conversion errors remain `NormalizationError` with the source and requested
units in the message. The conversion does not mutate the input dataset.

After conversion, the existing metadata behavior remains: the target unit replaces the source
unit, the target field is recorded in `field_mapping`, and `drop_unmapped` retains its current
semantics. A mapping without units continues to rename/copy fields without numeric coercion.

## Error handling

- Invalid target names, duplicate mappings, missing sources, and overwrite collisions keep their
  existing `NormalizationError` behavior.
- A shaped value that cannot be represented as a regular numeric array raises `NormalizationError`
  identifying the source field and record position.
- A shaped value with a declared-shape mismatch raises `NormalizationError` identifying the
  expected shape and observed shape.
- An incompatible or undefined unit raises `NormalizationError` without returning a partially
  normalized dataset.

## Compatibility

The `normalize_dataset(dataset, schema, mappings, *, drop_unmapped=False)` signature is unchanged.
Existing scalar mappings and no-unit renames retain their output columns and metadata semantics.
Existing CSV/JSON/HDF5 readers and the CPDataKit HDF5 layout are unchanged. New shaped conversion
behavior is additive for schemas that already declare `shape`.

## Test strategy

Tests will be written before the implementation and run in focused red/green cycles. The suite
will verify:

- scalar Pa-to-MPa conversion remains correct;
- vector, matrix, and rank-three tensor conversions scale every element and preserve per-record
  shape;
- converted shaped values have numeric floating dtype and updated target units;
- the mapping log records source, target, input unit, output unit, and note;
- malformed/ragged arrays, wrong shapes, strings, booleans, and incompatible units fail clearly;
- the original DataFrame and nested values remain unchanged after successful normalization.

## Documentation

`docs/data-format.md`, `README.md`, `README.zh-CN.md`, and `CHANGELOG.md` will state that explicit
unit conversion applies elementwise to declared shaped numeric fields and preserves their trailing
dimensions. The documentation will continue to require producers to declare tensor conventions;
unit conversion will not infer stress measures, strain measures, orientation representations, or
component order.

## Acceptance criteria

- All focused normalization tests and the full test suite pass.
- Scalar/vector/matrix/tensor conversions preserve the declared shape and produce expected values.
- Malformed shaped data and incompatible units raise documented `NormalizationError` failures.
- Existing public APIs and HDF5 format version 1.0 remain compatible.
- Ruff, format, coverage, and package build checks remain green.
