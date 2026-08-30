"""Stable data and validation result objects."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd


@dataclass(slots=True)
class Dataset:
    """A tabular dataset plus explicit metadata and optional source path."""

    data: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None

    def copy(self) -> Dataset:
        """Return a deep-enough copy for safe normalization."""
        return Dataset(self.data.copy(deep=True), deepcopy(self.metadata), self.source)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One actionable validation finding."""

    code: str
    field: str | None
    message: str
    affected_records: int
    suggestion: str | None = None
    severity: Literal["error", "warning"] = "error"


@dataclass(slots=True)
class ValidationResult:
    """Structured validation report for the declared schema."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Whether the declared schema checks found zero errors."""
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "valid": self.valid,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "scope_note": (
                "Validation reports declared format constraints; physical or scientific "
                "interpretation remains part of the domain workflow."
            ),
        }
