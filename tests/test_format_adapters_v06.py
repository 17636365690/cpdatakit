from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from cpdatakit.data import ScientificDataset
from cpdatakit.exceptions import DataReadError, DataValidationError
from cpdatakit.formats import (
    DatasetReader,
    DatasetWriter,
    NetCDFReader,
    NetCDFWriter,
    ParquetReader,
    ParquetWriter,
    ReadLimits,
    ZarrReader,
    ZarrWriter,
)
from cpdatakit.model import Dataset

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "tests" / "fixtures" / "schema-v2" / "composed.json"


def _scientific_value() -> ScientificDataset:
    return ScientificDataset(
        xr.Dataset(
            {"temperature": (("time", "y", "x"), np.arange(48).reshape(4, 3, 4))},
            coords={
                "time": ("time", [0.0, 10.0, 20.0, 30.0]),
                "y": ("y", [-1.0, 0.0, 1.0]),
                "x": ("x", [0.0, 1.0, 2.0, 3.0]),
                "stage": ("time", ["ambient", "heating", "hold", "cooling"]),
            },
        ),
        metadata={"units": {"temperature": "K"}},
    )


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_netcdf_adapter_round_trip_and_bounded_inspection(tmp_path: Path, engine: str) -> None:
    output = tmp_path / f"thermal-{engine}.nc"
    reader = NetCDFReader(engine=engine)
    writer = NetCDFWriter(engine=engine)
    value = _scientific_value()

    assert isinstance(reader, DatasetReader)
    assert isinstance(writer, DatasetWriter)
    assert writer.check(value).supported
    writer.write(value, output)
    loaded = reader.load(output)

    assert tuple(loaded.data.dims) == ("time", "y", "x")
    assert loaded.data["temperature"].shape == (4, 3, 4)
    assert loaded.data["stage"].values.tolist() == ["ambient", "heating", "hold", "cooling"]
    assert reader.inspect(output, limits=ReadLimits(max_records=4))["record_count"] == 4
    with pytest.raises(DataReadError, match="record"):
        reader.inspect(output, limits=ReadLimits(max_records=3))


def test_zarr_v3_adapter_round_trip_does_not_require_consolidated_metadata(tmp_path: Path) -> None:
    output = tmp_path / "thermal.zarr"
    writer = ZarrWriter()
    reader = ZarrReader()

    writer.write(_scientific_value(), output)
    loaded = reader.load(output)

    assert reader.detect(output).matched
    assert loaded.data["temperature"].shape == (4, 3, 4)
    assert loaded.data["stage"].values.tolist() == ["ambient", "heating", "hold", "cooling"]
    assert reader.inspect(output, limits=ReadLimits(max_records=4))["format"] == "Zarr 3"


def test_parquet_adapter_round_trip_stays_tabular(tmp_path: Path) -> None:
    output = tmp_path / "curve.parquet"
    dataset = Dataset(pd.DataFrame({"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]}))
    writer = ParquetWriter()
    reader = ParquetReader()

    writer.write(dataset, output)
    loaded = reader.load(output)

    assert reader.detect(output).matched
    assert isinstance(loaded, Dataset)
    assert loaded.data.to_dict(orient="records") == [
        {"step": 0, "strain": 0.0, "stress": 0.0},
        {"step": 1, "strain": 0.1, "stress": 10.0},
    ]
    assert reader.inspect(output, limits=ReadLimits(max_records=2))["record_count"] == 2


def test_parquet_writer_rejects_scientific_dataset_before_creating_output(tmp_path: Path) -> None:
    output = tmp_path / "thermal.parquet"
    writer = ParquetWriter()
    result = writer.check(_scientific_value())

    assert not result.supported
    assert any("N-dimensional" in message for message in result.messages)
    with pytest.raises(DataValidationError, match="N-dimensional"):
        writer.write(_scientific_value(), output)
    assert not output.exists()


def test_format_adapters_expose_explicit_engine_and_format_metadata() -> None:
    assert NetCDFReader(engine="h5netcdf").info.format_name == "NetCDF"
    assert NetCDFReader(engine="netcdf4").info.format_name == "NetCDF"
    assert ZarrReader().info.format_name == "Zarr 3"
    assert ParquetWriter().info.format_name == "Parquet"
