# Five-minute quickstart

This walkthrough uses only deterministic synthetic data. It validates a declared crystal-plasticity
curve, writes an auditable HDF5 file, and renders a stress-strain plot.

## 1. Install the current release

Until the PyPI trusted publisher is activated, install the signed-off wheel attached to the GitHub
release:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install "https://github.com/17636365690/cpdatakit/releases/download/v0.1.0/cpdatakit-0.1.0-py3-none-any.whl"
```

On POSIX shells:

```bash
source .venv/bin/activate
python -m pip install "https://github.com/17636365690/cpdatakit/releases/download/v0.1.0/cpdatakit-0.1.0-py3-none-any.whl"
```

## 2. Generate a reproducible example

```bash
python -c "from cpdatakit.samples import generate_sample_data; generate_sample_data('cpdatakit-demo')"
```

The generator uses a fixed seed and creates no experimental or commercial-solver data.

## 3. Validate and summarize

```bash
cpdatakit validate cpdatakit-demo/synthetic_curve.csv --schema curve --json-output validation.json
cpdatakit summary cpdatakit-demo/synthetic_curve.csv --schema curve --json-output summary.json
```

The validation report records schema findings. The summary contains field-level descriptive
statistics and a copy of the validation result.

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

You should now have `validation.json`, `summary.json`, `curve.h5`, and `stress-strain.png`.
CPDataKit checks explicit data contracts; it does not certify physical correctness.

## Try invalid data

The generator also creates a deliberately malformed point dataset. A validation exit status of
`1` means findings were reported successfully:

```bash
cpdatakit validate cpdatakit-demo/intentionally_invalid_point.csv --schema point
```

If this workflow is useful, please star the repository so other materials researchers can find it,
and open an issue with the data contract or solver-neutral workflow you would like supported.
