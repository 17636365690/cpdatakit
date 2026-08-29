from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpdatakit.exceptions import SchemaError
from cpdatakit.model import Dataset
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset


def codes(result) -> set[str]:
    return {item.code for item in [*result.errors, *result.warnings]}


def test_valid_curve(curve: Dataset) -> None:
    assert validate_dataset(curve, "curve").valid


def test_validation_scope_note_describes_domain_workflow(curve: Dataset) -> None:
    assert validate_dataset(curve, "curve").to_dict()["scope_note"] == (
        "Validation reports declared format constraints; physical or scientific interpretation "
        "remains part of the domain workflow."
    )


def test_duplicate_detection_supports_pandas_without_dataframe_map(
    curve: Dataset, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(pd.DataFrame, "map", raising=False)

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


def test_duplicate_index_finding_includes_actionable_suggestion(curve: Dataset) -> None:
    curve.data.loc[2, "step"] = 0

    result = validate_dataset(curve, "curve")

    issue = next(item for item in result.errors if item.code == "duplicate_index")
    assert issue.suggestion == "Review whether repeated index values are intentional."


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


def test_unsupported_schema_version_is_rejected(tmp_path) -> None:
    schema = tmp_path / "unsupported-version.json"
    schema.write_text('{"profile":"curve","schema_version":"2.0","fields":[]}', encoding="utf-8")
    with pytest.raises(SchemaError, match="Unsupported schema version"):
        load_schema(schema)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ('{"name":"value","dtype":"decimal","unit":"1"}', "unsupported dtype"),
        ('{"name":"value","dtype":"float","shape":"2","unit":"1"}', "shape"),
    ],
)
def test_malformed_field_schema_is_rejected(tmp_path, field: str, message: str) -> None:
    schema = tmp_path / "malformed.json"
    schema.write_text(
        f'{{"profile":"point","schema_version":"1.0","fields":[{field}]}}',
        encoding="utf-8",
    )
    with pytest.raises(SchemaError, match=message):
        validate_dataset(pd.DataFrame({"value": [1]}), schema)


def test_boolean_schema_enforces_boolean_values(tmp_path) -> None:
    schema = tmp_path / "boolean.json"
    schema.write_text(
        '{"profile":"point","schema_version":"1.0","fields":['
        '{"name":"flag","dtype":"boolean","required":true,"unit":null}]}',
        encoding="utf-8",
    )
    assert validate_dataset(pd.DataFrame({"flag": [True, False]}), schema).valid
    assert "invalid_dtype" in codes(
        validate_dataset(pd.DataFrame({"flag": ["not boolean"]}), schema)
    )


@pytest.mark.parametrize("value", [True, 1 + 0j, pd.Timestamp("2026-08-17")])
def test_scalar_numeric_fields_reject_non_real_values(value) -> None:
    dataset = pd.DataFrame({"step": [0], "strain": [0.0], "stress": [value]})
    assert "invalid_dtype" in codes(validate_dataset(dataset, "curve"))


def test_shaped_numeric_fields_enforce_ranges_and_integer_values(tmp_path) -> None:
    schema = tmp_path / "arrays.json"
    schema.write_text(
        '{"profile":"point","schema_version":"1.0","fields":['
        '{"name":"vector","dtype":"float","required":true,"shape":[2],'
        '"unit":"1","minimum":0,"maximum":1},'
        '{"name":"indices","dtype":"integer","required":true,"shape":[2],"unit":"1"}]}',
        encoding="utf-8",
    )
    dataset = pd.DataFrame({"vector": [[-1.0, 0.5], [0.5, 2.0]], "indices": [[0, 1], [2, 3.5]]})
    assert {"below_minimum", "above_maximum", "invalid_integer"}.issubset(
        codes(validate_dataset(dataset, schema))
    )


def test_nested_extension_values_do_not_crash_duplicate_detection() -> None:
    matrix = np.array([[1.0, 2.0], [3.0, 4.0]])
    dataset = pd.DataFrame(
        {
            "step": [0, 0],
            "strain": [0.0, 0.0],
            "stress": [1.0, 1.0],
            "user_metadata": [{"matrix": matrix}, {"matrix": matrix.copy()}],
        }
    )
    assert "duplicate_record" in codes(validate_dataset(dataset, "curve"))
