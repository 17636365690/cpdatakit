from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

import cpdatakit
from cpdatakit.exceptions import DataReadError

CASE_ROOT = Path(__file__).parents[1] / "examples" / "public-datasets" / "surfalex-aa6016a"


def _load_case_module(name: str):
    spec = importlib.util.spec_from_file_location(name, CASE_ROOT / f"{name}.py")
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load case module {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_volume_output(
    volume_data: h5py.Group,
    name: str,
    values: np.ndarray,
    increments: np.ndarray,
) -> None:
    output = volume_data.create_group(f"'{name}'")
    output_data = output.create_group("data")
    output_values = output_data.create_group("'data'")
    output_values.create_dataset("data", data=values)
    output_meta = output_data.create_group("'meta'")
    meta_data = output_meta.create_group("data")
    increment_data = meta_data.create_group("'increments'")
    increment_data.create_dataset("data", data=increments)


def _write_fixture(path: Path, *, omit: str | None = None, mismatch: str | None = None) -> None:
    increments = np.asarray([0, 1], dtype=np.int64)
    stress = np.asarray(
        [
            [[1_000_000.0, 0.0, 0.0], [0.0, 2_000_000.0, 0.0], [0.0, 0.0, 3_000_000.0]],
            [[4_000_000.0, 0.0, 0.0], [0.0, 5_000_000.0, 0.0], [0.0, 0.0, 6_000_000.0]],
        ]
    )
    strain = np.asarray(
        [
            [[0.01, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 0.03]],
            [[0.04, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 0.06]],
        ]
    )
    deformation = np.asarray(
        [
            [[1.01, 0.0, 0.0], [0.0, 1.02, 0.0], [0.0, 0.0, 1.03]],
            [[1.04, 0.0, 0.0], [0.0, 1.05, 0.0], [0.0, 0.0, 1.06]],
        ]
    )
    values = {
        "vol_avg_stress": stress,
        "vol_avg_strain": strain,
        "vol_avg_def_grad": deformation,
        "vol_avg_def_grad_plastic": deformation - 0.005,
    }
    with h5py.File(path, "w") as handle:
        handle.attrs["matflow_version"] = "0.2.26"
        handle.attrs["workflow_id"] = "synthetic-surfalex"
        handle.attrs["workflow_version"] = 0
        response_data = (
            handle.create_group("element_data")
            .create_group("0022_volume_element_response")
            .create_group("data")
        )
        volume_data = response_data.create_group("'volume_data'").create_group("data")
        for name, value in values.items():
            if name == omit:
                continue
            selected = value[:-1] if name == mismatch else value
            _write_volume_output(volume_data, name, selected, increments)


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
    loaded = cpdatakit.load_hdf5(output, fields=["step", "stress", "strain", "F", "Fp"])
    assert list(loaded.data.columns) == ["step", "stress", "strain", "F", "Fp"]
    assert loaded.data["stress"].iloc[0][0, 0] == pytest.approx(1.0)
    assert loaded.data["stress"].iloc[1][2, 2] == pytest.approx(6.0)
    assert loaded.metadata["units"]["stress"] == "MPa"
    assert loaded.metadata["schema_snapshot"]["schema"]["profile"] == "curve"
    assert loaded.metadata["provenance"]["input_filename"] == raw.name
    report_text = report.read_text(encoding="utf-8")
    payload = json.loads(report_text)
    assert payload["validation"]["valid"] is True
    assert str(raw) not in report_text


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


def test_fetch_verifier_checks_md5_and_sha256(tmp_path: Path) -> None:
    fetch = _load_case_module("fetch_data")
    path = tmp_path / "payload.bin"
    path.write_bytes(b"hello world")

    fetch.verify_file(
        path,
        {
            "name": "payload.bin",
            "md5": "5eb63bbbe01eeed093cb22bb8f5acdc3",
            "sha256": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        },
    )


def test_fetch_verifier_rejects_wrong_digest(tmp_path: Path) -> None:
    fetch = _load_case_module("fetch_data")
    path = tmp_path / "payload.bin"
    path.write_bytes(b"hello world")

    with pytest.raises(ValueError, match="MD5 mismatch"):
        fetch.verify_file(
            path,
            {
                "name": "payload.bin",
                "md5": "0" * 32,
                "sha256": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            },
        )
