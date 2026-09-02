# CPDataKit schema 2.0

Schema 2.0 is the planned contract for `ScientificDataset`. It adds named dimensions, coordinates,
N-dimensional variables, attributes, chunk hints, and explicit local composition. Schema 1.0 remains
the contract for the existing `Dataset` and its built-in profiles.

## Shape of a contract

Every dimension has a name and finite length. Coordinates name their ordered dimensions, dtype, and
unit. Variables name their ordered dimensions, dtype, unit, role, and optional component labels.
String coordinates may use a null unit. Numeric variables retain the current requirement for an
explicit unit, including `dimensionless` when appropriate.

The fixtures under `tests/fixtures/schema-v2/` use a `thermal-field` profile with dimensions
`time=4`, `y=3`, and `x=4`. `temperature(time,y,x)` is a measured field. The source fragments split
the time/stage contract, spatial coordinates, and temperature declaration.

## Composition

`extends` resolves one base schema. `includes` adds named fragments. Resolution is local and follows
the source manifest in declaration order. A resolver rejects cycles, duplicate dimensions/
coordinates/variables, incompatible overrides, schema-version mismatches, missing files, and
ambiguous paths before it reads data. HTTP references are outside the default resolver.

The resolved contract is canonicalized with sorted object keys and stable array order. The source
manifest is part of the audit record, while the resolved contract is the input to the schema hash.
Changing a fragment changes the resolved hash. Existing schema 1.0 canonical JSON and hashes remain
byte-identical.

## Migration boundary

Schema 1.0 data are not silently promoted to 2.0. A future migration manifest will name the source
and target hashes, dimension/coordinate operations, unit choices, and any dropped or added values.
Lossy flattening and inferred physical meaning are errors.
