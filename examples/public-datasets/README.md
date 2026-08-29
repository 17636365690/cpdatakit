# Public dataset reference cases

These cases demonstrate CPDataKit at the boundary between openly published scientific data and
validated, reusable datasets. Raw third-party files are never committed here. Each case provides
a source citation, license note, download-and-hash instructions, explicit schema and mapping
files, an offline synthetic test fixture, and a reproducible workflow.

## Available cases

- [Surfalex HF (AA6016A) Workflow 7A](surfalex-aa6016a/README.md): a real MatFlow/DAMASK
  finite-strain workflow with 3 x 3 stress, strain, and deformation-gradient fields.

The case-specific extractor is intentionally not a generic MatFlow or DAMASK adapter. New
solver-specific adapters still require official format evidence, licensing review, and
redistribution-safe fixtures.
