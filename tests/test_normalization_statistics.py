from __future__ import annotations

import pandas as pd
import pytest

from cpdatakit.exceptions import NormalizationError
from cpdatakit.model import Dataset
from cpdatakit.normalization import FieldMapping, normalize_dataset
from cpdatakit.statistics import summarize_dataset


def test_normalize_explicit_mapping_preserves_unmapped() -> None:
    source = Dataset(
        pd.DataFrame(
            {"increment": [0, 1], "eps": [0.0, 0.1], "sigma_pa": [0.0, 1e6], "raw": [7, 8]}
        )
    )
    result = normalize_dataset(
        source,
        "curve",
        [
            FieldMapping("increment", "step", "1", "dimensionless"),
            FieldMapping("eps", "strain", "1", "dimensionless"),
            FieldMapping("sigma_pa", "stress", "Pa", "MPa"),
        ],
    )
    assert result.data["stress"].tolist() == [0.0, 1.0]
    assert "raw" in result.data
    assert "sigma_pa" not in result.data
    assert list(source.data.columns) == ["increment", "eps", "sigma_pa", "raw"]


def test_mapping_conflict_and_units() -> None:
    data = Dataset(pd.DataFrame({"a": [1], "b": [2], "stress": [3]}))
    with pytest.raises(NormalizationError):
        normalize_dataset(data, "curve", [FieldMapping("a", "strain"), FieldMapping("b", "strain")])
    with pytest.raises(NormalizationError):
        normalize_dataset(data, "curve", [FieldMapping("a", "stress")])
    with pytest.raises(NormalizationError):
        normalize_dataset(
            Dataset(pd.DataFrame({"a": [1]})), "curve", [FieldMapping("a", "stress", "s", "MPa")]
        )


def test_dimensionless_unit_conversion_is_cross_version_safe() -> None:
    source = Dataset(pd.DataFrame({"increment": [0, 1]}))
    result = normalize_dataset(
        source,
        "curve",
        [FieldMapping("increment", "step", "1", "dimensionless")],
    )
    assert result.data["step"].tolist() == [0.0, 1.0]


def test_summary_values_and_not_available(curve: Dataset) -> None:
    report = summarize_dataset(curve, "curve")
    assert report["record_count"] == 3
    assert report["numeric_fields"]["stress"]["max"] == 180.0
    assert report["unique_grains"] == "not available"
    assert report["missing_values"]["time"] == "not available"
