# Architecture

The `src` package separates contracts (`schema`, `model`), boundary failures (`exceptions`),
read/write (`io`), pure transformations (`normalization`), checks (`validation`), descriptive
output (`statistics`), graphics (`plotting`), provenance, and the thin `cli` orchestration layer.

The dependency direction is inward: adapters and CLI create `Dataset` values; validation and
normalization consume schemas; HDF5 serialization records results and provenance. Public API
imports are intentionally small and stable. Built-in schemas are package resources, so wheels do
not depend on the working tree. External-format integrations belong behind `DatasetAdapter` and
must remain narrow, read-only where possible, and independently evidenced. The bundled DAMASK
DADF5 reader uses h5py without importing the DAMASK runtime.

Trust boundaries are explicit: parsers do not infer science, normalizers do not mutate inputs,
validation does not claim physical correctness, and output paths are protected unless force is
given.

