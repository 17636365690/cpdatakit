from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpdatakit.exceptions import NormalizationError
from cpdatakit.model import Dataset
from cpdatakit.normalization import FieldMapping, normalize_dataset
from cpdatakit.schema import make_field_schema, make_profile_schema
from cpdatakit.statistics import summarize_dataset


def _shaped_schema(shape: tuple[int, ...]):
    return make_profile_schema(
        "point",
        [make_field_schema("measure", "float", required=True, shape=shape, unit="MPa")],
    )


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


def test_offset_unit_conversion_applies_scale_and_offset(tmp_path) -> None:
    schema = tmp_path / "temperature.json"
    schema.write_text(
        '{"profile":"point","schema_version":"1.0","fields":['
        '{"name":"temperature","dtype":"float","required":true,"unit":"K"}]}',
        encoding="utf-8",
    )
    source = Dataset(pd.DataFrame({"temperature": [0.0, 100.0]}))
    result = normalize_dataset(
        source,
        schema,
        [FieldMapping("temperature", "temperature", "degC", "K")],
    )
    assert result.data["temperature"].tolist() == pytest.approx([273.15, 373.15])
    assert result.metadata["units"]["temperature"] == "K"


def test_summary_values_and_not_available(curve: Dataset) -> None:
    report = summarize_dataset(curve, "curve")
    assert report["record_count"] == 3
    assert report["numeric_fields"]["stress"]["max"] == 180.0
    assert report["unique_grains"] == "not available"
    assert report["missing_values"]["time"] == "not available"


@pytest.mark.parametrize(
    ("shape", "raw", "expected"),
    [
        ((2,), [[1_000_000.0, 2_000_000.0]], [[1.0, 2.0]]),
        (
            (2, 2),
            [[[1_000_000.0, 0.0], [0.0, 2_000_000.0]]],
            [[[1.0, 0.0], [0.0, 2.0]]],
        ),
        (
            (2, 1, 2),
            [[[[1_000_000.0, 0.0]], [[0.0, 2_000_000.0]]]],
            [[[[1.0, 0.0]], [[0.0, 2.0]]]],
        ),
    ],
)
def test_normalize_unit_conversion_preserves_shaped_values(
    shape: tuple[int, ...], raw: list[object], expected: list[object]
) -> None:
    source = Dataset(pd.DataFrame({"measure": raw}), {"units": {"measure": "Pa"}})

    result = normalize_dataset(
        source,
        _shaped_schema(shape),
        [FieldMapping("measure", "measure", "Pa", "MPa", "source specification")],
    )

    assert np.allclose(np.stack(result.data["measure"]), np.asarray(expected))
    assert all(np.asarray(value).shape == shape for value in result.data["measure"])
    assert all(np.asarray(value).dtype == np.dtype("float64") for value in result.data["measure"])
    assert result.metadata["units"]["measure"] == "MPa"
    assert result.metadata["field_mapping"]["measure"] == {
        "target": "measure",
        "input_unit": "Pa",
        "output_unit": "MPa",
        "source_note": "source specification",
    }
    assert source.data["measure"].iloc[0][0] == raw[0][0]
    assert source.metadata["units"]["measure"] == "Pa"


def test_normalize_rejects_wrong_shaped_record_with_position() -> None:
    source = Dataset(pd.DataFrame({"measure": [[[1.0, 2.0]]]}))

    with pytest.raises(
        NormalizationError, match=r"measure.*record 0.*expected shape \(2, 2\)"
    ):
        normalize_dataset(
            source,
            _shaped_schema((2, 2)),
            [FieldMapping("measure", "measure", "Pa", "MPa")],
        )


def test_normalize_rejects_ragged_shaped_record_with_position() -> None:
    source = Dataset(pd.DataFrame({"measure": [[[1.0, 2.0], [3.0]]]}))

    with pytest.raises(
        NormalizationError, match=r"measure.*record 0.*regular numeric array"
    ):
        normalize_dataset(
            source,
            _shaped_schema((2, 2)),
            [FieldMapping("measure", "measure", "Pa", "MPa")],
        )


def test_normalize_rejects_string_shaped_record_with_position() -> None:
    source = Dataset(pd.DataFrame({"measure": [["1", "2"]]}))

    with pytest.raises(NormalizationError, match=r"measure.*record 0.*numeric"):
        normalize_dataset(
            source,
            _shaped_schema((2,)),
            [FieldMapping("measure", "measure", "Pa", "MPa")],
        )
