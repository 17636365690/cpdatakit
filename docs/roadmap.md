# Roadmap

- **v0.2.0 (released 2026-08-24):** schema authoring helpers, clearer tensor-valued tabular
  encodings, explicit CLI mapping files, and richer nested-field validation coverage.
- **Unreleased maintenance:** strict HDF5 metadata validation, validation-aware atomic writes,
  explicit field/range and lazy chunk reads, immutable `FieldSchema` collection fields, expanded
  regression coverage, a deterministic HDF5 read benchmark, and an acceptance checklist for
  optional adapters.
- **v0.3.0 (next release target):** API isolation through deep `Dataset.copy()` metadata copies
  and recursively immutable `ProfileSchema.conventions`, with JSON object/list serialization
  preserved; opt-in record-axis HDF5 storage chunking; 100k/1M-record scaling evidence; and an
  85% CI coverage gate with clean-wheel HDF5 API smoke checks. The first optional adapter remains
  a separate evidence-gated item requiring an official format, license review, and reproducible
  fixtures. Broader large-file optimization remains tracked by Issue #4.
- **v0.4.0:** schema migration tools, comparison/report bundles, and stronger compatibility tests.

No roadmap item promises direct ODB/DADF5 support. Such work remains evidence- and license-gated.

