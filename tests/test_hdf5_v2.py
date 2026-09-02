from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import xarray as xr

from cpdatakit.data import ScientificDataset
from cpdatakit.exceptions import DataReadError, OutputExistsError
from cpdatakit.formats import Selection
from cpdatakit.io import load_hdf5_v2, write_hdf5_v2
from cpdatakit.schemas import resolve_schema_v2, schema_v2_sha256

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "tests" / "fixtures" / "schema-v2" / "composed.json"
GENERATOR = ROOT / "scripts" / "generate_hdf5_v2_fixtures.py"


def _value() -> ScientificDataset:
    return ScientificDataset(
        xr.Dataset(
            data_vars={
                "temperature": (
                    ("time", "y", "x"),
                    np.asarray(
                        [
                            [[273.15, 274.15, 275.15, 276.15]] * 3,
                            [[283.15, 284.15, 285.15, 286.15]] * 3,
                            [[293.15, 294.15, 295.15, 296.15]] * 3,
                            [[303.15, 304.15, 305.15, 306.15]] * 3,
                        ]
                    ),
                    {"unit": "K", "role": "measured_field"},
                )
            },
            coords={
                "time": ("time", [0.0, 10.0, 20.0, 30.0], {"unit": "s"}),
                "y": ("y", [-1.0, 0.0, 1.0], {"unit": "mm"}),
                "x": ("x", [0.0, 1.0, 2.0, 3.0], {"unit": "mm"}),
                "stage": (
                    "time",
                    ["ambient", "heating", "hold", "cooling"],
                ),
            },
        ),
        metadata={
            "units": {"time": "s", "y": "mm", "x": "mm", "temperature": "K"},
            "provenance": {"source_description": "test fixture"},
            "validation_summary": {"valid": True, "error_count": 0, "warning_count": 0},
        },
        source=Path("thermal-field.nc"),
    )


def _generate_fixtures(output: Path) -> None:
    spec = importlib.util.spec_from_file_location("generate_hdf5_v2_fixtures", GENERATOR)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load HDF5 v2 fixture generator: {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.generate_fixtures(output)


def test_hdf5_v2_round_trip_preserves_dimensions_coordinates_variables_and_metadata(
    tmp_path: Path,
) -> None:
    output = tmp_path / "thermal-field.h5"
    schema = resolve_schema_v2(SCHEMA)

    write_hdf5_v2(_value(), output, schema)
    loaded = load_hdf5_v2(output)

    assert tuple(loaded.data.dims) == ("time", "y", "x")
    assert loaded.data["temperature"].shape == (4, 3, 4)
    assert loaded.data["temperature"].attrs["unit"] == "K"
    assert loaded.data["stage"].values.tolist() == ["ambient", "heating", "hold", "cooling"]
    assert loaded.metadata["units"]["temperature"] == "K"
    assert loaded.metadata["provenance"]["source_description"] == "test fixture"
    assert loaded.source == output


def test_hdf5_v2_written_layout_has_schema_digest_and_ordered_dimension_references(
    tmp_path: Path,
) -> None:
    output = tmp_path / "thermal-field.h5"
    schema = resolve_schema_v2(SCHEMA)

    write_hdf5_v2(_value(), output, schema)

    with h5py.File(output, "r") as handle:
        schema_payload = json.loads(handle.attrs["schema_json"])
        assert handle.attrs["format"] == "CPDataKit"
        assert handle.attrs["format_version"] == "2.0"
        assert handle.attrs["profile"] == "thermal-field"
        assert handle.attrs["schema_sha256"] == schema_v2_sha256(schema)
        assert json.loads(handle["variables"]["temperature"].attrs["dims_json"]) == [
            "time",
            "y",
            "x",
        ]
        assert schema_payload["resolved"]["schema_version"] == "2.0"
        assert sorted(handle) == ["coordinates", "dimensions", "metadata", "variables"]


def test_hdf5_v2_selection_bounds_the_record_axis_and_variable_set(tmp_path: Path) -> None:
    output = tmp_path / "thermal-field.h5"
    write_hdf5_v2(_value(), output, resolve_schema_v2(SCHEMA))

    loaded = load_hdf5_v2(
        output,
        selection=Selection(fields=("temperature",), start=1, stop=3),
    )

    assert tuple(loaded.data.data_vars) == ("temperature",)
    assert loaded.data["temperature"].shape == (2, 3, 4)
    assert loaded.data["time"].values.tolist() == [10.0, 20.0]


def test_hdf5_v2_rejects_existing_output_without_force(tmp_path: Path) -> None:
    output = tmp_path / "thermal-field.h5"
    schema = resolve_schema_v2(SCHEMA)
    write_hdf5_v2(_value(), output, schema)

    with pytest.raises(OutputExistsError, match="already exists"):
        write_hdf5_v2(_value(), output, schema)


def test_hdf5_v2_reader_rejects_preflight_corruption_fixtures(tmp_path: Path) -> None:
    _generate_fixtures(tmp_path)

    with pytest.raises(DataReadError, match="missing dimension"):
        load_hdf5_v2(tmp_path / "missing-dimension-reference.h5")
    with pytest.raises(DataReadError, match="format_version"):
        load_hdf5_v2(tmp_path / "root-version-mismatch.h5")
    with pytest.raises(DataReadError, match="schema_sha256"):
        load_hdf5_v2(tmp_path / "schema-hash-mismatch.h5")
