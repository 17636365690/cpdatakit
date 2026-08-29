# Architecture

The `src` package separates contracts (`schema`, `model`), boundary failures (`exceptions`),
read/write (`io`), pure transformations (`normalization`), checks (`validation`), descriptive
output (`statistics`), structure inspection (`inspection`), offline report rendering (`reporting`),
graphics (`plotting`), provenance, and the thin `cli` orchestration layer.

The dependency direction is inward: adapters and CLI create `Dataset` values; validation and
normalization consume schemas; HDF5 serialization records results and provenance. Inspection reads
structure and metadata. Reporting reuses the validation and statistics results, leaving scientific
interpretation to the caller. Public API imports are intentionally small and stable. Built-in
schemas ship as package resources, so installed wheels resolve them directly. External-format
integrations use `DatasetAdapter` or a case-specific documented extractor, with narrow, read-only
behavior and independent evidence. The bundled DAMASK DADF5 reader uses h5py and keeps the DAMASK
runtime outside the import path.

The `inspect` boundary uses h5py directly for CPDataKit HDF5 attrs, dataset shape/dtype/chunks, and
bounded slices. Structure discovery therefore stays independent of full-table materialization. The
`report` boundary uses the established `Dataset` path required by the validation and statistics APIs,
then emits aggregate values and sanitized metadata. Its HTML renderer carries a small print
stylesheet and remains self-contained for offline use.

Trust boundaries are explicit: parsers consume declared fields, normalizers work on copies,
validation reports declared conformance, and output paths require an explicit force option before
replacement.

