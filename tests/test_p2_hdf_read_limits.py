"""Regression evidence for pre-allocation bounds and single-pass HDF5 reports."""

import h5py
import numpy as np
import pandas as pd
import pytest

from cpdatakit.application.data_access import inspect_input, load_value
from cpdatakit.exceptions import DataReadError
from cpdatakit.formats import ReadLimits, Selection
from cpdatakit.inspection import inspect_dataset
from cpdatakit.io import _load_hdf5 as load_hdf5
from cpdatakit.io import write_hdf5
from cpdatakit.jobs.manager import JobCancelled, JobContext
from cpdatakit.model import Dataset
from cpdatakit.reporting import build_report
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset


def _native(path, rows=10_000):
    frame = pd.DataFrame(
        {
            "step": np.arange(rows),
            "strain": np.arange(rows) * 0.001,
            "stress": np.arange(rows) * 0.5,
            "user_extra": np.arange(rows),
        }
    )
    value = Dataset(frame, {"units": {"step": "1", "strain": "1", "stress": "MPa"}})
    schema = load_schema("curve")
    write_hdf5(value, path, schema, validate_dataset(value, schema))
    return value


def _count_reads(monkeypatch):
    reads = []
    original = h5py.Dataset.__getitem__

    def counted(self, key, *args, **kwargs):
        result = original(self, key, *args, **kwargs)
        reads.append((self.name, key, np.size(result)))
        return result

    monkeypatch.setattr(h5py.Dataset, "__getitem__", counted)
    return reads


def _v2(path, rows=10_000):
    import xarray as xr

    from cpdatakit.data import ScientificDataset
    from cpdatakit.io import write_hdf5_v2
    from cpdatakit.schemas import resolve_schema_v2

    schema = resolve_schema_v2(
        {
            "schema_version": "2.0",
            "profile": "bounded",
            "dimensions": [{"name": "row", "length": rows}],
            "coordinates": [{"name": "row", "dims": ["row"], "dtype": "integer", "unit": "1"}],
            "variables": [
                {
                    "name": "value",
                    "dims": ["row"],
                    "dtype": "float",
                    "unit": "K",
                    "role": "measured_field",
                }
            ],
        }
    )
    value = ScientificDataset(
        xr.Dataset(
            {"value": ("row", np.arange(rows, dtype=float), {"unit": "K"})},
            coords={"row": ("row", np.arange(rows), {"unit": "1"})},
        )
    )
    write_hdf5_v2(value, path, schema)


@pytest.mark.parametrize("v2", [False, True])
def test_record_limit_rejects_before_any_payload_read(tmp_path, monkeypatch, v2):
    path = tmp_path / "input.h5"
    (_v2 if v2 else _native)(path)
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="record limit"):
        inspect_input(path, None, ReadLimits(max_records=1, max_bytes=10_000_000))
    assert reads == []


@pytest.mark.parametrize("v2", [False, True])
def test_compressed_payload_rejected_before_allocation(tmp_path, monkeypatch, v2):
    path = tmp_path / "input.h5"
    (_v2 if v2 else _native)(path)
    compressed = tmp_path / "compressed.h5"
    with h5py.File(path, "r") as source, h5py.File(compressed, "w") as dest:
        dest.attrs.update(dict(source.attrs))
        for group_name in source:
            if group_name not in {"variables", "data", "coordinates"}:
                source.copy(group_name, dest)
                continue
            group = dest.create_group(group_name)
            for name, original in source[group_name].items():
                item = group.create_dataset(name, data=original[:], compression="gzip")
                item.attrs.update(dict(original.attrs))
    path = compressed
    reads = _count_reads(monkeypatch)
    budget = path.stat().st_size + 1
    assert budget < (160_000 if v2 else 320_000)
    with pytest.raises(DataReadError, match="byte limit"):
        load_value(path, limits=ReadLimits(max_records=10_000, max_bytes=budget))
    assert reads == []


