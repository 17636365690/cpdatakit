# Public Reference Case 1: Surfalex HF (AA6016A), Workflow 7A

This is the first CPDataKit example built from a published research dataset. It starts with a
real MatFlow/Hickle HDF5 file from the Surfalex project, selects four documented volume outputs,
and writes a CPDataKit HDF5 file that can be checked and reused.

The source files are downloaded when you run fetch_data.py. They stay out of this repository.

## Source

- Data record: [Surfalex HF formability study - Workflow 7 - Lankford coefficient](https://doi.org/10.5281/zenodo.7307639)
- Paper: [A novel integrated framework for reproducible formability predictions using virtual materials testing](https://doi.org/10.12688/materialsopenres.17516.1)
- Authors: Adam J. Plowman, Patryk Jedrasiak, Thomas Jailin, Peter Crowther, Sumeet Mishra,
  Pratheek Shanthraj, and Joao Quinta da Fonseca.
- Data license: CC BY 4.0.
- Analysis code: [LightForm-group/surfalex_data_explorer](https://github.com/LightForm-group/surfalex_data_explorer),
  licensed under MIT.

The two source files and their checksums are:

| File | Bytes | Published MD5 | Expected SHA-256 |
| --- | ---: | --- | --- |
| 7A_simulate_uniaxial_tension.yml | 2,864 | 3500212694d54f8a974af4c8a9af9b84 | d548c12dfd7fabf01b3dce4233c00faf5c4bb13e04d5a5bb8e1d7ea77a393abb |
| 7A_workflow.hdf5 | 7,623,248 | 58abe7493d55d8f5e0033ba740e76f8e | a4c1c51609e9dadcd3ea680ab6b3511877affac5f24fe25b84daa6daf8fb0693 |

The same values are stored in expected/manifest.json.

## What is in the source file

Workflow 7A is a uniaxial-tension CP-FFT workflow. It uses DAMASK through the published MatFlow
workflow. The HDF5 file uses MatFlow/Hickle workflow storage.

The selected volume outputs sit below:

    element_data/
    └── 0022_volume_element_response/
        └── data/'volume_data'/data/
            ├── 'vol_avg_stress'
            ├── 'vol_avg_strain'
            ├── 'vol_avg_def_grad'
            └── 'vol_avg_def_grad_plastic'

Each output contains 1,501 records and a 3 x 3 tensor for each record. The Workflow 7A YAML calls
the stress output volume-averaged Cauchy stress and the strain output volume-averaged Hencky strain.

## Before and after

The raw file spreads its data across nested Hickle containers. Its useful fields still carry the
names chosen by the workflow:

    Raw MatFlow/Hickle HDF5
    ├── workflow metadata
    ├── nested data/data containers
    ├── vol_avg_stress
    ├── vol_avg_strain
    ├── vol_avg_def_grad
    └── vol_avg_def_grad_plastic

The converted file has a small, declared record table:

    CPDataKit HDF5
    ├── /data/step
    ├── /data/stress          [1501, 3, 3], MPa
    ├── /data/strain          [1501, 3, 3], dimensionless
    ├── /data/F               [1501, 3, 3], dimensionless
    ├── /data/Fp              [1501, 3, 3], dimensionless
    ├── schema_json
    ├── schema_sha256
    ├── units_json
    ├── field_mapping_json
    ├── provenance_json       [source name + SHA-256]
    ├── validation_summary_json
    └── operation log

The mapping contains the Pa-to-MPa stress conversion and the dimensionless conversions for strain
and the two gradients. The schema records the stress measure, strain measure, finite-strain
kinematics, and row-major component order, making each choice explicit.

## Run it

From the repository root:

    python examples/public-datasets/surfalex-aa6016a/fetch_data.py --output data
    python examples/public-datasets/surfalex-aa6016a/workflow.py \
      --input data/7A_workflow.hdf5 \
      --output artifacts/surfalex-7a.h5 \
      --report artifacts/surfalex-7a-report.json

fetch_data.py checks both MD5 and SHA-256. workflow.py reads the four paths above, checks their
record axes and shapes, applies the mapping, and writes the output with the schema snapshot.
The report is plain JSON. It contains counts, metadata, and validation findings; tensor records
remain in the converted HDF5 artifact.

The expected result has 1,501 records, fields step/stress/strain/F/Fp, MPa stress, (3, 3)
per-record tensor shapes, and zero validation errors. The expected schema hash is in the manifest.

## Case boundary

This extractor follows the paths and conventions documented for Workflow 7A. Raw data stays under
its upstream license and is downloaded by the user. Future readers can extend the same pattern with
their own format evidence, licensing record, schema, mapping, and offline fixture.

Reports may leave shaped-field aggregate statistics empty. That is deliberate. CPDataKit keeps
tensor components intact instead of silently flattening them.
