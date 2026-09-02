# Architecture

CPDataKit has a generic scientific-data contract core and a crystal-plasticity compatibility
vertical. The core does not infer physical semantics. It operates on tabular records whose fields,
units, scalar or fixed per-record shapes, constraints, and conventions are explicitly declared.

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

The additive `application` package owns the first v0.6 service migration slice: typed import/inspect,
schema/mapping resolution, validation/summary, HDF5 1.0 conversion, reports, comparisons, and
declared plots. It translates typed CPDataKit exceptions into sanitized service results, keeps
artifacts workspace-relative, and has no argparse, HTTP, template, or browser dependency. The CLI
routes these current data workflows through the service boundary while preserving its v0.5 exit-code
and output contracts; schema diff remains on its existing path until its adapter is tested.

Bundled `curve`, `point`, and `field2d` schemas, grain/phase summary enrichment, stress-strain and
identifier plots, and the DAMASK adapter form the CP vertical. Generic profiles arrive as explicit
JSON schemas and use the same core without acquiring CP fields or statistics. CP-specific functions
remain available as compatibility entry points rather than implicit requirements of every profile.

External adapters retain `DatasetAdapter.load(path)`. Optional immutable descriptors and format
detection are registered in an in-process `AdapterRegistry`; detection identifies representation
only and never chooses scientific selections. Native CSV, JSON records, and CPDataKit HDF5 stay in
the core reader boundary.

The `inspect` boundary uses h5py directly for CPDataKit HDF5 attrs, dataset shape/dtype/chunks, and
bounded slices. Structure discovery therefore stays independent of full-table materialization. The
`report` boundary uses the established `Dataset` path required by the validation and statistics APIs,
then emits aggregate values and sanitized metadata. Its HTML renderer carries a small print
stylesheet and remains self-contained for offline use.

Trust boundaries are explicit: parsers consume declared fields, normalizers work on copies,
validation reports declared conformance, and callers pass the explicit force option when output
paths may replace existing files.

