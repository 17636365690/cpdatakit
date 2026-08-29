# Shaped Field Unit Conversion

**Date:** 2026-08-29  
**Status:** Approved in chat. Implementation in progress.

## Why this change is needed

The current normalizer calls pandas astype(float) on a whole column. That works for scalar
records. It fails when a cell contains a vector or tensor, because pandas treats the nested value
as one object rather than as a numeric array.

The normalizer should use the target FieldSchema shape. A scalar target accepts one real numeric
value per record. A shaped target accepts one regular numeric array per record with the declared
shape. Nothing is flattened, and no scientific convention is inferred.

## Behavior

FieldMapping keeps the current public API. It remains the place where a caller names the source
and target fields and supplies the input and output units.

The normalizer works on Dataset.copy(). For a scalar field it checks the values and sends the
column through Pint. For a vector, matrix, or higher-rank tensor it checks each non-missing
record with NumPy, converts its elements with Pint, and stores one float64 array per record.
Missing scalar records remain missing so the schema's allow_missing setting can decide whether
they are acceptable. NaN elements inside an array remain present for the existing non-finite
value check.

Ragged arrays, wrong shapes, booleans, strings, complex values, and other non-numeric objects
raise NormalizationError. The message includes the source field and record position. Pint errors
include the requested input and output units. An error leaves no partially normalized result.

After a successful conversion, the target unit and field mapping log are updated exactly as they
are for scalar fields. A mapping without units still performs only a rename or copy. The input
Dataset and its metadata remain unchanged.

## Compatibility

The normalize_dataset(dataset, schema, mappings, *, drop_unmapped=False) signature stays the same.
Existing scalar mappings and no-unit renames keep their current columns and metadata. CSV, JSON,
and CPDataKit HDF5 readers are untouched. HDF5 format version 1.0 is unchanged.

## Tests and documentation

The tests cover a scalar conversion, a vector, a matrix, and a rank-three tensor. They also cover
ragged arrays, wrong shapes, strings, source isolation, updated units, and the mapping log.

The data-format guide and both READMEs will say that unit conversion applies elementwise to
declared shaped numeric fields. They will keep the existing rule that stress measures, strain
measures, tensor component order, orientation representation, and identifier semantics must be
declared by the producer.

The implementation is accepted when the focused tests, full suite, coverage gate, Ruff, format
check, and package build pass.
