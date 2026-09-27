"""Effective units keep their declaration or schema-assumption provenance."""

import json

import h5py
import pandas as pd
import pytest

from cpdatakit.comparison import compare_reports, render_comparison_markdown
from cpdatakit.exceptions import DataReadError
from cpdatakit.inspection import inspect_dataset, render_inspection_text
from cpdatakit.io import load_dataset, load_hdf5, write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.normalization import FieldMapping, normalize_dataset
from cpdatakit.reporting import build_report, render_report_html, render_report_markdown
from cpdatakit.schema import make_field_schema, make_profile_schema
from cpdatakit.validation import validate_dataset


@pytest.fixture
def schema():
    return make_profile_schema(
        "stages",
        [make_field_schema("time", "float", unit="s"), make_field_schema("stage", "string")],
    )


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("time,stage\n0,heat\n1,cool\n", encoding="utf-8")
    return path


def _write(value, target, schema):
    write_hdf5(value, target, schema, validate_dataset(value, schema))
    return target


def test_undeclared_csv_unit_warns_without_invalidating(source, schema):
    result = validate_dataset(load_dataset(source), schema)
    assert result.valid
    issue = next(item for item in result.warnings if item.code == "unit_not_declared")
    assert issue.severity == "warning"
    assert issue.field == "time"
    assert issue.affected_records == 2
    assert "s" in issue.message
    assert issue.suggestion
    assert result.errors == []


def test_declared_source_unit_is_preserved(source, schema, tmp_path):
    value = load_dataset(source)
    value.metadata["units"] = {"time": "ms"}
    result = validate_dataset(value, schema)
    assert result.valid
    assert not any(item.code == "unit_not_declared" for item in result.warnings)
    target = _write(value, tmp_path / "declared.h5", schema)
    restored = load_hdf5(target)
    assert restored.metadata["units"]["time"] == "ms"
    assert restored.metadata["units_source"]["time"] == "declared"
    assert restored.data["time"].tolist() == [0, 1]


def test_assumed_units_remain_assumed_across_read_and_rewrite(source, schema, tmp_path):
    target = _write(load_dataset(source), tmp_path / "assumed.h5", schema)
    with h5py.File(target) as handle:
        assert json.loads(handle.attrs["units_json"]) == {"stage": None, "time": "s"}
        assert json.loads(handle.attrs["units_source_json"]) == {
            "stage": "unspecified",
            "time": "assumed",
        }
        assert handle.attrs["format_version"] == "1.0"
    restored = load_hdf5(target)
    assert restored.metadata["units_source"]["time"] == "assumed"
    assert any(
        issue.code == "unit_not_declared" for issue in validate_dataset(restored, schema).warnings
    )
    second = _write(restored, tmp_path / "second.h5", schema)
    assert load_hdf5(second).metadata["units_source"]["time"] == "assumed"


def test_legacy_file_unit_origin_is_unknown_and_stays_readable(source, schema, tmp_path):
    target = _write(load_dataset(source), tmp_path / "legacy.h5", schema)
    with h5py.File(target, "r+") as handle:
        if "units_source_json" in handle.attrs:
            del handle.attrs["units_source_json"]
    restored = load_hdf5(target)
    assert restored.data["stage"].tolist() == ["heat", "cool"]
    assert restored.metadata["units"] == {"stage": None, "time": "s"}
    assert restored.metadata["units_source"]["time"] == "unknown"
    assert validate_dataset(restored, schema).valid


@pytest.mark.parametrize("payload", ["[]", '{"time":"invented"}'])
def test_invalid_unit_source_metadata_is_a_read_error(source, schema, tmp_path, payload):
    target = _write(load_dataset(source), tmp_path / "invalid.h5", schema)
    with h5py.File(target, "r+") as handle:
        handle.attrs["units_source_json"] = payload
    with pytest.raises(DataReadError, match="units_source"):
        load_hdf5(target)


def test_inspection_and_reports_show_assumed_and_declared_units(source, schema, tmp_path):
    assumed = _write(load_dataset(source), tmp_path / "assumed.h5", schema)
    value = load_dataset(source)
    value.metadata["units"] = {"time": "s"}
    declared = _write(value, tmp_path / "declared.h5", schema)
    for path, origin in ((source, "assumed"), (assumed, "assumed"), (declared, "declared")):
        inspection = inspect_dataset(path, schema=schema)
        field = next(item for item in inspection["fields"] if item["name"] == "time")
        assert field["unit"] == "s"
        assert field["unit_source"] == origin
        assert origin in render_inspection_text(inspection)
        report = build_report(path, schema)
        field = next(item for item in report["fields"] if item["name"] == "time")
        assert field["unit_source"] == origin
        assert origin in render_report_markdown(report)
        assert origin in render_report_html(report)
    comparison = compare_reports(build_report(assumed, schema), build_report(declared, schema))
    assert comparison["units"]["left"]["time"] == {"unit": "s", "source": "assumed"}
    assert comparison["units"]["right"]["time"] == {"unit": "s", "source": "declared"}
    rendered = render_comparison_markdown(comparison)
    assert "assumed" in rendered and "declared" in rendered


def test_explicit_mapping_declares_units_and_rename_preserves_assumptions(schema):
    raw = Dataset(pd.DataFrame({"seconds": [0.0, 1.0], "stage": ["heat", "cool"]}))
    explicit = normalize_dataset(raw, schema, [FieldMapping("seconds", "time", "s", "s")])
    assert not any(
        issue.code == "unit_not_declared" for issue in validate_dataset(explicit, schema).warnings
    )
    raw.metadata = {"units": {"seconds": "s"}, "units_source": {"seconds": "assumed"}}
    renamed = normalize_dataset(raw, schema, [FieldMapping("seconds", "time")])
    assert renamed.metadata["units_source"] == {"time": "assumed"}
    assert any(
        issue.code == "unit_not_declared" for issue in validate_dataset(renamed, schema).warnings
    )


@pytest.mark.parametrize("origins", [None, [], {"time": "invented"}, {"time": ["declared"]}])
def test_invalid_unit_origins_are_rejected_before_publication(source, schema, tmp_path, origins):
    from cpdatakit.exceptions import DataValidationError
    from cpdatakit.model import ValidationResult

    value = load_dataset(source)
    value.metadata.update(units={"time": "s"}, units_source=origins)
    result = validate_dataset(value, schema)
    assert not result.valid
    assert any(issue.code == "invalid_units_source" for issue in result.errors)
    target = tmp_path / "preserved.h5"
    target.write_bytes(b"previous complete output")
    with pytest.raises(DataValidationError, match="units_source"):
        write_hdf5(value, target, schema, ValidationResult(), force=True, allow_invalid=True)
    assert target.read_bytes() == b"previous complete output"
