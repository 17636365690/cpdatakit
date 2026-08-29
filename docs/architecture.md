# Architecture

The `src` package separates contracts (`schema`, `model`), boundary failures (`exceptions`),
read/write (`io`), pure transformations (`normalization`), checks (`validation`), descriptive
output (`statistics`), structure inspection (`inspection`), offline report rendering (`reporting`),
graphics (`plotting`), provenance, and the thin `cli` orchestration layer.

The dependency direction is inward: adapters and CLI create `Dataset` values; validation and
normalization consume schemas; HDF5 serialization records results and provenance. Inspection reads
structure and metadata. Reporting reuses the validation and statistics results, leaving scientific
interpretation to the caller. Public API imports are intentionally small and stable. Built-in
schemas are package resources, so wheels do not depend on the working tree. External-format
integrations belong behind `DatasetAdapter` and must remain narrow, read-only where possible, and
independently evidenced. The bundled DAMASK DADF5 reader uses h5py without importing the DAMASK
runtime.

The `inspect` boundary uses h5py directly for CPDataKit HDF5 attrs, dataset shape/dtype/chunks, and
bounded slices. Structure discovery therefore stays independent of full-table materialization. The
`report` boundary uses the established `Dataset` path required by the validation and statistics APIs,
then emits aggregate values and sanitized metadata. Its HTML renderer carries a small print
stylesheet and has no JavaScript, CDN, or network resource.

Trust boundaries are explicit: parsers do not infer science, normalizers do not mutate inputs,
validation does not claim physical correctness, and output paths are protected unless force is
given.