@pytest.mark.parametrize("defect", ["shape", "dimension", "scalar"])
def test_v2_bad_later_field_rejected_before_first_payload(tmp_path, monkeypatch, defect):
    path = tmp_path / "input.h5"
    _v2(path)
    with h5py.File(path, "r+") as handle:
        attrs = dict(handle["variables/value"].attrs)
        if defect == "dimension":
            attrs["dims_json"] = '["absent"]'
        elif defect == "scalar":
            attrs["dims_json"] = "[]"
        item = handle["variables"].create_dataset("z_bad", data=np.arange(7))
        item.attrs.update(attrs)
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError):
        load_value(path, limits=ReadLimits(10_000, 10_000_000))
    assert reads == []


def test_v2_selected_100_rows_reads_only_subset(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    _v2(path)
    reads = _count_reads(monkeypatch)
    value = load_value(
        path,
        selection=Selection(fields=("value",), start=10, stop=110),
        limits=ReadLimits(10_000, 10_000_000),
    )
    assert value.data["value"].values.tolist() == list(range(10, 110))
    assert sum(size for _, _, size in reads) == 200


@pytest.mark.parametrize("operation", ["inspect", "report"])
def test_hdf5_complete_results_read_each_payload_once(tmp_path, monkeypatch, operation):
    path = tmp_path / "input.h5"
    _native(path, rows=23)
    reads = _count_reads(monkeypatch)
    result = (
        inspect_dataset(path, schema="curve")
        if operation == "inspect"
        else build_report(path, "curve")
    )
    assert result["record_count"] == 23
    assert sum(size for _, _, size in reads) == 23 * 4
    validation = result["schema"]["validation"] if operation == "inspect" else result["validation"]
    assert validation["valid"] is True


@pytest.mark.parametrize("v2", [False, True])
def test_hdf5_cancellation_during_read_and_recovery(tmp_path, monkeypatch, v2):
    path = tmp_path / "input.h5"
    (_v2 if v2 else _native)(path, rows=30_000)
    reads = _count_reads(monkeypatch)
    context = JobContext(lambda stage: context.set() if reads else None)
    with pytest.raises(JobCancelled):
        load_value(path, context=context)
    assert 0 < sum(size for _, _, size in reads) < (60_000 if v2 else 120_000)
    assert load_value(path) is not None


def test_report_cancel_does_not_publish(tmp_path):
    from cpdatakit.application import ReportRequest
    from cpdatakit.application import build_report as service_report

    path = tmp_path / "input.h5"
    _native(path)
    output = tmp_path / "report.json"
    context = JobContext()
    context.set()
    result = service_report(
        ReportRequest(data=path, schema="curve", output=output), context=context
    )
    assert not result.ok
    assert not output.exists()


@pytest.mark.parametrize("v2", [False, True])
def test_source_record_budget_is_not_bypassed_by_selection(tmp_path, monkeypatch, v2):
    path = tmp_path / "input.h5"
    (_v2 if v2 else _native)(path)
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="record limit"):
        if v2:
            load_value(
                path, selection=Selection(fields=("value",), stop=100), limits=ReadLimits(100)
            )
        else:
            load_hdf5(path, fields=("step",), stop=100, limits=ReadLimits(100))
    assert reads == []


