from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cpdatakit.comparison import compare_reports, write_comparison_bundle
from cpdatakit.exceptions import CPDataKitError, OutputExistsError
from cpdatakit.schema import load_schema, schema_to_dict


def _field(name: str, *, unit: str = "MPa", shape: list[int] | None = None) -> dict[str, object]:
    return {
        "name": name,
        "dtype": "float64",
        "shape": [3] if shape is None else shape,
        "record_shape": [] if shape is None else shape[1:],
        "unit": unit,
        "missing_count": 0,
        "description": "Synthetic field",
        "chunks": None,
    }


def _report(
    *,
    schema: dict[str, object] | None = None,
    fields: list[dict[str, object]] | None = None,
    record_count: int = 3,
    stress_mean: float | str = 100.0,
    source_description: str = "Synthetic report",
) -> dict[str, object]:
    contract = schema or schema_to_dict(load_schema("curve"))
    report_fields = fields or [
        _field("step", unit="1"),
        _field("strain", unit="1"),
        _field("stress"),
    ]
    numeric_stress: object = (
        {"min": 0.0, "max": 180.0, "mean": stress_mean, "std": 10.0}
        if isinstance(stress_mean, (int, float))
        else stress_mean
    )
    return {
        "file": {"filename": "curve.h5", "format": "CPDataKit HDF5", "format_version": "1.0"},
        "schema": contract,
        "record_count": record_count,
        "fields": report_fields,
        "validation": {"valid": True, "errors": [], "warnings": []},
        "statistics": {
            "record_count": record_count,
            "numeric_fields": {"stress": numeric_stress},
        },
        "provenance": {
            "input_filename": r"C:\\private\\curve.h5",
            "source_description": source_description,
            "api_token": "secret-token",
        },
        "adapter": {},
        "hdf5": {},
        "scope_note": "Declared aggregates only.",
    }


def test_compare_reports_identical_result_is_stable() -> None:
    result = compare_reports(_report(), _report())

    assert result["format"] == "CPDataKit comparison 1.0"
    assert result["schema"]["classification"] == "identical"
    assert result["structure"] == {
        "fields_added": [],
        "fields_removed": [],
        "fields_changed": [],
    }
    assert result["statistics"] == {"changed": [], "unavailable": []}
    assert result["left"]["record_count"] == 3
    assert json.dumps(result, sort_keys=True, allow_nan=False) == json.dumps(
        result, sort_keys=True, allow_nan=False
    )


def test_compare_reports_captures_schema_structure_and_scalar_deltas() -> None:
    schema = schema_to_dict(load_schema("curve"))
    schema["fields"] = [*schema["fields"], {"name": "optional", "dtype": "float", "unit": "1"}]
    right = _report(
        schema=schema,
        fields=[*_report()["fields"], _field("optional", unit="1")],
        record_count=4,
        stress_mean=125.0,
    )

    result = compare_reports(_report(), right)

    assert result["schema"]["classification"] == "backward-compatible"
    assert result["structure"]["fields_added"] == ["optional"]
    assert {item["metric"] for item in result["statistics"]["changed"]} >= {
        "record_count",
        "mean",
    }
    mean_change = next(item for item in result["statistics"]["changed"] if item["metric"] == "mean")
    assert mean_change == {
        "field": "stress",
        "metric": "mean",
        "left": 100.0,
        "right": 125.0,
        "delta": 25.0,
    }


def test_compare_reports_keeps_shaped_values_unavailable_and_redacts_metadata() -> None:
    left = _report(source_description=r"password=super-secret C:\\private\\input.h5")
    right = _report(stress_mean="not available")

    result = compare_reports(left, right)
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert result["statistics"]["unavailable"]
    assert r"C:\\private" not in rendered
    assert "super-secret" not in rendered
    assert "secret-token" not in rendered


def test_render_comparison_markdown_lists_unavailable_statistics() -> None:
    from cpdatakit.comparison import render_comparison_markdown

    comparison = compare_reports(_report(), _report(stress_mean="not available"))

    rendered = render_comparison_markdown(comparison)

    assert "## Unavailable statistics" in rendered
    assert "stress" in rendered


def test_compare_reports_rejects_non_mapping_input() -> None:
    with pytest.raises(CPDataKitError, match="report"):
        compare_reports([], _report())  # type: ignore[arg-type]


def test_compare_reports_is_exported_from_package_root() -> None:
    import cpdatakit

    assert cpdatakit.compare_reports is compare_reports


def test_write_comparison_bundle_creates_hashed_offline_members(
    tmp_path: Path,
) -> None:
    comparison = compare_reports(_report(), _report(stress_mean=125.0))
    output = tmp_path / "bundle"

    result = write_comparison_bundle(comparison, output)

    assert result == output
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "comparison.json",
        "comparison.md",
        "comparison.html",
    }
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in manifest["members"]] == [
        "comparison.json",
        "comparison.md",
        "comparison.html",
    ]
    for item in manifest["members"]:
        payload = (output / item["name"]).read_bytes()
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()
    html = (output / "comparison.html").read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    assert "secret-token" not in html


def test_write_comparison_bundle_protects_existing_output_and_supports_force(
    tmp_path: Path,
) -> None:
    comparison = compare_reports(_report(), _report(stress_mean=125.0))
    output = tmp_path / "bundle"
    write_comparison_bundle(comparison, output)
    original = (output / "comparison.json").read_bytes()

    with pytest.raises(OutputExistsError):
        write_comparison_bundle(comparison, output)

    write_comparison_bundle(comparison, output, force=True)
    assert (output / "comparison.json").read_bytes() == original


def test_write_comparison_bundle_cleans_temporary_directory_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparison = compare_reports(_report(), _report(stress_mean=125.0))
    output = tmp_path / "bundle"
    original_write_bytes = Path.write_bytes

    def fail_on_markdown(path: Path, data: bytes) -> int:
        if path.name == "comparison.md":
            raise OSError("synthetic member failure")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_on_markdown)
    with pytest.raises(CPDataKitError, match="Cannot write comparison bundle"):
        write_comparison_bundle(comparison, output)

    assert not output.exists()
    assert list(tmp_path.glob(".bundle.*")) == []
