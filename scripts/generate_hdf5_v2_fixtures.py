"""Generate deterministic HDF5 2.0 protocol fixtures for the v0.6 preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_SCHEMA = {
    "profile": "thermal-field",
    "schema_version": "2.0",
    "source_manifest": ["base.json", "fragment-space.json", "fragment-temperature.json"],
    "resolved_order": ["time", "y", "x", "stage", "temperature"],
}
_DIMENSIONS = {"time": 4, "y": 3, "x": 4}
_TEMPERATURE = np.asarray(
    [
        [
            [273.15, 274.15, 275.15, 276.15],
            [275.15, 276.15, 277.15, 278.15],
            [277.15, 278.15, 279.15, 280.15],
        ],
        [
            [283.15, 284.15, 285.15, 286.15],
            [285.15, 286.15, 287.15, 288.15],
            [287.15, 288.15, 289.15, 290.15],
        ],
        [
            [293.15, 294.15, 295.15, 296.15],
            [295.15, 296.15, 297.15, 298.15],
            [297.15, 298.15, 299.15, 300.15],
        ],
        [
            [303.15, 304.15, 305.15, 306.15],
            [305.15, 306.15, 307.15, 308.15],
            [307.15, 308.15, 309.15, 310.15],
        ],
    ],
    dtype=np.float64,
)


def _schema_json() -> str:
    return json.dumps(_SCHEMA, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_fixture(path: Path, *, mutation: str | None = None) -> None:
    with h5py.File(path, "w", libver="earliest") as handle:
        handle.attrs["format"] = "CPDataKit"
        handle.attrs["format_version"] = "1.0" if mutation == "root-version" else "2.0"
        handle.attrs["profile"] = "thermal-field"
        handle.attrs["schema_version"] = "2.0"
        handle.attrs["schema_json"] = _schema_json()
        handle.attrs["schema_sha256"] = (
            "0" * 64
            if mutation == "schema-hash"
            else hashlib.sha256(_schema_json().encode()).hexdigest()
        )
        handle.attrs["units_json"] = json.dumps(
            {"stage": None, "temperature": "K", "time": "s", "x": "mm", "y": "mm"},
            sort_keys=True,
        )
        handle.attrs["provenance_json"] = json.dumps(
            {"source_description": "v0.6 preflight fixture"}, sort_keys=True
        )
        handle.attrs["validation_summary_json"] = json.dumps(
            {"valid": True, "error_count": 0, "warning_count": 0}, sort_keys=True
        )
        dimensions = handle.create_group("dimensions")
        for name, length in _DIMENSIONS.items():
            group = dimensions.create_group(name)
            group.attrs["length"] = length
        coordinates = handle.create_group("coordinates")
        coordinate_values: dict[str, Any] = {
            "time": np.asarray([0.0, 10.0, 20.0, 30.0]),
            "y": np.asarray([-1.0, 0.0, 1.0]),
            "x": np.asarray([0.0, 1.0, 2.0, 3.0]),
            "stage": np.asarray(
                ["ambient", "heating", "hold", "cooling"], dtype=h5py.string_dtype()
            ),
        }
        coordinate_dims = {"time": ["time"], "y": ["y"], "x": ["x"], "stage": ["time"]}
        coordinate_units = {"time": "s", "y": "mm", "x": "mm", "stage": None}
        for name, values in coordinate_values.items():
            dataset = coordinates.create_dataset(name, data=values)
            dataset.attrs["dims_json"] = json.dumps(coordinate_dims[name], separators=(",", ":"))
            dataset.attrs["unit"] = coordinate_units[name] or ""
        variables = handle.create_group("variables")
        temperature = variables.create_dataset("temperature", data=_TEMPERATURE)
        temperature.attrs["dims_json"] = json.dumps(["time", "y", "x"], separators=(",", ":"))
        temperature.attrs["unit"] = "K"
        temperature.attrs["role"] = "measured_field"
        if mutation == "missing-dimension":
            temperature.attrs["dims_json"] = json.dumps(
                ["time", "missing", "x"], separators=(",", ":")
            )


def generate_fixtures(output: Path) -> Path:
    """Create valid and malformed HDF5 2.0 fixtures in a new directory."""
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Fixture output already exists and is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    _write_fixture(output / "valid.h5")
    _write_fixture(output / "missing-dimension-reference.h5", mutation="missing-dimension")
    _write_fixture(output / "root-version-mismatch.h5", mutation="root-version")
    _write_fixture(output / "schema-hash-mismatch.h5", mutation="schema-hash")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate HDF5 2.0 preflight fixtures")
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    print(generate_fixtures(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
