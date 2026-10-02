"""Reject implicit HDF5 dependencies before reading or registering input data."""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

import h5py
import httpx
import pytest
import xarray as xr

from cpdatakit.adapters import DamaskDADF5Adapter
from cpdatakit.application import ImportInspectRequest, import_and_inspect
from cpdatakit.data import ScientificDataset
from cpdatakit.exceptions import DataReadError
from cpdatakit.formats import NetCDFReader, ReadLimits, Selection
from cpdatakit.inspection import inspect_dataset
from cpdatakit.io import iter_hdf5_chunks, load_dataset, load_hdf5, load_hdf5_v2, write_hdf5_v2


def _native(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            format="CPDataKit",
            format_version="1.0",
            profile="curve",
            schema_version="1.0",
            units_json='{"step":"1"}',
            field_mapping_json="{}",
            provenance_json="{}",
            validation_summary_json='{"valid":true}',
        )
        handle.create_group("data").create_dataset("step", data=[0, 1])


def _scientific(path: Path) -> None:
    value = ScientificDataset(
        xr.Dataset({"signal": ("time", [2.0, 3.0])}, coords={"time": [0.0, 1.0]}),
        {"units": {"time": "s", "signal": "N"}},
    )
    schema = {
        "schema_version": "2.0",
        "profile": "synthetic-signal",
        "dimensions": [{"name": "time", "length": 2}],
        "coordinates": [{"name": "time", "dims": ["time"], "dtype": "float", "unit": "s"}],
        "variables": [
            {"name": "signal", "dims": ["time"], "dtype": "float", "unit": "N", "role": "measured"}
        ],
    }
    write_hdf5_v2(value, path, schema)


