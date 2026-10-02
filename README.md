# CPDataKit

[简体中文](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/README.zh-CN.md) | English

[![CI](https://github.com/koocmitwho/cpdatakit/actions/workflows/ci.yml/badge.svg)](https://github.com/koocmitwho/cpdatakit/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/koocmitwho/cpdatakit)](https://github.com/koocmitwho/cpdatakit/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/cpdatakit)](https://pypi.org/project/cpdatakit/)
[![License](https://img.shields.io/github/license/koocmitwho/cpdatakit)](https://github.com/koocmitwho/cpdatakit/blob/main/LICENSE)

**Make fields, units, and checks explicit before validating, converting, and handing off scientific or engineering data.**

CPDataKit is a Python toolkit with a local Chinese-language workbench, a command-line interface,
and a Python API. It is for experimental and engineering users who need to organize instrument
exports, reconcile conventions across sources, or check data before analysis.
It began with crystal-plasticity (CP) workflows and also handles data without CP fields,
such as thermal cycles.

For example, an instrument exports a semicolon-separated table with force in `N`, while a
downstream script expects `kN`. Preview the actual columns, confirm the field names, types,
source units, and output units, then save the converted data, original file, and schema.
Anyone checking or receiving the result can see which declarations governed the conversion.

This guide covers **v0.10.1**, which repairs numeric precision, input boundaries, upload limits,
workspace sessions, conversion provenance and bounded reads. Install from
[PyPI](https://pypi.org/project/cpdatakit/0.10.1/); see the
[release notes](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/.github/release-notes/v0.10.1.md) and
[GitHub Release](https://github.com/koocmitwho/cpdatakit/releases/tag/v0.10.1) for changes.

> CPDataKit checks declared data rules and conversions. It does not establish experimental validity
> or infer scientific definitions such as engineering versus true stress and strain.

## Features

- **Confirm what a CSV contains.** Set the delimiter, header row, separate unit row, decimal separator,
  and encoding. Preview the file, then confirm each field's name, type, units, and role.
  Retain the original bytes and a record of excluded columns.
- **Validate against explicit rules.** A schema declares fields, types, shapes, units, missing-value
  policies, indexes, ranges, and scientific conventions. Findings distinguish errors from warnings.
- **Normalize names and units explicitly.** A field mapping handles renaming and unit conversion.
  Vectors, matrices, and tensors follow their declared shapes. CSV confirmation accepts these
  declarations directly.
- **Keep results traceable.** CPDataKit HDF5 can retain the schema, unit provenance, source digest,
  validation results, and processing records. Reports support offline HTML, Markdown, and JSON.
- **Continue from saved results.** Local projects retain files, schemas, jobs, and results.
  Verified conversion snapshots can become subsequent inputs without downloading and uploading again.
- **Use scripts as well as the workbench.** CLI and Python API operations cover validation, summaries,
  conversion, inspection, plotting, reporting, and comparison. Additional workflows provide
  selective reads, multidimensional slices, and batch processing.

## Requirements and installation

- Python **3.12 or later**. Full CI for this release covers Python 3.12 and 3.13.
- Windows, macOS, or Linux. The workbench requires a browser; CLI/API use does not.
- Installation fetches the Python dependencies. Workbench assets are bundled in the package:
  **using the workbench requires neither Node.js nor a CDN**.

The Python 3.12 minimum was introduced in v0.6.0. The published v0.5.x line remains the
compatibility path for Python 3.10 and 3.11; see the
[v0.5.0 release](https://github.com/koocmitwho/cpdatakit/releases/tag/v0.5.0).
That older version does not include the v0.10.0 CSV confirmation and result-reuse workflow below.

Start in an empty directory and create an isolated environment.
If an environment, workspace, or output name below already exists, choose a new name.
You do not need to activate the environment or change PowerShell's script execution policy.

Windows PowerShell:

```powershell
python -m venv .venv-cpdatakit
.venv-cpdatakit\Scripts\python.exe -m pip install "cpdatakit==0.10.1"
.venv-cpdatakit\Scripts\cpdatakit.exe --version
.venv-cpdatakit\Scripts\cpdatakit.exe ui --workspace ./csv-demo-workspace
```

macOS / Linux:

```bash
python3 -m venv .venv-cpdatakit
.venv-cpdatakit/bin/python -m pip install "cpdatakit==0.10.1"
.venv-cpdatakit/bin/cpdatakit --version
.venv-cpdatakit/bin/cpdatakit ui --workspace ./csv-demo-workspace
```

The version output should be `cpdatakit 0.10.1`.
The workbench binds only to a loopback address and opens the browser by default.
If it does not open, visit the address printed in the terminal.
Keep the terminal running; press `Ctrl+C` when finished to stop the service.
Initial installation downloads dependencies. Once installed, the local CSV workflow below
requires no external service or AI model.

The workspace contains original files, schemas, job records, and results.
Keep the whole directory to resume work, and inspect its contents before sharing.
For a headless launch, append `--no-browser`; interactive use still requires a browser
that can reach the service.

## First use: convert a three-row CSV to HDF5

This synthetic example demonstrates file processing; it has no experimental or material-validation
meaning. Save the following text as a UTF-8 file named `instrument-demo.csv`,
or use the repository's [instrument.csv](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/csv-intake/instrument.csv).

```csv
(sec);(mm);(N);;(MPa);(mm/mm)
0;0;100;0;20;0
1;0.5;250;0;40;0.01
2;1.25;375;0;60;0.02
```

The workbench UI is in Chinese. Instructions below include its actual labels.

### 1. Preview the source

Create a new project and open “CSV import · preview and confirm fields”
(`CSV 导入 · 预览并确认字段`). Select the file.
Choose semicolon (`分号`), set header row to `1` and unit row to `0`,
choose “.” for the decimal separator, and select “UTF-8 / UTF-8 BOM”.
Click “Preview table” (`预览表格`): expect **3 records and 6 columns**.

Row numbers start at 1 and include blank lines in the original file.
`0` means there is no header or separate unit row.
Changing the file or parsing settings requires a new preview.

### 2. Confirm fields and units

Choose decimal (`小数`) for all five retained fields and deselect “Keep” (`保留`)
for column four. Fill in the declarations below:

| Source column | Output field | Source unit | Output unit | Role |
|---|---|---|---|---|
| 1 `(sec)` | `time` | `s` | `s` | Time (`时间`) |
| 2 `(mm)` | `extension` | `mm` | `mm` | Measured quantity (`测量值`) |
| 3 `(N)` | `force` | `N` | `kN` | Measured quantity (`测量值`) |
| 4 Unnamed | Deselect Keep | — | — | — |
| 5 `(MPa)` | `reported_stress` | `MPa` | `MPa` | Measured quantity (`测量值`) |
| 6 `(mm/mm)` | `reported_strain` | `mm/mm` | `dimensionless` | Measured quantity (`测量值`) |

Enter this source description: “Synthetic example; units are defined by the example header.
Column four is excluded but retained in the original file.
No engineering/true stress-strain definition is inferred.”
After checking the declarations, tick the confirmation box and click “Confirm and import”
(`确认并导入`). Numeric columns require explicit source and output units.
Investigate unknown units rather than declaring them dimensionless.
The original fourth column remains in the source file.

### 3. Check, save, and continue

1. The imported data and schema are selected automatically.
   Click “Generate report” (`生成报告`), select JSON or HTML and a new output path,
   and check for **3 records, zero errors, and zero warnings**.
2. Click “Convert and save” (`转换并保存`).
   Select HDF5 and a new project-relative path, such as `results/csv-demo.h5`.
3. When conversion completes, click “Use this result to continue”
   (`使用此结果继续处理`). The input switches to the saved conversion snapshot
   and its original schema. Generate another report with a new output path.
4. Under “View and download results” (`查看与下载结果`), open the report, download
   the HDF5 file, and check the original file, schema, and import manifest.

The resulting field order should be
`time, extension, force, reported_stress, reported_strain`;
`force` should contain **`0.1, 0.25, 0.375 kN`**.
CSV import has already applied the declared conversions: do not repeat them in the advanced mapping.
Selecting the same result again reuses the same input record.

For an existing output name, choose a new name or explicitly confirm replacement.
Previously registered conversion snapshots retain their original content.
Reuse is rejected if a snapshot has changed, its original schema is unavailable,
or the result belongs to another project.

See the [complete CSV example](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/csv-intake/README.md) and
[Chinese workbench guide](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/workbench-guide.md) for detailed steps, a runnable example script,
and troubleshooting. Ordinary wheels do not include the repository's `examples/` directory.
The manual workflow above needs only the installed package.

## Outputs

| Output | Purpose |
|---|---|
| `source.csv` | Download of the original bytes; the import manifest records the source filename and SHA-256 |
| `schema.json` | The confirmed CSV schema, reusable for later checks |
| `manifest.json` | Parsing settings, field declarations, excluded columns, record count, and source digest |
| Confirmed HDF5 and subsequent conversion files | Processable data with its declarations; names and directories depend on the operation |
| HTML / Markdown / JSON reports | Validation overview, fields and statistics, findings, and provenance; HTML opens and prints offline |
| Project and job records | Processing state, input selections, and result references for use after reopening the workspace |

Original files and processing results are retained separately.
“Valid” in a report means the data violates none of the declared rules in that check.
Warning-only results can remain valid; assess the particular warnings before downstream use.

## Command line and Python API

### A command-line example without a source checkout

Use the same isolated environment in the installation directory.
These commands generate a fixed-seed synthetic curve, then validate, summarize, convert,
inspect, report, and plot it.
This workflow uses the built-in `curve` schema for the generator's fields;
it cannot be applied directly to arbitrary instrument tables.

Windows PowerShell:

```powershell
.venv-cpdatakit\Scripts\python.exe -c "from cpdatakit.samples import generate_sample_data; generate_sample_data('cpdatakit-demo')"
.venv-cpdatakit\Scripts\cpdatakit.exe validate cpdatakit-demo/synthetic_curve.csv --schema curve --json-output validation.json
.venv-cpdatakit\Scripts\cpdatakit.exe summary cpdatakit-demo/synthetic_curve.csv --schema curve --json-output summary.json
.venv-cpdatakit\Scripts\cpdatakit.exe convert cpdatakit-demo/synthetic_curve.csv --schema curve --output curve.h5 --source-description "Fixed-seed README example"
.venv-cpdatakit\Scripts\cpdatakit.exe inspect curve.h5 --format json --output inspect.json
.venv-cpdatakit\Scripts\cpdatakit.exe report curve.h5 --schema curve --output report.html
.venv-cpdatakit\Scripts\cpdatakit.exe plot curve.h5 --schema curve --kind stress-strain --output stress-strain.png
```

On macOS / Linux, use the same arguments with `.venv-cpdatakit/bin/python`
and `.venv-cpdatakit/bin/cpdatakit`.
Because the CSV has no source-unit declarations, this built-in schema example produces
`unit_not_declared` warnings. Reports distinguish source declarations from schema assumptions;
this example must not be described as having “zero warnings”.

Existing outputs are kept by default.
To replace them intentionally, add `--force` to commands that support it.
Validation-related commands generally return `0` for no validation errors (warnings may remain),
`1` for validation errors or structural risks found during inspection,
and `2` for argument, schema, read, or output errors.
Consult `cpdatakit --help` and subcommand help for full options.

### Check data in Python

Run the generator above first, then execute this code in the same environment:

```python
from cpdatakit import load_dataset, validate_dataset, summarize_dataset

dataset = load_dataset("cpdatakit-demo/synthetic_curve.csv")
validation = validate_dataset(dataset, "curve")
summary = summarize_dataset(dataset, "curve", validation=validation)
print(validation.valid)
print(summary)
```

See the [schema and mapping guide](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/schema-authoring.md) for custom fields and units,
the [five-minute quickstart](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/quickstart.md) for more complete commands,
and [advanced workflows](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/post-v07-workflows.md) for selective reads,
multidimensional viewing, schema drafts, and batches.

## Input formats and scope

| Data path | Scope and requirements |
|---|---|
| Confirmed CSV import | Comma, semicolon, or Tab; UTF-8/BOM or GB18030; explicit fields, types, units, and roles; default limits of 64 MiB and 100,000 records |
| Regular CSV / JSON records | UTF-8 CSV or JSON arrays of objects with a built-in or external schema; absent source units produce schema-assumption warnings |
| CPDataKit HDF5 | Tabular HDF5 1.0 and multidimensional HDF5 2.0; schemas, units, provenance, and selective reads |
| Multidimensional and other formats | Numeric N-dimensional `ScientificDataset` data, NetCDF, Zarr 3, and tabular Parquet; operations depend on adapter capabilities, not unrestricted conversion between formats |
| DAMASK DADF5 | A documented read-only selection adapter; specify kind, label, field, and datasets; it does not promise to read every DAMASK output |

Built-in `curve`, `point`, and `field2d` schemas come from the original CP workflows.
External JSON schemas may use other non-empty profile names,
but types, shapes, units, and conventions must remain explicit.
See the [data-format documentation](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/data-format.md) for contracts and adapter boundaries.

Keep these limits in mind:

- The data provider confirms numeric units, stress/strain definitions, tensor component order,
  orientation representations, and identifier meanings. Unknown scientific semantics are not inferred.
- Confirmed CSV import stops on malformed rows, missing numeric units, or conversions whose precision
  cannot be guaranteed. It does not discard bad rows to obtain a passing result.
- Newly written HDF5 retains column creation order. Older files without order metadata cannot recover
  their original input order. Specify fields and order explicitly when building positional feature arrays.
- v0.10.1 fixes native NetCDF3 reading from Windows Unicode paths using a temporary ASCII snapshot.
  Date coordinates can be read, but general date-coordinate schema support remains unimplemented.
  See the [known issue](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/known-issues/netcdf3-datetime.md).
- CPDataKit does not run crystal-plasticity or finite-element solvers.
  Existing integration examples demonstrate data preparation and handoff, not automatic integration
  between independent projects.

## Examples and verification

Start with synthetic data, then build schemas from your own source records.

- [Three-row instrument CSV](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/csv-intake/README.md):
  column confirmation, unit conversion, original-byte retention, and conversion-result reuse.
- [Thermal cycle](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/thermal-cycle/README.md):
  a custom profile, Celsius/kelvin and time-unit conversions, HDF5 round trips, and general x-y plots.
- [KupferDigital/FE tensile case](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/cpfe-tensile/README.md):
  attributed CC BY 4.0 processed data demonstrating experimental-data handoff.
- [Surfalex HF public reference workflow](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/public-datasets/surfalex-aa6016a/README.md):
  explicit tensor mappings and source checks, with third-party raw data fetched from upstream on request.

Current repair validation is recorded in the
[v0.10.1 verification report](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/verification/2026-10-02-v0101.md).
For the historical v0.10.0 release commit `7ef4ece`,
[full CI](https://github.com/koocmitwho/cpdatakit/actions/runs/36811526428) passed:
all six Windows/Linux/macOS and Python 3.12/3.13 combinations had **1559 passing tests** each.
All 12 [lower/latest dependency-matrix checks](https://github.com/koocmitwho/cpdatakit/actions/runs/36811526427)
also passed. These results describe the release commit checked on 2026-10-01.

Release acceptance also checked a clean installation, the three-row CSV browser workflow,
and the source bytes, declared units, and numeric values of 12 CSV files with 24,073 rows
in the original IN718 archive from
[Mendeley DOI 10.17632/nx55jj48rx.2](https://doi.org/10.17632/nx55jj48rx.2).
That raw archive is not included in the repository; only its source fingerprint and a synthetic CSV
are included. Passing tests establish that the tested paths satisfy their declarations and assertions,
not that experimental data is physically correct.
Historical review snapshots and measurement conditions are in the
[verification directory](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/docs/verification/).
Prepublication snapshots are distinct from final publication receipts.

## Contributions and license

Report issues and suggest features through [Issues](https://github.com/koocmitwho/cpdatakit/issues).
Include a minimal synthetic sample, expected fields and units, and reproduction steps.
Do not submit private experimental data or credentials.
See [CONTRIBUTING.md](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/CONTRIBUTING.md) for code contributions,
[SECURITY.md](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/SECURITY.md) for security reports, and [CHANGELOG.md](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/CHANGELOG.md) for version history.

CPDataKit uses the [Apache-2.0 license](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/LICENSE).
See [NOTICE](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/NOTICE) for dependencies and third-party materials,
and [CITATION.cff](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/CITATION.cff) for citation details.
Third-party data follows its own license and attribution requirements.
