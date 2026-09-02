from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cpdatakit.application import (
    ComparisonRequest,
    ReportRequest,
    ServiceResult,
    build_report,
    compare_reports,
)
from cpdatakit.reporting import render_report_json


def _write_curve(path: Path, *, invalid: bool = False, stress_offset: float = 0.0) -> Path:
    pd.DataFrame(
        {
            "step": [-1, 1, 2] if invalid else [0, 1, 2],
            "strain": [0.0, 0.01, 0.02],
            "stress": [0.0 + stress_offset, 100.0 + stress_offset, 180.0 + stress_offset],
        }
    ).to_csv(path, index=False)
    return path


def _write_json_report(path: Path, *, stress_offset: float = 0.0) -> Path:
    data = _write_curve(path.with_suffix(".csv"), stress_offset=stress_offset)
    from cpdatakit.reporting import build_report as build_core_report

    path.write_text(render_report_json(build_core_report(data, "curve")), encoding="utf-8")
    return path


def test_report_service_writes_a_typed_workspace_relative_artifact(tmp_path: Path) -> None:
    data = _write_curve(tmp_path / "curve.csv")
    output = tmp_path / "reports" / "curve.json"

    result = build_report(
        ReportRequest(data=data, schema="curve", output=output, format="json", workspace=tmp_path)
    )

    assert isinstance(result, ServiceResult)
    assert result.ok
    assert result.value is not None
    assert result.value.report["validation"]["valid"] is True
    assert result.artifact == "reports/curve.json"
    assert output.exists()
    assert str(tmp_path) not in json.dumps(result.to_dict())


def test_report_service_writes_invalid_findings_without_turning_them_into_service_errors(
    tmp_path: Path,
) -> None:
    data = _write_curve(tmp_path / "invalid.csv", invalid=True)
    output = tmp_path / "reports" / "invalid.md"

    result = build_report(
        ReportRequest(
            data=data,
            schema="curve",
            output=output,
            format="markdown",
            workspace=tmp_path,
        )
    )

    assert result.ok
    assert result.value is not None
    assert result.value.report["validation"]["valid"] is False
    assert result.value.artifact == "reports/invalid.md"
    assert output.read_text(encoding="utf-8").startswith("# CPDataKit Validation Report")


def test_report_service_preserves_existing_output_without_force(tmp_path: Path) -> None:
    data = _write_curve(tmp_path / "curve.csv")
    output = tmp_path / "report.json"
    request = ReportRequest(
        data=data, schema="curve", output=output, format="json", workspace=tmp_path
    )

    assert build_report(request).ok
    output.write_text("sentinel", encoding="utf-8")
    result = build_report(request)

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "output_exists"
    assert output.read_text(encoding="utf-8") == "sentinel"


def test_comparison_service_writes_the_complete_offline_bundle(tmp_path: Path) -> None:
    left = _write_json_report(tmp_path / "left.json")
    right = _write_json_report(tmp_path / "right.json", stress_offset=5.0)
    output = tmp_path / "comparisons" / "curve"

    result = compare_reports(
        ComparisonRequest(left=left, right=right, output=output, workspace=tmp_path)
    )

    assert result.ok
    assert result.value is not None
    assert result.value.comparison["format"] == "CPDataKit comparison 1.0"
    assert result.artifact == "comparisons/curve"
    assert (output / "manifest.json").exists()
    assert (output / "comparison.json").exists()
    assert (output / "comparison.md").exists()
    assert (output / "comparison.html").exists()
    assert str(tmp_path) not in json.dumps(result.to_dict())


def test_comparison_service_sanitizes_missing_report_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    result = compare_reports(
        ComparisonRequest(
            left=missing,
            right=missing,
            output=tmp_path / "comparison",
            workspace=tmp_path,
        )
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "data_read_error"
    assert str(tmp_path) not in result.error.message
