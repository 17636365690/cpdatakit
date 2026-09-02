from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "generate_hdf5_v2_fixtures.py"
MANIFEST = ROOT / "tests" / "fixtures" / "hdf5-v2" / "manifest.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_hdf5_v2_fixtures", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load HDF5 v2 generator: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*.h5"))
    }


def test_hdf5_v2_generator_is_deterministic_and_matches_manifest(tmp_path: Path) -> None:
    generator = _load_generator()
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first = tmp_path / "first"
    second = tmp_path / "second"

    generator.generate_fixtures(first)
    generator.generate_fixtures(second)

    assert _hashes(first) == _hashes(second)
    assert sorted(_hashes(first)) == expected["files"]


def test_hdf5_v2_valid_fixture_has_declared_groups_and_shapes(tmp_path: Path) -> None:
    generator = _load_generator()
    output = tmp_path / "fixtures"
    generator.generate_fixtures(output)

    with h5py.File(output / "valid.h5", "r") as handle:
        assert handle.attrs["format"] == "CPDataKit"
        assert handle.attrs["format_version"] == "2.0"
        assert sorted(handle["dimensions"]) == ["time", "x", "y"]
        assert sorted(handle["coordinates"]) == ["stage", "time", "x", "y"]
        assert handle["variables"]["temperature"].shape == (4, 3, 4)
        assert json.loads(handle["variables"]["temperature"].attrs["dims_json"]) == [
            "time",
            "y",
            "x",
        ]


def test_hdf5_v2_malformed_fixtures_expose_named_failures(tmp_path: Path) -> None:
    generator = _load_generator()
    output = tmp_path / "fixtures"
    generator.generate_fixtures(output)

    with h5py.File(output / "missing-dimension-reference.h5", "r") as handle:
        dims = json.loads(handle["variables"]["temperature"].attrs["dims_json"])
        assert "missing" in dims
    with h5py.File(output / "root-version-mismatch.h5", "r") as handle:
        assert handle.attrs["format_version"] == "1.0"
    with h5py.File(output / "schema-hash-mismatch.h5", "r") as handle:
        assert handle.attrs["schema_sha256"] == "0" * 64
