# CPDataKit HDF5 2.0

HDF5 2.0 is the planned storage envelope for `ScientificDataset`. It stores named dimensions,
coordinates, and variables directly. It does not first flatten an N-dimensional value into a table.

## Layout

```text
/
  attrs: format=CPDataKit, format_version=2.0, profile, schema_version,
         schema_json, schema_sha256, units_json, provenance_json,
         validation_summary_json
  /dimensions/<name>       attrs: length
  /coordinates/<name>      data + attrs: dims_json, unit
  /variables/<name>        data + attrs: dims_json, unit, role, dtype
```

Dimension names are ordered references. Every coordinate and variable must reference dimensions
that exist in `/dimensions`. A variable's HDF5 shape must match the referenced dimension lengths.
Coordinates are first-class arrays and may be numeric or string. A string coordinate has an empty
unit attribute in the storage layer and a null unit in the resolved schema.

The hand-authored generator in `scripts/generate_hdf5_v2_fixtures.py` creates a thermal-field case
with `temperature(time=4,y=3,x=4)`. It also creates malformed files for a missing dimension
reference, a root version mismatch, and a schema digest mismatch.

## Metadata and integrity

The schema snapshot is compact canonical JSON. `schema_sha256` is its lowercase SHA-256 digest over
UTF-8 bytes. Units, provenance, validation summary, variable roles, and dimension references are
explicit metadata. Reader code must reject a malformed envelope before materializing values.

Writes use the same-directory temporary-file and replacement pattern as HDF5 1.0. Readers expose
field/variable selection and bounded slices through an explicit `ReadLimits` value. A v2 reader never
weakens the v1 reader's required metadata checks.

## Version dispatch and migration

The root `format_version` selects the reader. HDF5 1.0 stays the tabular reader. A v1-to-v2 change is
an explicit migration with source/target schema and format hashes. It can add named dimensions or
coordinates only when the operation is lossless. Physical meaning and record axes are never inferred.
