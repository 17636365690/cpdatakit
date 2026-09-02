"""Install and run one v0.6 dependency matrix cell in an isolated environment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

_CANDIDATES = Path(__file__).with_name("v06-dependency-candidates.json")
_SETS = {"lower", "latest"}


def _read_candidates(path: Path = _CANDIDATES) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("packages"), list):
        raise ValueError("Dependency candidates must contain a packages list")
    return payload


def requirements_for(candidate_set: str, candidates: Path = _CANDIDATES) -> list[str]:
    """Return deterministic pip requirements for one named candidate set."""
    if candidate_set not in _SETS:
        raise ValueError("candidate set must be 'lower' or 'latest'")
    payload = _read_candidates(candidates)
    requirements = []
    for item in payload["packages"]:
        requirement = item[candidate_set]
        requirements.append(
            item["distribution"]
            if requirement == "latest"
            else f"{item['distribution']}{requirement}"
        )
    return requirements


def install_command(
    candidate_set: str,
    *,
    python_executable: str | Path | None = None,
    root: str | Path = ".",
    report: str | Path | None = None,
) -> list[str]:
    """Build a wheel-only pip command for one isolated matrix cell."""
    executable = str(python_executable or sys.executable)
    command = [
        executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--only-binary=:all:",
    ]
    if report is not None:
        command.extend(["--report", str(report)])
    command.extend([*requirements_for(candidate_set), "-e", str(root)])
    return command


def _venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _normalise_distribution_name(value: str) -> str:
    return value.replace("-", "_").replace(".", "_").lower()


def wheel_availability(
    report: dict[str, Any], distributions: tuple[str, ...] | None = None
) -> dict[str, bool]:
    """Return wheel availability for selected distributions in a pip report."""
    expected = (
        {_normalise_distribution_name(name): name for name in distributions}
        if distributions is not None
        else None
    )
    result: dict[str, bool] = {}
    for item in report.get("install", []):
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        url = item.get("download_info", {}).get("url", "")
        if isinstance(name, str):
            normalised = _normalise_distribution_name(name)
            if expected is not None and normalised not in expected:
                continue
            output_name = expected.get(normalised, name) if expected is not None else name
            result[output_name] = isinstance(url, str) and url.split("?", 1)[0].lower().endswith(
                ".whl"
            )
    return dict(sorted(result.items()))


def _write_report(payload: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return output


def run_matrix_cell(
    candidate_set: str,
    *,
    root: Path,
    output: Path,
    python_executable: str | Path | None = None,
) -> Path:
    """Create an isolated venv, install candidates, and persist its probe report."""
    if output.exists():
        raise FileExistsError(f"Matrix output already exists: {output}")
    with tempfile.TemporaryDirectory(prefix="cpdatakit-v06-matrix-") as directory:
        environment = Path(directory) / "venv"
        builder = venv.EnvBuilder(with_pip=True, clear=True)
        builder.create(environment)
        executable = _venv_python(environment)
        pip_report = Path(directory) / "pip-report.json"
        command = install_command(
            candidate_set,
            python_executable=executable,
            root=root,
            report=pip_report,
        )
        subprocess.run(command, cwd=root, check=True)
        probe_output = Path(directory) / "probe.json"
        subprocess.run(
            [
                str(executable),
                str(root / "scripts" / "probe_v06_dependencies.py"),
                "--candidate-set",
                candidate_set,
                "--operations",
                "--output",
                str(probe_output),
            ],
            cwd=root,
            check=True,
        )
        payload = json.loads(probe_output.read_text(encoding="utf-8"))
        pip_payload = json.loads(pip_report.read_text(encoding="utf-8"))
        candidate_distributions = tuple(
            item["distribution"] for item in _read_candidates()["packages"]
        )
        payload["matrix"] = {
            "candidate_set": candidate_set,
            "wheel_only_install": True,
            "wheel_availability": wheel_availability(pip_payload, candidate_distributions),
            "requirements": requirements_for(candidate_set),
        }
        return _write_report(payload, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a CPDataKit v0.6 dependency matrix cell")
    parser.add_argument("--candidate-set", choices=sorted(_SETS), required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(
        run_matrix_cell(
            args.candidate_set,
            root=args.root,
            output=args.output,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
