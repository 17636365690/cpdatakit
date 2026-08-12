"""Stable data and validation result objects."""

from __future__ import annotations

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
        return Dataset(self.data.copy(deep=True), dict(self.metadata), self.source)


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
    """Structured validation report; validity means schema conformance only."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Whether no schema-conformance errors were found."""
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "valid": self.valid,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "scope_note": (
                "Validation checks declared format constraints; it does not certify "
                "physical or scientific correctness."
            ),
        }
