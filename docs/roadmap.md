# Roadmap

- **v0.2.0 (released 2026-08-24):** schema authoring helpers, clearer tensor-valued tabular
  encodings, explicit CLI mapping files, and richer nested-field validation coverage.
- **v0.3.0 (released 2026-08-30):** strict HDF5 metadata validation, validation-aware atomic
  writes, explicit field/range and lazy chunk reads, immutable schema state, expanded regression
  coverage, deterministic HDF5 scaling benchmarks, and a documented adapter acceptance checklist.
  It also includes the read-only DAMASK DADF5 selection reader, the hash-verified Surfalex HF
  Workflow 7A reference case, an 85% CI coverage gate, lower-bound dependency tests, and clean-wheel
  HDF5 API smoke checks.
- **v0.4.0 (released 2026-08-31):** schema diff, the first pieces of explicit migration support,
  comparison/report bundles, and compatibility tests. The schema command compares contracts. The
  comparison command reads JSON reports and compares their schema, validation, structure, and
  scalar statistics.
- **v0.5.0 (released 2026-09-02):** scientific/engineering contract-core positioning, external
  non-CP profile names, self-describing custom-profile HDF5 1.0 files, generic x-y plots, explicit
  separation of CP identifier statistics, a lightweight adapter registry, and a complete
  thermal-cycle example.

Potential v0.6 work includes explicit migration manifests, additional evidence-backed adapters,
and richer schema-driven generic plots. N-dimensional array models, mesh topology, bulk new storage
formats, physical inference, GUI/cloud platforms, and solver execution require separate designs and
are not implied by v0.5.

Further DADF5 and ODB coverage follows the documented evidence and license review process.
