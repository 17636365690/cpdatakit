# Changelog

All notable changes follow Keep a Changelog; versions follow Semantic Versioning.

## [Unreleased]

### Added

- Add CodeQL v4 scanning for Python code on pushes, pull requests, and a weekly schedule.

### Changed

- Pin Hatchling and normalize the tagged commit timestamp for reproducible distributions.
- Build distributions twice in CI and reject byte-level differences before packaging.

## [0.1.1] - 2026-08-17

### Fixed

- Enforce custom-schema dtype, shape, bounds, alias, and option declarations at load time.
- Validate boolean and shaped numeric fields without accepting unrelated coercible values.
- Handle nested custom values safely during duplicate-record detection.
- Apply affine unit conversions with both scale and offset.
- Reject malformed CPDataKit HDF5 tables with consistent `DataReadError` failures.
- Reject shaped or non-numeric histogram fields with a concise domain error.

### Added

- PyPI Trusted Publishing workflow with tagged, inspected distributions and OIDC authentication.
- Five-minute synthetic-data quickstart and a scientifically scoped repository social-preview asset.
- Release metadata and semantic-version tag consistency checks.

### Changed

- The README now offers a one-command GitHub Release installation for non-contributors.
- Repository-relative README links are absolute so they work correctly on PyPI.
- Publishing documentation and workflow now target the complete v0.1.1 distribution.

## [0.1.0] - 2026-08-12

### Added

- Versioned `curve`, `point`, and `field2d` schemas.
- CSV, JSON records, and CPDataKit HDF5 I/O with provenance.
- Structured validation, explicit normalization, descriptive summaries, plotting, CLI, and API.
- Deterministic synthetic datasets, tests, documentation, and cross-platform CI.

