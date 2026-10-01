"""Exercise the first-use example with independently specified data and source bytes."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from cpdatakit.io import load_hdf5

EXAMPLE = Path(__file__).parents[1] / "examples/csv-intake"


def run_example(output, *arguments):
    return subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(EXAMPLE / "run_example.py"),
            "--output",
            str(output),
            *arguments,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def test_csv_first_use_example_preserves_declared_values_and_source(tmp_path):
    output = tmp_path / "example"
    result = run_example(output)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / "source.csv").read_bytes() == (EXAMPLE / "instrument.csv").read_bytes()
    dataset = load_hdf5(output / "data.h5")
    assert list(dataset.data) == [
        "time",
        "extension",
        "force",
        "reported_stress",
        "reported_strain",
    ]
    np.testing.assert_array_equal(dataset.data["time"], [0, 1, 2])
    np.testing.assert_allclose(dataset.data["force"], [0.1, 0.25, 0.375], rtol=0, atol=1e-15)
    assert dataset.metadata["units"] == {
        "time": "s",
        "extension": "mm",
        "force": "kN",
        "reported_stress": "MPa",
        "reported_strain": "dimensionless",
    }
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 3
    assert manifest["excluded_columns"] == [{"index": 3, "source_name": ""}]
    assert "synthetic" in manifest["confirmed_source_definition"].lower()
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["record_count"] == 3
    assert report["validation"]["valid"] is True


def test_csv_first_use_example_refuses_to_replace_existing_output(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"retain existing output")
    result = run_example(output)
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert sentinel.read_bytes() == b"retain existing output"
    assert list(output.iterdir()) == [sentinel]


@pytest.mark.parametrize("raw", [b"x;y\n1\n", b"x;y\n1;2\n"])
def test_csv_first_use_example_rejects_invalid_input_before_creating_output(tmp_path, raw):
    source = tmp_path / "bad.csv"
    source.write_bytes(raw)
    output = tmp_path / "rejected"
    result = run_example(output, "--input", str(source))
    assert result.returncode != 0
    assert "CSV" in result.stderr or "column" in result.stderr
    assert not output.exists()
    assert source.read_bytes() == raw
