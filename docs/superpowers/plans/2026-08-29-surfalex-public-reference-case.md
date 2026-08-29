# Surfalex Public Reference Case Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add an offline-testable, hash-verified Surfalex Workflow 7A reference case that converts a real MatFlow/DAMASK workflow HDF5 artifact into a provenance-rich CPDataKit HDF5 dataset.

**Architecture:** Keep the core package solver-independent. Put a narrow, case-specific MatFlow/Hickle extractor, explicit local schema, explicit mapping, fetch script, and workflow runner under examples/public-datasets/surfalex-aa6016a. Test the extractor against a tiny synthetic file with the same nested path names; never commit the third-party raw files.

**Tech Stack:** Python 3.10+, stdlib urllib/hashlib/h5py, pandas, NumPy, CPDataKit Python API, pytest, JSON, Markdown.

**Spec:** docs/superpowers/specs/2026-08-29-surfalex-public-reference-case-design.md

## Global Constraints

- The source record is Zenodo DOI 10.5281/zenodo.7307639 and the source data license is CC BY 4.0.
- The associated publication is DOI 10.12688/materialsopenres.17516.1.
- The selected files are 7A_simulate_uniaxial_tension.yml and 7A_workflow.hdf5.
- Fetch verifies the published MD5 and the recorded SHA-256 for both files.
- Keep source data upstream and keep solver binaries, MatFlow, and DAMASK runtimes outside core dependencies.
- All field names, units, Cauchy/Hencky measures, and row-major tensor ordering are explicit.
- The case produces 1,501 records with stress, strain, F, and Fp per-record shape (3, 3).
- Tests run offline using only synthetic MatFlow/Hickle-shaped HDF5 fixtures.

### Task 1: Specify the case boundary with offline failing tests

Files:
- Create: tests/test_surfalex_public_reference_case.py

Interfaces:
- Imports examples/public-datasets/surfalex-aa6016a/workflow.py through importlib.
- Calls extract_dataset(input_path) -> Dataset.
- Calls run(input_path, output_path, *, report_path=None, force=False) -> Path.
- Imports fetch_data.py constants and hash verifier without downloading.

- [ ] Step 1: Add a test module loader and a synthetic nested MatFlow fixture

