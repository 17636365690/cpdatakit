from __future__ import annotations

import json

import pytest

from cpdatakit.exceptions import SchemaError
from cpdatakit.schema import make_field_schema, make_profile_schema, schema_sha256
from cpdatakit.schema_diff import diff_schemas


def _point_schema(
    *,
    value_dtype: str = "float",
    value_shape: tuple[int, ...] = (),
    value_components: tuple[str, ...] = (),
    value_unit: str | None = "1",
    value_required: bool = True,
    value_aliases: tuple[str, ...] = (),
    value_minimum: float | None = None,
    value_index: bool = False,
    conventions: dict[str, object] | None = None,
    extension_prefix: str = "user_",
):
    return make_profile_schema(
        "point",
        [
            make_field_schema(
                "value",
                value_dtype,  # type: ignore[arg-type]
                required=value_required,
                shape=value_shape,
                components=value_components,
                unit=value_unit,
                aliases=value_aliases,
                minimum=value_minimum,
                index=value_index,
            ),
        ],
        conventions=conventions,
        extension_prefix=extension_prefix,
    )


def test_diff_schemas_identical_result_is_deterministic() -> None:
    result = diff_schemas("curve", "curve")

    assert result["classification"] == "identical"
    assert result["source"]["sha256"] == schema_sha256("curve")
    assert result["target"]["sha256"] == schema_sha256("curve")
    assert result["fields"] == {"added": [], "removed": [], "changed": []}
    assert result["conventions_changed"] == []
    assert result["extension_prefix_changed"] is False
    assert result["requires_explicit_data_mapping"] is False
    assert json.dumps(result, sort_keys=True, allow_nan=False) == json.dumps(
        result, sort_keys=True, allow_nan=False
    )


def test_diff_schemas_accepts_safe_optional_changes() -> None:
    source = _point_schema()
    target = make_profile_schema(
        "point",
        [
            make_field_schema(
                "value",
                "float",
                required=True,
                unit="1",
                aliases=["measurement"],
                description="Updated description",
            ),
            make_field_schema("optional", "float", unit="1"),
        ],
    )

    result = diff_schemas(source, target)

    assert result["classification"] == "backward-compatible"
    assert result["fields"]["added"] == ["optional"]
    assert result["fields"]["removed"] == []
    assert result["fields"]["changed"] == [{"name": "value", "changes": ["aliases", "description"]}]
    assert result["requires_explicit_data_mapping"] is False


@pytest.mark.parametrize(
    ("target_kwargs", "expected_changes"),
    [
        ({"value_dtype": "string", "value_unit": None}, ["dtype", "unit"]),
        ({"value_shape": (2,)}, ["shape"]),
        (
            {"value_shape": (2,), "value_components": ("x", "y")},
            ["shape", "components"],
        ),
        ({"value_unit": "MPa"}, ["unit"]),
        ({"value_minimum": 0.0}, ["minimum"]),
        ({"value_index": True}, ["index"]),
    ],
)
def test_diff_schemas_classifies_field_changes_as_breaking(
    target_kwargs: dict[str, object], expected_changes: list[str]
) -> None:
    source = _point_schema()
    target = _point_schema(**target_kwargs)

    result = diff_schemas(source, target)

    assert result["classification"] == "breaking"
    assert result["requires_explicit_data_mapping"] is True
    assert result["fields"]["changed"] == [{"name": "value", "changes": expected_changes}]


def test_diff_schemas_classifies_convention_changes_as_breaking() -> None:
    result = diff_schemas(_point_schema(), _point_schema(conventions={"measure": "explicit"}))

    assert result["classification"] == "breaking"
    assert result["conventions_changed"] == ["measure"]
    assert result["requires_explicit_data_mapping"] is True


def test_diff_schemas_classifies_extension_prefix_changes_as_breaking() -> None:
    result = diff_schemas(_point_schema(), _point_schema(extension_prefix="custom_"))

    assert result["classification"] == "breaking"
    assert result["extension_prefix_changed"] is True
    assert result["requires_explicit_data_mapping"] is True


def test_diff_schemas_represents_rename_as_explicit_addition_and_removal() -> None:
    source = _point_schema()
    target = make_profile_schema(
        "point",
        [make_field_schema("measurement", "float", required=True, unit="1")],
    )

    result = diff_schemas(source, target)

    assert result["classification"] == "breaking"
    assert result["fields"]["removed"] == ["value"]
    assert result["fields"]["added"] == ["measurement"]
    assert result["requires_explicit_data_mapping"] is True


def test_diff_schemas_rejects_unsupported_schema_version() -> None:
    with pytest.raises(SchemaError, match="Unsupported schema version"):
        diff_schemas("curve", {"profile": "curve", "schema_version": "2.0", "fields": []})


def test_diff_schemas_is_exported_from_package_root() -> None:
    import cpdatakit

    assert cpdatakit.diff_schemas is diff_schemas
