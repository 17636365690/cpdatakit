"""Explicit field mapping and unit conversion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from pint import DimensionalityError, UndefinedUnitError, UnitRegistry

from .data.scientific import _same_values
from .exceptions import NormalizationError
from .model import Dataset
from .schema import ProfileSchema, load_schema

_UREG = UnitRegistry()
_DECIMAL_UREG = UnitRegistry(non_int_type=Decimal)


class _UnitConversionError(NormalizationError):
    """Keep a numeric failure's position available to the CSV intake boundary."""

    def __init__(self, source: str, record: object, reason: str, component=()):
        self.source = source
        self.record = record
        self.reason = reason
        location = f"Field {source!r} record {record!r}"
        if component:
            location += f" component {component}"
        super().__init__(f"{location}: {reason}")


@lru_cache(maxsize=128)
def _identity_units(input_unit: str, output_unit: str) -> bool:
    reference = _UREG.Quantity(np.array([0.0, 1.0]), input_unit).to(output_unit).magnitude
    return bool(np.array_equal(reference, [0.0, 1.0]))


def _convert_array_units(
    array: np.ndarray, *, source: str, record: object, input_unit: str, output_unit: str
) -> np.ndarray:
    """Convert numeric values without losing integers or creating zero/infinity.

    Ordinary floating-point rounding remains part of a nonidentity conversion.
    Existing NaN/infinity values remain available to the validation layer.
    """
    try:
        if _identity_units(input_unit, output_unit):
            return array.copy()
    except (DimensionalityError, UndefinedUnitError, TypeError, ValueError) as exc:
        raise NormalizationError(
            f"Cannot convert {source!r} from {input_unit!r} to {output_unit!r}: {exc}"
        ) from exc

    def reject(mask: np.ndarray, reason: str) -> None:
        if np.any(mask):
            component = tuple(int(i) for i in np.argwhere(mask)[0])
            raise _UnitConversionError(source, record, reason, component)

    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        floating = np.asarray(array, dtype=np.float64)
    if array.dtype.kind in "iu":
        # Comparing uint64 with float64 directly promotes both sides and can
        # conceal the very rounding we need to detect. Python scalar comparison
        # compares an integer with the float's exact value instead.
        reject(
            array.astype(object) != floating.astype(object),
            "integer precision would be lost in float64 unit conversion",
        )
    elif array.dtype.itemsize > np.dtype("float64").itemsize:
        reject(
            np.isfinite(array) & (array != floating.astype(array.dtype)),
            "numeric precision would be lost in float64 unit conversion",
        )
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        converted = np.asarray(
            _UREG.Quantity(floating, input_unit).to(output_unit).magnitude, dtype=np.float64
        )
    reject(np.isfinite(array) & ~np.isfinite(converted), "unit conversion overflows float64")
    # Check only suspect zeros with decimal arithmetic: offset conversions such
    # as 273.15 K -> 0 degC are valid and must not be mistaken for underflow.
    suspect = np.isfinite(array) & (array != 0) & (converted == 0)
    if array.dtype.kind in "iu":
        suspect |= np.abs(converted) >= 2**53
    for position in np.argwhere(suspect):
        component = tuple(int(i) for i in position)
        with localcontext() as context:
            context.prec = 80
            exact = (
                _DECIMAL_UREG.Quantity(Decimal(str(array[component].item())), input_unit)
                .to(output_unit)
                .magnitude
            )
        if converted[component] == 0 and exact != 0:
            raise _UnitConversionError(
                source, record, "unit conversion underflows float64", component
            )
        if (
            array.dtype.kind in "iu"
            and exact == exact.to_integral_value()
            and Decimal.from_float(float(converted[component])) != exact
        ):
            raise _UnitConversionError(
                source,
                record,
                "integer result precision would be lost in unit conversion",
                component,
            )
    return converted


def _is_missing_scalar(value: object) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _numeric_array(
    value: object, *, source: str, record: object, shape: tuple[int, ...]
) -> np.ndarray:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(
            f"Field {source!r} record {record!r} is not a regular numeric array"
        ) from exc
    if tuple(array.shape) != shape:
        raise NormalizationError(
            f"Field {source!r} record {record!r} has shape {tuple(array.shape)}; "
            f"expected shape {shape}"
        )
    if array.dtype.kind not in {"i", "u", "f"}:
        raise NormalizationError(f"Field {source!r} record {record!r} is not numeric")
    if (
        shape
        and not isinstance(value, np.ndarray)
        and not _same_values(np.asarray(value, dtype=object), array)
    ):
        raise _UnitConversionError(
            source, record, "numeric precision would be lost forming an array"
        )
    return array


def _convert_series_units(
    series: pd.Series,
    *,
    source: str,
    shape: tuple[int, ...],
    input_unit: str,
    output_unit: str,
) -> pd.Series:
    try:
        identity = _identity_units(input_unit, output_unit)
    except (DimensionalityError, UndefinedUnitError, TypeError, ValueError) as exc:
        raise NormalizationError(
            f"Cannot convert {source!r} from {input_unit!r} to {output_unit!r}: {exc}"
        ) from exc
    converted: list[object] = []
    for record, value in series.items():
        if _is_missing_scalar(value):
            converted.append(value)
            continue
        array = _numeric_array(value, source=source, record=record, shape=shape)
        converted_array = _convert_array_units(
            array, source=source, record=record, input_unit=input_unit, output_unit=output_unit
        )
        converted.append(converted_array.item() if not shape else converted_array)
    # Explicit dtype avoids pandas re-inferring nullable integer values through
    # a float column even though the unit transform did not change a value.
    dtype = series.dtype if identity else None
    return pd.Series(converted, index=series.index, name=series.name, dtype=dtype)


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """An explicit, traceable field mapping and optional unit conversion."""

    source: str
    target: str
    input_unit: str | None = None
    output_unit: str | None = None
    source_note: str = "user supplied"


