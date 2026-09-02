from __future__ import annotations

import hashlib
import json

import pytest

from cpdatakit.exceptions import SchemaError
from cpdatakit.schema import (
    FieldSchema,
    describe_schema,
    load_schema,
    make_field_schema,
    make_profile_schema,
    schema_sha256,
    schema_to_canonical_json,
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
        [make_field_schema("vector", "float", shape=[2], components=["x", "y"], unit="MPa")],
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


def test_validate_schema_accepts_non_builtin_profile_name() -> None:
    schema = validate_schema(
        {
            "profile": "thermal-cycle",
            "schema_version": "1.0",
            "fields": [
                {
                    "name": "temperature",
                    "dtype": "float",
                    "required": True,
                    "unit": "K",
                }
            ],
        }
    )

    assert schema.profile == "thermal-cycle"


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("curve", "6234e8cd78f0ad9f0251cd233fd7111f6c62fc17835289ab521369880977fa44"),
        ("point", "c668c4b05cf542ab4c3af8aba7b1b03ebd4a20d49186773b2a5a229f27e6c59b"),
        ("field2d", "766d6ee0e1ad3b2a77d0fdffb3a5aec4274a33490a51315676fb48d57817e4b0"),
    ],
)
def test_builtin_schema_hash_is_a_compatibility_contract(profile: str, expected: str) -> None:
    assert schema_sha256(profile) == expected


def test_schema_canonical_json_and_hash_are_stable() -> None:
    schema = make_profile_schema(
        "point",
        [make_field_schema("value", "float", required=True, unit="MPa")],
        conventions={"z": ["last", "value"], "a": {"measure": "explicit"}},
    )
    canonical = schema_to_canonical_json(schema)

    assert canonical == schema_to_canonical_json(schema_to_dict(schema))
    assert canonical.startswith('{"conventions":')
    assert "\n" not in canonical
    assert canonical.endswith("}")
    assert schema_sha256(schema) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_profile_schema_conventions_are_recursively_immutable() -> None:
    source = {"nested": {"labels": ["Cauchy stress"]}}
    schema = make_profile_schema(
        "point",
        [make_field_schema("point_id", "integer", required=True, unit="1")],
        conventions=source,
    )

    source["nested"]["labels"].append("mutated outside")
    assert schema.conventions["nested"]["labels"] == ("Cauchy stress",)

    with pytest.raises(TypeError):
        schema.conventions["new"] = "value"
    with pytest.raises(TypeError):
        schema.conventions["nested"]["labels"] += ("mutated inside",)


def test_profile_schema_conventions_thaw_to_json_lists() -> None:
    schema = make_profile_schema(
        "point",
        [make_field_schema("point_id", "integer", required=True, unit="1")],
        conventions={"nested": {"labels": ["Cauchy stress"]}},
    )

    assert schema_to_dict(schema)["conventions"] == {"nested": {"labels": ["Cauchy stress"]}}
