from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cpdatakit.model import Dataset


@pytest.fixture
def curve() -> Dataset:
    return Dataset(
        pd.DataFrame(
            {"step": [0, 1, 2], "strain": [0.0, 0.01, 0.02], "stress": [0.0, 100.0, 180.0]}
        ),
        {"units": {"step": "dimensionless", "strain": "dimensionless", "stress": "MPa"}},
    )


@pytest.fixture
def curve_csv(tmp_path: Path) -> Path:
    path = tmp_path / "curve.CSV"
    pd.DataFrame({"step": [0, 1], "strain": [0.0, 0.01], "stress": [0.0, 100.0]}).to_csv(
        path, index=False
    )
    return path
