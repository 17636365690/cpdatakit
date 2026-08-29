# Surfalex Public Reference Case Design

**Date:** 2026-08-29  
**Status:** Approved in chat; implementation in progress

## Goal

Add CPDataKit Public Reference Case #1 using the openly licensed Surfalex HF (AA6016A)
Workflow 7A dataset, demonstrating an auditable conversion from a real MatFlow/DAMASK
workflow artifact to a validated CPDataKit HDF5 dataset.

## Evidence basis

The source case is the Zenodo record 10.5281/zenodo.7307639, “Surfalex HF formability study -
Workflow 7 - Lankford coefficient”, published by Adam J. Plowman and released under CC BY 4.0.
The associated 2023 paper is “A novel integrated framework for reproducible formability
predictions using virtual materials testing”, DOI 10.12688/materialsopenres.17516.1. The
upstream analysis repository is LightForm-group/surfalex_data_explorer under MIT.

The selected 7A files are:

- 7A_simulate_uniaxial_tension.yml, 2,864 bytes, upstream MD5
  3500212694d54f8a974af4c8a9af9b84, local SHA-256
  D548C12DFD7FABF01B3DCE4233C00FAF5C4BB13E04D5A5BB8E1D7EA77A393ABB.
- 7A_workflow.hdf5, 7,623,248 bytes, upstream MD5
  58abe7493d55d8f5e0033ba740e76f8e, local SHA-256
  A4C1C51609E9DADCD3EA680AB6B3511877AFFAC5F24FE25B84DAA6DAF8FB0693.

The HDF5 file is MatFlow/Hickle workflow storage, not DAMASK DADF5. Its documented volume
outputs include vol_avg_stress, vol_avg_strain, vol_avg_def_grad, and
vol_avg_def_grad_plastic, each with 1,501 records and a 3 x 3 trailing tensor shape.

## Scope

This case adds:

1. A no-network test fixture matching the relevant nested MatFlow/Hickle paths.
2. A local schema declaring a finite-strain curve with explicit stress/strain conventions and
   row-major 3 x 3 tensor components.
3. A local mapping declaring source names and units explicitly.
4. A fetch script that downloads only the two selected files on explicit user request and checks
   both upstream MD5 and expected SHA-256.
5. A workflow script that extracts selected arrays with h5py, normalizes them through CPDataKit,
   writes a provenance-rich HDF5 file, and optionally writes an offline report.
6. A README with source citation, license, exact hashes, before/after structure, commands, and
   limitations.
7. A manifest with expected record count, fields, shapes, units, and schema hash.

Out of scope: a general MatFlow adapter, a DAMASK solver dependency, redistribution of raw files,
automatic unit or convention inference, solver execution, scientific correctness claims, and a
second 316L case.

## Case workflow

The user explicitly runs:

    python examples/public-datasets/surfalex-aa6016a/fetch_data.py --output data
    python examples/public-datasets/surfalex-aa6016a/workflow.py \
      --input data/7A_workflow.hdf5 \
      --output artifacts/surfalex-7a.h5 \
      --report artifacts/surfalex-7a-report.json

fetch_data.py uses stdlib urllib, creates the selected output directory, refuses to silently
replace an existing file with different content, and validates MD5 plus SHA-256. It does not run
during import or tests.

workflow.py reads only these explicit paths:

    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_stress'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_strain'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_def_grad'
    /element_data/0022_volume_element_response/data/'volume_data'/data/'vol_avg_def_grad_plastic'

The extractor obtains each array from the nested data/data node and obtains the record axis from
the stress output metadata increments array. It checks that all selected arrays have shape
(1501, 3, 3) and matching increments before constructing a Dataset with source path and raw
units metadata.

The case mapping explicitly renames increment to step, vol_avg_stress to stress with Pa-to-MPa
conversion, vol_avg_strain to strain, vol_avg_def_grad to F, and
vol_avg_def_grad_plastic to Fp. The schema declares Cauchy stress, Hencky strain, and
row-major tensor component order; these declarations are case metadata, not inferred by the
extractor.

## Output contract

The normalized output is a CPDataKit HDF5 file with fields step, stress, strain, F, and Fp.
All tensor fields retain per-record shape (3, 3), stress is stored in MPa, and dimensionless
fields retain dimensionless units. The HDF5 writer embeds the local schema JSON and SHA-256,
the raw input basename and digest, explicit mapping, conversion time, CPDataKit/Python versions,
validation summary, and operation log.

The report is optional, offline, and contains aggregate structure/statistics/validation metadata
only. It must not include raw tensor records or absolute local paths.

## Testing and acceptance

Tests run entirely offline against a tiny synthetic HDF5 fixture with the same path conventions.
They verify extraction, shape/count checks, explicit mapping, HDF5 schema snapshot recovery,
report generation, and failure for missing selected paths or inconsistent record counts.

Acceptance requires the example tests, full project tests, coverage gate, Ruff, format check,
package build, and diff audit to pass. No raw third-party data may appear in Git history.
