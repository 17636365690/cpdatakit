"""CSV, JSON records, and CPDataKit HDF5 I/O."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Iterator
from numbers import Integral
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd

from ..exceptions import DataReadError, DataValidationError, OutputExistsError
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
        raise DataReadError(f"HDF5 metadata attribute {name!r} must encode a JSON object: {path}")
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
        raise DataReadError(f"Unsupported HDF5 metadata schema_version {schema_version!r}: {path}")

    return {
        "profile": profile,
        "schema_version": schema_version,
        "units": _required_json_object(handle, "units_json", path),
        "field_mapping": _required_json_object(handle, "field_mapping_json", path),
        "provenance": _required_json_object(handle, "provenance_json", path),
        "validation_summary": _required_json_object(handle, "validation_summary_json", path),
    }


def _normalize_hdf5_fields(group: h5py.Group, fields: Iterable[str] | None) -> list[str]:
    available = [name for name, item in group.items() if isinstance(item, h5py.Dataset)]
    if fields is None:
        names = available
    else:
        if isinstance(fields, (str, bytes)):
            raise DataReadError("HDF5 fields must be an iterable of field names, not a string")
        try:
            names = list(fields)
        except TypeError as exc:
            raise DataReadError("HDF5 fields must be an iterable of field names") from exc
        if not names:
            raise DataReadError("HDF5 field selection cannot be empty")
        if any(not isinstance(name, str) for name in names):
            raise DataReadError("HDF5 field names must be strings")
        for name in names:
            item = group.get(name)
            if not isinstance(item, h5py.Dataset):
                raise DataReadError(f"Unknown HDF5 field {name!r}")
    if not names:
        raise DataReadError("CPDataKit HDF5 /data group contains no fields")
    return names


def _resolve_hdf5_bounds(record_count: int, start: int | None, stop: int | None) -> tuple[int, int]:
    def normalize(value: int | None, name: str, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise DataReadError(f"HDF5 {name} must be an integer or None")
        return int(value)

    resolved_start = normalize(start, "start", 0)
    resolved_stop = normalize(stop, "stop", record_count)
    if not 0 <= resolved_start <= resolved_stop <= record_count:
        raise DataReadError(f"HDF5 read bounds must satisfy 0 <= start <= stop <= {record_count}")
    return resolved_start, resolved_stop


def _resolve_hdf5_selection(
    group: h5py.Group, fields: Iterable[str] | None
) -> tuple[list[str], int]:
    available = [name for name, item in group.items() if isinstance(item, h5py.Dataset)]
    if not available:
        raise DataReadError("CPDataKit HDF5 /data group contains no fields")
    record_count: int | None = None
    for name in available:
        item = group[name]
        if item.ndim == 0:
            raise DataReadError(f"CPDataKit HDF5 field {name!r} must contain records")
        field_count = item.shape[0]
        if record_count is None:
            record_count = field_count
        elif field_count != record_count:
            raise DataReadError("CPDataKit HDF5 fields have inconsistent record counts")
    if record_count is None:
        raise DataReadError("CPDataKit HDF5 /data group contains no fields")
    if record_count == 0:
        raise DataReadError("CPDataKit HDF5 contains no records")
    names = _normalize_hdf5_fields(group, fields)
    return names, record_count


def _decode_hdf5_value(value: Any) -> Any:
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        if value.dtype.kind == "S":
            return np.char.decode(value, "utf-8")
        if value.dtype.kind == "O":
            return [_decode_hdf5_value(item) for item in value]
    return value


def _read_hdf5_columns(
    group: h5py.Group, names: Iterable[str], start: int, stop: int
) -> dict[str, Any]:
    columns: dict[str, Any] = {}
    for name in names:
        item = group[name]
        if not isinstance(item, h5py.Dataset) or item.ndim == 0:
            raise DataReadError(f"CPDataKit HDF5 field {name!r} must contain records")
        values = item[start:stop]
        decoded = _decode_hdf5_value(values)
        if isinstance(decoded, np.ndarray) and decoded.ndim > 1:
            columns[name] = list(decoded)
        else:
            columns[name] = decoded
    return columns


def _prepare_hdf5_read(
    handle: h5py.File,
    path: Path,
    fields: Iterable[str] | None,
    start: int | None,
    stop: int | None,
) -> tuple[dict[str, Any], h5py.Group, list[str], int, int]:
    metadata = _read_hdf5_metadata(handle, path)
    data_group = handle.get("data")
    if not isinstance(data_group, h5py.Group):
        raise DataReadError("CPDataKit HDF5 is missing the /data group")
    names, record_count = _resolve_hdf5_selection(data_group, fields)
    resolved_start, resolved_stop = _resolve_hdf5_bounds(record_count, start, stop)
    return metadata, data_group, names, resolved_start, resolved_stop


def load_hdf5(
    path: str | Path,
    *,
    fields: Iterable[str] | None = None,
    start: int | None = None,
    stop: int | None = None,
) -> Dataset:
    """Load a CPDataKit HDF5 dataset with optional field and row selection."""
    input_path = Path(path)
    _ensure_readable(input_path)
    try:
        with h5py.File(input_path, "r") as handle:
            metadata, data_group, names, resolved_start, resolved_stop = _prepare_hdf5_read(
                handle, input_path, fields, start, stop
            )
            frame = pd.DataFrame(
                _read_hdf5_columns(data_group, names, resolved_start, resolved_stop)
            )
    except DataReadError:
        raise
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise DataReadError(f"Cannot read CPDataKit HDF5 {input_path}: {exc}") from exc
    return Dataset(frame, metadata, input_path)


def _resolve_hdf5_chunk_size(chunk_size: int) -> int:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, Integral) or chunk_size <= 0:
        raise DataReadError("HDF5 chunk_size must be a positive integer")
    return int(chunk_size)


def iter_hdf5_chunks(
    path: str | Path,
    *,
    fields: Iterable[str] | None = None,
    chunk_size: int = 10_000,
) -> Iterator[Dataset]:
    """Lazily yield fixed-size CPDataKit HDF5 dataset chunks."""
    input_path = Path(path)
    _ensure_readable(input_path)
    resolved_chunk_size = _resolve_hdf5_chunk_size(chunk_size)
    try:
        with h5py.File(input_path, "r") as handle:
            metadata, data_group, names, start, stop = _prepare_hdf5_read(
                handle, input_path, fields, None, None
            )
            for offset in range(start, stop, resolved_chunk_size):
                chunk_stop = min(offset + resolved_chunk_size, stop)
                frame = pd.DataFrame(_read_hdf5_columns(data_group, names, offset, chunk_stop))
                yield Dataset(frame, dict(metadata), input_path)
    except DataReadError:
        raise
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise DataReadError(f"Cannot read CPDataKit HDF5 {input_path}: {exc}") from exc


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
        return load_hdf5(input_path)
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
    allow_invalid: bool = False,
) -> Path:
    """Write the documented CPDataKit HDF5 interchange format."""
    target = Path(output)
    if target.exists() and not force:
        raise OutputExistsError(f"Output already exists: {target}; pass force=True to replace it")
    if not validation.valid and not allow_invalid:
        raise DataValidationError(
            "Cannot write a dataset with validation errors; pass allow_invalid=True explicitly"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    declared_units = {item.name: item.unit for item in schema.fields if item.name in dataset.data}
    units = {**declared_units, **dataset.metadata.get("units", {})}
    stored_mapping = (
        field_mapping if field_mapping is not None else dataset.metadata.get("field_mapping", {})
    )
    provenance = build_provenance(
        dataset.source, source_description=source_description, operation_log=operation_log
    )
    temp_path: Path | None = None
    try:
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=target.suffix, dir=target.parent
        )
        temp_path = Path(temp_name)
        os.close(temp_fd)
        with h5py.File(temp_path, "w") as handle:
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
        os.replace(temp_path, target)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return target
