from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "run_v06_dependency_matrix.py"
WORKFLOW = ROOT / ".github" / "workflows" / "v06-dependency-matrix.yml"


def _load_matrix_module():
    spec = importlib.util.spec_from_file_location("run_v06_dependency_matrix", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load dependency matrix runner: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dependency_matrix_builds_deterministic_lower_and_latest_requirements() -> None:
    module = _load_matrix_module()

    lower = module.requirements_for("lower")
    latest = module.requirements_for("latest")

    assert lower[0] == "numpy>=2.0,<3"
    assert "h5py>=3.8,<4" in lower
    assert latest[0] == "numpy"
    assert "python-multipart" in latest
    assert lower != latest
    with pytest.raises(ValueError, match="candidate set"):
        module.requirements_for("unsupported")


def test_dependency_matrix_install_command_requires_binary_wheels() -> None:
    module = _load_matrix_module()

    command = module.install_command("lower")

    assert "--only-binary=:all:" in command
    assert "numpy>=2.0,<3" in command
    assert command[-2:] == ["-e", "."]


def test_dependency_matrix_wheel_report_excludes_editable_project_install() -> None:
    module = _load_matrix_module()

    report = {
        "install": [
            {
                "metadata": {"name": "cpdatakit"},
                "download_info": {"url": "file:///workspace/cpdatakit"},
            },
            {
                "metadata": {"name": "numpy"},
                "download_info": {"url": "https://files.example/numpy.whl"},
            },
        ]
    }

    assert module.wheel_availability(report, ("numpy",)) == {"numpy": True}


def test_dependency_matrix_workflow_covers_supported_platform_matrix() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "ubuntu-latest" in text
    assert "macos-latest" in text
    assert "windows-latest" in text
    assert 'python-version: ["3.12", "3.13"]' in text
    assert "dependency-set: [lower, latest]" in text
    assert "scripts/run_v06_dependency_matrix.py" in text
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in text
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in text
