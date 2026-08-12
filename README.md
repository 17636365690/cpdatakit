# CPDataKit

[![CI](https://github.com/17636365690/cpdatakit/actions/workflows/ci.yml/badge.svg)](https://github.com/17636365690/cpdatakit/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/17636365690/cpdatakit)](https://github.com/17636365690/cpdatakit/releases/latest)

**Crystal Plasticity Data Quality Toolkit** is a solver-independent Python toolkit for
validating, normalizing, summarizing, and visualizing crystal-plasticity simulation
datasets.

> **Alpha software:** CPDataKit verifies conformance to an explicit data contract. It does
> not certify that a simulation, constitutive model, or physical interpretation is correct.
> Bundled datasets are deterministic, wholly synthetic examples for demonstration and tests.

## Why and for whom

CPDataKit helps researchers, simulation engineers, and data stewards make tabular materials
simulation data explicit and traceable before analysis or exchange. The core package is not a
finite-element solver, DAMASK post-processor, Abaqus plug-in, UMAT runner, or ODB reader. It has
no official affiliation with DAMASK, Abaqus, or Dassault Systèmes.

## Supported contracts and formats

The open CPDataKit schema v1.0 defines three profiles:

- `curve`: ordered macroscopic steps such as time, strain, stress, and load curves;
- `point`: material-point, integration-point, element, or sample records;
- `field2d`: scalar samples with two-dimensional Cartesian coordinates.

Inputs are UTF-8 CSV, JSON arrays of records, and CPDataKit HDF5 (`.h5`/`.hdf5`). CSV and JSON
take units and semantics from the selected schema. HDF5 embeds units, mapping, validation
summary, source filename and SHA-256, UTC conversion time, Python/CPDataKit versions, and an
operation log. CPDataKit HDF5 is not DAMASK DADF5 or Abaqus ODB.

Schemas declare standard names, aliases, requiredness, dtype, per-record shape, role, unit,
missing-value policy, index constraints, ranges, and scientific conventions. Custom fields
must be declared or use `user_`. CPDataKit never guesses stress/strain measures, tensor order,
orientation representation, units, or identifier semantics. See [the data format](docs/data-format.md).

## Install

```bash
git clone https://github.com/17636365690/cpdatakit.git
cd cpdatakit
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Activate on POSIX shells:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Regenerate the fixed-seed examples at any time:

```bash
python examples/generate_sample_data.py --output sample_data
```

## Command line

Validate and write a JSON report:

```bash
cpdatakit validate sample_data/synthetic_curve.csv --schema curve --json-output validation.json
```

Summarize, convert, and create both image formats:

```bash
cpdatakit summary sample_data/synthetic_curve.csv --schema curve --json-output summary.json
cpdatakit convert sample_data/synthetic_curve.csv --schema curve --output curve.h5 --source-description "Synthetic README example"
cpdatakit plot curve.h5 --schema curve --kind stress-strain --output stress-strain.png
cpdatakit plot curve.h5 --schema curve --kind stress-strain --output stress-strain.svg
```

Use `--force` to replace an output. Expected errors are concise and have no traceback; put the
global `--debug` option before the subcommand to debug unexpected failures. A validation or
summary command returns `0` for conforming data and `1` for findings; usage/read/output failures
return `2`. Run `cpdatakit --help` or `cpdatakit <command> --help` for details.

## Python API

```python
from cpdatakit import (
    FieldMapping,
    load_dataset,
    normalize_dataset,
    summarize_dataset,
    validate_dataset,
)

raw = load_dataset("raw.csv")
normalized = normalize_dataset(
    raw,
    "curve",
    [
        FieldMapping("increment", "step", "1", "dimensionless"),
        FieldMapping("eps", "strain", "1", "dimensionless"),
        FieldMapping("sigma_pa", "stress", "Pa", "MPa", "export specification"),
    ],
)
report = validate_dataset(normalized, "curve")
summary = summarize_dataset(normalized, "curve", validation=report)
print(report.valid, summary["record_count"])
```

Mapping conflicts, unknown fields, and incompatible units raise documented subclasses of
`CPDataKitError`. Normalization returns a copy and preserves unmapped columns unless
`drop_unmapped=True`.

## Example outputs

After running the commands above, `stress-strain.png` and `stress-strain.svg` contain a titled,
unit-labeled synthetic curve with a legend. Plotting functions in `cpdatakit.plotting` return
Matplotlib `(Figure, Axes)` for further editing and use the non-interactive `Agg` backend.

## Development

```bash
pytest --cov=cpdatakit
ruff check .
ruff format --check .
python -m build
```

Architecture, extension boundaries, and maintainer checks are in [docs](docs/architecture.md).
Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Known limitations and roadmap

Version 0.1.0 handles in-memory tabular data and an explicit two-dimensional scalar sample
representation. It does not perform solver integration, constitutive integration, 3D interactive
graphics, automatic scientific inference, streaming, or distributed processing. DAMASK and
Abaqus are only reserved adapter boundaries; no unverified adapter is shipped. See the
[roadmap](docs/roadmap.md) for the next three versions.

## Citation and license

Use [CITATION.cff](CITATION.cff) to cite the software. CPDataKit is licensed under Apache-2.0;
see [LICENSE](LICENSE). Direct runtime dependency licenses and review notes are in
[NOTICE](NOTICE). No real experimental or commercial-solver data are redistributed.
