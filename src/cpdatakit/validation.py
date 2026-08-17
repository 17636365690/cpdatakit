"""Schema-conformance validation."""

from __future__ import annotations

from numbers import Real

import numpy as np
import pandas as pd
from pint import DimensionalityError, UndefinedUnitError, UnitRegistry

from .model import Dataset, ValidationIssue, ValidationResult
from .schema import FieldSchema, ProfileSchema, load_schema

_UREG = UnitRegistry()


def _issue(
    code: str,
    field: str | None,
    message: str,
    affected: int,
    suggestion: str | None = None,
    *,
    severity: str = "error",
) -> ValidationIssue:
    return ValidationIssue(code, field, message, int(affected), suggestion, severity)  # type: ignore[arg-type]


def _is_real_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, (bool, np.bool_))


def _matches_shape(value: object, shape: list[int]) -> bool:
    return isinstance(value, (list, tuple, np.ndarray)) and list(np.asarray(value).shape) == shape


def _array_dtype_matches(value: object, dtype: str) -> bool:
    kind = np.asarray(value).dtype.kind
    if dtype in {"float", "integer"}:
        return kind in {"i", "u", "f"}
    if dtype == "string":
        return kind in {"S", "U"}
    if dtype == "boolean":
        return kind == "b"
    return False


def _make_hashable(value: object) -> object:
    if isinstance(value, np.ndarray):
        return _make_hashable(value.tolist())
    if isinstance(value, dict):
        pairs = [(_make_hashable(key), _make_hashable(item)) for key, item in value.items()]
        return tuple(sorted(pairs, key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_make_hashable(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_make_hashable(item) for item in value), key=repr))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _check_field(frame: pd.DataFrame, spec: FieldSchema, result: ValidationResult) -> None:
    if spec.name not in frame:
        if spec.required:
            result.errors.append(
                _issue(
                    "required_field_missing",
                    spec.name,
                    f"Required field {spec.name!r} is absent.",
                    len(frame),
                    "Add the field or declare an explicit mapping before validation.",
                )
            )
        return
    series = frame[spec.name]
    missing = series.isna()
    if not spec.allow_missing and missing.any():
        result.errors.append(
            _issue(
                "missing_value",
                spec.name,
                "Field contains missing values.",
                missing.sum(),
                "Provide values or explicitly permit missing values in the schema.",
            )
        )
    if spec.shape:
        invalid_shape = series.notna() & ~series.map(
            lambda value: _matches_shape(value, spec.shape)
        )
        if invalid_shape.any():
            result.errors.append(
                _issue(
                    "invalid_shape",
                    spec.name,
                    f"Expected per-record shape {spec.shape}.",
                    invalid_shape.sum(),
                )
            )
        valid_values = series[~invalid_shape & series.notna()]
        invalid_dtype = valid_values.map(lambda value: not _array_dtype_matches(value, spec.dtype))
        if invalid_dtype.any():
            result.errors.append(
                _issue(
                    "invalid_dtype",
                    spec.name,
                    f"Expected {spec.dtype} array values.",
                    invalid_dtype.sum(),
                )
            )
        arrays = valid_values[~invalid_dtype].map(np.asarray)
        if spec.dtype in {"float", "integer"}:
            non_finite = arrays.map(lambda value: not np.isfinite(value).all())
            if non_finite.any():
                result.errors.append(
                    _issue(
                        "non_finite",
                        spec.name,
                        "Array field contains NaN or positive or negative infinity.",
                        non_finite.sum(),
                    )
                )
            if spec.dtype == "integer":
                fractional = arrays.map(
                    lambda value: bool(np.any(value[np.isfinite(value)] % 1 != 0))
                )
                if fractional.any():
                    result.errors.append(
                        _issue(
                            "invalid_integer",
                            spec.name,
                            "Integer array field has fractional values.",
                            fractional.sum(),
                        )
                    )
            if spec.minimum is not None:
                low = arrays.map(lambda value: bool(np.any(value < spec.minimum)))
                if low.any():
                    result.errors.append(
                        _issue(
                            "below_minimum",
                            spec.name,
                            f"Array values are below {spec.minimum}.",
                            low.sum(),
                        )
                    )
            if spec.maximum is not None:
                high = arrays.map(lambda value: bool(np.any(value > spec.maximum)))
                if high.any():
                    result.errors.append(
                        _issue(
                            "above_maximum",
                            spec.name,
                            f"Array values exceed {spec.maximum}.",
                            high.sum(),
                        )
                    )
        elif spec.dtype == "string":
            empty = arrays.map(lambda value: any(not str(item).strip() for item in value.flat))
            if empty.any():
                result.errors.append(
                    _issue(
                        "empty_string",
                        spec.name,
                        "Array field contains empty strings.",
                        empty.sum(),
                    )
                )
    elif spec.dtype in {"float", "integer"}:
        invalid = series.notna() & ~series.map(_is_real_number)
        if invalid.any():
            result.errors.append(
                _issue(
                    "invalid_dtype",
                    spec.name,
                    f"Expected {spec.dtype} values.",
                    invalid.sum(),
                    f"Convert {spec.name!r} to {spec.dtype} explicitly.",
                )
            )
        non_finite = (
            series.notna()
            & ~invalid
            & series.map(lambda value: _is_real_number(value) and not np.isfinite(value))
        )
        if non_finite.any():
            result.errors.append(
                _issue(
                    "non_finite",
                    spec.name,
                    "Field contains NaN or positive or negative infinity.",
                    non_finite.sum(),
                )
            )
        if spec.dtype == "integer":
            fractional = (
                series.notna()
                & ~invalid
                & series.map(
                    lambda value: _is_real_number(value) and np.isfinite(value) and value % 1 != 0
                )
            )
            if fractional.any():
                result.errors.append(
                    _issue(
                        "invalid_integer",
                        spec.name,
                        "Integer field has fractional values.",
                        fractional.sum(),
                    )
                )
        if spec.minimum is not None:
            low = (
                series.notna()
                & ~invalid
                & series.map(lambda value: _is_real_number(value) and value < spec.minimum)
            )
            if low.any():
                result.errors.append(
                    _issue(
                        "below_minimum", spec.name, f"Values are below {spec.minimum}.", low.sum()
                    )
                )
        if spec.maximum is not None:
            high = (
                series.notna()
                & ~invalid
                & series.map(lambda value: _is_real_number(value) and value > spec.maximum)
            )
            if high.any():
                result.errors.append(
                    _issue("above_maximum", spec.name, f"Values exceed {spec.maximum}.", high.sum())
                )
    elif spec.dtype == "string":
        invalid = series.notna() & ~series.map(lambda value: isinstance(value, str))
        if invalid.any():
            result.errors.append(
                _issue("invalid_dtype", spec.name, "Expected string values.", invalid.sum())
            )
        empty = series.map(lambda value: isinstance(value, str) and not value.strip())
        if empty.any():
            result.errors.append(
                _issue("empty_string", spec.name, "Field contains empty strings.", empty.sum())
            )
    elif spec.dtype == "boolean":
        invalid = series.notna() & ~series.map(lambda value: isinstance(value, (bool, np.bool_)))
        if invalid.any():
            result.errors.append(
                _issue("invalid_dtype", spec.name, "Expected boolean values.", invalid.sum())
            )


