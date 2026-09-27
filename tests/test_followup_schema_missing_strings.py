"""String missing-value declarations are rejected at the shared schema boundary."""

import json

import pytest

from cpdatakit.exceptions import SchemaError
from cpdatakit.schema import (
    FieldSchema,
    ProfileSchema,
    load_schema,
    make_field_schema,
    validate_schema,
)


@pytest.mark.parametrize("entry", ["factory", "mapping", "json"])
def test_schema_rejects_missing_text_declarations_with_field_and_action(tmp_path, entry):
    payload = {
        "profile": "stages",
        "schema_version": "1.0",
        "fields": [{"name": "stage", "dtype": "string", "allow_missing": True}],
    }
    with pytest.raises(SchemaError) as caught:
        if entry == "factory":
            make_field_schema("stage", "string", allow_missing=True)
        elif entry == "mapping":
            validate_schema(payload)
        else:
            path = tmp_path / "schema.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            load_schema(path)
    message = str(caught.value)
    assert "stage" in message
    assert "string" in message
    assert "allow_missing" in message
    assert "validation" in message
    assert "allow_missing=False" in message


def test_string_without_missing_and_numeric_missing_declarations_remain_valid():
    assert make_field_schema("stage", "string").allow_missing is False
    field = make_field_schema("time", "float", unit="s", allow_missing=True)
    assert field.allow_missing is True


def test_raw_historical_declaration_is_rechecked_at_public_schema_boundary():
    historical = ProfileSchema(
        "stages", "1.0", (FieldSchema("stage", "string", allow_missing=True),)
    )
    with pytest.raises(SchemaError, match="stage"):
        validate_schema(historical)
