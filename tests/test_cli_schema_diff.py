from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpdatakit.cli import main


def _write_schema(path: Path, *, unit: str = "1", optional: bool = False) -> None:
    fields = [
        {
            "name": "value",
            "dtype": "float",
            "required": True,
            "unit": unit,
        }
    ]
    if optional:
        fields.append({"name": "optional", "dtype": "float", "unit": "1"})
    path.write_text(
        json.dumps({"profile": "point", "schema_version": "1.0", "fields": fields}),
        encoding="utf-8",
    )


def test_cli_schema_diff_writes_json_without_mutating_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    output = tmp_path / "diff.json"
    _write_schema(source)
    _write_schema(target, optional=True)
    source_before = source.read_text(encoding="utf-8")
    target_before = target.read_text(encoding="utf-8")

    status = main(
        [
            "schema",
            "diff",
            str(source),
            str(target),
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )

    assert status == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["classification"] == "backward-compatible"
    assert payload["fields"]["added"] == ["optional"]
    assert source.read_text(encoding="utf-8") == source_before
    assert target.read_text(encoding="utf-8") == target_before


def test_cli_schema_diff_reports_breaking_result_as_success(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    _write_schema(source)
    _write_schema(target, unit="MPa")

    assert main(["schema", "diff", str(source), str(target)]) == 0


def test_cli_schema_diff_protects_output_and_supports_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    output = tmp_path / "diff.md"
    _write_schema(source)
    _write_schema(target, optional=True)

    assert (
        main(
            [
                "schema",
                "diff",
                str(source),
                str(target),
                "--format",
                "markdown",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert "## Classification" in output.read_text(encoding="utf-8")
    output.write_text("sentinel", encoding="utf-8")

    assert (
        main(
            [
                "schema",
                "diff",
                str(source),
                str(target),
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
                "schema",
                "diff",
                str(source),
                str(target),
                "--format",
                "markdown",
                "--output",
                str(output),
                "--force",
            ]
        )
        == 0
    )
    assert "## Classification" in output.read_text(encoding="utf-8")
    capsys.readouterr()


def test_cli_schema_diff_returns_two_for_bad_schema(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "bad.json"
    _write_schema(source)
    target.write_text('{"profile":"point","schema_version":"2.0","fields":[]}', encoding="utf-8")

    assert main(["schema", "diff", str(source), str(target)]) == 2
