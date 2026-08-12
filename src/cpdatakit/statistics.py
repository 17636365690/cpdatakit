"""Descriptive summaries bounded by a declared schema."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .model import Dataset, ValidationResult
from .schema import ProfileSchema, load_schema
from .validation import validate_dataset


def summarize_dataset(
    dataset: Dataset | pd.DataFrame,
    schema: str | ProfileSchema,
    *,
    validation: ValidationResult | None = None,
) -> dict[str, Any]:
    """Summarize declared data without inventing unavailable quantities."""
    value = dataset if isinstance(dataset, Dataset) else Dataset(dataset)
    contract = load_schema(schema)
    report = validation or validate_dataset(value, contract)
    numeric: dict[str, Any] = {}
    missing: dict[str, int | str] = {}
    infinite: dict[str, int | str] = {}
    for spec in contract.fields:
        if spec.name not in value.data:
            missing[spec.name] = "not available"
            infinite[spec.name] = "not available"
            if spec.dtype in {"float", "integer"}:
                numeric[spec.name] = "not available"
            continue
        series = value.data[spec.name]
        missing[spec.name] = int(series.isna().sum())
        if spec.dtype in {"float", "integer"}:
            values = pd.to_numeric(series, errors="coerce")
            finite = values[np.isfinite(values)]
            infinite[spec.name] = int((values.notna() & ~np.isfinite(values)).sum())
            numeric[spec.name] = (
                {
                    "min": float(finite.min()),
                    "max": float(finite.max()),
                    "mean": float(finite.mean()),
                    "std": float(finite.std(ddof=0)),
                }
                if not finite.empty
                else "not available"
            )
    return {
        "record_count": len(value.data),
        "field_count": len(value.data.columns),
        "unique_grains": (
            int(value.data["grain_id"].nunique(dropna=True))
            if "grain_id" in value.data
            else "not available"
        ),
        "unique_phases": (
            int(value.data["phase_id"].nunique(dropna=True))
            if "phase_id" in value.data
            else "not available"
        ),
        "numeric_fields": numeric,
        "missing_values": missing,
        "infinite_values": infinite,
        "quality_status": "valid" if report.valid else "invalid",
        "error_count": len(report.errors),
        "warning_count": len(report.warnings),
        "scope_note": "Schema conformance is not evidence of physical correctness.",
    }