def _dadf5(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs["DADF5_version_major"] = 1
        handle.attrs["DADF5_version_minor"] = 1
        handle.create_group("geometry")
        handle.create_group("cell_to/homogenization").create_dataset("label", data=[0, 0])
        field = handle.create_group("increment_0/homogenization/Taylor/mechanical")
        dataset = field.create_dataset("signal", data=[2.0, 3.0])
        dataset.attrs["unit"] = "N"
        dataset.attrs["description"] = "Synthetic force"


def _dependency(path: Path, kind: str) -> Path:
    """Plant declarations; never read an external target in fixture validation."""
    target = path.parent / "external-target.h5"
    with h5py.File(target, "w") as external:
        external.create_dataset("payload", data=[41.0, 42.0])
        external.create_group("group").create_dataset("signal", data=[41.0, 42.0])
    with h5py.File(path, "a") as handle:
        group = handle.create_group("unselected/nested")
        if kind == "relative-link":
            group["dependency"] = h5py.ExternalLink(target.name, "/payload")
        elif kind == "absolute-link":
            group["dependency"] = h5py.ExternalLink(str(target), "/payload")
        elif kind == "group-link":
            group["dependency"] = h5py.ExternalLink(str(target), "/group")
        elif kind == "dangling-link":
            group["dependency"] = h5py.ExternalLink("missing-target.h5", "/payload")
        elif kind == "raw-storage":
            group.create_dataset(
                "dependency", shape=(2,), dtype="f8", external=[("missing.raw", 0, 16)]
            )
        elif kind == "virtual":
            layout = h5py.VirtualLayout(shape=(2,), dtype="f8")
            layout[:] = h5py.VirtualSource(str(target), "/payload", shape=(2,))
            group.create_virtual_dataset("dependency", layout)
        elif kind == "soft-link":
            group["dependency"] = h5py.SoftLink("/data/step")
        elif kind == "soft-cycle":
            group["dependency"] = h5py.SoftLink("/unselected/nested/dependency")
        else:
            raise AssertionError(kind)
    return target


DEPENDENCIES = (
    "relative-link",
    "absolute-link",
    "group-link",
    "dangling-link",
    "raw-storage",
    "virtual",
    "soft-link",
    "soft-cycle",
)


@pytest.mark.parametrize("dependency", DEPENDENCIES)
@pytest.mark.parametrize("reader", ["load", "selection", "chunks", "inspect", "dispatch"])
def test_native_readers_reject_dependencies_even_outside_selected_fields(
    tmp_path: Path, dependency: str, reader: str
) -> None:
    path = tmp_path / "input.h5"
    _native(path)
    target = _dependency(path, dependency)
    original = path.read_bytes()
    external = target.read_bytes()
    with pytest.raises(DataReadError, match="self-contained"):
        if reader == "load":
            load_hdf5(path)
        elif reader == "selection":
            load_hdf5(path, fields=["step"], start=0, stop=1)
        elif reader == "chunks":
            list(iter_hdf5_chunks(path, fields=["step"], chunk_size=1))
        elif reader == "inspect":
            inspect_dataset(path)
        else:
            load_dataset(path)
    assert path.read_bytes() == original
    assert target.read_bytes() == external
    assert not (tmp_path / "missing.raw").exists()


@pytest.mark.parametrize("dependency", DEPENDENCIES)
def test_scientific_selection_and_inspection_reject_hidden_dependencies(
    tmp_path: Path, dependency: str
) -> None:
    path = tmp_path / "input.h5"
    _scientific(path)
    _dependency(path, dependency)
    with pytest.raises(DataReadError, match="self-contained"):
        load_hdf5_v2(path, selection=Selection(fields=("signal",), start=0, stop=1))
    result = import_and_inspect(ImportInspectRequest(path))
    assert not result.ok
    assert "self-contained" in result.error.message


@pytest.mark.parametrize("dependency", DEPENDENCIES)
def test_damask_rejects_hidden_dependencies_before_loading_or_detecting(
    tmp_path: Path, dependency: str
) -> None:
    path = tmp_path / "input.h5"
    _dadf5(path)
    _dependency(path, dependency)
    with pytest.raises(DataReadError, match="self-contained"):
        DamaskDADF5Adapter(datasets=["signal"]).load(path)
    with pytest.raises(DataReadError, match="self-contained"):
        DamaskDADF5Adapter.detect(path)


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
@pytest.mark.parametrize("dependency", ["absolute-link", "raw-storage", "virtual"])
def test_netcdf_hdf5_backing_rejects_hidden_dependencies(
    tmp_path: Path, engine: str, dependency: str
) -> None:
    path = tmp_path / "input.nc"
    xr.Dataset({"signal": ("time", [2.0, 3.0])}).to_netcdf(path, engine=engine)
    _dependency(path, dependency)
    reader = NetCDFReader(engine=engine)
    with pytest.raises(DataReadError, match="self-contained"):
        reader.inspect(path, limits=ReadLimits())
    with pytest.raises(DataReadError, match="self-contained"):
        reader.load(path, selection=Selection(fields=("signal",)))


def test_classic_netcdf_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "classic.nc"
    xr.Dataset({"signal": ("time", [2.0, 3.0])}).to_netcdf(
        path, engine="netcdf4", format="NETCDF3_CLASSIC"
    )
    reader = NetCDFReader(engine="netcdf4")
    assert reader.inspect(path, limits=ReadLimits())["record_count"] == 2
    assert reader.load(path).data["signal"].values.tolist() == [2.0, 3.0]


def test_hardlink_aliases_and_group_cycles_preserve_normal_loading(tmp_path: Path) -> None:
    path = tmp_path / "hardlinks.h5"
    _native(path)
    with h5py.File(path, "a") as handle:
        group = handle.create_group("aliases")
        group["root"] = handle["/"]
        group["self"] = group
        group["step"] = handle["data/step"]
    assert load_hdf5(path).data["step"].tolist() == [0, 1]
    assert inspect_dataset(path)["record_count"] == 2


def test_dependency_rejected_before_any_dataset_payload_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.h5"
    _native(path)
    _dependency(path, "absolute-link")

    def forbid_read(*args, **kwargs):
        pytest.fail("Dataset payload was read before self-containment validation")

    monkeypatch.setattr(h5py.Dataset, "__getitem__", forbid_read)
    with pytest.raises(DataReadError, match="self-contained"):
        inspect_dataset(path)


def test_external_group_is_rejected_before_link_dereference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.h5"
    _native(path)
    target = _dependency(path, "group-link")
    with h5py.File(path, "a") as handle:
        del handle["data"]
        handle["data"] = h5py.ExternalLink(str(target), "/group")
    original_getitem = h5py.Group.__getitem__

    def forbid_external(group, name):
        if (
            isinstance(name, str)
            and name not in {"/", "."}
            and isinstance(group.get(name, getlink=True), h5py.ExternalLink)
        ):
            pytest.fail("An ExternalLink was dereferenced before validation")
        return original_getitem(group, name)

    monkeypatch.setattr(h5py.Group, "__getitem__", forbid_external)
    monkeypatch.setattr(h5py.File, "__getitem__", forbid_external)
    with pytest.raises(DataReadError, match="self-contained"):
        load_hdf5(path)


def test_external_target_changes_cannot_escape_the_input_hash_boundary(tmp_path: Path) -> None:
    path = tmp_path / "input.h5"
    _native(path)
    target = _dependency(path, "absolute-link")
    with h5py.File(path, "a") as handle:
        del handle["data/step"]
        handle["data/step"] = h5py.ExternalLink(str(target), "/payload")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for values in ([1, 2], [100, 200]):
        with h5py.File(target, "a") as external:
            external["payload"][:] = values
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        with pytest.raises(DataReadError, match="self-contained"):
            load_hdf5(path)


def test_rejected_upload_leaves_no_catalog_entry_or_staging_payload(tmp_path: Path) -> None:
    from cpdatakit.web import create_app

    path = tmp_path / "input.h5"
    _native(path)
    target = _dependency(path, "absolute-link")
    original_target = target.read_bytes()
    workspace = tmp_path / "workspace"
    app = create_app(workspace)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            home = await client.get("/")
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', home.text).group(1)
            headers = {"X-CSRF-Token": csrf}
            created = await client.post("/api/projects", headers=headers, data={"name": "safety"})
            project = created.json()
            response = await client.post(
                f"/api/projects/{project['id']}/inspect",
                headers=headers,
                data={"schema": "curve"},
                files={"file": ("input.h5", path.read_bytes(), "application/octet-stream")},
            )
            assert response.status_code == 400
            assert "self-contained" in response.json()["error"]["message"]
            uploads = workspace / "projects" / str(project["id"]) / "uploads"
            assert list(uploads.iterdir()) == []
            assert app.state.catalog.list_datasets(project["id"]) == ()

    asyncio.run(exercise())
    assert target.read_bytes() == original_target
