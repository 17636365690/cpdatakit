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
from ..schema import SUPPORTED_PROFILES, SUPPORTED_SCHEMA_VERSION, ProfileSchema

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


def _required_text_attr(handle: h5py.File, name: str, path: Path) -> str:
    if name not in handle.attrs:
        raise DataReadError(f"HDF5 metadata attribute {name!r} is required: {path}")
    value = handle.attrs[name]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DataReadError(
                f"HDF5 metadata attribute {name!r} is not valid UTF-8: {path}"
            ) from exc
    if not isinstance(value, str):
        raise DataReadError(f"HDF5 metadata attribute {name!r} must be text: {path}")
    return value


def _required_json_object(handle: h5py.File, name: str, path: Path) -> dict[str, Any]:
    text = _required_text_attr(handle, name, path)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataReadError(
            f"Invalid HDF5 metadata JSON in attribute {name!r}: {path}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise DataReadError(
            f"HDF5 metadata attribute {name!r} must encode a JSON object: {path}"
        )
    return value


def _read_hdf5_metadata(handle: h5py.File, path: Path) -> dict[str, Any]:
    if _required_text_attr(handle, "format", path) != "CPDataKit":
        raise DataReadError("HDF5 is not a CPDataKit file (missing format marker)")

    format_version = _required_text_attr(handle, "format_version", path)
    if format_version != "1.0":
        raise DataReadError(f"Unsupported HDF5 metadata format_version {format_version!r}: {path}")

    profile = _required_text_attr(handle, "profile", path)
    if profile not in SUPPORTED_PROFILES:
        raise DataReadError(f"Unsupported HDF5 metadata profile {profile!r}: {path}")

    schema_version = _required_text_attr(handle, "schema_version", path)
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise DataReadError(
            f"Unsupported HDF5 metadata schema_version {schema_version!r}: {path}"
        )

    return {
        "profile": profile,
        "schema_version": schema_version,
        "units": _required_json_object(handle, "units_json", path),
        "field_mapping": _required_json_object(handle, "field_mapping_json", path),
        "provenance": _required_json_object(handle, "provenance_json", path),
        "validation_summary": _required_json_object(
            handle, "validation_summary_json", path
        ),
    }


def _read_hdf5(path: Path) -> Dataset:
    try:
        with h5py.File(path, "r") as handle:
            metadata = _read_hdf5_metadata(handle, path)
            if "data" not in handle or not isinstance(handle["data"], h5py.Group):
                raise DataReadError("CPDataKit HDF5 is missing the /data group")
            columns: dict[str, Any] = {}
            record_count: int | None = None
            for name, item in handle["data"].items():
                if not isinstance(item, h5py.Dataset):
                    continue
                values = item[()]
                if values.ndim == 0:
                    raise DataReadError(f"CPDataKit HDF5 field {name!r} must contain records")
                if values.dtype.kind in {"S", "O"}:
                    values = np.asarray(
                        [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]
                    )
                if record_count is None:
                    record_count = len(values)
                elif len(values) != record_count:
                    raise DataReadError("CPDataKit HDF5 fields have inconsistent record counts")
                columns[name] = list(values) if values.ndim > 1 else values
            if not columns:
                raise DataReadError("CPDataKit HDF5 /data group contains no fields")
            if record_count == 0:
                raise DataReadError("CPDataKit HDF5 contains no records")
            frame = pd.DataFrame(columns)
    except DataReadError:
        raise
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise DataReadError(f"Cannot read CPDataKit HDF5 {path}: {exc}") from exc
    return Dataset(frame, metadata, path)


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
