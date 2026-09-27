"""Explicit read budgets protect loading real external-format files."""

import os
import subprocess

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from cpdatakit.application.data_access import load_value
from cpdatakit.exceptions import DataReadError
from cpdatakit.formats import NetCDFReader, ParquetReader, ReadLimits, Selection, ZarrReader


@pytest.fixture(params=["h5netcdf", "netcdf4", "zarr", "parquet"])
def external_input(tmp_path, request):
    backend = request.param
    values = np.arange(5, dtype=np.int64)
    dataset = xr.Dataset({"value": ("record", values)})
    if backend == "parquet":
        path = tmp_path / "data.parquet"
        pd.DataFrame({"value": values}).to_parquet(path)
        reader = ParquetReader()
    elif backend == "zarr":
        path = tmp_path / "data.zarr"
        dataset.to_zarr(path, zarr_format=3, consolidated=False)
        reader = ZarrReader()
    else:
        path = tmp_path / "data.nc"
        dataset.to_netcdf(path, engine=backend)
        reader = NetCDFReader(engine=backend)
    return path, reader


@pytest.mark.parametrize("entry", ["reader", "application"])
@pytest.mark.parametrize(
    "limits, label", [(ReadLimits(max_bytes=1), "byte"), (ReadLimits(max_records=2), "record")]
)
def test_over_limit_load_raises_data_read_error(external_input, entry, limits, label):
    path, reader = external_input
    loader = reader.load if entry == "reader" else load_value
    with pytest.raises(DataReadError, match=f"configured {label} limit"):
        loader(path, limits=limits)


def test_limits_none_and_sufficient_limits_preserve_selection(external_input):
    path, reader = external_input
    for limits in (None, ReadLimits(max_records=5)):
        value = reader.load(path, selection=Selection(start=1, stop=3), limits=limits)
        assert value.data["value"].values.tolist() == [1, 2]


def _directory_link(link, target):
    if os.name == "nt":
        # A real NTFS directory link is available without symlink privilege.
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=True,
        )
        assert link.is_junction()
    else:
        link.symlink_to(target, target_is_directory=True)
        assert link.is_symlink()


@pytest.mark.parametrize("limits", [None, ReadLimits()])
@pytest.mark.parametrize("root_link", [False, True])
def test_zarr_load_rejects_real_directory_links(tmp_path, limits, root_link):
    store = tmp_path / "data.zarr"
    xr.Dataset({"value": ("record", [1, 2])}).to_zarr(store, consolidated=False, zarr_format=3)
    if root_link:
        path = tmp_path / "alias.zarr"
        _directory_link(path, store)
    else:
        path = store
        outside = tmp_path / "outside"
        outside.mkdir()
        _directory_link(store / "linked", outside)
    if limits is None:
        assert ZarrReader().load(path).data["value"].values.tolist() == [1, 2]
    else:
        with pytest.raises(DataReadError, match=r"symbolic links|directory links"):
            ZarrReader().load(path, limits=limits)


@pytest.mark.parametrize("backend", ["h5netcdf", "zarr"])
@pytest.mark.parametrize("first", ["scalar", "other_axis"])
def test_record_limit_checks_selected_variables(tmp_path, backend, first):
    initial = xr.DataArray(1) if first == "scalar" else xr.DataArray([1], dims="short")
    data = xr.Dataset({first: initial, "records": ("record", [0, 1, 2, 3, 4])})
    path = tmp_path / ("values.zarr" if backend == "zarr" else "values.nc")
    if backend == "zarr":
        data.to_zarr(path, zarr_format=3, consolidated=False)
        reader = ZarrReader()
    else:
        data.to_netcdf(path, engine=backend)
        reader = NetCDFReader(engine=backend)
    with pytest.raises(DataReadError, match="record limit"):
        reader.load(
            path, selection=Selection(fields=("records",)), limits=ReadLimits(max_records=2)
        )
    with pytest.raises(DataReadError, match="record limit"):
        reader.load(path, limits=ReadLimits(max_records=2))
