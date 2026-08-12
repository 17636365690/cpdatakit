from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpdatakit.exceptions import SchemaError
from cpdatakit.model import Dataset
from cpdatakit.validation import validate_dataset


def codes(result) -> set[str]:
    return {item.code for item in [*result.errors, *result.warnings]}


def test_valid_curve(curve: Dataset) -> None:
    assert validate_dataset(curve, "curve").valid


def test_missing_field_and_units() -> None:
    result = validate_dataset(pd.DataFrame({"step": [0]}), "curve")
    assert "required_field_missing" in codes(result)


def test_dtype_nan_infinity_and_range(curve: Dataset) -> None:
    curve.data.loc[0, "step"] = -1
    curve.data["strain"] = curve.data["strain"].astype(object)
    curve.data.loc[1, "strain"] = "bad"
    curve.data.loc[2, "stress"] = np.inf
    result = validate_dataset(curve, "curve")
    assert {"below_minimum", "invalid_dtype", "non_finite"}.issubset(codes(result))


def test_duplicate_index_and_record(curve: Dataset) -> None:
    curve.data.loc[2] = curve.data.loc[1]
    result = validate_dataset(curve, "curve")
    assert {"duplicate_record", "duplicate_index"}.issubset(codes(result))


def test_units_compatible_and_incompatible(curve: Dataset) -> None:
    curve.metadata["units"]["stress"] = "Pa"
    assert validate_dataset(curve, "curve").valid
    curve.metadata["units"]["stress"] = "second"
    assert "unit_incompatible" in codes(validate_dataset(curve, "curve"))


def test_custom_extension_and_undeclared(curve: Dataset) -> None:
    curve.data["user_temperature"] = 300.0
    assert validate_dataset(curve, "curve").valid
    curve.data["mystery"] = 1.0
    assert "undeclared_field" in codes(validate_dataset(curve, "curve"))


def test_point_indices_and_coordinates() -> None:
    dataset = Dataset(
        pd.DataFrame(
            {"point_id": [0, 0], "grain_id": [1, -1], "phase_id": [0, 1], "x": [0.0, np.inf]}
        ),
        {"units": {"point_id": "1", "grain_id": "1", "phase_id": "1", "x": "um"}},
    )
    assert {"duplicate_index", "below_minimum", "non_finite"}.issubset(
        codes(validate_dataset(dataset, "point"))
    )


def test_repeated_grain_and_phase_ids_are_valid() -> None:
    dataset = Dataset(
        pd.DataFrame({"point_id": [0, 1], "grain_id": [3, 3], "phase_id": [1, 1]}),
        {"units": {"point_id": "1", "grain_id": "1", "phase_id": "1"}},
    )
    assert validate_dataset(dataset, "point").valid


def test_empty_string_and_shape_with_custom_schema(tmp_path) -> None:
    schema = tmp_path / "custom.json"
    schema.write_text(
        '{"profile":"point","schema_version":"1.0","fields":['
        '{"name":"point_id","dtype":"integer","required":true,"index":true,"unit":"dimensionless"},'
        '{"name":"label","dtype":"string","required":true,"unit":null},'
        '{"name":"vector","dtype":"float","required":true,"shape":[3],"unit":"dimensionless"}'
        "]}",
        encoding="utf-8",
    )
    data = Dataset(
        pd.DataFrame({"point_id": [0], "label": [" "], "vector": [[1, 2]]}),
        {"units": {"point_id": "1", "vector": "1"}},
    )
    assert {"empty_string", "invalid_shape"}.issubset(codes(validate_dataset(data, schema)))


def test_numeric_custom_field_requires_unit(tmp_path) -> None:
    schema = tmp_path / "missing-unit.json"
    schema.write_text(
        '{"profile":"curve","schema_version":"1.0","fields":['
        '{"name":"step","dtype":"integer","required":true,"unit":null}]}',
        encoding="utf-8",
    )
    with pytest.raises(SchemaError, match="must declare a unit"):
        validate_dataset(pd.DataFrame({"step": [0]}), schema)