Create a test-only loader:

    CASE_ROOT = Path(__file__).parents[1] / "examples" / "public-datasets" / "surfalex-aa6016a"


    def _load_case_module(name: str):
        spec = importlib.util.spec_from_file_location(name, CASE_ROOT / f"{name}.py")
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot load case module {name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

Create a fixture writer that uses these exact groups:

    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_stress'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_strain'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_def_grad'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_def_grad_plastic'

For each output name, write the numeric array under data/'data'/data and write increments under
data/'meta'/data/'increments'/data. Use two records with hand-derived values:

    stress = [[[1_000_000.0, 0.0, 0.0], [0.0, 2_000_000.0, 0.0], [0.0, 0.0, 3_000_000.0]],
              [[4_000_000.0, 0.0, 0.0], [0.0, 5_000_000.0, 0.0], [0.0, 0.0, 6_000_000.0]]]
    strain = [[[0.01, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 0.03]],
              [[0.04, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 0.06]]]
    deformation = [[[1.01, 0.0, 0.0], [0.0, 1.02, 0.0], [0.0, 0.0, 1.03]],
                   [[1.04, 0.0, 0.0], [0.0, 1.05, 0.0], [0.0, 0.0, 1.06]]]
    increments = [0, 1]

The fixture must be created in tmp_path and must not be committed.

- [ ] Step 2: Add extraction, mapping, and output assertions

Add:

    def test_extract_dataset_reads_explicit_volume_tensors(tmp_path: Path) -> None:
        workflow = _load_case_module("workflow")
        raw = tmp_path / "7A_workflow.hdf5"
        _write_fixture(raw)

        dataset = workflow.extract_dataset(raw)

        assert list(dataset.data.columns) == [
            "increment",
            "vol_avg_stress",
            "vol_avg_strain",
            "vol_avg_def_grad",
            "vol_avg_def_grad_plastic",
        ]
        assert dataset.data["vol_avg_stress"].iloc[0].shape == (3, 3)
        assert dataset.data["vol_avg_stress"].iloc[0][0, 0] == 1_000_000.0
        assert dataset.metadata["units"]["vol_avg_stress"] == "Pa"
        assert dataset.source == raw


    def test_run_writes_normalized_hdf5_and_offline_report(tmp_path: Path) -> None:
        workflow = _load_case_module("workflow")
        raw = tmp_path / "7A_workflow.hdf5"
        output = tmp_path / "surfalex-7a.h5"
        report = tmp_path / "surfalex-7a-report.json"
        _write_fixture(raw)

        result = workflow.run(raw, output, report_path=report)

        assert result == output
        loaded = cpdatakit.load_hdf5(output)
        assert list(loaded.data.columns) == ["step", "stress", "strain", "F", "Fp"]
        assert loaded.data["stress"].iloc[0][0, 0] == pytest.approx(1.0)
        assert loaded.data["stress"].iloc[1][2, 2] == pytest.approx(6.0)
        assert loaded.metadata["units"]["stress"] == "MPa"
        assert loaded.metadata["schema_snapshot"]["schema"]["profile"] == "curve"
        assert loaded.metadata["provenance"]["input_filename"] == raw.name
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["validation"]["valid"] is True
        assert str(raw) not in report.read_text(encoding="utf-8")

- [ ] Step 3: Add structural failure and fetch-manifest tests

Add tests for missing output paths and inconsistent record axes:

    def test_extract_dataset_rejects_missing_volume_output(tmp_path: Path) -> None:
        workflow = _load_case_module("workflow")
        raw = tmp_path / "missing.hdf5"
        _write_fixture(raw, omit="vol_avg_strain")

        with pytest.raises(DataReadError, match="vol_avg_strain"):
            workflow.extract_dataset(raw)


    def test_extract_dataset_rejects_inconsistent_record_counts(tmp_path: Path) -> None:
        workflow = _load_case_module("workflow")
        raw = tmp_path / "mismatched.hdf5"
        _write_fixture(raw, mismatch="vol_avg_strain")

        with pytest.raises(DataReadError, match="inconsistent record counts"):
            workflow.extract_dataset(raw)


    def test_fetch_manifest_contains_published_hashes() -> None:
        fetch = _load_case_module("fetch_data")

        assert {item["name"] for item in fetch.SOURCE_FILES} == {
            "7A_simulate_uniaxial_tension.yml",
            "7A_workflow.hdf5",
        }
        assert all(len(item["md5"]) == 32 for item in fetch.SOURCE_FILES)
        assert all(len(item["sha256"]) == 64 for item in fetch.SOURCE_FILES)

- [ ] Step 4: Run the new tests and verify the expected red state

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest tests/test_surfalex_public_reference_case.py -q

Expected: tests fail because the case workflow.py and fetch_data.py do not exist yet. No network access should occur.

- [ ] Step 5: Commit only the failing case tests

    git add tests/test_surfalex_public_reference_case.py
    git commit -m "test: specify Surfalex public reference case"

### Task 2: Add the explicit case schema, mapping, and manifest

Files:
- Create: examples/public-datasets/README.md
- Create: examples/public-datasets/surfalex-aa6016a/schema/cp-finite-strain.json
- Create: examples/public-datasets/surfalex-aa6016a/mappings/workflow-7a.json
- Create: examples/public-datasets/surfalex-aa6016a/expected/manifest.json

Interfaces:
- The schema is loaded by workflow.py through cpdatakit.load_schema().
- The mapping is loaded by workflow.py through cpdatakit.load_mapping_file().
- The manifest is documentation/acceptance metadata and contains no raw records.

- [ ] Step 1: Add the finite-strain schema

Create cp-finite-strain.json with profile curve, schema_version 1.0, extension_prefix user_, and
these fields:

    step: integer, required, non-negative, index=true, unique=true, unit=dimensionless
    stress: float, required, shape=[3,3], components=[xx,xy,xz,yx,yy,yz,zx,zy,zz], unit=MPa
    strain: float, required, shape=[3,3], same components, unit=dimensionless
    F: float, required, shape=[3,3], same components, unit=dimensionless
    Fp: float, required, shape=[3,3], same components, unit=dimensionless

Set conventions to Cauchy stress, Hencky strain, row-major tensor component order, explicit
finite-strain kinematics, and orientation not used in this case.

- [ ] Step 2: Add the explicit mapping

Create workflow-7a.json with drop_unmapped=true and these mappings:

    increment -> step, no unit conversion
    vol_avg_stress -> stress, input_unit=Pa, output_unit=MPa
    vol_avg_strain -> strain, input_unit=1, output_unit=dimensionless
    vol_avg_def_grad -> F, input_unit=1, output_unit=dimensionless
    vol_avg_def_grad_plastic -> Fp, input_unit=1, output_unit=dimensionless

Every mapping receives a source_note naming the Zenodo Workflow 7A output and the explicit
convention it represents. No alias or field-name inference is permitted.

- [ ] Step 3: Add a manifest without generated artifacts

Create expected/manifest.json containing:

    case: surfalex-aa6016a-workflow-7a
    source DOI: 10.5281/zenodo.7307639
    publication DOI: 10.12688/materialsopenres.17516.1
    data_license: CC BY 4.0
    record_count: 1501
    raw files: names, byte sizes, MD5, SHA-256
    output fields: step, stress, strain, F, Fp
    output tensor shape: [1501, 3, 3]
    output stress unit: MPa
    validation: valid=true, error_count=0
    schema_sha256: the digest calculated from cp-finite-strain.json

The manifest must not include tensor values, local paths, timestamps, or credentials.

- [ ] Step 4: Commit the case contract files

    git add examples/public-datasets/README.md examples/public-datasets/surfalex-aa6016a/schema/cp-finite-strain.json examples/public-datasets/surfalex-aa6016a/mappings/workflow-7a.json examples/public-datasets/surfalex-aa6016a/expected/manifest.json
    git commit -m "docs: add Surfalex reference case contract"

### Task 3: Implement the offline case extractor and workflow runner

Files:
- Create: examples/public-datasets/surfalex-aa6016a/workflow.py
- Test: tests/test_surfalex_public_reference_case.py

Interfaces:
- Implements extract_dataset(path: str | Path) -> Dataset.
- Implements run(input_path: str | Path, output_path: str | Path, *, report_path: str | Path | None = None, force: bool = False) -> Path.
- Provides a main(argv: list[str] | None = None) -> int CLI entry point.

- [ ] Step 1: Implement quote-tolerant explicit HDF5 path helpers

Use h5py and implement:

    def _child(group: h5py.Group, name: str) -> h5py.Group | h5py.Dataset:
        candidates = (name, f"'{name}'") if not name.startswith("'") else (name, name[1:-1])
        for candidate in candidates:
            if candidate in group:
                return group[candidate]
        raise DataReadError(f"MatFlow output path is missing {name!r}")


    def _descend(group: h5py.Group, names: tuple[str, ...]):
        current = group
        for name in names:
            current = _child(current, name)
        return current

Read the four named volume outputs only. Do not walk arbitrary HDF5 nodes or select fields by
similarity. Convert h5py datasets to NumPy arrays only after resolving the explicit paths.

- [ ] Step 2: Implement extract_dataset() validation

Open the input with h5py.File(path, "r"). Read increments from the stress output metadata and
each value array from its data/data node. Require:

    increments.ndim == 1
    len(increments) > 0
    each array.shape == (len(increments), 3, 3)
    all selected arrays have numeric dtype

Raise DataReadError with the output name for missing, scalar, non-numeric, empty, or inconsistent
data. Return a Dataset whose columns are increment, vol_avg_stress, vol_avg_strain,
vol_avg_def_grad, and vol_avg_def_grad_plastic; use list(array) for shaped DataFrame cells,
metadata units increment=1, stress=Pa, and all strain/gradient fields=1, and source=Path(path).

- [ ] Step 3: Implement run() through the CPDataKit APIs

Load the case schema and mapping paths relative to __file__, then:

    raw = extract_dataset(input_path)
    mappings, drop_unmapped = load_mapping_file(MAPPING_PATH)
    normalized = normalize_dataset(raw, schema, mappings, drop_unmapped=drop_unmapped)
    validation = validate_dataset(normalized, schema)
    if not validation.valid:
        raise DataValidationError("Surfalex reference-case normalization failed validation")
    write_hdf5(
        normalized,
        output_path,
        schema,
        validation,
        schema_uri=SCHEMA_URI,
        source_description="Surfalex HF Workflow 7A; Zenodo 10.5281/zenodo.7307639",
        operation_log=[
            "source:zenodo:10.5281/zenodo.7307639",
            "extract:matflow:volume_data",
            "normalize:workflow-7a.json",
            "validate",
            "write:cpdatakit-hdf5",
        ],
        force=force,
    )

If report_path is provided, call build_report(output_path, schema) and write_report(..., format="json", force=force). Return Path(output_path). Let existing CPDataKit output-protection and DataReadError/DataValidationError semantics propagate.

- [ ] Step 4: Add the CLI wrapper and run offline tests

Add argparse options --input, --output, --report, and --force. Run:

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest tests/test_surfalex_public_reference_case.py -q

Expected: extraction, shape, explicit Pa-to-MPa conversion, schema snapshot, report, and malformed-fixture tests pass.

- [ ] Step 5: Commit the extractor and workflow runner

    git add examples/public-datasets/surfalex-aa6016a/workflow.py tests/test_surfalex_public_reference_case.py
    git commit -m "feat: add Surfalex reference workflow"

### Task 4: Implement hash-verified source fetching

Files:
- Create: examples/public-datasets/surfalex-aa6016a/fetch_data.py
- Test: tests/test_surfalex_public_reference_case.py

Interfaces:
- Exposes SOURCE_FILES with name, URL, MD5, and SHA-256 for the two selected files.
- Exposes verify_file(path, spec) -> None for offline hash tests.
- Provides main(argv: list[str] | None = None) -> int.

- [ ] Step 1: Add the source manifest constants

Use stable Zenodo file URLs:

    https://zenodo.org/records/7307639/files/7A_simulate_uniaxial_tension.yml?download=1
    https://zenodo.org/records/7307639/files/7A_workflow.hdf5?download=1

Set the published MD5 values 3500212694d54f8a974af4c8a9af9b84 and
58abe7493d55d8f5e0033ba740e76f8e. Set the recorded SHA-256 values from the case specification.

- [ ] Step 2: Implement verify_file() and atomic downloads

verify_file() computes MD5 and SHA-256 in 1 MiB blocks and raises ValueError naming the file and
which digest mismatched. The downloader creates a same-directory temporary file, streams urllib
response bytes, verifies the temporary file, then uses os.replace() only after both hashes match.
Existing matching files are reused; existing mismatched files require --force. No URL is followed
for schema_uri or any other metadata.

- [ ] Step 3: Add the fetch CLI and offline verifier test

The CLI accepts --output with default data and --force. Add a test that writes a tiny file and
asserts verify_file() raises ValueError for a wrong digest, without opening a network connection.

- [ ] Step 4: Commit the fetch script

    git add examples/public-datasets/surfalex-aa6016a/fetch_data.py tests/test_surfalex_public_reference_case.py
    git commit -m "feat: add hash-verified Surfalex fetcher"

### Task 5: Write the before/after case documentation

Files:
- Modify: examples/public-datasets/README.md
- Create: examples/public-datasets/surfalex-aa6016a/README.md
- Modify: README.md
- Modify: README.zh-CN.md
- Modify: docs/roadmap.md

Interfaces:
- Documentation must describe runnable commands and the actual output contract.
- Documentation must not imply that CPDataKit reads MatFlow generically or certifies physical correctness.

- [ ] Step 1: Document the public source and license

In the case README, include the source DOI, publication DOI, authors/citation, CC BY 4.0 license,
upstream MIT analysis repository, file sizes/hashes, and the statement that raw files are fetched
on demand and are not committed to CPDataKit.

- [ ] Step 2: Add the before/after comparison

Document the raw MatFlow/Hickle nesting and solver-specific names:

    volume_data -> vol_avg_stress / vol_avg_strain / vol_avg_def_grad / vol_avg_def_grad_plastic
    arrays: (1501, 3, 3)

Contrast it with the CPDataKit output:

    /data/step, stress, strain, F, Fp
    MPa/dimensionless units
    schema_json, schema_sha256, field mapping, source basename/SHA-256, validation summary

State that Cauchy stress, Hencky strain, Pa input units, and row-major component order are
explicit case declarations; they are not inferred from names.

- [ ] Step 3: Add copyable commands and limitations

Include:

    python examples/public-datasets/surfalex-aa6016a/fetch_data.py --output data
    python examples/public-datasets/surfalex-aa6016a/workflow.py --input data/7A_workflow.hdf5 --output artifacts/surfalex-7a.h5 --report artifacts/surfalex-7a-report.json

Explain that the report is offline, raw records are not embedded in the report, shaped-field
statistics may be unavailable, and physical/model correctness remains outside CPDataKit scope.

- [ ] Step 4: Link the case from repository navigation docs

Add the case to examples/public-datasets/README.md and a concise link/bullet to both root READMEs
and docs/roadmap.md. Do not change the released version metadata.

- [ ] Step 5: Commit documentation

    git add examples/public-datasets/README.md examples/public-datasets/surfalex-aa6016a/README.md README.md README.zh-CN.md docs/roadmap.md
    git commit -m "docs: document Surfalex public reference case"

### Task 6: Run full verification and audit redistribution boundaries

Files:
- Modify only files required by failing verification evidence; otherwise do not edit additional files.

- [ ] Step 1: Run case-focused and full tests

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest tests/test_surfalex_public_reference_case.py -q
    python -m pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85

Expected: case tests and the full existing suite pass, with coverage at least 85%.

- [ ] Step 2: Run lint, format, and build

    .\.venv\Scripts\ruff.exe check .
    .\.venv\Scripts\ruff.exe format --check .
    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m build

Expected: no Ruff errors, all files formatted, and the existing cpdatakit-0.2.0 distributions build.

- [ ] Step 3: Run the case using the local synthetic fixture path only

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -c "import json; from pathlib import Path; import tempfile; import importlib.util; p=Path('examples/public-datasets/surfalex-aa6016a/workflow.py'); s=importlib.util.spec_from_file_location('surfalex_case', p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.SCHEMA_PATH.name, m.MAPPING_PATH.name)"

Expected: the example imports without network access and resolves its local contract files.

- [ ] Step 4: Audit no raw-data redistribution and final state

    git diff --check
    git status --short
    git log --oneline -14
    rg --files examples/public-datasets/surfalex-aa6016a
    rg -n "7A_workflow|Dataset.zip|\\.hdf5|\\.zip|raw|CC BY|schema_json|schema_sha256|matflow|DADF5" examples/public-datasets README.md README.zh-CN.md docs

Confirm downloaded raw HDF5/ZIP files stay upstream, runtime dependencies remain unchanged, the case follows its documented MatFlow/DAMASK paths, and the HDF5 schema snapshot/hash is present in the generated output.

- [ ] Step 5: Report only fresh evidence

Report case test counts, full test/coverage counts, lint/format/build results, tracked example files, exact source hashes, and follow-up limitations. Keep PR merge, branch retargeting, issue closure, GitHub comments, releases, and pushes as separate maintainer actions.
