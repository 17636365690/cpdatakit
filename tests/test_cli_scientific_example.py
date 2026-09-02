from __future__ import annotations

import json
from pathlib import Path

from cpdatakit.cli import main
from cpdatakit.io import load_hdf5

EXAMPLE = Path(__file__).parents[1] / "examples" / "thermal-cycle"


def test_thermal_cycle_cli_end_to_end(tmp_path: Path) -> None:
    schema = EXAMPLE / "schema" / "thermal-cycle.json"
    data = EXAMPLE / "input" / "thermal-cycle.csv"
    mapping = EXAMPLE / "mappings" / "thermal-cycle.json"
    validation = tmp_path / "validation.json"
    summary = tmp_path / "summary.json"
    converted = tmp_path / "thermal-cycle.h5"
    inspection = tmp_path / "inspection.json"
    report_a = tmp_path / "report-a.json"
    report_b = tmp_path / "report-b.json"
    comparison = tmp_path / "comparison"
    plot = tmp_path / "temperature-vs-time.png"

    common = [str(data), "--schema", str(schema), "--mapping", str(mapping)]
    assert main(["validate", *common, "--json-output", str(validation)]) == 0
    assert main(["summary", *common, "--json-output", str(summary)]) == 0
    assert main(["convert", *common, "--output", str(converted)]) == 0
    assert (
        main(
            [
                "inspect",
                str(converted),
                "--schema",
                str(schema),
                "--format",
                "json",
                "--output",
                str(inspection),
            ]
        )
        == 0
    )
    for output in (report_a, report_b):
        assert (
            main(
                [
                    "report",
                    str(converted),
                    "--schema",
                    str(schema),
                    "--format",
                    "json",
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
    assert main(["compare", str(report_a), str(report_b), "--output", str(comparison)]) == 0
    assert (
        main(
            [
                "plot",
                str(converted),
                "--schema",
                str(schema),
                "--kind",
                "xy",
                "--x",
                "time",
                "--y",
                "temperature",
                "--output",
                str(plot),
            ]
        )
        == 0
    )

    loaded = load_hdf5(converted)
    assert loaded.metadata["profile"] == "thermal-cycle"
    assert loaded.metadata["schema_snapshot"]["schema"]["profile"] == "thermal-cycle"
    assert json.loads(validation.read_text(encoding="utf-8"))["valid"] is True
    assert "unique_grains" not in json.loads(summary.read_text(encoding="utf-8"))
    assert json.loads(inspection.read_text(encoding="utf-8"))["schema"]["profile"] == (
        "thermal-cycle"
    )
    assert (comparison / "manifest.json").exists()
    assert plot.stat().st_size > 100
