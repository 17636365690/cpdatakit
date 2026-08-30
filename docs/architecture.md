# Architecture

The `src` package separates contracts (`schema`, `model`), boundary failures (`exceptions`),
read/write (`io`), pure transformations (`normalization`), checks (`validation`), descriptive
output (`statistics`), structure inspection (`inspection`), offline report rendering (`reporting`),
graphics (`plotting`), provenance, and the thin `cli` orchestration layer.

The dependency direction is inward. Adapters and CLI create `Dataset` values. Validation and
normalization consume schemas. HDF5 serialization records results and provenance. Inspection reads
structure and metadata. Reporting returns validation and statistics results for callers to interpret
with their domain methods. Public API imports are intentionally small and stable. Built-in schemas
ship as package resources, so installed wheels resolve them directly. External-format integrations
use `DatasetAdapter` or a case-specific documented extractor with a focused read-only contract and
independent evidence. The bundled DAMASK DADF5 reader uses h5py and keeps the DAMASK runtime outside
the import path.

The `inspect` boundary uses h5py directly for CPDataKit HDF5 attrs, dataset shape/dtype/chunks, and
bounded slices. Structure discovery therefore stays independent of full-table materialization. The
`report` boundary uses the established `Dataset` path required by the validation and statistics APIs,
then emits aggregate values and sanitized metadata. Its HTML renderer carries a small print
stylesheet and remains self-contained for offline use.

Trust boundaries are explicit: parsers consume declared fields, normalizers work on copies,
validation reports declared conformance, and callers pass the explicit force option when output
paths may replace existing files.