def load_mapping_file(path: str | Path) -> tuple[list[FieldMapping], bool]:
    """Load a strict JSON mapping file for explicit CLI normalization."""
    mapping_path = Path(path)
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NormalizationError(f"Mapping file does not exist: {mapping_path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NormalizationError(f"Cannot read mapping file {mapping_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise NormalizationError("Mapping file root must be a JSON object")
    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, list):
        raise NormalizationError("Mapping file 'mappings' must be a list")
    drop_unmapped = payload.get("drop_unmapped", False)
    if not isinstance(drop_unmapped, bool):
        raise NormalizationError("Mapping file 'drop_unmapped' must be boolean")

    allowed = {"source", "target", "input_unit", "output_unit", "source_note"}
    mappings: list[FieldMapping] = []
    for index, raw in enumerate(raw_mappings):
        if not isinstance(raw, dict):
            raise NormalizationError(f"Mapping {index} must be a JSON object")
        unknown = set(raw) - allowed
        if unknown:
            raise NormalizationError(
                f"Mapping {index} contains unsupported keys: {sorted(unknown)}"
            )
        source = raw.get("source")
        target = raw.get("target")
        if not isinstance(source, str) or not source.strip():
            raise NormalizationError(f"Mapping {index} source must be a non-empty string")
        if not isinstance(target, str) or not target.strip():
            raise NormalizationError(f"Mapping {index} target must be a non-empty string")
        input_unit = raw.get("input_unit")
        output_unit = raw.get("output_unit")
        source_note = raw.get("source_note", "user supplied")
        if input_unit is not None and not isinstance(input_unit, str):
            raise NormalizationError(f"Mapping {index} input_unit must be a string or null")
        if output_unit is not None and not isinstance(output_unit, str):
            raise NormalizationError(f"Mapping {index} output_unit must be a string or null")
        if not isinstance(source_note, str):
            raise NormalizationError(f"Mapping {index} source_note must be a string")
        mappings.append(
            FieldMapping(
                source=source,
                target=target,
                input_unit=input_unit,
                output_unit=output_unit,
                source_note=source_note,
            )
        )
    return mappings, drop_unmapped


def normalize_dataset(
    dataset: Dataset,
    schema: str | ProfileSchema,
    mappings: list[FieldMapping] | None = None,
    *,
    drop_unmapped: bool = False,
) -> Dataset:
    """Normalize fields from explicit mappings and schema conventions."""
    contract = load_schema(schema)
    items = list(mappings or [])
    sources = [item.source for item in items]
    targets = [item.target for item in items]
    if len(sources) != len(set(sources)) or len(targets) != len(set(targets)):
        raise NormalizationError("Mappings contain a duplicate source or target")
    unknown = set(targets) - set(contract.field_map())
    if unknown:
        raise NormalizationError(
            f"Mapping targets are not declared by the schema: {sorted(unknown)}"
        )
    missing = set(sources) - set(dataset.data.columns)
    if missing:
        raise NormalizationError(f"Mapping sources do not exist: {sorted(missing)}")
    collisions = {
        item.target for item in items if item.target in dataset.data and item.target != item.source
    }
    if collisions:
        raise NormalizationError(f"Mappings would overwrite existing fields: {sorted(collisions)}")

    result = dataset.copy()
    units = dict(result.metadata.get("units", {}))
    unit_sources = dict(result.metadata.get("units_source", {}))
    mapping_log: dict[str, dict[str, str | None]] = {}
    for item in items:
        series = result.data[item.source]
        if bool(item.input_unit) != bool(item.output_unit):
            raise NormalizationError("Both input_unit and output_unit are required for conversion")
        if item.input_unit and item.output_unit:
            if item.source in units:
                try:
                    reference = (
                        _UREG.Quantity(np.array([0.0, 1.0]), units[item.source])
                        .to(item.input_unit)
                        .magnitude
                    )
                    agrees = np.allclose(reference, [0.0, 1.0], rtol=1e-12, atol=0.0)
                except (DimensionalityError, UndefinedUnitError, TypeError, ValueError) as exc:
                    raise NormalizationError(
                        f"Invalid source unit declaration for {item.source!r}"
                    ) from exc
                if not agrees:
                    raise NormalizationError(
                        f"Input unit declaration conflicts for {item.source!r}: "
                        f"stored {units[item.source]!r}, mapping {item.input_unit!r}"
                    )
            spec = contract.field_map()[item.target]
            series = _convert_series_units(
                series,
                source=item.source,
                shape=spec.shape,
                input_unit=item.input_unit,
                output_unit=item.output_unit,
            )
            units[item.target] = item.output_unit
            unit_sources[item.target] = "declared"
        elif item.source in units:
            units[item.target] = units[item.source]
            unit_sources[item.target] = unit_sources.get(item.source, "declared")
        result.data[item.target] = series
        if item.target != item.source:
            result.data = result.data.drop(columns=[item.source])
            units.pop(item.source, None)
            unit_sources.pop(item.source, None)
        mapping_log[item.source] = {
            "target": item.target,
            "input_unit": item.input_unit,
            "output_unit": item.output_unit,
            "source_note": item.source_note,
        }
    if drop_unmapped:
        keep = [item.name for item in contract.fields if item.name in result.data]
        result.data = result.data.loc[:, keep]
        units = {key: value for key, value in units.items() if key in keep}
        unit_sources = {key: value for key, value in unit_sources.items() if key in keep}
    result.metadata.update(
        {
            "profile": contract.profile,
            "schema_version": contract.schema_version,
            "units": units,
            "units_source": unit_sources,
            "field_mapping": mapping_log,
        }
    )
    return result
