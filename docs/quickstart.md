# Five-minute quickstart

This run uses deterministic synthetic data. It validates a declared crystal-plasticity curve,
writes an HDF5 file with provenance, and renders a stress-strain plot.

## 1. Install the current release

Start in a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On POSIX shells:

```bash
source .venv/bin/activate
```

Install the current release from PyPI:

```bash
python -m pip install cpdatakit
```

For a pinned GitHub release wheel, use:

```bash
python -m pip install "https://github.com/17636365690/cpdatakit/releases/download/v0.2.0/cpdatakit-0.2.0-py3-none-any.whl"
```

## 2. Generate a reproducible example

```bash
python -c "from cpdatakit.samples import generate_sample_data; generate_sample_data('cpdatakit-demo')"
```

The generator uses a fixed seed. It creates no experimental or commercial-solver data.

## 3. Validate and summarize

```bash
cpdatakit validate cpdatakit-demo/synthetic_curve.csv --schema curve --json-output validation.json
cpdatakit summary cpdatakit-demo/synthetic_curve.csv --schema curve --json-output summary.json
```

The validation report records schema findings. The summary contains field-level descriptive
statistics and the validation result used to produce it.

## 4. Convert with provenance

```bash
cpdatakit convert cpdatakit-demo/synthetic_curve.csv --schema curve --output curve.h5 --source-description "Fixed-seed quickstart example"
```

The CPDataKit HDF5 file embeds the schema/profile, units, source filename and SHA-256, conversion
time, software versions, validation summary, and operation log.

## 5. Plot the declared curve

```bash
cpdatakit plot curve.h5 --schema curve --kind stress-strain --output stress-strain.png
```

At this point, the directory contains `validation.json`, `summary.json`, `curve.h5`, and
`stress-strain.png`. CPDataKit checks the data contract. Physical correctness remains outside
the package's scope.

## Try invalid data

The generator also creates a deliberately malformed point dataset. A validation exit status of
`1` means findings were reported successfully:

```bash
cpdatakit validate cpdatakit-demo/intentionally_invalid_point.csv --schema point
```

To try another case, edit one of the generated CSV files and run `validate` again. For a new data
contract or input format, open an issue with a small synthetic sample and its field rules.
