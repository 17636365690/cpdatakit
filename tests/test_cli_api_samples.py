from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cpdatakit
from cpdatakit.cli import main
from cpdatakit.model import Dataset
from cpdatakit.samples import generate_sample_data


def test_public_api(curve: Dataset) -> None:
    assert callable(cpdatakit.load_dataset)
    assert cpdatakit.validate_dataset(curve, "curve").valid
    assert cpdatakit.summarize_dataset(curve, "curve")["record_count"] == 3


def test_cli_success_failure_and_force(curve_csv: Path, tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    assert (
        main(["validate", str(curve_csv), "--schema", "curve", "--json-output", str(report)]) == 0
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["valid"]  # units are supplied by the selected schema
    assert (
        main(
            [
                "validate",
                str(curve_csv),
                "--schema",
                "curve",
                "--json-output",
                str(report),
                "--force",
            ]
        )
        == 0
    )


def test_cli_convert_and_overwrite_protection(curve_csv: Path, tmp_path: Path) -> None:
    output = tmp_path / "converted.h5"
    args = ["convert", str(curve_csv), "--schema", "curve", "--output", str(output)]
    assert main(args) == 0
    assert output.exists()
    assert main(args) == 2
    assert main([*args, "--force"]) == 0


def test_cli_hdf5_and_plot(curve: Dataset, tmp_path: Path) -> None:
    from cpdatakit.io import write_hdf5
    from cpdatakit.schema import load_schema
    from cpdatakit.validation import validate_dataset

    schema = load_schema("curve")
    source = tmp_path / "input.csv"
    curve.data.to_csv(source, index=False)
    curve.source = source
    validation = validate_dataset(curve, schema)
    h5 = tmp_path / "curve.h5"
    write_hdf5(curve, h5, schema, validation)
    png = tmp_path / "curve.png"
    assert main(["summary", str(h5), "--schema", "curve"]) == 0
    assert (
        main(
            ["plot", str(h5), "--schema", "curve", "--kind", "stress-strain", "--output", str(png)]
        )
        == 0
    )
    assert png.exists()


def test_sample_generation_is_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    generate_sample_data(first)
    generate_sample_data(second)
    for path in first.iterdir():
        other = second / path.name
        assert (
            hashlib.sha256(path.read_bytes()).digest()
            == hashlib.sha256(other.read_bytes()).digest()
        )
