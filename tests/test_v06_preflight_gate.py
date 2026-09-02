from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "check_v06_preflight.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_v06_preflight", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load preflight gate: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v06_preflight_gate_accepts_complete_repository() -> None:
    gate = _load_gate()

    assert gate.check_preflight(ROOT) == []


def test_v06_preflight_gate_reports_missing_artifacts(tmp_path: Path) -> None:
    gate = _load_gate()

    failures = gate.check_preflight(tmp_path)

    assert failures
    assert any("v0.5-public-contract.json" in failure for failure in failures)
    assert any("v06-dependency-matrix.yml" in failure for failure in failures)
    assert any("test_application_services.py" in failure for failure in failures)
    assert any("test_application_report_services.py" in failure for failure in failures)
    assert any("test_application_plot_services.py" in failure for failure in failures)
    assert any("src/cpdatakit/data/scientific.py" in failure for failure in failures)


def test_v06_preflight_gate_reports_tampered_compatibility_snapshot(tmp_path: Path) -> None:
    gate = _load_gate()
    snapshot = tmp_path / "tests" / "compat" / "v0.5-public-contract.json"
    snapshot.parent.mkdir(parents=True)
    payload = json.loads(
        (ROOT / "tests" / "compat" / "v0.5-public-contract.json").read_text(encoding="utf-8")
    )
    payload["builtin_schema_hashes"]["curve"] = "0" * 64
    snapshot.write_text(json.dumps(payload), encoding="utf-8")

    failures = gate.check_preflight(tmp_path)

    assert any("compatibility snapshot" in failure for failure in failures)
