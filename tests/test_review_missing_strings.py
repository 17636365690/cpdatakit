"""Missing text is diagnosed consistently before conversion starts."""

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from cpdatakit.cli import main
from cpdatakit.exceptions import DataValidationError
from cpdatakit.io import write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import FieldSchema, ProfileSchema, schema_to_json
from cpdatakit.validation import validate_dataset


def _schema(allow_missing):
    return ProfileSchema(
        "stages", "1.0", (FieldSchema("stage", "string", allow_missing=allow_missing),)
    )


@pytest.fixture
def legacy_schema_acceptance(monkeypatch, allow_missing):
    """Replay an accepted legacy declaration through real data validation and storage."""
    if allow_missing:
        import cpdatakit.schema as schema_module

        validate_field = schema_module._validate_field

        def accept_historical_field(item):
            checked = (
                replace(item, allow_missing=False)
                if item.dtype == "string" and item.allow_missing
                else item
            )
            validate_field(checked)

        monkeypatch.setattr(schema_module, "_validate_field", accept_historical_field)


@pytest.mark.parametrize("allow_missing", [True, False])
@pytest.mark.parametrize("missing", [None, pd.NA, np.nan])
def test_missing_text_validation_and_writer_agree(
    tmp_path, allow_missing, missing, legacy_schema_acceptance
):
    value = Dataset(pd.DataFrame({"stage": pd.Series(["heat", missing], dtype=object)}))
    schema = _schema(allow_missing)
    result = validate_dataset(value, schema)
    assert not result.valid
    issue = next(issue for issue in result.errors if issue.field == "stage")
    assert issue.affected_records == 1
    assert issue.suggestion
    assert "permit missing" not in issue.suggestion
    if allow_missing:
        assert issue.code == "missing_string_value"
        assert "stage" in issue.message
    target = tmp_path / "stages.h5"
    with pytest.raises(DataValidationError):
        write_hdf5(value, target, schema, result)
    assert not target.exists()


@pytest.mark.parametrize("allow_missing", [True, False])
@pytest.mark.parametrize("suffix", ["csv", "json"])
def test_cli_missing_text_is_invalid_before_conversion(
    tmp_path, allow_missing, suffix, legacy_schema_acceptance
):
    source = tmp_path / f"stages.{suffix}"
    source.write_text(
        'stage\nheat\n""\n' if suffix == "csv" else '[{"stage":"heat"},{"stage":null}]',
        encoding="utf-8",
    )
    schema = tmp_path / "schema.json"
    schema.write_text(schema_to_json(_schema(allow_missing)), encoding="utf-8")
    validation = tmp_path / "validation.json"
    assert (
        main(["validate", str(source), "--schema", str(schema), "--json-output", str(validation)])
        == 1
    )
    payload = json.loads(validation.read_text(encoding="utf-8"))
    assert payload["valid"] is False
    assert payload["errors"][0]["field"] == "stage"
    target = tmp_path / "stages.h5"
    assert main(["convert", str(source), "--schema", str(schema), "--output", str(target)]) != 0
    assert not target.exists()


@pytest.mark.parametrize("allow_missing", [True, False])
def test_complete_text_still_validates_and_round_trips(
    tmp_path, allow_missing, legacy_schema_acceptance
):
    from cpdatakit.io import load_hdf5

    value = Dataset(pd.DataFrame({"stage": ["heat", "冷却"]}))
    schema = _schema(allow_missing)
    result = validate_dataset(value, schema)
    assert result.valid
    target = tmp_path / "stages.h5"
    write_hdf5(value, target, schema, result)
    assert load_hdf5(target).data["stage"].tolist() == ["heat", "冷却"]
