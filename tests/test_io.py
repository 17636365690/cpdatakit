from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import h5py
import numpy as np
import pandas as pd
import pytest

from cpdatakit.exceptions import DataReadError, OutputExistsError
from cpdatakit.io import load_dataset, write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset


def test_csv_case_insensitive(curve_csv: Path) -> None:
    assert len(load_dataset(curve_csv).data) == 2


def test_json_records(tmp_path: Path) -> None:
    path = tmp_path / "data.JSON"
    path.write_text(json.dumps([{"x": 1, "y": 2}]), encoding="utf-8")
    assert load_dataset(path).data.iloc[0]["x"] == 1


@pytest.mark.parametrize("filename,content", [("empty.csv", b""), ("bad.json", b"{")])
def test_bad_text_inputs(tmp_path: Path, filename: str, content: bytes) -> None:
    path = tmp_path / filename
    path.write_bytes(content)
    with pytest.raises(DataReadError):
        load_dataset(path)


def test_header_only_csv_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "header-only.csv"
    path.write_text("step,strain,stress\n", encoding="utf-8")
    with pytest.raises(DataReadError, match="no records"):
        load_dataset(path)


def test_unsupported_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(DataReadError):
        load_dataset(path)
    with pytest.raises(DataReadError):
        load_dataset(tmp_path / "missing.csv")


def test_corrupt_hdf5(tmp_path: Path) -> None:
    path = tmp_path / "bad.h5"
    path.write_bytes(b"not hdf5")
    with pytest.raises(DataReadError):
        load_dataset(path)


def test_hdf5_roundtrip_and_provenance(curve_csv: Path, tmp_path: Path) -> None:
    dataset = load_dataset(curve_csv)
    dataset.metadata["units"] = {"step": "1", "strain": "1", "stress": "MPa"}
    schema = load_schema("curve")
    validation = validate_dataset(dataset, schema)
    output = tmp_path / "result.h5"
    write_hdf5(dataset, output, schema, validation, field_mapping={}, operation_log=["test"])
    loaded = load_dataset(output)
    assert loaded.metadata["profile"] == "curve"
    assert loaded.metadata["provenance"]["input_filename"] == curve_csv.name
    assert len(loaded.metadata["provenance"]["input_sha256"]) == 64
    assert loaded.data.shape == dataset.data.shape
    with pytest.raises(OutputExistsError):
        write_hdf5(dataset, output, schema, validation)


def test_structurally_wrong_hdf5(tmp_path: Path) -> None:
    path = tmp_path / "wrong.h5"
    with h5py.File(path, "w") as handle:
        handle.attrs["format"] = "Other"
    with pytest.raises(DataReadError):
        load_dataset(path)


@pytest.mark.parametrize("case", ["empty", "scalar", "mismatched"])
def test_malformed_cpdatakit_hdf5_raises_data_read_error(tmp_path: Path, case: str) -> None:
    path = tmp_path / f"{case}.h5"
    with h5py.File(path, "w") as handle:
        handle.attrs["format"] = "CPDataKit"
        data = handle.create_group("data")
        if case == "scalar":
            data.create_dataset("value", data=1.0)
        elif case == "mismatched":
            data.create_dataset("x", data=[0.0, 1.0])
            data.create_dataset("y", data=[0.0])
    with pytest.raises(DataReadError):
        load_dataset(path)


def test_path_styles_are_representable() -> None:
    assert PureWindowsPath(r"C:\data\curve.csv").suffix == ".csv"
    assert PurePosixPath("/data/curve.csv").suffix == ".csv"


def test_vector_hdf5_roundtrip(tmp_path: Path) -> None:
    schema_path = tmp_path / "vector-schema.json"
    schema_path.write_text(
        '{"profile":"point","schema_version":"1.0","fields":['
        '{"name":"point_id","dtype":"integer","required":true,"index":true,"unit":"1"},'
        '{"name":"vector","dtype":"float","required":true,"shape":[3],"unit":"MPa"}'
        "]}",
        encoding="utf-8",
    )
    schema = load_schema(schema_path)
    dataset = Dataset(
        pd.DataFrame({"point_id": [0, 1], "vector": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]}),
        {"units": {"point_id": "1", "vector": "MPa"}},
    )
    result = validate_dataset(dataset, schema)
    assert result.valid
    output = tmp_path / "vector.h5"
    write_hdf5(dataset, output, schema, result)
    assert np.allclose(load_dataset(output).data["vector"].iloc[1], [4.0, 5.0, 6.0])
