from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

import cpdatakit.adapters as adapters
from cpdatakit.exceptions import CPDataKitError
from cpdatakit.validation import validate_dataset


def _write_dadf5(
    path: Path,
    *,
    version: tuple[int, int] = (1, 1),
    labels: tuple[str, ...] = ("Taylor",),
    values: dict[str, np.ndarray] | None = None,
    units: dict[str, str] | None = None,
) -> None:
    values = values or {
        "F": np.arange(18, dtype=float).reshape(2, 3, 3),
        "P": np.arange(18, dtype=float).reshape(2, 3, 3) + 100.0,
    }
    units = units or {name: "1" for name in values}
    with h5py.File(path, "w") as handle:
        handle.attrs["DADF5_version_major"] = version[0]
        handle.attrs["DADF5_version_minor"] = version[1]
        geometry = handle.create_group("geometry")
        geometry.attrs["cells"] = [2, 1, 1]
        geometry.attrs["size"] = [1.0, 1.0, 1.0]
        geometry.attrs["origin"] = [0.0, 0.0, 0.0]
        cell_to = handle.create_group("cell_to")
        for kind in ("phase", "homogenization"):
            group = cell_to.create_group(kind)
            group.create_dataset("label", data=np.asarray(["label0", "label0"], dtype="S"))
        increment = handle.create_group("increment_0")
        increment.attrs["t/s"] = 0.0
        selected = increment.create_group("homogenization").create_group(labels[0])
        mechanical = selected.create_group("mechanical")
        for name, value in values.items():
            dataset = mechanical.create_dataset(name, data=value)
            dataset.attrs["unit"] = units[name]
            dataset.attrs["description"] = f"Synthetic DADF5 {name}"
        for label in labels[1:]:
            group = increment["homogenization"].create_group(label).create_group("mechanical")
            for name, value in values.items():
                dataset = group.create_dataset(name, data=value)
                dataset.attrs["unit"] = units[name]
                dataset.attrs["description"] = f"Synthetic DADF5 {name}"


def _adapter(**kwargs):
    implementation = getattr(adapters, "DamaskDADF5Adapter", None)
    assert implementation is not None, "DamaskDADF5Adapter is missing"
    return implementation(**kwargs)


def test_damask_dadf5_adapter_loads_selected_datasets(tmp_path: Path) -> None:
    path = tmp_path / "result.hdf5"
    _write_dadf5(path)

    dataset = _adapter(label="Taylor", datasets=["F", "P"]).load(path)

    assert list(dataset.data.columns) == [
        "point_id",
        "user_dadf5_homogenization_Taylor_mechanical_F",
        "user_dadf5_homogenization_Taylor_mechanical_P",
    ]
    assert dataset.data["point_id"].tolist() == [0, 1]
    np.testing.assert_allclose(
        np.stack(dataset.data.iloc[1]["user_dadf5_homogenization_Taylor_mechanical_F"]),
        np.arange(9, 18, dtype=float).reshape(3, 3),
    )
    assert dataset.metadata["units"]["user_dadf5_homogenization_Taylor_mechanical_F"] == "1"
    assert dataset.metadata["field_mapping"]["user_dadf5_homogenization_Taylor_mechanical_F"][
        "source"
    ].endswith("/increment_0/homogenization/Taylor/mechanical/F")
    assert dataset.metadata["adapter"]["format"] == "DAMASK DADF5"
    assert validate_dataset(dataset, "point").valid


@pytest.mark.parametrize("version", [(0, 13), (2, 0)])
def test_damask_dadf5_adapter_rejects_unsupported_version(
    tmp_path: Path, version: tuple[int, int]
) -> None:
    path = tmp_path / "unsupported.hdf5"
    _write_dadf5(path, version=version)

    with pytest.raises(CPDataKitError, match="DADF5"):
        _adapter(label="Taylor").load(path)


def test_damask_dadf5_adapter_requires_explicit_label_when_ambiguous(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.hdf5"
    _write_dadf5(path, labels=("Taylor", "Voigt"))

    with pytest.raises(CPDataKitError, match="label"):
        _adapter().load(path)


def test_damask_dadf5_adapter_rejects_inconsistent_dataset_lengths(tmp_path: Path) -> None:
    path = tmp_path / "inconsistent.hdf5"
    _write_dadf5(
        path,
        values={
            "F": np.zeros((2, 3, 3)),
            "P": np.zeros((1, 3, 3)),
        },
    )

    with pytest.raises(CPDataKitError, match="record counts"):
        _adapter(label="Taylor").load(path)


def test_damask_dadf5_adapter_requires_dataset_metadata(tmp_path: Path) -> None:
    path = tmp_path / "missing-unit.hdf5"
    _write_dadf5(path, units={"F": "1", "P": ""})

    with pytest.raises(CPDataKitError, match="unit"):
        _adapter(label="Taylor", datasets=["P"]).load(path)
