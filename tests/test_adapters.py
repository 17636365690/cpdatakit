from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import cpdatakit.adapters as adapters
from cpdatakit.adapters import DatasetAdapter
from cpdatakit.exceptions import AdapterError
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


def test_old_style_adapter_receives_backward_compatible_descriptor_defaults() -> None:
    class FixtureAdapter(DatasetAdapter):
        def load(self, path: Path) -> Dataset:
            return Dataset(pd.DataFrame({"source": [path.name]}))

    info = FixtureAdapter.info()

    assert info.name == "FixtureAdapter"
    assert info.format_name == "FixtureAdapter"
    assert info.capabilities == frozenset({"load"})
    assert FixtureAdapter.detect(Path("fixture.dat")) is False


def test_adapter_registry_registers_resolves_and_detects_without_loading(tmp_path: Path) -> None:
    class FixtureAdapter(DatasetAdapter):
        adapter_name = "fixture"
        format_name = "Fixture records"
        capabilities = frozenset({"detect", "load"})

        @classmethod
        def detect(cls, path: Path) -> bool:
            return path.suffix == ".fixture"

        def load(self, path: Path) -> Dataset:
            return Dataset(pd.DataFrame({"source": [path.name]}))

    registry = adapters.AdapterRegistry()
    registry.register(FixtureAdapter)
    fixture = tmp_path / "records.fixture"
    fixture.write_text("fixture", encoding="utf-8")

    assert registry.get("fixture") is FixtureAdapter
    assert registry.describe() == (FixtureAdapter.info(),)
    assert registry.detect(fixture) == (FixtureAdapter,)
    with pytest.raises(AdapterError, match="already registered"):
        registry.register(FixtureAdapter)
