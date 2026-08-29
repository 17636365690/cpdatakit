"""Convert the published Surfalex Workflow 7A result into CPDataKit HDF5."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from cpdatakit import (
    build_report,
    load_mapping_file,
    load_schema,
    normalize_dataset,
    validate_dataset,
)
from cpdatakit.exceptions import CPDataKitError, DataReadError, DataValidationError
from cpdatakit.io import write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.reporting import write_report

CASE_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = CASE_ROOT / "schema" / "cp-finite-strain.json"
MAPPING_PATH = CASE_ROOT / "mappings" / "workflow-7a.json"
SCHEMA_URI = (
    "https://github.com/17636365690/cpdatakit/blob/main/"
    "examples/public-datasets/surfalex-aa6016a/schema/cp-finite-strain.json"
)
_OUTPUT_NAMES = (
    "vol_avg_stress",
    "vol_avg_strain",
    "vol_avg_def_grad",
    "vol_avg_def_grad_plastic",
)


def _child(group: h5py.File | h5py.Group, name: str) -> h5py.File | h5py.Group | h5py.Dataset:
    candidates = (name, f"'{name}'") if not name.startswith("'") else (name, name[1:-1])
    for candidate in candidates:
        if candidate in group:
            return group[candidate]
    raise DataReadError(f"MatFlow output path is missing {name!r}")


def _descend(
    group: h5py.File | h5py.Group, names: tuple[str, ...]
) -> h5py.File | h5py.Group | h5py.Dataset:
    current: h5py.File | h5py.Group | h5py.Dataset = group
    for name in names:
        if not isinstance(current, (h5py.File, h5py.Group)):
            raise DataReadError(f"MatFlow output path cannot descend through {name!r}")
        current = _child(current, name)
    return current


def _numeric_dataset(node: object, *, name: str) -> np.ndarray:
    if not isinstance(node, h5py.Dataset):
        raise DataReadError(f"MatFlow output {name!r} is not a dataset")
    try:
        values = np.asarray(node[()])
    except (OSError, TypeError, ValueError) as exc:
        raise DataReadError(f"Cannot read MatFlow output {name!r}: {exc}") from exc
    if values.dtype.kind not in {"i", "u", "f"}:
        raise DataReadError(f"MatFlow output {name!r} is not a real numeric array")
    return values


def _output_values(output: h5py.Group, name: str) -> np.ndarray:
    node = _descend(output, ("data", "data", "data"))
    return _numeric_dataset(node, name=name)


def _output_increments(output: h5py.Group) -> np.ndarray:
    node = _descend(output, ("data", "meta", "data", "increments", "data"))
    increments = _numeric_dataset(node, name="increments")
    if increments.ndim != 1 or not len(increments):
        raise DataReadError("MatFlow increments must be a non-empty one-dimensional array")
    return increments


def extract_dataset(path: str | Path) -> Dataset:
    """Read the explicit Workflow 7A volume-output paths into a Dataset."""
    input_path = Path(path).expanduser()
    if not input_path.exists() or not input_path.is_file():
        raise DataReadError(f"Surfalex Workflow 7A input is not a file: {input_path}")

    try:
        with h5py.File(input_path, "r") as handle:
            response = _descend(
                handle,
                (
                    "element_data",
                    "0022_volume_element_response",
                    "data",
                    "volume_data",
                    "data",
                ),
            )
            if not isinstance(response, h5py.Group):
                raise DataReadError("Surfalex volume_data node is not a group")

            outputs: dict[str, h5py.Group] = {}
            values: dict[str, np.ndarray] = {}
            for name in _OUTPUT_NAMES:
                node = _child(response, name)
                if not isinstance(node, h5py.Group):
                    raise DataReadError(f"MatFlow output {name!r} is not a group")
                outputs[name] = node
                values[name] = _output_values(node, name)

            increments = _output_increments(outputs["vol_avg_stress"])
            record_count = len(increments)
            for name, output in outputs.items():
                array = values[name]
                if array.ndim != 3 or tuple(array.shape[1:]) != (3, 3):
                    raise DataReadError(
                        f"MatFlow output {name!r} has shape {array.shape}. "
                        f"Expected ({record_count}, 3, 3)"
                    )
                if array.shape[0] != record_count:
                    raise DataReadError(
                        f"MatFlow outputs have inconsistent record counts: {name!r}"
                    )
                output_increments = _output_increments(output)
                if not np.array_equal(output_increments, increments):
                    raise DataReadError(f"MatFlow outputs have inconsistent increments: {name!r}")
    except DataReadError:
        raise
    except (OSError, KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise DataReadError(f"Cannot read Surfalex Workflow 7A {input_path}: {exc}") from exc

    frame = pd.DataFrame(
        {
            "increment": increments.astype(np.int64, copy=False),
            **{name: list(values[name]) for name in _OUTPUT_NAMES},
        }
    )
    return Dataset(
        frame,
        {
            "units": {
                "increment": "1",
                "vol_avg_stress": "Pa",
                "vol_avg_strain": "1",
                "vol_avg_def_grad": "1",
                "vol_avg_def_grad_plastic": "1",
            }
        },
        input_path,
    )


def run(
    input_path: str | Path,
    output_path: str | Path,
    *,
    report_path: str | Path | None = None,
    force: bool = False,
) -> Path:
    """Extract, normalize, validate, and write the Workflow 7A reference artifact."""
    schema = load_schema(SCHEMA_PATH)
    mappings, drop_unmapped = load_mapping_file(MAPPING_PATH)
    raw = extract_dataset(input_path)
    normalized = normalize_dataset(raw, schema, mappings, drop_unmapped=drop_unmapped)
    validation = validate_dataset(normalized, schema)
    if not validation.valid:
        raise DataValidationError("Surfalex reference-case normalization failed validation")
    output = write_hdf5(
        normalized,
        output_path,
        schema,
        validation,
        schema_uri=SCHEMA_URI,
        source_description="Surfalex HF Workflow 7A. Zenodo 10.5281/zenodo.7307639",
        operation_log=[
            "source:zenodo:10.5281/zenodo.7307639",
            "extract:matflow:volume_data",
            "normalize:workflow-7a.json",
            "validate",
            "write:cpdatakit-hdf5",
        ],
        force=force,
    )
    if report_path is not None:
        report = build_report(output, schema)
        write_report(report, report_path, format="json", force=force)
    return output


def main(argv: list[str] | None = None) -> int:
    """Run the reference-case workflow from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        run(args.input, args.output, report_path=args.report, force=args.force)
    except CPDataKitError as exc:
        print(f"surfalex reference case: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
