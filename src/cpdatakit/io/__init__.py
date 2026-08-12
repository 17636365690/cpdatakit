"""CSV, JSON records, and CPDataKit HDF5 I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd

from ..exceptions import DataReadError, OutputExistsError
from ..model import Dataset, ValidationResult
from ..provenance import build_provenance
from ..schema import ProfileSchema

_SUPPORTED = {".csv", ".json", ".h5", ".hdf5"}


def _ensure_readable(path: Path) -> None:
    if not path.exists():
        raise DataReadError(f"Input path does not exist: {path}")
    if not path.is_file():
        raise DataReadError(f"Input path is not a file: {path}")
    if path.stat().st_size == 0:
        raise DataReadError(f"Input file is empty: {path}")
    if path.suffix.lower() not in _SUPPORTED:
        raise DataReadError(
            f"Unsupported extension {path.suffix!r}; supported: {', '.join(sorted(_SUPPORTED))}"
        )


def _read_hdf5(path: Path) -> Dataset:
    try:
        with h5py.File(path, "r") as handle:
            if handle.attrs.get("format") != "CPDataKit":
                raise DataReadError("HDF5 is not a CPDataKit file (missing format marker)")
            if "data" not in handle or not isinstance(handle["data"], h5py.Group):
                raise DataReadError("CPDataKit HDF5 is missing the /data group")
            columns: dict[str, Any] = {}
            for name, item in handle["data"].items():
                if not isinstance(item, h5py.Dataset):
                    continue
                values = item[()]
                if values.dtype.kind in {"S", "O"}:
                    values = np.asarray(
                        [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]
                    )
                columns[name] = list(values) if values.ndim > 1 else values
            metadata = {
                "profile": str(handle.attrs.get("profile", "")),
                "schema_version": str(handle.attrs.get("schema_version", "")),
                "units": json.loads(str(handle.attrs.get("units_json", "{}"))),
                "field_mapping": json.loads(str(handle.attrs.get("field_mapping_json", "{}"))),
                "provenance": json.loads(str(handle.attrs.get("provenance_json", "{}"))),
                "validation_summary": json.loads(
                    str(handle.attrs.get("validation_summary_json", "{}"))
                ),
            }
    except DataReadError:
        raise
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise DataReadError(f"Cannot read CPDataKit HDF5 {path}: {exc}") from exc
    return Dataset(pd.DataFrame(columns), metadata, path)


def load_dataset(path: str | Path) -> Dataset:
    """Load CSV, JSON records, or CPDataKit HDF5 from a filesystem path."""
    input_path = Path(path)
    _ensure_readable(input_path)
    suffix = input_path.suffix.lower()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(input_path)
            if frame.empty:
                raise DataReadError(f"CSV has no records: {input_path}")
            return Dataset(frame, {}, input_path)
        if suffix == ".json":
            with input_path.open(encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
                raise DataReadError("JSON input must be an array of record objects")
            if not payload:
                raise DataReadError("JSON records input is empty")
            return Dataset(pd.DataFrame.from_records(payload), {}, input_path)
        return _read_hdf5(input_path)
    except DataReadError:
        raise
    except UnicodeError as exc:
        raise DataReadError(f"Input is not valid UTF-8: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise DataReadError(f"Invalid JSON in {input_path}: {exc.msg}") from exc
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataReadError(f"Cannot read {input_path}: {exc}") from exc


def write_hdf5(
    dataset: Dataset,
    output: str | Path,
    schema: ProfileSchema,
    validation: ValidationResult,
    *,
    field_mapping: dict[str, str] | None = None,
    source_description: str | None = None,
    operation_log: list[str] | None = None,
    force: bool = False,
) -> Path:
    """Write the documented CPDataKit HDF5 interchange format."""
    target = Path(output)
    if target.exists() and not force:
        raise OutputExistsError(f"Output already exists: {target}; pass force=True to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    declared_units = {item.name: item.unit for item in schema.fields if item.name in dataset.data}
    units = {**declared_units, **dataset.metadata.get("units", {})}
    stored_mapping = (
        field_mapping if field_mapping is not None else dataset.metadata.get("field_mapping", {})
    )
    provenance = build_provenance(
        dataset.source, source_description=source_description, operation_log=operation_log
    )
    with h5py.File(target, "w") as handle:
        handle.attrs["format"] = "CPDataKit"
        handle.attrs["format_version"] = "1.0"
        handle.attrs["profile"] = schema.profile
        handle.attrs["schema_version"] = schema.schema_version
        handle.attrs["units_json"] = json.dumps(units, sort_keys=True)
        handle.attrs["field_mapping_json"] = json.dumps(stored_mapping, sort_keys=True)
        handle.attrs["provenance_json"] = json.dumps(provenance, sort_keys=True)
        handle.attrs["validation_summary_json"] = json.dumps(
            {
                "valid": validation.valid,
                "error_count": len(validation.errors),
                "warning_count": len(validation.warnings),
            },
            sort_keys=True,
        )
        group = handle.create_group("data")
        for name in dataset.data.columns:
            values = dataset.data[name].to_numpy()
            if values.dtype.kind in {"O", "U"}:
                if len(values) and all(
                    isinstance(item, (list, tuple, np.ndarray)) for item in values
                ):
                    try:
                        values = np.stack(values)
                    except ValueError as exc:
                        raise DataReadError(
                            f"Cannot write inconsistent array shapes in field {name!r}"
                        ) from exc
                else:
                    values = values.astype(h5py.string_dtype(encoding="utf-8"))
            group.create_dataset(name, data=values)
    return target
