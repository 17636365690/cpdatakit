from __future__ import annotations

import json

import pytest

from cpdatakit.exceptions import SchemaError
from cpdatakit.schema import (
    FieldSchema,
    describe_schema,
    load_schema,
    make_field_schema,
    make_profile_schema,
    schema_to_dict,
    schema_to_json,
    validate_schema,
    write_schema,
)


def test_schema_authoring_round_trip_and_documentation(tmp_path) -> None:
    schema = make_profile_schema(
        "point",
        [
            make_field_schema(
                "point_id", "integer", required=True, unit="dimensionless", index=True, unique=True
            ),
            make_field_schema(
                "stress",
                "float",
                required=True,
                shape=[2, 2],
                components=["xx", "xy", "yx", "yy"],
                unit="MPa",
            ),
        ],
        conventions={"stress_measure": "Cauchy stress"},
    )
    output = tmp_path / "point-tensor.json"
    write_schema(schema, output)
    loaded = load_schema(output)
    assert loaded.fields[1].components == ("xx", "xy", "yx", "yy")
    assert schema_to_dict(loaded)["fields"][1]["shape"] == [2, 2]
    assert json.loads(schema_to_json(loaded))["profile"] == "point"
    assert "Cauchy stress" in describe_schema(loaded)
    with pytest.raises(SchemaError, match="already exists"):
        write_schema(schema, output)


def test_field_schema_normalizes_collection_fields_to_tuples() -> None:
    field = FieldSchema(
        "stress",
        "float",
        shape=[2],
        components=["x", "y"],
        aliases=["sigma"],
        unit="MPa",
    )
    assert field.shape == (2,)
    assert field.components == ("x", "y")
    assert field.aliases == ("sigma",)
    with pytest.raises(AttributeError):
        field.shape += (3,)
    with pytest.raises(AttributeError):
        field.components.append("z")


def test_schema_json_keeps_collection_fields_as_lists() -> None:
    schema = make_profile_schema(
        "point",
        [
            make_field_schema(
                "vector", "float", shape=[2], components=["x", "y"], unit="MPa"
            )
        ],
    )
    payload = schema_to_dict(schema)
    assert payload["fields"][0]["shape"] == [2]
    assert payload["fields"][0]["components"] == ["x", "y"]


def test_tensor_component_count_is_checked() -> None:
    with pytest.raises(SchemaError, match="expected 4"):
        make_field_schema(
            "stress",
            "float",
            shape=[2, 2],
            components=["xx", "xy", "yy"],
            unit="MPa",
        )


def test_validate_schema_accepts_json_like_mapping() -> None:
    schema = validate_schema(
        {
            "profile": "point",
            "schema_version": "1.0",
            "fields": [{"name": "value", "dtype": "float", "unit": "1"}],
        }
    )
    assert schema.profile == "point"
