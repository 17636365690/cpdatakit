from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cpdatakit.adapters import DatasetAdapter
from cpdatakit.model import Dataset


def test_dataset_adapter_is_abstract() -> None:
    with pytest.raises(TypeError):
        DatasetAdapter()


def test_dataset_adapter_load_contract_returns_dataset(tmp_path: Path) -> None:
    class FixtureAdapter(DatasetAdapter):
        def load(self, path: Path) -> Dataset:
            return Dataset(pd.DataFrame({"source": [path.name]}), {"units": {}})

    result = FixtureAdapter().load(tmp_path / "fixture.dat")
    assert isinstance(result, Dataset)
    assert result.data["source"].tolist() == ["fixture.dat"]
