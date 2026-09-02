from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from cpdatakit.data import (
    AmbiguousRecordAxisError,
    LossyConversionError,
    RaggedDataError,
    ScientificDataset,
    UnsupportedDataError,
    dataset_to_scientific,
    scientific_to_dataset,
)
from cpdatakit.model import Dataset

ROOT = Path(__file__).parents[1]
REFERENCE = ROOT / "examples" / "thermal-field-v2" / "reference.json"


def _thermal_xarray() -> xr.Dataset:
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    coordinates = {
        name: (tuple(item["dims"]), item["values"]) for name, item in payload["coordinates"].items()
    }
    variables = {
        name: (tuple(item["dims"]), item["values"], {"units": item["unit"]})
        for name, item in payload["variables"].items()
    }
    return xr.Dataset(data_vars=variables, coords=coordinates)


def test_scientific_dataset_copy_isolates_xarray_data_and_nested_metadata() -> None:
    original = ScientificDataset(
        xr.Dataset({"temperature": (("time",), [273.15, 283.15])}),
        metadata={"provenance": {"source": "fixture"}},
        source=Path("fixture.nc"),
    )

    copied = original.copy()
    copied.data["temperature"].values[0] = 999.0
    copied.metadata["provenance"]["source"] = "changed"

    assert original.data["temperature"].values[0] == 273.15
    assert original.metadata["provenance"]["source"] == "fixture"
    assert copied.source == original.source


def test_dataset_to_scientific_preserves_order_units_and_record_dimension() -> None:
    dataset = Dataset(
        pd.DataFrame(
            {
                "time": [0.0, 10.0],
                "temperature": [273.15, 283.15],
                "stage": ["heat", "cool"],
            }
        ),
        metadata={"units": {"time": "s", "temperature": "K"}},
    )

    scientific = dataset_to_scientific(dataset)

    assert list(scientific.data.data_vars) == ["time", "temperature", "stage"]
    assert tuple(scientific.data["temperature"].dims) == ("record",)
    assert scientific.data["temperature"].attrs["unit"] == "K"
    assert scientific.metadata["record_dim"] == "record"


def test_dataset_to_scientific_gives_fixed_array_fields_stable_trailing_axes() -> None:
    dataset = Dataset(
        pd.DataFrame(
            {
                "step": [0, 1],
                "tensor": [
                    np.asarray([[1.0, 2.0], [3.0, 4.0]]),
                    np.asarray([[5.0, 6.0], [7.0, 8.0]]),
                ],
            }
        )
    )

    scientific = dataset_to_scientific(dataset)

    assert tuple(scientific.data["tensor"].dims) == (
        "record",
        "tensor__axis_0",
        "tensor__axis_1",
    )
    assert scientific.data["tensor"].shape == (2, 2, 2)
    assert scientific.data["tensor"].dtype == np.dtype("float64")


def test_dataset_to_scientific_rejects_ragged_array_values() -> None:
    dataset = Dataset(pd.DataFrame({"values": [np.asarray([1.0, 2.0]), np.asarray([3.0])]}))

    with pytest.raises(RaggedDataError, match="values"):
        dataset_to_scientific(dataset)


def test_dataset_to_scientific_rejects_unsupported_object_values() -> None:
    dataset = Dataset(pd.DataFrame({"metadata": [{"a": 1}, {"a": 2}]}))

    with pytest.raises(UnsupportedDataError, match="object"):
        dataset_to_scientific(dataset)


def test_tabular_round_trip_is_lossless_for_scalars_and_metadata() -> None:
    dataset = Dataset(
        pd.DataFrame(
            {
                "step": [0, 1],
                "temperature": [273.15, 283.15],
                "stage": ["heat", "cool"],
            }
        ),
        metadata={"units": {"temperature": "K"}, "provenance": {"case": "thermal"}},
        source=Path("thermal.csv"),
    )

    restored = scientific_to_dataset(dataset_to_scientific(dataset))

    pd.testing.assert_frame_equal(restored.data, dataset.data)
    assert restored.metadata == dataset.metadata
    assert restored.source == dataset.source


def test_scientific_to_dataset_rejects_ambiguous_record_axes() -> None:
    value = ScientificDataset(_thermal_xarray())

    with pytest.raises(AmbiguousRecordAxisError, match="record dimension"):
        scientific_to_dataset(value)


def test_scientific_to_dataset_rejects_non_record_coordinates_as_lossy() -> None:
    value = ScientificDataset(_thermal_xarray())

    with pytest.raises(LossyConversionError, match="Coordinate"):
        scientific_to_dataset(value, record_dim="time")


def test_scientific_dataset_requires_json_compatible_metadata() -> None:
    with pytest.raises(TypeError, match="JSON"):
        ScientificDataset(xr.Dataset(), metadata={"not_json": object()})
