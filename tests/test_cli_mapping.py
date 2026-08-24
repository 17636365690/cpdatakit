from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cpdatakit.cli import main
from cpdatakit.io import load_dataset


def _write_input_and_mapping(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "export.csv"
    pd.DataFrame(
        {
            "increment": [0, 1],
            "eps": [0.0, 0.1],
            "sigma_pa": [0.0, 1_000_000.0],
            "raw_note": ["a", "b"],
        }
    ).to_csv(data, index=False)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "source": "increment",
                        "target": "step",
                        "input_unit": "1",
                        "output_unit": "dimensionless",
                    },
                    {
                        "source": "eps",
                        "target": "strain",
                        "input_unit": "1",
                        "output_unit": "dimensionless",
                    },
                    {
                        "source": "sigma_pa",
                        "target": "stress",
                        "input_unit": "Pa",
                        "output_unit": "MPa",
                    },
                ],
                "drop_unmapped": True,
            }
        ),
        encoding="utf-8",
    )
    return data, mapping


def test_cli_mapping_file_normalizes_and_records_mapping(tmp_path: Path) -> None:
    data, mapping = _write_input_and_mapping(tmp_path)
    report = tmp_path / "report.json"
    assert (
        main(
            [
                "validate",
                str(data),
                "--schema",
                "curve",
                "--mapping",
                str(mapping),
                "--json-output",
                str(report),
            ]
        )
        == 0
    )
    assert json.loads(report.read_text(encoding="utf-8"))["valid"]

    output = tmp_path / "converted.h5"
    assert (
        main(
            [
                "convert",
                str(data),
                "--schema",
                "curve",
                "--mapping",
                str(mapping),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    loaded = load_dataset(output)
    assert list(loaded.data.columns) == ["step", "strain", "stress"]
    assert loaded.data["stress"].tolist() == [0.0, 1.0]
    assert loaded.metadata["field_mapping"]["sigma_pa"]["target"] == "stress"


def test_cli_rejects_unknown_mapping_keys(tmp_path: Path, capsys) -> None:
    data, _ = _write_input_and_mapping(tmp_path)
    mapping = tmp_path / "bad-mapping.json"
    mapping.write_text(
        '{"mappings":[{"source":"increment","target":"step","infer":true}]}',
        encoding="utf-8",
    )
    assert main(["validate", str(data), "--schema", "curve", "--mapping", str(mapping)]) == 2
    assert "unsupported keys" in capsys.readouterr().err
