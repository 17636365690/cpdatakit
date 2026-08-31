from __future__ import annotations

import json
from pathlib import Path

from cpdatakit.cli import main
from cpdatakit.schema import load_schema, schema_to_dict


def _report(*, valid: bool = True, raw_value: str = "Synthetic report") -> dict[str, object]:
    schema = schema_to_dict(load_schema("curve"))
    return {
        "file": {"filename": "curve.h5", "format": "CPDataKit HDF5", "format_version": "1.0"},
        "schema": schema,
        "record_count": 3,
        "fields": [
            {"name": "step", "dtype": "int64", "shape": [3], "unit": "1"},
            {"name": "strain", "dtype": "float64", "shape": [3], "unit": "1"},
            {"name": "stress", "dtype": "float64", "shape": [3], "unit": "MPa"},
        ],
        "validation": {
            "valid": valid,
            "errors": [] if valid else [{"code": "invalid", "message": raw_value}],
            "warnings": [{"code": "warning", "message": raw_value}],
        },
        "statistics": {
            "record_count": 3,
            "numeric_fields": {"stress": {"min": 0.0, "max": 180.0, "mean": 100.0, "std": 10.0}},
        },
        "provenance": {
            "input_filename": r"C:\\private\\input.h5",
            "source_description": "password=super-secret",
        },
        "adapter": {},
        "hdf5": {},
    }


def _write_report(path: Path, *, valid: bool = True, raw_value: str = "Synthetic report") -> None:
    path.write_text(json.dumps(_report(valid=valid, raw_value=raw_value)), encoding="utf-8")


def test_cli_compare_writes_offline_bundle(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    output = tmp_path / "comparison"
    _write_report(left)
    _write_report(right, raw_value="right report")

    status = main(["compare", str(left), str(right), "--output", str(output)])

    assert status == 0
    assert (output / "manifest.json").exists()
    assert (output / "comparison.json").exists()
    assert (output / "comparison.md").exists()
    assert (output / "comparison.html").exists()
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert "super-secret" not in rendered
    assert r"C:\\private" not in rendered


def test_cli_compare_keeps_validation_findings_as_content(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    output = tmp_path / "comparison"
    _write_report(left, valid=False, raw_value="left finding")
    _write_report(right, raw_value="right warning")

    assert main(["compare", str(left), str(right), "--output", str(output)]) == 0
    comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    assert comparison["validation"]["left"]["errors"]
    assert comparison["validation"]["right"]["warnings"]


def test_cli_compare_protects_output_and_supports_force(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    output = tmp_path / "comparison"
    _write_report(left)
    _write_report(right)

    assert main(["compare", str(left), str(right), "--output", str(output)]) == 0
    (output / "sentinel.txt").write_text("sentinel", encoding="utf-8")
    assert main(["compare", str(left), str(right), "--output", str(output)]) == 2
    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "sentinel"
    assert main(["compare", str(left), str(right), "--output", str(output), "--force"]) == 0
    assert not (output / "sentinel.txt").exists()


def test_cli_compare_returns_two_for_invalid_json(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    output = tmp_path / "comparison"
    left.write_text("{", encoding="utf-8")
    _write_report(right)

    assert main(["compare", str(left), str(right), "--output", str(output)]) == 2
