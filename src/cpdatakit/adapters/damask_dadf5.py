"""Read documented DAMASK DADF5 result selections into CPDataKit datasets."""

from __future__ import annotations

import re
from collections.abc import Iterable
from numbers import Integral, Real
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np
import pandas as pd

from ..exceptions import AdapterError
from ..model import Dataset
from ..provenance import build_provenance
from .base import DatasetAdapter

_INCREMENT_RE = re.compile(r"increment_(\d+)")


def _text_attribute(attributes: h5py.AttributeManager, name: str, path: Path) -> str:
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


def _column_name(kind: str, label: str, field: str, dataset: str) -> str:
    parts = []
    for value in (kind, label, field, dataset):
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        parts.append(cleaned or "value")
    return "user_dadf5_" + "_".join(parts)


def _decode_values(values: np.ndarray) -> np.ndarray:
    if values.dtype.kind == "S":
        return np.char.decode(values, "utf-8")
    if values.dtype.kind == "O":
        decoded = []
        for value in values:
            if isinstance(value, (bytes, np.bytes_)):
                decoded.append(bytes(value).decode("utf-8"))
            else:
                decoded.append(value)
        return np.asarray(decoded, dtype=object)
    return values


class DamaskDADF5Adapter(DatasetAdapter):
    """Read one explicit selection from a documented DAMASK DADF5 result file.

    The adapter reads data beneath one increment/kind/label/field group and returns a
    CPDataKit ``point`` dataset. External field names are preserved in a ``user_dadf5_``
    namespace; no DAMASK runtime or source code is required.
    """

    def __init__(
        self,
        *,
        increment: int | str = -1,
        kind: Literal["phase", "homogenization"] = "homogenization",
        label: str | None = None,
        field: str = "mechanical",
        datasets: Iterable[str] | None = None,
    ) -> None:
        if isinstance(increment, bool) or not isinstance(increment, (Integral, str)):
            raise AdapterError("DAMASK DADF5 increment must be an integer or string")
        if kind not in {"phase", "homogenization"}:
            raise AdapterError("DAMASK DADF5 kind must be 'phase' or 'homogenization'")
        if not isinstance(field, str) or not field.strip():
            raise AdapterError("DAMASK DADF5 field must be a non-empty string")
        if label is not None and (not isinstance(label, str) or not label.strip()):
            raise AdapterError("DAMASK DADF5 label must be a non-empty string or None")
        if datasets is None:
            selected_datasets = None
        else:
            if isinstance(datasets, (str, bytes)):
                raise AdapterError("DAMASK DADF5 datasets must be an iterable of names")
            try:
                selected_datasets = tuple(datasets)
            except TypeError as exc:
                raise AdapterError("DAMASK DADF5 datasets must be an iterable of names") from exc
            if not selected_datasets or any(
                not isinstance(name, str) or not name.strip() for name in selected_datasets
            ):
                raise AdapterError("DAMASK DADF5 datasets must contain non-empty names")
            if len(selected_datasets) != len(set(selected_datasets)):
                raise AdapterError("DAMASK DADF5 datasets must not contain duplicates")
        self.increment = increment
        self.kind = kind
        self.label = label
        self.field = field
        self.datasets = selected_datasets

    def _resolve_increment(self, handle: h5py.File, path: Path) -> str:
        available = {
            name: int(match.group(1)) for name in handle if (match := _INCREMENT_RE.fullmatch(name))
        }
        if not available:
            raise AdapterError(f"DAMASK DADF5 file contains no increment groups: {path}")
        if isinstance(self.increment, Integral):
            number = max(available.values()) if self.increment == -1 else int(self.increment)
            if number < 0:
                raise AdapterError("DAMASK DADF5 increment must be -1 or non-negative")
            increment_name = f"increment_{number}"
        else:
            increment_name = self.increment
            if increment_name.isdigit():
                increment_name = f"increment_{increment_name}"
        if increment_name not in available:
            raise AdapterError(f"DAMASK DADF5 increment does not exist: {increment_name}")
        return increment_name

    def _validate_root(self, handle: h5py.File, path: Path) -> tuple[int, int]:
        try:
            major = handle.attrs["DADF5_version_major"]
            minor = handle.attrs["DADF5_version_minor"]
        except KeyError as exc:
            raise AdapterError(f"DAMASK DADF5 version metadata is incomplete: {path}") from exc
        if (
            isinstance(major, bool)
            or isinstance(minor, bool)
            or not isinstance(major, Integral)
            or not isinstance(minor, Integral)
        ):
            raise AdapterError(f"DAMASK DADF5 version metadata must be integer-valued: {path}")
        major_number, minor_number = int(major), int(minor)
        if not (major_number == 1 or (major_number == 0 and minor_number == 14)):
            raise AdapterError(
                f"Unsupported DAMASK DADF5 version {major_number}.{minor_number}: {path}"
            )
        for name in ("geometry", "cell_to"):
            if not isinstance(handle.get(name), h5py.Group):
                raise AdapterError(f"DAMASK DADF5 file is missing /{name}: {path}")
        kind_group = handle["cell_to"].get(self.kind)
        if not isinstance(kind_group, h5py.Group) or not isinstance(
            kind_group.get("label"), h5py.Dataset
        ):
            raise AdapterError(f"DAMASK DADF5 file is missing /cell_to/{self.kind}/label: {path}")
        return major_number, minor_number

    def _read_selection(
        self, handle: h5py.File, path: Path, increment_name: str
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        increment = handle.get(increment_name)
        if not isinstance(increment, h5py.Group):
            raise AdapterError(f"DAMASK DADF5 increment is not a group: {increment_name}")
        kind_group = increment.get(self.kind)
        if not isinstance(kind_group, h5py.Group):
            raise AdapterError(f"DAMASK DADF5 increment is missing {self.kind!r}: {path}")
        labels = [name for name, item in kind_group.items() if isinstance(item, h5py.Group)]
        if self.label is None:
            if len(labels) != 1:
                raise AdapterError(
                    f"DAMASK DADF5 selection has multiple labels; pass label explicitly: {labels}"
                )
            label = labels[0]
        else:
            label = self.label
        label_group = kind_group.get(label)
        if not isinstance(label_group, h5py.Group):
            raise AdapterError(f"DAMASK DADF5 label does not exist: {label}")
        field_group = label_group.get(self.field)
        if not isinstance(field_group, h5py.Group):
            raise AdapterError(
                "DAMASK DADF5 field group does not exist: "
                f"{increment_name}/{self.kind}/{label}/{self.field}"
            )
        available = [name for name, item in field_group.items() if isinstance(item, h5py.Dataset)]
        names = available if self.datasets is None else list(self.datasets)
        if not names:
            raise AdapterError(f"DAMASK DADF5 field group contains no datasets: {path}")
        for name in names:
            if not isinstance(field_group.get(name), h5py.Dataset):
                raise AdapterError(f"DAMASK DADF5 dataset does not exist: {name}")

        record_count: int | None = None
        columns: dict[str, Any] = {}
        units: dict[str, str] = {"point_id": "dimensionless"}
        mapping: dict[str, dict[str, str]] = {}
        columns["point_id"] = np.array([], dtype=np.int64)
        for name in names:
            dataset = field_group[name]
            if dataset.ndim == 0:
                raise AdapterError(f"DAMASK DADF5 dataset must contain records: {name}")
            count = dataset.shape[0]
            if count == 0:
                raise AdapterError(f"DAMASK DADF5 dataset contains no records: {name}")
            if record_count is None:
                record_count = count
            elif count != record_count:
                raise AdapterError("DAMASK DADF5 datasets have inconsistent record counts")
            unit = _text_attribute(dataset.attrs, "unit", path)
            description = _text_attribute(dataset.attrs, "description", path)
            values = _decode_values(np.asarray(dataset[()]))
            column = _column_name(self.kind, label, self.field, name)
            if column in columns:
                raise AdapterError(
                    f"DAMASK DADF5 dataset names collide after normalization: {name}"
                )
            columns[column] = list(values) if values.ndim > 1 else values
            units[column] = unit
            mapping[column] = {
                "source": f"/{increment_name}/{self.kind}/{label}/{self.field}/{name}",
                "description": description,
                "source_note": "DAMASK DADF5 dataset metadata",
            }
        assert record_count is not None
        columns["point_id"] = np.arange(record_count, dtype=np.int64)
        metadata = {
            "profile": "point",
            "schema_version": "1.0",
            "units": units,
            "field_mapping": mapping,
            "adapter": {
                "name": "DamaskDADF5Adapter",
                "format": "DAMASK DADF5",
                "increment": increment_name,
                "kind": self.kind,
                "label": label,
                "field": self.field,
            },
        }
        return pd.DataFrame(columns), metadata

    def load(self, path: Path) -> Dataset:
        """Load one explicit DADF5 result selection into a CPDataKit point dataset."""
        input_path = Path(path).expanduser()
        if not input_path.exists() or not input_path.is_file():
            raise AdapterError(f"DAMASK DADF5 input path is not a file: {input_path}")
        try:
            with h5py.File(input_path, "r") as handle:
                major, minor = self._validate_root(handle, input_path)
                increment_name = self._resolve_increment(handle, input_path)
                frame, metadata = self._read_selection(handle, input_path, increment_name)
                time_value = handle[increment_name].attrs.get("t/s")
                if isinstance(time_value, Real) and not isinstance(time_value, bool):
                    metadata["adapter"]["time_s"] = float(time_value)
        except AdapterError:
            raise
        except (OSError, KeyError, TypeError, UnicodeError, ValueError) as exc:
            raise AdapterError(f"Cannot read DAMASK DADF5 file {input_path}: {exc}") from exc
        metadata["adapter"]["format_version"] = f"{major}.{minor}"
        metadata["provenance"] = build_provenance(
            input_path,
            source_description="DAMASK DADF5 result selection",
            operation_log=["adapter:damask_dadf5", f"read:{metadata['adapter']['increment']}"],
        )
        return Dataset(frame, metadata, input_path)
