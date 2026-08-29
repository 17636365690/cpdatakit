# Public Reference Case #1: Surfalex HF (AA6016A) Workflow 7A

This case shows how CPDataKit can turn a real, published crystal-plasticity workflow artifact
into a validated, reusable dataset. The source files are downloaded only when the user runs the
fetch command; neither raw file is committed to this repository.

## Source and citation

- Data record: [Surfalex HF formability study - Workflow 7 - Lankford coefficient](https://doi.org/10.5281/zenodo.7307639)
- Publication: [A novel integrated framework for reproducible formability predictions using virtual materials testing](https://doi.org/10.12688/materialsopenres.17516.1)
- Authors: Adam J. Plowman, Patryk Jedrasiak, Thomas Jailin, Peter Crowther, Sumeet Mishra,
  Pratheek Shanthraj, and Joao Quinta da Fonseca.
- Data license: CC BY 4.0, as declared by the Zenodo record and Workflow 7A specification.
- Upstream analysis code: [LightForm-group/surfalex_data_explorer](https://github.com/LightForm-group/surfalex_data_explorer),
  MIT licensed.

The exact source files used by this case are:

| File | Bytes | Published MD5 | Expected SHA-256 |
| --- | ---: | --- | --- |
| 7A_simulate_uniaxial_tension.yml | 2,864 | 3500212694d54f8a974af4c8a9af9b84 | d548c12dfd7fabf01b3dce4233c00faf5c4bb13e04d5a5bb8e1d7ea77a393abb |
| 7A_workflow.hdf5 | 7,623,248 | 58abe7493d55d8f5e0033ba740e76f8e | a4c1c51609e9dadcd3ea680ab6b3511877affac5f24fe25b84daa6daf8fb0693 |

The same values are machine-readable in expected/manifest.json.

## What the source contains

Workflow 7A is a uniaxial-tension CP-FFT workflow using DAMASK in the published MatFlow
workflow. The HDF5 file is MatFlow/Hickle workflow storage, not DAMASK DADF5. The relevant
volume outputs are nested below:

    element_data/
    └── 0022_volume_element_response/
        └── data/'volume_data'/data/
            ├── 'vol_avg_stress'
            ├── 'vol_avg_strain'
            ├── 'vol_avg_def_grad'
            └── 'vol_avg_def_grad_plastic'

Each selected output has 1,501 records with a 3 x 3 tensor per record. The Workflow 7A YAML
documents the stress output as volume-averaged Cauchy stress and the strain output as
volume-averaged Hencky strain.

## Before / after

The raw artifact has solver/workflow-specific names, nested Hickle containers, and metadata
distributed through separate nodes:

    Raw MatFlow/Hickle HDF5
    ├── workflow metadata
    ├── nested data/data containers
    ├── vol_avg_stress
    ├── vol_avg_strain
    ├── vol_avg_def_grad
    └── vol_avg_def_grad_plastic

The workflow produces a CPDataKit HDF5 artifact:

    Validated CPDataKit HDF5
    ├── /data/step
    ├── /data/stress          [1501, 3, 3], MPa
    ├── /data/strain          [1501, 3, 3], dimensionless
    ├── /data/F               [1501, 3, 3], dimensionless
    ├── /data/Fp              [1501, 3, 3], dimensionless
    ├── schema_json
    ├── schema_sha256
    ├── units_json
    ├── field_mapping_json
    ├── provenance_json       [source basename + SHA-256]
    ├── validation_summary_json
    └── operation log

The mapping declares the Pa-to-MPa stress conversion and the dimensionless strain/gradient
fields. The schema declares Cauchy stress, Hencky strain, finite-strain kinematics, and row-major
tensor component order. None of these scientific meanings are inferred from a field name.

## Reproduce the conversion

From the repository root:

    python examples/public-datasets/surfalex-aa6016a/fetch_data.py --output data
    python examples/public-datasets/surfalex-aa6016a/workflow.py \
      --input data/7A_workflow.hdf5 \
      --output artifacts/surfalex-7a.h5 \
      --report artifacts/surfalex-7a-report.json

The fetch step verifies both MD5 and SHA-256. The workflow step reads only the four explicit
volume-output paths, validates their record axes and tensor shapes, applies the local mapping,
and writes the output with the embedded schema snapshot. The JSON report is offline and contains
aggregate metadata and validation findings, not raw tensor records.

Expected acceptance metadata:

- record_count: 1,501;
- fields: step, stress, strain, F, Fp;
- stress: MPa;
- all tensor fields: per-record shape (3, 3);
- validation: valid with zero errors;
- schema hash: the value in expected/manifest.json.

## Boundaries and limitations

This is a case-specific extraction workflow, not a generic MatFlow adapter and not a claim of
generic DAMASK support. It does not run DAMASK, require MatFlow, read DADF5, reconstruct global
cell mappings, or certify physical/model correctness. The raw data remains under its upstream
license and is intentionally fetched by the user rather than redistributed in CPDataKit.

The case is designed to prove data-contract and provenance behavior. Some aggregate statistics
for shaped tensor fields may remain unavailable because CPDataKit does not silently flatten tensor
components.
