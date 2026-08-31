# Schema Diff and Explicit Migration Design

**Date:** 2026-08-31
**Status:** Proposed for v0.4.0; implementation starts only after maintainer review

## Goal

Give CPDataKit users a deterministic way to compare two schema contracts and classify whether a
change is compatible, while keeping future schema/data migration explicit and free of scientific
inference.

## Current boundary

CPDataKit currently supports schema contract version `1.0`, serializes a complete canonical schema
snapshot into new HDF5 files, and already has explicit field mappings and unit conversions. A schema
diff must therefore compare canonical schema objects and must not treat a renamed field, changed
unit, changed tensor order, or changed stress/strain measure as harmless text edits.

## v0.4.0 first slice

The first slice is pure schema comparison and compatibility classification. It does not rewrite raw
records, infer units, infer tensor component order, or silently migrate a HDF5 envelope. A later
slice may add an explicit migration manifest only after a real source/target schema-version pair is
approved.

The proposed public function is:

```python
def diff_schemas(
    source: str | Path | ProfileSchema | Mapping[str, Any],
    target: str | Path | ProfileSchema | Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic JSON-compatible schema compatibility diff."""
```

The result has this exact shape:

```text
{
  "source": {"profile": str, "schema_version": str, "sha256": str},
  "target": {"profile": str, "schema_version": str, "sha256": str},
  "classification": "identical" | "backward-compatible" | "breaking",
  "fields": {
    "added": [str],
    "removed": [str],
    "changed": [{"name": str, "changes": [str]}]
  },
  "conventions_changed": [str],
  "extension_prefix_changed": bool,
  "requires_explicit_data_mapping": bool
}
```

All lists use source/target schema order, and `changed[*].changes` uses a fixed order: `dtype`,
`shape`, `components`, `unit`, `required`, `allow_missing`, `minimum`, `maximum`, `index`, `unique`,
`aliases`, `role`, and `description`.

## Compatibility rules

- `identical` means the two canonical JSON strings and hashes are equal.
- `backward-compatible` permits adding an optional field, adding an alias, or changing a
  description. The profile, schema version, extension prefix, conventions, and all existing field
  meanings must remain unchanged.
- `breaking` covers a removed field, a newly required field, dtype/shape/component/unit changes,
  range or index changes, convention changes, extension-prefix changes, profile changes, and schema
  version changes.
- A field rename is represented as a removal plus an addition and sets
  `requires_explicit_data_mapping=true`; no name similarity is inferred.
- Any changed unit or scientific convention requires an explicit caller mapping and domain review,
  even if Pint could perform a dimensional conversion.

## Future explicit migration manifest

When a schema version beyond `1.0` is approved, a separate manifest may enumerate exact operations
such as `rename_field`, `add_optional_field`, and `copy_unit`. Each operation must name its source,
target, input/output units where relevant, and scientific note. The manifest must declare source and
target schema hashes, reject unknown operations, and fail closed on missing or ambiguous fields.
Automatic conversion of stress/strain measures, tensor order, orientations, identifiers, or
physical meaning is prohibited.

## CLI and artifacts

The CLI proposal is:

```text
cpdatakit schema diff SOURCE TARGET [--format json|markdown] [--output PATH] [--force]
```

The command writes only the diff; it does not alter either schema or any HDF5 file. JSON uses the
project's sorted-key, `allow_nan=False` renderer. Markdown preserves the fixed field/change order.
Existing output protection and status `0/2` semantics follow the current CLI contract; a breaking
diff is a successful comparison result, not a parser failure.

## Testing and compatibility

Tests must cover identical schemas, optional additions, alias/description changes, every breaking
field property, profile/version changes, convention changes, rename detection, deterministic JSON,
and redaction of paths in error/output metadata. Existing `schema_to_dict()`, canonical hash,
HDF5 snapshot, and legacy format-1.0 tests remain unchanged and must pass.
