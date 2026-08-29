from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from cpdatakit.exceptions import DataReadError
from cpdatakit.io import write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import load_schema, schema_sha256
from cpdatakit.validation import validate_dataset


def _write_minimal_cpdatakit_hdf5(path: Path, attrs: dict[str, object] | None = None) -> None:
    defaults = {
        "format": "CPDataKit",
        "format_version": "1.0",
        "profile": "curve",
        "schema_version": "1.0",
        "units_json": '{"step":"1"}',
        "field_mapping_json": "{}",
        "provenance_json": '{"input_filename":"input.csv"}',
        "validation_summary_json": '{"valid": true, "error_count": 0, "warning_count": 0}',
    }
    defaults.update(attrs or {})
    with h5py.File(path, "w") as handle:
        for name, value in defaults.items():
            handle.attrs[name] = value
        handle.create_group("data").create_dataset("step", data=[0, 1])


def _write_dadf5(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs["DADF5_version_major"] = 1
        handle.attrs["DADF5_version_minor"] = 1
        geometry = handle.create_group("geometry")
        geometry.attrs["cells"] = [2, 1, 1]
        geometry.attrs["size"] = [1.0, 1.0, 1.0]
        geometry.attrs["origin"] = [0.0, 0.0, 0.0]
        cell_to = handle.create_group("cell_to")
        cell_to.create_group("homogenization").create_dataset(
            "label", data=np.asarray(["label0", "label0"], dtype="S")
        )
        cell_to.create_group("phase").create_dataset(
            "label", data=np.asarray(["label0", "label0"], dtype="S")
        )
        mechanical = (
            handle.create_group("increment_0")
            .create_group("homogenization")
            .create_group("Taylor")
            .create_group("mechanical")
        )
        field = mechanical.create_dataset("F", data=np.arange(18, dtype=float).reshape(2, 3, 3))
        field.attrs["unit"] = "1"
        field.attrs["description"] = "Synthetic deformation gradient"


def test_inspect_csv_describes_fields_and_records(tmp_path: Path) -> None:
    from cpdatakit.inspection import inspect_dataset

    path = tmp_path / "curve.csv"
    path.write_text("step,strain,stress\n0,0.0,0.0\n1,0.1,10.0\n", encoding="utf-8")

    result = inspect_dataset(path, schema="curve")

    assert result["file"]["format"] == "CSV"
    assert result["record_count"] == 2
    assert [field["name"] for field in result["fields"]] == ["step", "strain", "stress"]
    assert result["fields"][0]["dtype"] == "int64"
    assert result["schema"]["validation"]["valid"] is True


def test_inspect_json_preserves_input_field_order(tmp_path: Path) -> None:
    from cpdatakit.inspection import inspect_dataset

    path = tmp_path / "records.json"
    path.write_text(json.dumps([{"label": "A", "value": 1.5}]), encoding="utf-8")

    result = inspect_dataset(path)

    assert result["file"]["format"] == "JSON"
    assert [field["name"] for field in result["fields"]] == ["label", "value"]
    assert result["record_count"] == 1


def test_inspection_json_renderer_is_sorted_and_newline_terminated() -> None:
    from cpdatakit.inspection import render_inspection_json

    assert render_inspection_json({"z": 1, "a": 2}) == '{\n  "a": 2,\n  "z": 1\n}\n'


def test_inspect_cpdatakit_hdf5_reports_shape_dtype_units_and_chunks(
    curve: Dataset, tmp_path: Path
) -> None:
    from cpdatakit.inspection import inspect_dataset

    output = tmp_path / "curve.h5"
    schema = load_schema("curve")
    write_hdf5(curve, output, schema, validate_dataset(curve, schema), hdf5_chunk_size=2)

    result = inspect_dataset(output)

    assert result["file"]["format"] == "CPDataKit HDF5"
    assert result["file"]["format_version"] == "1.0"
    assert result["record_count"] == 3
    assert result["fields"][0]["shape"] == [3]
    assert result["fields"][0]["chunks"] == [2]
    assert result["fields"][2]["unit"] == "MPa"
    assert result["hdf5"]["chunks"]["step"] == [2]
    assert "input_filename" in result["provenance"]


def test_inspect_hdf5_catches_duplicate_index_across_chunks(
    curve: Dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cpdatakit.inspection import inspect_dataset

    curve.data.loc[2, "step"] = 0
    schema = load_schema("curve")
    output = tmp_path / "duplicate-index-across-chunks.h5"
    write_hdf5(
        curve,
        output,
        schema,
        validate_dataset(curve, schema),
        allow_invalid=True,
        hdf5_chunk_size=2,
    )
    monkeypatch.setattr("cpdatakit.inspection._INSPECTION_CHUNK_SIZE", 2)

    result = inspect_dataset(output, schema="curve")["schema"]["validation"]

    issue = next(item for item in result["errors"] if item["code"] == "duplicate_index")
    assert result["valid"] is False
    assert issue["field"] == "step"
    assert issue["affected_records"] == 2


def test_inspect_hdf5_catches_duplicate_record_across_chunks(
    curve: Dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cpdatakit.inspection import inspect_dataset

    curve.data.loc[2] = curve.data.loc[0]
    schema = load_schema("curve")
    output = tmp_path / "duplicate-record-across-chunks.h5"
    write_hdf5(
        curve,
        output,
        schema,
        validate_dataset(curve, schema),
        allow_invalid=True,
        hdf5_chunk_size=2,
    )
    monkeypatch.setattr("cpdatakit.inspection._INSPECTION_CHUNK_SIZE", 2)

    result = inspect_dataset(output, schema="curve")["schema"]["validation"]

    issue = next(item for item in result["warnings"] if item["code"] == "duplicate_record")
    assert issue["affected_records"] == 2


def test_inspect_text_includes_hdf5_provenance_and_adapter(curve: Dataset, tmp_path: Path) -> None:
    from cpdatakit.inspection import inspect_dataset, render_inspection_text

    output = tmp_path / "curve.h5"
    schema = load_schema("curve")
    write_hdf5(curve, output, schema, validate_dataset(curve, schema), hdf5_chunk_size=2)

    rendered = render_inspection_text(inspect_dataset(output))

    assert "HDF5" in rendered
    assert "Provenance:" in rendered
    assert "Adapter:" in rendered
    assert "chunks" in rendered


def test_inspect_hdf5_reads_bounded_slices_without_load_dataset(
    curve: Dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cpdatakit.inspection import inspect_hdf5_structure

    output = tmp_path / "curve.h5"
    schema = load_schema("curve")
    write_hdf5(curve, output, schema, validate_dataset(curve, schema), hdf5_chunk_size=1)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("inspect must not call load_dataset")

    monkeypatch.setattr("cpdatakit.inspection.load_dataset", fail)

    result = inspect_hdf5_structure(output)

    assert result["record_count"] == 3
    assert result["fields"][0]["missing_count"] == 0


def test_inspect_hdf5_reports_missing_values_and_array_shape(tmp_path: Path) -> None:
    from cpdatakit.inspection import inspect_hdf5_structure
    from cpdatakit.schema import make_field_schema, make_profile_schema

    schema = make_profile_schema(
        "point",
        [
            make_field_schema("point_id", "integer", required=True, unit="1"),
            make_field_schema("vector", "float", required=True, shape=[2], unit="1"),
        ],
    )
    dataset = Dataset(
        pd.DataFrame(
            {"point_id": [0, 1], "vector": [np.array([1.0, np.nan]), np.array([2.0, 3.0])]}
        ),
        {"units": {"point_id": "1", "vector": "1"}},
    )
    output = tmp_path / "point.h5"
    validation = validate_dataset(dataset, schema)
    write_hdf5(dataset, output, schema, validation, allow_invalid=True, hdf5_chunk_size=1)

    result = inspect_hdf5_structure(output)

    vector = next(field for field in result["fields"] if field["name"] == "vector")
    assert vector["shape"] == [2, 2]
    assert vector["record_shape"] == [2]
    assert vector["missing_count"] == 1


def test_inspect_reports_missing_values_and_schema_errors(tmp_path: Path) -> None:
    from cpdatakit.inspection import inspect_dataset

    path = tmp_path / "invalid.csv"
    path.write_text("step,strain,stress\n0,,0.0\n0,0.1,NaN\n", encoding="utf-8")

    result = inspect_dataset(path, schema="curve")

    assert result["fields"][1]["missing_count"] == 1
    assert result["risks"]["missing_values"][0]["field"] == "strain"
    assert result["schema"]["validation"]["valid"] is False
    assert {item["code"] for item in result["schema"]["validation"]["errors"]} >= {
        "missing_value",
        "duplicate_index",
    }


@pytest.mark.parametrize("attribute", ["format_version", "units_json", "provenance_json"])
def test_inspect_rejects_missing_cpdatakit_metadata(tmp_path: Path, attribute: str) -> None:
    from cpdatakit.inspection import inspect_hdf5_structure

    path = tmp_path / "broken.h5"
    _write_minimal_cpdatakit_hdf5(path)
    with h5py.File(path, "r+") as handle:
        del handle.attrs[attribute]

    with pytest.raises(DataReadError, match="metadata"):
        inspect_hdf5_structure(path)


def test_inspect_identifies_damask_dadf5(tmp_path: Path) -> None:
    from cpdatakit.inspection import inspect_hdf5_structure

    path = tmp_path / "result.hdf5"
    _write_dadf5(path)

    result = inspect_hdf5_structure(path)

    assert result["file"]["format"] == "DAMASK DADF5"
    assert result["adapter"]["name"] == "DamaskDADF5Adapter"
    assert result["adapter"]["label"] == "Taylor"
    assert result["fields"][0]["name"] == "point_id"
    field = next(field for field in result["fields"] if field["name"].startswith("user_dadf5_"))
    assert field["shape"] == [2, 3, 3]


def test_inspection_and_reporting_apis_are_exported() -> None:
    import cpdatakit
    from cpdatakit.inspection import inspect_dataset
    from cpdatakit.reporting import render_report_html

    assert cpdatakit.inspect_dataset is inspect_dataset
    assert cpdatakit.render_report_html is render_report_html


def test_inspect_hdf5_reports_schema_snapshot(curve: Dataset, tmp_path: Path) -> None:
    schema = load_schema("curve")
    path = tmp_path / "inspect-snapshot.h5"
    write_hdf5(
        curve,
        path,
        schema,
        validate_dataset(curve, schema),
        schema_uri="https://example.org/schema.json",
    )

    from cpdatakit.inspection import inspect_hdf5_structure

    result = inspect_hdf5_structure(path)

    assert result["hdf5"]["schema_snapshot"] == {
        "present": True,
        "sha256": schema_sha256(schema),
        "uri": "https://example.org/schema.json",
    }
