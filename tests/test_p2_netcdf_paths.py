"""A native NetCDF3 file must keep its meaning under a Unicode source path."""

import hashlib
import os
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from cpdatakit.application.data_access import inspect_input, load_value
from cpdatakit.exceptions import DataReadError
from cpdatakit.formats import ReadLimits, Selection
from cpdatakit.formats import netcdf as netcdf_module
from cpdatakit.jobs.manager import JobCancelled, JobContext


def _classic_bytes():
    root = netCDF4.Dataset("synthetic.nc", mode="w", memory=4096, format="NETCDF3_CLASSIC")
    root.createDimension("time", 2)
    time = root.createVariable("time", "f8", ("time",))
    time.units = "days since 2026-10-01"
    time.calendar = "standard"
    time[:] = [0, 1]
    value = root.createVariable("temperature", "f8", ("time",))
    value.units = "K"
    value[:] = [293.15, 294.25]
    root.title = "synthetic Unicode path acceptance"
    return bytes(root.close())


@pytest.mark.parametrize("directory", ["ascii path", "实验 中文"])
def test_native_netcdf3_unicode_path_preserves_values_and_dates(tmp_path, directory):
    folder = tmp_path / directory
    folder.mkdir()
    source = folder / "temperature.nc"
    original = _classic_bytes()
    source.write_bytes(original)
    value = load_value(source, selection=Selection(start=1, stop=2))
    assert value.source == source
    assert value.data["temperature"].values.tolist() == [294.25]
    assert (
        value.data["time"].values.tolist()
        == np.array(["2026-10-02"], dtype="datetime64[ns]").tolist()
    )
    assert value.data["temperature"].attrs["units"] == "K"
    assert value.data.attrs["title"] == "synthetic Unicode path acceptance"
    info = inspect_input(source, None, ReadLimits())
    assert info["record_count"] == 2
    assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(original).digest()


def test_unicode_source_is_bounded_before_backend_open(tmp_path):
    source = tmp_path / "数据.nc"
    source.write_bytes(_classic_bytes())
    with pytest.raises(DataReadError, match="byte limit"):
        load_value(source, limits=ReadLimits(max_bytes=1))
    assert source.read_bytes().startswith(b"CDF")


def test_invalid_unicode_netcdf_does_not_leave_new_files(tmp_path):
    source = tmp_path / "损坏.nc"
    source.write_bytes(b"CDF" + b"\x00" * 300)
    before = sorted(path.name for path in tmp_path.iterdir())
    with pytest.raises(DataReadError):
        load_value(source)
    assert sorted(path.name for path in tmp_path.iterdir()) == before


@pytest.mark.parametrize("outcome", ["success", "invalid", "cancel"])
def test_unicode_backend_snapshot_closes_and_cleans_up(tmp_path, monkeypatch, outcome):
    source = tmp_path / "原数据.nc"
    original = _classic_bytes() if outcome != "invalid" else b"CDF" + b"\x00" * 300
    source.write_bytes(original)
    directories = []
    create = netcdf_module.tempfile.TemporaryDirectory

    def track(*args, **kwargs):
        result = create(*args, **kwargs)
        directories.append(result.name)
        return result

    monkeypatch.setattr(netcdf_module.tempfile, "TemporaryDirectory", track)
    context = JobContext()
    context.on_progress = lambda _stage: context.set()
    if outcome == "success":
        assert load_value(source).data["temperature"].values.tolist() == [293.15, 294.25]
    elif outcome == "invalid":
        with pytest.raises(DataReadError):
            load_value(source)
    else:
        with pytest.raises(JobCancelled):
            load_value(source, context=context)
    if os.name == "nt":
        assert directories
    assert all(not os.path.exists(name) for name in directories)
    assert source.read_bytes() == original
    # A Windows handle leak would prevent rename even after the request ended.
    assert source.rename(tmp_path / "after.nc").read_bytes() == original


@pytest.mark.parametrize("context", [None, JobContext()])
def test_unicode_snapshot_encoding_points_to_original_source(tmp_path, context):
    source = tmp_path / "原数据.nc"
    source.write_bytes(_classic_bytes())
    value = load_value(source, context=context)
    assert value.source == source
    for encoding in [
        value.data.encoding,
        *(array.encoding for array in value.data.variables.values()),
    ]:
        if "source" in encoding:
            assert Path(encoding["source"]) == source
        assert "cpdatakit-netcdf-" not in str(encoding)
