"""Deterministic synthetic sample-data generation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def generate_sample_data(output: str | Path) -> None:
    """Write all synthetic CPDataKit demonstration datasets with a fixed seed."""
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20250812)
    strain = np.linspace(0, 0.18, 61)
    stress = 260 * (1 - np.exp(-22 * strain)) + 410 * strain
    pd.DataFrame({"step": np.arange(len(strain)), "strain": strain, "stress": stress}).to_csv(
        target / "synthetic_curve.csv", index=False
    )

    grid_x, grid_y = np.meshgrid(np.linspace(0, 9, 10), np.linspace(0, 7, 8))
    grain = rng.integers(0, 12, grid_x.size)
    records = [
        {
            "x": float(x),
            "y": float(y),
            "value": float(grain_id),
            "grain_id": int(grain_id),
            "phase_id": int(grain_id % 3),
        }
        for x, y, grain_id in zip(grid_x.ravel(), grid_y.ravel(), grain, strict=True)
    ]
    (target / "synthetic_field2d.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )

    pd.DataFrame(
        {
            "point_id": [0, -1, 2, 2],
            "grain_id": [0, 1, np.nan, 3],
            "phase_id": [0, 1, 1, 1],
            "x": [0.0, 1.0, 2.0, np.inf],
            "user_note": ["demo"] * 4,
        }
    ).to_csv(target / "intentionally_invalid_point.csv", index=False)
