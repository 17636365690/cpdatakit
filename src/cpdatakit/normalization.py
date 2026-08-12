"""Explicit field mapping and unit conversion."""

from __future__ import annotations

from dataclasses import dataclass

from pint import DimensionalityError, UndefinedUnitError, UnitRegistry

from .exceptions import NormalizationError
from .model import Dataset
from .schema import ProfileSchema, load_schema

_UREG = UnitRegistry()


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """An explicit, traceable field mapping and optional unit conversion."""

    source: str
    target: str
    input_unit: str | None = None
    output_unit: str | None = None
    source_note: str = "user supplied"


def normalize_dataset(
    dataset: Dataset,
    schema: str | ProfileSchema,
    mappings: list[FieldMapping] | None = None,
    *,
    drop_unmapped: bool = False,
) -> Dataset:
    """Normalize fields only from explicit mappings; never infer scientific conventions."""
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
    mapping_log: dict[str, dict[str, str | None]] = {}
    for item in items:
        series = result.data[item.source]
        if bool(item.input_unit) != bool(item.output_unit):
            raise NormalizationError("Both input_unit and output_unit are required for conversion")
        if item.input_unit and item.output_unit:
            try:
                factor = _UREG.Quantity(1, item.input_unit).to(item.output_unit).magnitude
            except (DimensionalityError, UndefinedUnitError) as exc:
                raise NormalizationError(
                    f"Cannot convert {item.source!r} from {item.input_unit!r} "
                    f"to {item.output_unit!r}: {exc}"
                ) from exc
            try:
                series = series.astype(float) * factor
            except (TypeError, ValueError) as exc:
                raise NormalizationError(f"Field {item.source!r} is not numeric") from exc
            units[item.target] = item.output_unit
        elif item.source in units:
            units[item.target] = units[item.source]
        result.data[item.target] = series
        if item.target != item.source:
            result.data = result.data.drop(columns=[item.source])
            units.pop(item.source, None)
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
    result.metadata.update(
        {
            "profile": contract.profile,
            "schema_version": contract.schema_version,
            "units": units,
            "field_mapping": mapping_log,
        }
    )
    return result
