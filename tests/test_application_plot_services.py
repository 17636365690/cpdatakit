from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from cpdatakit.application import PlotRequest, ServiceResult, plot_declared_fields


@pytest.mark.parametrize(
    ("schema", "columns", "kind", "options"),
    [
        (
            "curve",
            {"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]},
            "stress-strain",
            {},
        ),
        (
            "curve",
            {"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]},
            "histogram",
            {"field": "stress"},
        ),
        (
            "curve",
            {"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]},
            "xy",
            {"x": "strain", "y": "stress"},
        ),
        (
            "point",
            {
                "point_id": [0, 1],
                "grain_id": [1, 2],
                "phase_id": [1, 1],
                "x": [0.0, 1.0],
                "y": [0.0, 1.0],
                "z": [0.0, 0.0],
            },
            "grain-count",
            {},
        ),
        (
            "point",
            {
                "point_id": [0, 1],
                "grain_id": [1, 2],
                "phase_id": [1, 1],
                "x": [0.0, 1.0],
                "y": [0.0, 1.0],
                "z": [0.0, 0.0],
            },
            "phase-count",
            {},
        ),
        (
            "field2d",
            {"x": [0.0, 1.0], "y": [0.0, 1.0], "value": [2.0, 3.0]},
            "field2d",
            {},
        ),
    ],
)
def test_plot_service_dispatches_declared_kinds_to_artifacts(
    tmp_path: Path,
    schema: str,
    columns: dict[str, list[float | int]],
    kind: str,
    options: dict[str, str],
) -> None:
    data = tmp_path / f"{kind}.csv"
    pd.DataFrame(columns).to_csv(data, index=False)
    output = tmp_path / "plots" / f"{kind}.png"

    result = plot_declared_fields(
        PlotRequest(
            data=data,
            schema=schema,
            output=output,
            kind=kind,
            workspace=tmp_path,
            **options,
        )
    )

    assert isinstance(result, ServiceResult)
    assert result.ok
    assert result.value is not None
    assert result.value.kind == kind
    assert result.artifact == f"plots/{kind}.png"
    assert output.stat().st_size > 100
    assert plt.get_fignums() == []


def test_plot_service_rejects_invalid_data_without_creating_an_artifact(tmp_path: Path) -> None:
    data = tmp_path / "invalid.csv"
    pd.DataFrame({"step": [-1, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]}).to_csv(
        data, index=False
    )
    output = tmp_path / "plots" / "invalid.png"

    result = plot_declared_fields(
        PlotRequest(
            data=data,
            schema="curve",
            output=output,
            kind="stress-strain",
            workspace=tmp_path,
        )
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "validation_failed"
    assert result.value is not None and not result.value.validation.valid
    assert not output.exists()
    assert plt.get_fignums() == []


def test_plot_service_returns_sanitized_capability_errors(tmp_path: Path) -> None:
    data = tmp_path / "curve.csv"
    pd.DataFrame({"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]}).to_csv(
        data, index=False
    )
    output = tmp_path / "plots" / "missing.png"

    result = plot_declared_fields(
        PlotRequest(
            data=data,
            schema="curve",
            output=output,
            kind="histogram",
            field="missing",
            workspace=tmp_path,
        )
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "cpdatakit_error"
    assert "Histogram field" in result.error.message
    assert str(tmp_path) not in json.dumps(result.to_dict())
    assert not output.exists()
    assert plt.get_fignums() == []


def test_plot_service_preserves_existing_output_without_force(tmp_path: Path) -> None:
    data = tmp_path / "curve.csv"
    pd.DataFrame({"step": [0, 1], "strain": [0.0, 0.1], "stress": [0.0, 10.0]}).to_csv(
        data, index=False
    )
    output = tmp_path / "plot.png"
    request = PlotRequest(
        data=data,
        schema="curve",
        output=output,
        kind="stress-strain",
        workspace=tmp_path,
    )

    assert plot_declared_fields(request).ok
    output.write_text("sentinel", encoding="utf-8")
    result = plot_declared_fields(request)

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "output_exists"
    assert output.read_text(encoding="utf-8") == "sentinel"
    assert plt.get_fignums() == []
