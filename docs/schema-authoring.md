# Schema authoring and explicit mapping

CPDataKit exposes small helpers for creating, checking, documenting, and writing external JSON
contracts. They validate the contract before it reaches a reader or normalizer:

```python
from cpdatakit import (
    describe_schema,
    make_field_schema,
    make_profile_schema,
    write_schema,
)

schema = make_profile_schema(
    "point",
    [
        make_field_schema(
            "point_id", "integer", required=True, unit="dimensionless", index=True, unique=True
        ),
        make_field_schema(
            "stress",
            "float",
            required=True,
            shape=[2, 2],
            components=["xx", "xy", "yx", "yy"],
            unit="MPa",
        ),
    ],
    conventions={"stress_measure": "Cauchy stress"},
)
write_schema(schema, "point-tensor.json")
print(describe_schema(schema))
```

`validate_schema` accepts a built-in profile, a JSON path, a `ProfileSchema`, or a JSON-like
mapping. `schema_to_dict` and `schema_to_json` provide canonical serialization for review and
version control. `write_schema` preserves an existing file. Pass `force=True` when replacement is
intended.

## Canonical schema hash

Use the compact form when you need to put a schema in an artifact or compare it later:

```python
from cpdatakit import schema_sha256, schema_to_canonical_json

canonical = schema_to_canonical_json(schema)
print(schema_sha256(schema))
```

The string has sorted keys, compact separators, UTF-8 encoding, and no trailing newline. The same
schema therefore produces the same hash on different runs. CPDataKit stores this string in the
HDF5 `schema_json` attribute. An optional `schema_uri` is recorded as provenance for caller-managed
access.

## CLI mapping files

All field renames and unit conversions must be explicit. Pass a JSON mapping file to `validate`,
`summary`, `convert`, or `plot`:

```json
{
  "mappings": [
    {
      "source": "sigma_pa",
      "target": "stress",
      "input_unit": "Pa",
      "output_unit": "MPa",
      "source_note": "exporter column documented by the producer"
    }
  ],
  "drop_unmapped": false
}
```

Example:

```bash
cpdatakit convert input.csv --schema curve --mapping mapping.json --output curve.h5
```

The mapping file applies declared field and unit choices. The schema declares each target, the input
provides each source, and duplicate targets produce a validation error. Pass `--force` when the
command should replace an existing output file.