def test_v1_selected_field_100_rows_have_bounded_payload(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    _native(path)
    reads = _count_reads(monkeypatch)
    value = load_hdf5(path, fields=("step",), start=5, stop=105, limits=ReadLimits(10_000))
    assert value.data["step"].tolist() == list(range(5, 105))
    assert sum(size for _, _, size in reads) == 100


def test_compound_dtype_estimate_accounts_for_all_fixed_fields(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    _native(path, rows=20)
    with h5py.File(path, "r+") as handle:
        del handle["data/user_extra"]
        handle["data"].create_dataset(
            "user_extra", shape=(20,), dtype=np.dtype([("a", "f8"), ("b", "f8", (100,))])
        )
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="byte limit"):
        load_hdf5(path, limits=ReadLimits(20, 1000))
    assert reads == []


def test_small_vlen_strings_remain_usable_under_default_limits(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    _native(path, rows=2)
    with h5py.File(path, "r+") as handle:
        del handle["data/user_extra"]
        handle["data"].create_dataset(
            "user_extra", data=["中文", "long text"], dtype=h5py.string_dtype()
        )
    reads = _count_reads(monkeypatch)
    assert load_hdf5(path, limits=ReadLimits()).data["user_extra"].tolist() == ["中文", "long text"]
    assert sum(size for _, _, size in reads) == 8
    assert load_hdf5(path).data["user_extra"].tolist() == ["中文", "long text"]


def test_native_report_reuses_values_without_weakening_global_validation(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    value = _native(path, rows=23)
    value.data.loc[22] = value.data.loc[0]
    schema = load_schema("curve")
    write_hdf5(value, path, schema, validate_dataset(value, schema), force=True, allow_invalid=True)
    monkeypatch.setattr("cpdatakit.inspection._INSPECTION_CHUNK_SIZE", 4)
    reads = _count_reads(monkeypatch)
    inspection = inspect_dataset(path, schema=schema)
    expected = validate_dataset(value, schema).to_dict()
    assert inspection["schema"]["validation"] == expected
    assert sum(size for _, _, size in reads) == 23 * 4
    reads.clear()
    report = build_report(path, schema)
    assert report["validation"] == expected
    assert sum(size for _, _, size in reads) == 23 * 4


@pytest.mark.parametrize("v2", [False, True])
def test_application_read_keeps_source_file_byte_limit(tmp_path, monkeypatch, v2):
    path = tmp_path / "input.h5"
    (_v2 if v2 else _native)(path, rows=2)
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="byte limit"):
        load_value(path, limits=ReadLimits(max_records=2, max_bytes=100))
    assert reads == []


@pytest.mark.parametrize("v2", [False, True])
def test_small_vlen_string_estimate_obeys_byte_budget_before_payload(tmp_path, monkeypatch, v2):
    path = tmp_path / "input.h5"
    (_v2 if v2 else _native)(path, rows=2)
    with h5py.File(path, "r+") as handle:
        group = handle["variables" if v2 else "data"]
        name = "value" if v2 else "user_extra"
        attrs = dict(group[name].attrs)
        del group[name]
        item = group.create_dataset(name, data=["中文", "long text"], dtype=h5py.string_dtype())
        item.attrs.update(attrs)
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="byte limit"):
        load_value(path, limits=ReadLimits(2, path.stat().st_size + 1))
    assert reads == []
    assert load_value(path, limits=ReadLimits()) is not None


def test_repeated_vlen_fillvalue_counts_every_materialized_string(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    _native(path, rows=2_000)
    with h5py.File(path, "r+") as handle:
        del handle["data/user_extra"]
        handle["data"].create_dataset(
            "user_extra",
            shape=(2_000,),
            dtype=h5py.string_dtype(),
            fillvalue="repeated string" * 100,
            compression="gzip",
        )
    assert path.stat().st_size < 1024 * 1024
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="byte limit"):
        inspect_input(path, None, ReadLimits(2_000, 1024 * 1024))
    assert reads == []


def test_numeric_vlen_is_still_rejected_with_explicit_memory_budget(tmp_path, monkeypatch):
    path = tmp_path / "input.h5"
    _native(path, rows=2)
    with h5py.File(path, "r+") as handle:
        del handle["data/user_extra"]
        array = handle["data"].create_dataset(
            "user_extra", shape=(2,), dtype=h5py.vlen_dtype(np.dtype("int64"))
        )
        array[0] = np.arange(2)
        array[1] = np.arange(3)
    reads = _count_reads(monkeypatch)
    with pytest.raises(DataReadError, match="variable-length"):
        load_value(path, limits=ReadLimits())
    assert reads == []
