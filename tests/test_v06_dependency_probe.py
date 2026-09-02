from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "probe_v06_dependencies.py"
CANDIDATES = ROOT / "scripts" / "v06-dependency-candidates.json"


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("probe_v06_dependencies", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load dependency probe: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dependency_probe_reports_candidates_and_environment() -> None:
    module = _load_probe_module()

    payload = module.probe_environment()

    assert payload["format"] == "CPDataKit v0.6 dependency probe 1.0"
    assert payload["python"]["major"] == 3
    assert payload["platform"]["system"]
    candidate_names = [
        item["name"] for item in json.loads(CANDIDATES.read_text(encoding="utf-8"))["packages"]
    ]
    assert list(payload["dependencies"]) == candidate_names
    for item in payload["dependencies"].values():
        assert isinstance(item["installed"], bool)
        assert "module" in item
        assert "distribution" in item
        assert "import_seconds" in item
        if item["installed"]:
            assert item["version"]
            assert len(item["license"] or "") <= 256
        else:
            assert item["error"]


def test_dependency_probe_writes_sorted_json_and_protects_existing_output(tmp_path: Path) -> None:
    module = _load_probe_module()
    output = tmp_path / "probe.json"
    payload = module.probe_environment()

    module.write_probe(payload, output)

    assert output.read_text(encoding="utf-8").endswith("\n")
    assert list(json.loads(output.read_text(encoding="utf-8"))) == sorted(payload)
    with pytest.raises(FileExistsError, match="already exists"):
        module.write_probe(payload, output)


def test_dependency_probe_cli_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "cli-probe.json"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["format"] == (
        "CPDataKit v0.6 dependency probe 1.0"
    )


def test_dependency_probe_reports_runtime_and_operation_contract() -> None:
    module = _load_probe_module()

    payload = module.probe_environment(candidate_set="lower")

    assert payload["candidate_set"] == "lower"
    assert payload["runtime"]["cpdatakit"]["module"] == "cpdatakit"
    assert set(payload["operations"]) == {
        "netcdf:h5netcdf",
        "netcdf:netcdf4",
        "zarr:v3",
        "parquet",
        "fastapi:httpx",
    }
    for operation in payload["operations"].values():
        assert operation["status"] in {"pass", "unavailable", "fail"}
        assert isinstance(operation["packages"], list)


def test_dependency_probe_fastapi_operation_exercises_bundled_cpdatakit_ui() -> None:
    module = _load_probe_module()

    payload = module.probe_environment(candidate_set="lower")
    operation = payload["operations"]["fastapi:httpx"]

    assert operation["status"] == "pass"
    assert operation["metrics"]["ui_home_status"] == 200
    assert operation["metrics"]["ui_static_statuses"] == [200, 200]
    assert operation["metrics"]["ui_has_external_asset"] is False
