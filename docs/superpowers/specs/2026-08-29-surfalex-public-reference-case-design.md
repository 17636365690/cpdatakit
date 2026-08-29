# Surfalex Public Reference Case

**Date:** 2026-08-29  
**Status:** Approved in chat. Implementation in progress.

## What this case is for

Public Reference Case 1 uses the Surfalex HF (AA6016A) Workflow 7A data. It gives CPDataKit a
real file to work on and shows the steps between a solver workflow and a checked CPDataKit HDF5
artifact.

The source record is Zenodo DOI 10.5281/zenodo.7307639, titled "Surfalex HF formability study -
Workflow 7 - Lankford coefficient". Adam J. Plowman is the listed creator. The record and the
Workflow 7A specification use CC BY 4.0. The accompanying 2023 paper is "A novel integrated
framework for reproducible formability predictions using virtual materials testing", DOI
10.12688/materialsopenres.17516.1. The analysis repository is
LightForm-group/surfalex_data_explorer, licensed under MIT.

The source files are:

- 7A_simulate_uniaxial_tension.yml, 2,864 bytes, MD5
  3500212694d54f8a974af4c8a9af9b84, SHA-256
  D548C12DFD7FABF01B3DCE4233C00FAF5C4BB13E04D5A5BB8E1D7EA77A393ABB.
- 7A_workflow.hdf5, 7,623,248 bytes, MD5
  58abe7493d55d8f5e0033ba740e76f8e, SHA-256
  A4C1C51609E9DADCD3EA680AB6B3511877AFFAC5F24FE25B84DAA6DAF8FB0693.

The HDF5 file is MatFlow/Hickle workflow storage. It is not a DAMASK DADF5 file. Its selected
volume outputs are vol_avg_stress, vol_avg_strain, vol_avg_def_grad, and
vol_avg_def_grad_plastic. Each has 1,501 records with a 3 x 3 tensor for each record.

## Files in this example

The case directory contains:

1. A small synthetic HDF5 fixture in the test suite that uses the same nested names as the source.
2. A local finite-strain schema with explicit Cauchy stress, Hencky strain, finite-strain, and
   row-major tensor declarations.
3. A local mapping for the four source outputs and their units.
4. fetch_data.py, which downloads the YAML and HDF5 files only when the user asks for them and
   checks both published MD5 and expected SHA-256.
5. workflow.py, which reads the selected nodes, runs CPDataKit normalization and validation, and
   writes the output HDF5 plus an optional offline report.
6. A manifest with source and expected-output metadata.

Raw source data is not committed.

## Workflow

The user runs:

    python examples/public-datasets/surfalex-aa6016a/fetch_data.py --output data
    python examples/public-datasets/surfalex-aa6016a/workflow.py \
      --input data/7A_workflow.hdf5 \
      --output artifacts/surfalex-7a.h5 \
      --report artifacts/surfalex-7a-report.json

The extractor reads these exact paths:

    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_stress'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_strain'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_def_grad'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_def_grad_plastic'

It takes the record axis from the stress output's increments metadata. It checks that every
selected output has shape (1501, 3, 3) and that the increment arrays agree before building a
Dataset.

The mapping renames increment to step. It converts stress from Pa to MPa. It maps strain, F, and
Fp to dimensionless fields. The schema stores the source's Cauchy and Hencky labels and the
row-major tensor order. These are written down for this case. The extractor never guesses them.

## Output

The converted file has step, stress, strain, F, and Fp under /data. The tensor fields retain their
(3, 3) per-record shape. The writer also records the canonical schema, its SHA-256, source name
and digest, mapping, units, validation summary, versions, and operation log.

The optional report contains field shapes, counts, metadata, statistics where available, and
validation findings. It contains no raw tensor values and no local absolute paths.

## Limits

This example is a case-specific extractor. It does not make CPDataKit a general MatFlow reader
or a generic DAMASK adapter. It does not run DAMASK, install MatFlow, read DADF5, reconstruct
global cell mappings, or judge the physical model. The user downloads the source files under the
license shown by the upstream record.

The report may leave aggregate statistics empty for shaped fields. CPDataKit keeps tensor
components intact instead of flattening them without a declared rule.

## Acceptance

The case tests run offline. They cover extraction, shapes, record counts, the Pa-to-MPa mapping,
schema snapshot recovery, report generation, and malformed source structure. The project checks
also cover the full test suite, coverage threshold, Ruff, formatting, build, and distribution
contents.
