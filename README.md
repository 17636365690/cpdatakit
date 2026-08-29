# CPDataKit

[![CI](https://github.com/17636365690/cpdatakit/actions/workflows/ci.yml/badge.svg)](https://github.com/17636365690/cpdatakit/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/17636365690/cpdatakit)](https://github.com/17636365690/cpdatakit/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/cpdatakit)](https://pypi.org/project/cpdatakit/)
[![License](https://img.shields.io/github/license/17636365690/cpdatakit)](https://github.com/17636365690/cpdatakit/blob/main/LICENSE)

CPDataKit is a solver-independent Python toolkit for checking, normalizing, summarizing, and
plotting crystal-plasticity simulation data.

> **Alpha software:** A passing validation report means that the records match the selected
> schema. It does not say that a simulation, constitutive model, or physical interpretation is
> correct. The bundled data are generated from a fixed seed and contain no experimental or
> commercial-solver output.

## When it helps

A hand-off can be as small as a column name. One exporter writes `eps`, another writes `strain`.
One stores `sigma_pa` in Pa, another expects `stress` in MPa. CPDataKit puts those choices in a
schema and an explicit mapping file, then keeps the validation result with the converted data.

Use it before an analysis script, when exchanging files with a colleague, or when you need to
explain later why a column was renamed. The package stays at the data boundary. It does not run
a solver, post-process DAMASK, act as an Abaqus plug-in, run a UMAT, or read ODB files. CPDataKit
has no official affiliation with DAMASK, Abaqus, or Dassault Systèmes.

## Supported contracts and formats

The built-in CPDataKit schema v1.0 has three profiles:

- `curve`: ordered macroscopic steps such as time, strain, stress, and load curves.
- `point`: material-point, integration-point, element, or sample records.
- `field2d`: scalar samples with two-dimensional Cartesian coordinates.

Inputs are UTF-8 CSV, JSON arrays of records, and CPDataKit HDF5 (`.h5`/`.hdf5`). CSV and JSON
take units and semantics from the selected schema. HDF5 stores the units, mapping, validation
summary, source filename and SHA-256, UTC conversion time, Python and CPDataKit versions, and an
operation log. The read-only DAMASK DADF5 adapter can also be inspected or reported when its
explicit selection is unambiguous; CPDataKit HDF5 is not DAMASK DADF5 or Abaqus ODB.

Schemas declare standard names, aliases, requiredness, dtype, per-record shape, role, unit,
missing-value policy, index constraints, ranges, and scientific conventions. Custom fields
must be declared or use `user_`. CPDataKit never guesses stress/strain measures, tensor order,
orientation representation, units, or identifier semantics. See
[the data format](https://github.com/17636365690/cpdatakit/blob/main/docs/data-format.md).

## Install

Install version `0.2.0` from PyPI:

```bash
python -m pip install cpdatakit
```

For a pinned GitHub release wheel, use:

```bash
python -m pip install "https://github.com/17636365690/cpdatakit/releases/download/v0.2.0/cpdatakit-0.2.0-py3-none-any.whl"
```

Then follow the
[five-minute quickstart](https://github.com/17636365690/cpdatakit/blob/main/docs/quickstart.md)
to validate, summarize, convert, and plot a deterministic example.

Installing from the source checkout is intended for contributors:

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

## Workflows covered by the repository

The examples and tests cover these paths:

- validate exported curve, point, or two-dimensional field records against an explicit contract.
- normalize exporter-specific column names and units with a reviewable JSON mapping file.
- preserve validated vectors and tensors in JSON/HDF5 with declared shapes and component order.
- convert records into auditable HDF5 with units, mapping, provenance, and validation metadata.
- inspect file structure and write portable validation reports without exposing raw records.
- run deterministic synthetic fixtures in notebooks, CI, and documentation examples.

## Useful links

- [PyPI package](https://pypi.org/project/cpdatakit/)
- [v0.2.0 GitHub Release](https://github.com/17636365690/cpdatakit/releases/tag/v0.2.0)
- [Quickstart](https://github.com/17636365690/cpdatakit/blob/main/docs/quickstart.md)
- [Schema authoring and mapping guide](https://github.com/17636365690/cpdatakit/blob/main/docs/schema-authoring.md)
- [Examples](https://github.com/17636365690/cpdatakit/tree/main/examples)
- [Roadmap and Issue tracker](https://github.com/17636365690/cpdatakit/issues)

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

For an exporter with different names or units, provide an explicit mapping file:

```bash
cpdatakit convert raw.csv --schema curve --mapping mapping.json --output curve.h5
```

See the [schema authoring and mapping guide](https://github.com/17636365690/cpdatakit/blob/main/docs/schema-authoring.md)
for the JSON format and no-inference rules.

Inspect a file and create a shareable offline report:

```bash
cpdatakit inspect curve.h5 --format json --output inspect.json
cpdatakit report curve.h5 --schema curve --output report.html
cpdatakit report curve.h5 --schema curve --format markdown --output report.md
```

`inspect` accepts an optional schema and reports the detected format, fields, dtype, shape, units,
missing values, HDF5 chunks, provenance, adapter, and structural risks. `report` requires a schema
and writes HTML by default; `--format markdown` and `--format json` are also available. The HTML
report is self-contained and can be opened or printed offline. Reports contain aggregate statistics
and validation findings, not raw records. Existing output files are protected unless `--force` is
passed.

Use `--force` to replace an output. Expected errors are concise and have no traceback. Put the
global `--debug` option before the subcommand when an unexpected failure needs more detail. A
validation, summary, inspect, or report command returns `0` when no validation errors are found and
`1` when data findings are present. Usage, read, schema, and output failures return `2`. A passing
validation report does not prove physical or scientific correctness. Run `cpdatakit --help` or
`cpdatakit <command> --help` for details.

## Python API

```python
from cpdatakit import (
    FieldMapping,
    build_report,
    inspect_dataset,
    load_hdf5,
    load_dataset,
    normalize_dataset,
    summarize_dataset,
    validate_dataset,
)
from cpdatakit.adapters import DamaskDADF5Adapter

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
inspection = inspect_dataset("curve.h5", schema="curve")
offline_report = build_report("curve.h5", "curve")
print(inspection["record_count"], offline_report["validation"]["valid"])

dadf5 = DamaskDADF5Adapter(
    kind="homogenization", label="Taylor", field="mechanical", datasets=["F", "P"]
).load("result.hdf5")
window = load_hdf5("curve.h5", fields=["step", "stress"], start=10, stop=20)
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

Architecture, extension boundaries, and maintainer checks are in the
[architecture documentation](https://github.com/17636365690/cpdatakit/blob/main/docs/architecture.md).
Contributions follow
[CONTRIBUTING.md](https://github.com/17636365690/cpdatakit/blob/main/CONTRIBUTING.md) and the
[Code of Conduct](https://github.com/17636365690/cpdatakit/blob/main/CODE_OF_CONDUCT.md).

When you need a new data contract or input format, open an issue with a small synthetic sample and
the field rules it should follow. That gives the next change something concrete to test.

## Known limitations and roadmap

Version 0.2.0 accepts in-memory tables, explicit vectors and tensors, and scalar `field2d` data.
It does not run solvers or constitutive integration, and it has no 3D interactive graphics,
automatic scientific inference, or distributed processing. Native HDF5 inspection uses bounded
reads, while report analysis uses the existing validation/statistics APIs. The bundled DAMASK DADF5
reader is a narrow, read-only selection adapter; it does not provide full solver integration or
global cell remapping. Further DAMASK/Abaqus work requires format evidence, license review, and
reproducible test data. See the
[roadmap](https://github.com/17636365690/cpdatakit/blob/main/docs/roadmap.md) for the next three
versions.

## Citation and license

Use [CITATION.cff](https://github.com/17636365690/cpdatakit/blob/main/CITATION.cff) to cite the
software. CPDataKit is licensed under Apache-2.0. See
[LICENSE](https://github.com/17636365690/cpdatakit/blob/main/LICENSE). Direct runtime dependency
licenses and review notes are in
[NOTICE](https://github.com/17636365690/cpdatakit/blob/main/NOTICE). No real experimental or
commercial-solver data are redistributed.