def _check_units(dataset: Dataset, schema: ProfileSchema, result: ValidationResult) -> None:
    units = dataset.metadata.get("units", {})
    if not isinstance(units, dict):
        result.errors.append(
            _issue(
                "invalid_units_metadata",
                None,
                "Dataset units metadata must be an object mapping field names to units.",
                len(dataset.data),
            )
        )
        return
    for spec in schema.fields:
        if spec.name not in dataset.data or not spec.unit:
            continue
        supplied = units.get(spec.name, spec.unit)
        try:
            if not isinstance(supplied, str) or not supplied.strip():
                raise ValueError("unit must be a non-empty string")
            _UREG.Quantity(1, supplied).to(spec.unit)
        except (DimensionalityError, UndefinedUnitError, TypeError, ValueError) as exc:
            result.errors.append(
                _issue(
                    "unit_incompatible",
                    spec.name,
                    f"Unit {supplied!r} is incompatible with {spec.unit!r}: {exc}",
                    len(dataset.data),
                )
            )


def validate_dataset(
    dataset: Dataset | pd.DataFrame,
    schema: str | ProfileSchema,
    *,
    units: dict[str, str] | None = None,
) -> ValidationResult:
    """Validate declared structure; this never certifies physical correctness."""
    value = dataset if isinstance(dataset, Dataset) else Dataset(dataset)
    contract = load_schema(schema)
    if units is not None:
        value = value.copy()
        value.metadata["units"] = dict(units)
    result = ValidationResult()
    expected = contract.field_map()
    for spec in contract.fields:
        _check_field(value.data, spec, result)
    _check_units(value, contract, result)
    comparable = value.data.map(_make_hashable)
    duplicates = comparable.duplicated(keep=False)
    if duplicates.any():
        result.warnings.append(
            _issue(
                "duplicate_record",
                None,
                "Duplicate records were found.",
                duplicates.sum(),
                "Review whether repeated rows are intentional.",
                severity="warning",
            )
        )
    for spec in contract.fields:
        if spec.index and spec.unique and spec.name in value.data:
            duplicated_index = value.data[spec.name].notna() & value.data[spec.name].duplicated(
                keep=False
            )
            if duplicated_index.any():
                result.errors.append(
                    _issue(
                        "duplicate_index",
                        spec.name,
                        "Index values must be unique.",
                        duplicated_index.sum(),
                    )
                )
    allowed = set(expected)
    for column in value.data.columns:
        is_extension = isinstance(column, str) and column.startswith(contract.extension_prefix)
        if column not in allowed and not is_extension:
            result.errors.append(
                _issue(
                    "undeclared_field",
                    str(column),
                    "Custom fields must use prefix "
                    f"{contract.extension_prefix!r} or be declared in the schema.",
                    len(value.data),
                    "Rename the field or add a complete schema declaration.",
                )
            )
    return result
