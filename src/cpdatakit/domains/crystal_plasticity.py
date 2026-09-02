"""Crystal-plasticity-specific descriptive statistics."""

from __future__ import annotations

from ..model import Dataset


def summarize_cp_identifiers(dataset: Dataset) -> dict[str, int | str]:
    """Return grain and phase counts for compatible CP profiles."""
    return {
        "unique_grains": (
            int(dataset.data["grain_id"].nunique(dropna=True))
            if "grain_id" in dataset.data
            else "not available"
        ),
        "unique_phases": (
            int(dataset.data["phase_id"].nunique(dropna=True))
            if "phase_id" in dataset.data
            else "not available"
        ),
    }
