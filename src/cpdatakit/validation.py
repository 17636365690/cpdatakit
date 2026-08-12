"""Schema-conformance validation."""

from __future__ import annotations

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


def _numeric_mask(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    converted = pd.to_numeric(series, errors="coerce")
    return converted, series.notna() & converted.isna()


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
    if spec.dtype in {"float", "integer"} and spec.shape:
        invalid_shape = series.notna() & ~series.map(
            lambda value: (
                isinstance(value, (list, tuple, np.ndarray))
                and list(np.asarray(value).shape) == spec.shape
            )
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
        invalid_numeric = valid_values.map(
            lambda value: not np.issubdtype(np.asarray(value).dtype, np.number)
        )
        if invalid_numeric.any():
            result.errors.append(
                _issue(
                    "invalid_dtype",
                    spec.name,
                    f"Expected numeric {spec.dtype} array values.",
                    invalid_numeric.sum(),
                )
            )
        numeric_values = valid_values[~invalid_numeric]
        non_finite = numeric_values.map(lambda value: not np.isfinite(value).all())
        if non_finite.any():
            result.errors.append(
                _issue(
                    "non_finite",
                    spec.name,
                    "Array field contains positive or negative infinity.",
                    non_finite.sum(),
                )
            )
    elif spec.dtype in {"float", "integer"}:
        values, invalid = _numeric_mask(series)
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
        finite = values.notna() & ~np.isfinite(values)
        if finite.any():
            result.errors.append(
                _issue(
                    "non_finite",
                    spec.name,
                    "Field contains positive or negative infinity.",
                    finite.sum(),
                )
            )
        if spec.dtype == "integer":
            fractional = values.notna() & np.isfinite(values) & (values % 1 != 0)
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
            low = values.notna() & (values < spec.minimum)
            if low.any():
                result.errors.append(
                    _issue(
                        "below_minimum", spec.name, f"Values are below {spec.minimum}.", low.sum()
                    )
                )
        if spec.maximum is not None:
            high = values.notna() & (values > spec.maximum)
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
    if spec.shape and spec.dtype not in {"float", "integer"}:
        bad_shape = series.notna() & ~series.map(
            lambda value: (
                isinstance(value, (list, tuple, np.ndarray))
                and list(np.asarray(value).shape) == spec.shape
            )
        )
        if bad_shape.any():
            result.errors.append(
                _issue(
                    "invalid_shape",
                    spec.name,
                    f"Expected per-record shape {spec.shape}.",
                    bad_shape.sum(),
                )
            )


def _check_units(dataset: Dataset, schema: ProfileSchema, result: ValidationResult) -> None:
    units: dict[str, str] = dataset.metadata.get("units", {})
    for spec in schema.fields:
        if spec.name not in dataset.data or not spec.unit:
            continue
        supplied = units.get(spec.name, spec.unit)
        try:
            (1 * _UREG(supplied)).to(spec.unit)
        except (DimensionalityError, UndefinedUnitError) as exc:
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
    comparable = value.data.map(
        lambda item: tuple(item) if isinstance(item, (list, np.ndarray)) else item
    )
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
        if column not in allowed and not column.startswith(contract.extension_prefix):
            result.errors.append(
                _issue(
                    "undeclared_field",
                    column,
                    "Custom fields must use prefix "
                    f"{contract.extension_prefix!r} or be declared in the schema.",
                    len(value.data),
                    "Rename the field or add a complete schema declaration.",
                )
            )
    return result
