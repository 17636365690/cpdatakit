from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from cpdatakit.cli import main
from cpdatakit.io import write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset


def _write_dadf5(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs["DADF5_version_major"] = 1
        handle.attrs["DADF5_version_minor"] = 1
        geometry = handle.create_group("geometry")
        geometry.attrs["cells"] = [2, 1, 1]
        geometry.attrs["size"] = [1.0, 1.0, 1.0]
        geometry.attrs["origin"] = [0.0, 0.0, 0.0]
        cell_to = handle.create_group("cell_to")
        for kind in ("phase", "homogenization"):
            cell_to.create_group(kind).create_dataset(
                "label", data=np.asarray(["label0", "label0"], dtype="S")
            )
        mechanical = (
            handle.create_group("increment_0")
            .create_group("homogenization")
            .create_group("Taylor")
            .create_group("mechanical")
        )
        field = mechanical.create_dataset("F", data=np.arange(18, dtype=float).reshape(2, 3, 3))
        field.attrs["unit"] = "1"
        field.attrs["description"] = "Synthetic deformation gradient"


def test_cli_inspect_json_writes_stable_output(tmp_path: Path) -> None:
    data = tmp_path / "curve.csv"
    data.write_text("step,strain,stress\n0,0.0,0.0\n1,0.1,10.0\n", encoding="utf-8")
    output = tmp_path / "inspect.json"

    status = main(
        [
            "inspect",
            str(data),
            "--schema",
            "curve",
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )

    assert status == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["file"]["format"] == "CSV"
    assert payload["schema"]["validation"]["valid"] is True


def test_cli_inspect_defaults_to_text_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "curve.csv"
    data.write_text("step,strain,stress\n0,0.0,0.0\n", encoding="utf-8")

    assert main(["inspect", str(data)]) == 0
    assert "CPDataKit inspection" in capsys.readouterr().out


def test_cli_report_html_and_markdown_write_offline_artifacts(tmp_path: Path) -> None:
    data = tmp_path / "curve.csv"
    data.write_text("step,strain,stress\n0,0.0,0.0\n1,0.1,10.0\n", encoding="utf-8")
    html = tmp_path / "report.html"
    markdown = tmp_path / "report.md"

    assert main(["report", str(data), "--schema", "curve", "--output", str(html)]) == 0
    assert (
        main(
            [
                "report",
                str(data),
                "--schema",
                "curve",
                "--format",
                "markdown",
                "--output",
                str(markdown),
            ]
        )
        == 0
    )
    html_text = html.read_text(encoding="utf-8")
    assert "<html" in html_text
    assert "<script" not in html_text.lower()
    assert markdown.read_text(encoding="utf-8").startswith("# CPDataKit Validation Report")


def test_cli_report_json_supports_native_hdf5(tmp_path: Path) -> None:
    dataset = Dataset(
        pd.DataFrame({"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]}),
        {"units": {"step": "1", "strain": "1", "stress": "MPa"}},
    )
    schema = load_schema("curve")
    input_path = tmp_path / "curve.h5"
    output = tmp_path / "report.json"
    write_hdf5(dataset, input_path, schema, validate_dataset(dataset, schema), hdf5_chunk_size=1)

    assert (
        main(
            [
                "report",
                str(input_path),
                "--schema",
                "curve",
                "--format",
                "json",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["hdf5"]["chunks"]["step"] == [1]
    assert report["validation"]["valid"] is True


def test_cli_report_handles_damask_dadf5_adapter(tmp_path: Path) -> None:
    input_path = tmp_path / "result.hdf5"
    output = tmp_path / "report.json"
    _write_dadf5(input_path)

    assert (
        main(
            [
                "report",
                str(input_path),
                "--schema",
                "point",
                "--format",
                "json",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["file"]["format"] == "DAMASK DADF5"
    assert report["adapter"]["name"] == "DamaskDADF5Adapter"


def test_cli_inspect_and_report_return_one_for_validation_errors(tmp_path: Path) -> None:
    data = tmp_path / "invalid.csv"
    data.write_text("step,strain,stress\n-1,0.0,1.0\n-1,0.0,1.0\n", encoding="utf-8")
    report = tmp_path / "invalid.html"

    assert main(["inspect", str(data), "--schema", "curve", "--format", "json"]) == 1
    assert main(["report", str(data), "--schema", "curve", "--output", str(report)]) == 1
    assert report.exists()
    assert "below_minimum" in report.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["inspect", "report"])
def test_cli_returns_two_for_missing_or_bad_input(
    tmp_path: Path, command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.csv"
    args = [command, str(missing)]
    if command == "inspect":
        args.extend(["--format", "json"])
    else:
        args.extend(["--schema", "curve", "--output", str(tmp_path / "report.html")])

    assert main(args) == 2
    assert str(missing) not in capsys.readouterr().err


def test_cli_returns_two_for_unknown_schema_and_empty_input(tmp_path: Path) -> None:
    data = tmp_path / "empty.csv"
    data.write_text("step,strain,stress\n", encoding="utf-8")

    assert main(["inspect", str(data), "--schema", "unknown"]) == 2
    assert (
        main(["report", str(data), "--schema", "curve", "--output", str(tmp_path / "x.html")]) == 2
    )


def test_cli_output_overwrite_requires_force(tmp_path: Path) -> None:
    data = tmp_path / "curve.csv"
    data.write_text("step,strain,stress\n0,0.0,0.0\n", encoding="utf-8")
    output = tmp_path / "report.md"
    assert (
        main(
            [
                "report",
                str(data),
                "--schema",
                "curve",
                "--format",
                "markdown",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    original = output.read_text(encoding="utf-8")
    output.write_text("sentinel", encoding="utf-8")

    assert (
        main(
            [
                "report",
                str(data),
                "--schema",
                "curve",
                "--format",
                "markdown",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert output.read_text(encoding="utf-8") == "sentinel"
    assert (
        main(
            [
                "report",
                str(data),
                "--schema",
                "curve",
                "--format",
                "markdown",
                "--output",
                str(output),
                "--force",
            ]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == original


def test_cli_inspect_output_overwrite_requires_force(tmp_path: Path) -> None:
    data = tmp_path / "curve.json"
    data.write_text(json.dumps([{"step": 0, "strain": 0.0, "stress": 0.0}]), encoding="utf-8")
    output = tmp_path / "inspect.json"
    assert main(["inspect", str(data), "--format", "json", "--output", str(output)]) == 0
    output.write_text("sentinel", encoding="utf-8")

    assert main(["inspect", str(data), "--format", "json", "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "sentinel"
    assert main(["inspect", str(data), "--format", "json", "--output", str(output), "--force"]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["file"]["format"] == "JSON"


def test_cli_returns_two_for_corrupt_hdf5(tmp_path: Path) -> None:
    input_path = tmp_path / "broken.h5"
    input_path.write_bytes(b"not hdf5")

    assert main(["inspect", str(input_path)]) == 2
