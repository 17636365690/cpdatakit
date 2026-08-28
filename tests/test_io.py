from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import h5py
import numpy as np
import pandas as pd
import pytest

import cpdatakit
from cpdatakit.exceptions import (
    CPDataKitError,
    DataReadError,
    DataValidationError,
    OutputExistsError,
)
from cpdatakit.io import iter_hdf5_chunks, load_dataset, load_hdf5, write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset


def _write_minimal_cpdatakit_hdf5(path: Path, attrs: dict[str, object] | None = None) -> None:
    defaults = {
        "format": "CPDataKit",
        "format_version": "1.0",
        "profile": "curve",
        "schema_version": "1.0",
        "units_json": "{}",
        "field_mapping_json": "{}",
        "provenance_json": "{}",
        "validation_summary_json": '{"valid": true, "error_count": 0, "warning_count": 0}',
    }
    defaults.update(attrs or {})
    with h5py.File(path, "w") as handle:
        for name, value in defaults.items():
            handle.attrs[name] = value
        handle.create_group("data").create_dataset("step", data=[0, 1])


def _make_test_hdf5(tmp_path: Path, rows: int) -> Path:
    schema = load_schema("curve")
    dataset = Dataset(
        pd.DataFrame(
            {
                "step": list(range(rows)),
                "strain": [index / 100 for index in range(rows)],
                "stress": [index * 10.0 for index in range(rows)],
            }
        ),
        {"units": {"step": "1", "strain": "1", "stress": "MPa"}},
    )
    output = tmp_path / "read-fixture.h5"
    write_hdf5(dataset, output, schema, validate_dataset(dataset, schema))
    return output


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


@pytest.mark.parametrize(
    "attribute",
    [
        "format_version",
        "profile",
        "schema_version",
        "units_json",
        "field_mapping_json",
        "provenance_json",
        "validation_summary_json",
    ],
)
def test_hdf5_requires_complete_metadata(tmp_path: Path, attribute: str) -> None:
    path = tmp_path / f"missing-{attribute}.h5"
    _write_minimal_cpdatakit_hdf5(path)
    with h5py.File(path, "r+") as handle:
        del handle.attrs[attribute]
    with pytest.raises(DataReadError, match="HDF5 metadata"):
        load_dataset(path)


@pytest.mark.parametrize(
    "attrs",
    [
        {"format_version": "2.0"},
        {"schema_version": "2.0"},
        {"profile": "unknown"},
        {"units_json": "[]"},
        {"field_mapping_json": "not-json"},
        {"provenance_json": 7},
    ],
)
def test_hdf5_rejects_invalid_metadata(tmp_path: Path, attrs: dict[str, object]) -> None:
    path = tmp_path / "invalid.h5"
    _write_minimal_cpdatakit_hdf5(path, attrs)
    with pytest.raises(DataReadError, match="HDF5 metadata"):
        load_dataset(path)


def test_hdf5_field_selection_still_checks_all_record_counts(tmp_path: Path) -> None:
    path = tmp_path / "inconsistent-selection.h5"
    _write_minimal_cpdatakit_hdf5(path)
    with h5py.File(path, "r+") as handle:
        handle["data"].create_dataset("stress", data=[0.0])

    with pytest.raises(DataReadError, match="inconsistent record counts"):
        load_hdf5(path, fields=["step"])


def test_load_hdf5_selects_fields_and_half_open_range(tmp_path: Path) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    selected = load_hdf5(path, fields=["stress", "step"], start=1, stop=4)
    assert list(selected.data.columns) == ["stress", "step"]
    assert selected.data["step"].tolist() == [1, 2, 3]
    assert selected.metadata["profile"] == "curve"


def test_iter_hdf5_chunks_reads_each_chunk_with_metadata(tmp_path: Path) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    chunks = list(iter_hdf5_chunks(path, fields=["step"], chunk_size=2))
    assert [len(chunk.data) for chunk in chunks] == [2, 2, 1]
    assert [chunk.data["step"].tolist() for chunk in chunks] == [[0, 1], [2, 3], [4]]
    assert all(chunk.metadata["profile"] == "curve" for chunk in chunks)


def test_hdf5_read_apis_are_exported() -> None:
    assert cpdatakit.load_hdf5 is load_hdf5
    assert cpdatakit.iter_hdf5_chunks is iter_hdf5_chunks


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fields": []},
        {"fields": "step"},
        {"fields": ["missing"]},
        {"start": -1},
        {"start": True},
        {"start": 1.5},
        {"start": 4, "stop": 3},
        {"stop": 6},
        {"stop": False},
    ],
)
def test_hdf5_read_rejects_invalid_selection(tmp_path: Path, kwargs: dict[str, object]) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    with pytest.raises(DataReadError):
        load_hdf5(path, **kwargs)


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5, "2"])
def test_hdf5_chunk_size_must_be_positive_integer(tmp_path: Path, chunk_size: object) -> None:
    path = _make_test_hdf5(tmp_path, rows=5)
    with pytest.raises(DataReadError):
        list(iter_hdf5_chunks(path, chunk_size=chunk_size))


def test_write_hdf5_rejects_invalid_validation_by_default(
    curve_csv: Path, tmp_path: Path
) -> None:
    dataset = load_dataset(curve_csv)
    schema = load_schema("curve")
    result = validate_dataset(dataset.data.drop(columns=["stress"]), schema)
    output = tmp_path / "invalid.h5"

    with pytest.raises(DataValidationError) as exc_info:
        write_hdf5(dataset, output, schema, result)

    assert isinstance(exc_info.value, CPDataKitError)
    assert not output.exists()


def test_write_hdf5_allows_explicit_invalid_output(curve_csv: Path, tmp_path: Path) -> None:
    dataset = load_dataset(curve_csv)
    schema = load_schema("curve")
    result = validate_dataset(dataset.data.drop(columns=["stress"]), schema)
    output = tmp_path / "invalid-allowed.h5"

    write_hdf5(dataset, output, schema, result, allow_invalid=True)

    assert load_dataset(output).metadata["validation_summary"]["valid"] is False


def test_write_hdf5_removes_temp_file_after_serialization_failure(tmp_path: Path) -> None:
    schema = load_schema("point")
    dataset = Dataset(
        pd.DataFrame({"point_id": [0, 1], "vector": [[1.0, 2.0], [3.0]]})
    )
    result = validate_dataset(dataset, schema)
    output = tmp_path / "broken.h5"

    with pytest.raises(DataReadError, match="inconsistent array shapes"):
        write_hdf5(dataset, output, schema, result, allow_invalid=True)

    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.*")) == []


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
