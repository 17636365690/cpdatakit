"""Inspect datasets and read native HDF5 structure in bounded slices."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd

from .adapters import DamaskDADF5Adapter
from .exceptions import AdapterError, CPDataKitError, DataReadError, OutputExistsError
from .io import _ensure_readable, _read_hdf5_metadata, iter_hdf5_chunks, load_dataset
from .model import Dataset, ValidationIssue, ValidationResult
from .provenance import sha256_file
from .schema import ProfileSchema, load_schema, schema_to_dict
from .validation import validate_dataset

_INSPECTION_CHUNK_SIZE = 10_000
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|token|secret|api[_-]?key|authorization|credential)",
    re.IGNORECASE,
)
_CREDENTIAL_VALUE = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization|credential)"
    r"\s*([:=])\s*[^\s,;]+"
)
_DRIVE_OR_UNC_PATH = re.compile(r"(?i)(?<![\w])(?:[a-z]:[\\/]|\\\\)[^<>\r\n\"']+")
_POSIX_PATH = re.compile(r"(?<![\w:<])/(?:[^<>\r\n\"']+)")


SchemaInput = str | Path | ProfileSchema | Mapping[str, Any]


def _portable_filename(value: object) -> str:
    text = str(value).replace("\\", "/")
    name = text.rsplit("/", 1)[-1]
    return name or "[redacted]"


def _safe_text(value: object, *, key: str | None = None) -> str:
    if key is not None and _SENSITIVE_KEY.search(key):
        return "[redacted]"
    if value is None:
        return "not available"
    if isinstance(value, Path):
        return _portable_filename(value)
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return "[redacted]"
    else:
        text = str(value)
    text = _CREDENTIAL_VALUE.sub(r"\1\2[redacted]", text)
    text = _DRIVE_OR_UNC_PATH.sub("[path]", text)
    text = _POSIX_PATH.sub("[path]", text)
    return text


def _safe_metadata(value: object, *, key: str | None = None) -> object:
    if key is not None and _SENSITIVE_KEY.search(key):
        return "[redacted]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        if key in {"input_filename", "output_filename"}:
            return _portable_filename(value)
        return _safe_text(value, key=key)
    if isinstance(value, Path):
        return _portable_filename(value)
    if isinstance(value, bytes):
        return _safe_text(value, key=key)
    if isinstance(value, np.generic):
        return _safe_metadata(value.item(), key=key)
    if isinstance(value, float):
        return value if np.isfinite(value) else "not available"
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            safe_key = _safe_text(raw_key)
            result[safe_key] = _safe_metadata(raw_value, key=str(raw_key))
        return result
    if isinstance(value, np.ndarray):
        return _safe_metadata(value.tolist(), key=key)
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_safe_metadata(item) for item in sorted(value, key=repr)]
    return _safe_text(value, key=key)


def sanitize_for_output(value: object) -> object:
    """Return a JSON-compatible value without paths or credential values."""

    return _safe_metadata(value)


def sanitize_error_message(value: object) -> str:
    """Return an expected-error message safe for new CLI output."""

    return _safe_text(value)


def _is_missing(value: object) -> bool:
    if value is None or isinstance(value, (list, tuple, np.ndarray)):
        return False
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, (bool, np.bool_)):
        return bool(missing)
    return False


def _missing_count(values: object) -> int:
    array = np.asarray(values)
    if array.dtype.kind in {"f", "c"}:
        return int(np.isnan(array).sum())
    if array.dtype.kind == "O":
        return sum(
            _missing_count(item)
            if isinstance(item, (list, tuple, np.ndarray))
            else int(_is_missing(item))
            for item in array.flat
        )
    if array.dtype.kind in {"m", "M"}:
        return int(np.asarray(pd.isna(array), dtype=bool).sum())
    try:
        missing = pd.isna(array)
    except (TypeError, ValueError):
        return 0
    if isinstance(missing, (bool, np.bool_)):
        return int(missing)
    return int(np.asarray(missing, dtype=bool).sum())


def _record_shape(values: Iterable[object]) -> list[int]:
    for value in values:
        if _is_missing(value):
            continue
        if isinstance(value, (list, tuple, np.ndarray)):
            return list(np.asarray(value).shape)
        return []
    return []


def _unit_value(units: Mapping[str, Any], name: str) -> str:
    value = units.get(name)
    if isinstance(value, str) and value.strip():
        return _safe_text(value)
    return "not available"


def _field_description(mapping: Mapping[str, Any], name: str) -> str:
    value = mapping.get(name)
    if isinstance(value, Mapping):
        value = value.get("description", "")
    return _safe_text(value) if value else ""


def _series_field_info(
    name: object,
    series: pd.Series,
    *,
    unit: str = "not available",
    description: str = "",
    chunks: list[int] | None = None,
) -> dict[str, Any]:
    values = list(series)
    record_shape = _record_shape(values)
    if record_shape:
        first = next(
            value
            for value in values
            if isinstance(value, (list, tuple, np.ndarray)) and not _is_missing(value)
        )
        dtype = str(np.asarray(first).dtype)
    else:
        dtype = str(series.dtype)
    info: dict[str, Any] = {
        "name": _safe_text(name),
        "dtype": dtype,
        "shape": [len(series), *record_shape],
        "record_shape": record_shape,
        "unit": _safe_text(unit),
        "missing_count": _missing_count(values),
        "description": _safe_text(description),
        "chunks": chunks,
    }
    return info


def _risk_summary(fields: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    missing_values = [
        {"field": field["name"], "count": field["missing_count"]}
        for field in fields
        if field["missing_count"]
    ]
    return {"missing_values": missing_values, "structural": []}


def _portable_provenance(
    raw: object,
    path: Path,
    *,
    source_description: str = "input file",
) -> dict[str, object]:
    source = raw if isinstance(raw, Mapping) else {}
    allowed = {
        "source_description",
        "converted_at_utc",
        "cpdatakit_version",
        "python_version",
        "operation_log",
        "input_filename",
        "input_sha256",
    }
    result: dict[str, object] = {}
    for key in (
        "source_description",
        "converted_at_utc",
        "cpdatakit_version",
        "python_version",
        "operation_log",
        "input_filename",
        "input_sha256",
    ):
        if key not in allowed:
            continue
        if key not in source:
            continue
        if key == "input_filename":
            result[key] = _portable_filename(source[key])
        else:
            result[key] = _safe_metadata(source[key], key=key)
    result.setdefault("source_description", _safe_text(source_description))
    result.setdefault("input_filename", _portable_filename(path))
    if "input_sha256" not in result:
        try:
            result["input_sha256"] = sha256_file(path)
        except OSError:
            result["input_sha256"] = "not available"
    return result


def _base_result(
    path: Path,
    *,
    file_format: str,
    format_version: str,
    fields: list[dict[str, Any]],
    provenance: object,
    adapter: Mapping[str, Any],
    hdf5: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "file": {
            "filename": _portable_filename(path),
            "file_type": "HDF5" if path.suffix.lower() in {".h5", ".hdf5"} else file_format,
            "format": file_format,
            "format_version": _safe_text(format_version),
        },
        "fields": fields,
        "record_count": fields[0]["shape"][0] if fields else 0,
        "hdf5": dict(hdf5 or {}),
        "provenance": _portable_provenance(provenance, path),
        "adapter": _safe_metadata(dict(adapter)),
        "risks": _risk_summary(fields),
    }


def _inspect_frame(
    path: Path,
    dataset: Dataset,
    *,
    file_format: str,
    format_version: str = "not applicable",
) -> dict[str, Any]:
    metadata = dataset.metadata if isinstance(dataset.metadata, Mapping) else {}
    units = metadata.get("units", {})
    units = units if isinstance(units, Mapping) else {}
    mapping = metadata.get("field_mapping", {})
    mapping = mapping if isinstance(mapping, Mapping) else {}
    fields = [
        _series_field_info(
            name,
            series,
            unit=_unit_value(units, str(name)),
            description=_field_description(mapping, str(name)),
        )
        for name, series in dataset.data.items()
    ]
    result = _base_result(
        path,
        file_format=file_format,
        format_version=format_version,
        fields=fields,
        provenance=metadata.get("provenance", {}),
        adapter={"name": "CPDataKit reader", "format": file_format},
    )
    if file_format in {"CSV", "JSON"}:
        result["provenance"] = _portable_provenance({}, path, source_description="input file")
    return result


def _attach_schema(
    result: dict[str, Any],
    contract: ProfileSchema,
    validation: ValidationResult,
) -> dict[str, Any]:
    fields = contract.field_map()
    for item in result["fields"]:
        spec = fields.get(item["name"])
        if spec is None:
            continue
        if item["unit"] == "not available" and spec.unit is not None:
            item["unit"] = _safe_text(spec.unit)
        if not item["description"] and spec.description:
            item["description"] = _safe_text(spec.description)
    result["schema"] = {
        "profile": contract.profile,
        "schema_version": contract.schema_version,
        "definition": sanitize_for_output(schema_to_dict(contract)),
        "validation": sanitize_for_output(validation.to_dict()),
    }
    return result


def _merge_issue(result: ValidationResult, issue: ValidationIssue) -> None:
    target = result.errors if issue.severity == "error" else result.warnings
    for index, existing in enumerate(target):
        if (
            existing.code,
            existing.field,
            existing.message,
            existing.suggestion,
        ) == (issue.code, issue.field, issue.message, issue.suggestion):
            target[index] = replace(
                existing,
                affected_records=existing.affected_records + issue.affected_records,
            )
            return
    target.append(issue)


def _validate_native_hdf5(path: Path, contract: ProfileSchema) -> ValidationResult:
    result = ValidationResult()
    for chunk in iter_hdf5_chunks(path, chunk_size=_INSPECTION_CHUNK_SIZE):
        chunk_result = validate_dataset(chunk, contract)
        for issue in [*chunk_result.errors, *chunk_result.warnings]:
            _merge_issue(result, issue)
    return result


def _attribute_text(attributes: h5py.AttributeManager, name: str, path: Path) -> str:
    if name not in attributes:
        raise DataReadError(f"HDF5 metadata attribute {name!r} is required: {path}")
    value = attributes[name]
    if isinstance(value, (bytes, np.bytes_)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DataReadError(
                f"HDF5 metadata attribute {name!r} is not valid UTF-8: {path}"
            ) from exc
    if not isinstance(value, str):
        raise DataReadError(f"HDF5 metadata attribute {name!r} must be text: {path}")
    return value


def _dadf5_text_attribute(attributes: h5py.AttributeManager, name: str, path: Path) -> str:
    if name not in attributes:
        raise AdapterError(f"DAMASK DADF5 dataset metadata is missing {name!r}: {path}")
    value = attributes[name]
    if isinstance(value, str):
        text = value
    elif isinstance(value, (bytes, np.bytes_)):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterError(
                f"DAMASK DADF5 dataset metadata {name!r} is not valid UTF-8: {path}"
            ) from exc
    else:
        raise AdapterError(f"DAMASK DADF5 dataset metadata {name!r} must be text: {path}")
    if not text.strip():
        raise AdapterError(f"DAMASK DADF5 dataset metadata {name!r} must not be empty: {path}")
    return text


def _dadf5_column_name(kind: str, label: str, field: str, dataset: str) -> str:
    parts = []
    for value in (kind, label, field, dataset):
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        parts.append(cleaned or "value")
    return "user_dadf5_" + "_".join(parts)


def _inspect_native_hdf5(handle: h5py.File, path: Path) -> dict[str, Any]:
    metadata = _read_hdf5_metadata(handle, path)
    data_group = handle.get("data")
    if not isinstance(data_group, h5py.Group):
        raise DataReadError("CPDataKit HDF5 is missing the /data group")
    datasets = [(name, item) for name, item in data_group.items() if isinstance(item, h5py.Dataset)]
    if not datasets:
        raise DataReadError("CPDataKit HDF5 /data group contains no fields")
    record_count: int | None = None
    for name, dataset in datasets:
        if dataset.ndim == 0:
            raise DataReadError(f"CPDataKit HDF5 field {name!r} must contain records")
        if record_count is None:
            record_count = dataset.shape[0]
        elif record_count != dataset.shape[0]:
            raise DataReadError("CPDataKit HDF5 fields have inconsistent record counts")
    if record_count is None or record_count == 0:
        raise DataReadError("CPDataKit HDF5 contains no records")
    units = metadata.get("units", {})
    units = units if isinstance(units, Mapping) else {}
    mapping = metadata.get("field_mapping", {})
    mapping = mapping if isinstance(mapping, Mapping) else {}
    fields: list[dict[str, Any]] = []
    chunks: dict[str, list[int] | None] = {}
    dataset_details: list[dict[str, Any]] = []
    for name, dataset in datasets:
        chunk_shape = list(dataset.chunks) if dataset.chunks is not None else None
        chunks[name] = chunk_shape
        missing_count = 0
        for offset in range(0, record_count, _INSPECTION_CHUNK_SIZE):
            stop = min(offset + _INSPECTION_CHUNK_SIZE, record_count)
            missing_count += _missing_count(dataset[offset:stop])
        description = _field_description(mapping, name)
        field = {
            "name": _safe_text(name),
            "dtype": str(dataset.dtype),
            "shape": list(dataset.shape),
            "record_shape": list(dataset.shape[1:]),
            "unit": _unit_value(units, name),
            "missing_count": missing_count,
            "description": description,
            "chunks": chunk_shape,
        }
        fields.append(field)
        dataset_details.append(
            {
                "name": _safe_text(name),
                "dtype": str(dataset.dtype),
                "shape": list(dataset.shape),
                "chunks": chunk_shape,
            }
        )
    result = _base_result(
        path,
        file_format="CPDataKit HDF5",
        format_version=_attribute_text(handle.attrs, "format_version", path),
        fields=fields,
        provenance=metadata.get("provenance", {}),
        adapter={"name": "CPDataKit HDF5", "format": "CPDataKit"},
        hdf5={
            "group": "/data",
            "record_axis": 0,
            "chunks": chunks,
            "datasets": dataset_details,
        },
    )
    result["record_count"] = record_count
    for field in fields:
        if field["unit"] == "not available":
            result["risks"]["structural"].append(
                {
                    "code": "unit_not_declared",
                    "field": field["name"],
                    "message": "No unit is declared for this field.",
                }
            )
    stored_validation = metadata.get("validation_summary")
    if isinstance(stored_validation, Mapping) and stored_validation.get("valid") is False:
        result["risks"]["structural"].append(
            {
                "code": "stored_validation_failed",
                "field": None,
                "message": "The stored HDF5 validation summary contains errors.",
            }
        )
    return result


def _inspect_dadf5(handle: h5py.File, path: Path) -> dict[str, Any]:
    adapter = DamaskDADF5Adapter()
    major, minor = adapter._validate_root(handle, path)
    increment_name = adapter._resolve_increment(handle, path)
    increment = handle[increment_name]
    kind_group = increment.get(adapter.kind)
    if not isinstance(kind_group, h5py.Group):
        raise AdapterError(f"DAMASK DADF5 increment is missing {adapter.kind!r}: {path}")
    labels = [name for name, item in kind_group.items() if isinstance(item, h5py.Group)]
    if adapter.label is None:
        if len(labels) != 1:
            raise AdapterError(
                f"DAMASK DADF5 selection has multiple labels; pass label explicitly: {labels}"
            )
        label = labels[0]
    else:
        label = adapter.label
    label_group = kind_group.get(label)
    if not isinstance(label_group, h5py.Group):
        raise AdapterError(f"DAMASK DADF5 label does not exist: {label}")
    field_group = label_group.get(adapter.field)
    if not isinstance(field_group, h5py.Group):
        raise AdapterError(
            "DAMASK DADF5 field group does not exist: "
            f"{increment_name}/{adapter.kind}/{label}/{adapter.field}"
        )
    datasets = [
        (name, item) for name, item in field_group.items() if isinstance(item, h5py.Dataset)
    ]
    if not datasets:
        raise AdapterError(f"DAMASK DADF5 field group contains no datasets: {path}")
    record_count: int | None = None
    fields: list[dict[str, Any]] = []
    chunks: dict[str, list[int] | None] = {}
    dataset_details: list[dict[str, Any]] = []
    for name, dataset in datasets:
        if dataset.ndim == 0:
            raise AdapterError(f"DAMASK DADF5 dataset must contain records: {name}")
        if dataset.shape[0] == 0:
            raise AdapterError(f"DAMASK DADF5 dataset contains no records: {name}")
        if record_count is None:
            record_count = dataset.shape[0]
        elif record_count != dataset.shape[0]:
            raise AdapterError("DAMASK DADF5 datasets have inconsistent record counts")
        unit = _dadf5_text_attribute(dataset.attrs, "unit", path)
        description = _dadf5_text_attribute(dataset.attrs, "description", path)
        column = _dadf5_column_name(adapter.kind, label, adapter.field, name)
        if any(item["name"] == column for item in fields):
            raise AdapterError(f"DAMASK DADF5 dataset names collide after normalization: {name}")
        chunk_shape = list(dataset.chunks) if dataset.chunks is not None else None
        chunks[column] = chunk_shape
        missing_count = 0
        for offset in range(0, dataset.shape[0], _INSPECTION_CHUNK_SIZE):
            stop = min(offset + _INSPECTION_CHUNK_SIZE, dataset.shape[0])
            missing_count += _missing_count(dataset[offset:stop])
        fields.append(
            {
                "name": column,
                "dtype": str(dataset.dtype),
                "shape": list(dataset.shape),
                "record_shape": list(dataset.shape[1:]),
                "unit": _safe_text(unit),
                "missing_count": missing_count,
                "description": _safe_text(description),
                "chunks": chunk_shape,
            }
        )
        dataset_details.append(
            {
                "name": column,
                "dtype": str(dataset.dtype),
                "shape": list(dataset.shape),
                "chunks": chunk_shape,
            }
        )
    assert record_count is not None
    fields.insert(
        0,
        {
            "name": "point_id",
            "dtype": "int64",
            "shape": [record_count],
            "record_shape": [],
            "unit": "dimensionless",
            "missing_count": 0,
            "description": "Adapter-generated record index.",
            "chunks": None,
        },
    )
    chunks["point_id"] = None
    dataset_details.insert(
        0,
        {"name": "point_id", "dtype": "int64", "shape": [record_count], "chunks": None},
    )
    result = _base_result(
        path,
        file_format="DAMASK DADF5",
        format_version=f"{major}.{minor}",
        fields=fields,
        provenance={},
        adapter={
            "name": "DamaskDADF5Adapter",
            "format": "DAMASK DADF5",
            "format_version": f"{major}.{minor}",
            "increment": increment_name,
            "kind": adapter.kind,
            "label": label,
            "field": adapter.field,
        },
        hdf5={
            "chunks": chunks,
            "datasets": dataset_details,
            "record_axis": 0,
        },
    )
    result["record_count"] = record_count
    result["provenance"] = _portable_provenance(
        {},
        path,
        source_description="DAMASK DADF5 result selection",
    )
    return result


def inspect_hdf5_structure(path: str | Path) -> dict[str, Any]:
    """Inspect CPDataKit or DAMASK HDF5 structure without full table loading."""

    input_path = Path(path)
    _ensure_readable(input_path)
    try:
        with h5py.File(input_path, "r") as handle:
            if "DADF5_version_major" in handle.attrs or "DADF5_version_minor" in handle.attrs:
                return _inspect_dadf5(handle, input_path)
            return _inspect_native_hdf5(handle, input_path)
    except (DataReadError, AdapterError):
        raise
    except (OSError, KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise DataReadError(f"Cannot inspect HDF5 {input_path}: {exc}") from exc


def inspect_dataset(
    path: str | Path,
    *,
    schema: SchemaInput | None = None,
) -> dict[str, Any]:
    """Inspect a supported dataset and optionally attach schema validation."""

    input_path = Path(path)
    if input_path.suffix.lower() in {".h5", ".hdf5"}:
        result = inspect_hdf5_structure(input_path)
        if schema is not None:
            contract = load_schema(schema)
            if result["file"]["format"] == "DAMASK DADF5":
                dataset = DamaskDADF5Adapter().load(input_path)
                validation = validate_dataset(dataset, contract)
            else:
                validation = _validate_native_hdf5(input_path, contract)
            _attach_schema(result, contract, validation)
        return result
    dataset = load_dataset(input_path)
    result = _inspect_frame(
        input_path,
        dataset,
        file_format={"csv": "CSV", "json": "JSON"}.get(
            input_path.suffix.lower().lstrip("."),
            input_path.suffix.lower().upper(),
        ),
    )
    if schema is not None:
        contract = load_schema(schema)
        _attach_schema(result, contract, validate_dataset(dataset, contract))
    return result


def render_inspection_json(result: Mapping[str, Any]) -> str:
    """Render inspection as canonical JSON."""

    return json.dumps(sanitize_for_output(result), indent=2, sort_keys=True, allow_nan=False) + "\n"


def render_inspection_text(result: Mapping[str, Any]) -> str:
    """Render inspection as stable concise text."""

    file_info = result.get("file", {})
    lines = [
        "CPDataKit inspection",
        f"File: {_safe_text(file_info.get('filename', 'not available'))}",
        f"Format: {_safe_text(file_info.get('format', 'not available'))}",
        f"Format version: {_safe_text(file_info.get('format_version', 'not available'))}",
        f"Records: {_safe_text(result.get('record_count', 'not available'))}",
        "Fields:",
    ]
    for field in result.get("fields", []):
        shape = json.dumps(field.get("shape", []), separators=(",", ":"))
        lines.append(
            f"  - {_safe_text(field.get('name'))}: dtype={_safe_text(field.get('dtype'))}, "
            f"shape={shape}, unit={_safe_text(field.get('unit'))}, "
            f"missing={_safe_text(field.get('missing_count'))}"
        )
    hdf5 = result.get("hdf5", {})
    if hdf5:
        lines.append(f"HDF5: {_safe_text(json.dumps(sanitize_for_output(hdf5), sort_keys=True))}")
    provenance = json.dumps(sanitize_for_output(result.get("provenance", {})), sort_keys=True)
    lines.append(f"Provenance: {_safe_text(provenance)}")
    lines.append(
        "Adapter: "
        f"{_safe_text(json.dumps(sanitize_for_output(result.get('adapter', {})), sort_keys=True))}"
    )
    risks = result.get("risks", {})
    missing = risks.get("missing_values", []) if isinstance(risks, Mapping) else []
    structural = risks.get("structural", []) if isinstance(risks, Mapping) else []
    if missing or structural:
        lines.append("Risks:")
        for item in [*missing, *structural]:
            lines.append(f"  - {_safe_text(item)}")
    schema = result.get("schema")
    if isinstance(schema, Mapping):
        validation = schema.get("validation", {})
        lines.append(
            f"Schema: {_safe_text(schema.get('profile'))} "
            f"(version {_safe_text(schema.get('schema_version'))})"
        )
        if isinstance(validation, Mapping):
            lines.append(
                f"Validation: valid={_safe_text(validation.get('valid'))}, "
                f"errors={len(validation.get('errors', []))}, "
                f"warnings={len(validation.get('warnings', []))}"
            )
            for label, key in (
                ("Validation errors", "errors"),
                ("Validation warnings", "warnings"),
            ):
                issues = validation.get(key, [])
                if not isinstance(issues, list) or not issues:
                    continue
                lines.append(f"{label}:")
                for issue in issues:
                    if isinstance(issue, Mapping):
                        lines.append(
                            f"  - {_safe_text(issue.get('code'))}: "
                            f"{_safe_text(issue.get('message'))} "
                            f"(field={_safe_text(issue.get('field'))}, "
                            f"affected={_safe_text(issue.get('affected_records'))})"
                        )
    return "\n".join(lines) + "\n"


def write_inspection(
    result: Mapping[str, Any],
    output: str | Path,
    *,
    format: str = "text",
    force: bool = False,
) -> Path:
    """Write an inspection artifact without overwriting by default."""

    if format == "json":
        rendered = render_inspection_json(result)
    elif format == "text":
        rendered = render_inspection_text(result)
    else:
        raise CPDataKitError(f"Unsupported inspection format: {format!r}")
    target = Path(output)
    if target.exists() and not force:
        raise OutputExistsError(f"Output already exists: {target}; pass --force to replace it")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise CPDataKitError(f"Cannot write inspection output {target}: {exc}") from exc
    return target
