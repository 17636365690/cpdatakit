from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cpdatakit.application import (
    ConvertRequest,
    DatasetRequest,
    ImportInspectRequest,
    ReadLimits,
    ResolveSchemaRequest,
    ServiceResult,
    convert_and_write,
    import_and_inspect,
    resolve_schema_and_mapping,
    validate_and_summarize,
)
from cpdatakit.cli import main
from cpdatakit.io import load_dataset


def _write_curve(path: Path, *, invalid: bool = False) -> Path:
    frame = pd.DataFrame(
        {
            "step": [-1, 1, 2] if invalid else [0, 1, 2],
            "strain": [0.0, 0.01, 0.02],
            "stress": [0.0, 100.0, 180.0],
        }
    )
    frame.to_csv(path, index=False)
    return path


def test_import_and_inspect_returns_a_typed_success_without_absolute_paths(tmp_path: Path) -> None:
    data = _write_curve(tmp_path / "curve.csv")

    result = import_and_inspect(ImportInspectRequest(data=data, schema="curve"))

    assert isinstance(result, ServiceResult)
    assert result.ok
    assert result.operation == "import_and_inspect"
    assert result.value is not None
    assert result.value["file"]["filename"] == "curve.csv"
    assert str(tmp_path) not in json.dumps(result.to_dict())


def test_import_and_inspect_rejects_a_record_limit_before_returning_data(tmp_path: Path) -> None:
    data = _write_curve(tmp_path / "curve.csv")

    result = import_and_inspect(
        ImportInspectRequest(data=data, schema="curve", read_limits=ReadLimits(max_records=2))
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "read_limit_exceeded"
    assert str(tmp_path) not in result.error.message


def test_resolve_schema_and_mapping_returns_explicit_typed_mapping(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {"source": "increment", "target": "step"},
                    {"source": "eps", "target": "strain"},
                ],
                "drop_unmapped": True,
            }
        ),
        encoding="utf-8",
    )

    result = resolve_schema_and_mapping(ResolveSchemaRequest(schema="curve", mapping=mapping))

    assert result.ok
    assert result.value is not None
    assert result.value.schema.profile == "curve"
    assert [item.target for item in result.value.mappings] == ["step", "strain"]
    assert result.value.drop_unmapped is True
    assert result.value.to_dict()["schema"]["schema_version"] == "1.0"


def test_validate_and_summarize_keeps_invalid_data_as_a_successful_operation(
    tmp_path: Path,
) -> None:
    data = _write_curve(tmp_path / "invalid.csv", invalid=True)

    result = validate_and_summarize(DatasetRequest(data=data, schema="curve"))

    assert result.ok
    assert result.value is not None
    assert result.value.validation.valid is False
    assert result.value.summary["quality_status"] == "invalid"
    assert any(issue.code == "below_minimum" for issue in result.value.validation.errors)


def test_convert_and_write_returns_workspace_relative_v1_artifact(tmp_path: Path) -> None:
    data = _write_curve(tmp_path / "curve.csv")
    output = tmp_path / "artifacts" / "curve.h5"

    result = convert_and_write(
        ConvertRequest(data=data, schema="curve", output=output, workspace=tmp_path)
    )

    assert result.ok
    assert result.artifact == "artifacts/curve.h5"
    assert result.value is not None
    assert result.value.artifact == "artifacts/curve.h5"
    assert load_dataset(output).metadata["schema_version"] == "1.0"
    assert str(tmp_path) not in json.dumps(result.to_dict())


def test_convert_and_write_reports_validation_failure_without_creating_output(
    tmp_path: Path,
) -> None:
    data = _write_curve(tmp_path / "invalid.csv", invalid=True)
    output = tmp_path / "artifacts" / "invalid.h5"

    result = convert_and_write(
        ConvertRequest(data=data, schema="curve", output=output, workspace=tmp_path)
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "validation_failed"
    assert result.value is not None and not result.value.validation.valid
    assert not output.exists()


def test_expected_service_errors_are_stable_and_sanitized(tmp_path: Path) -> None:
    result = validate_and_summarize(
        DatasetRequest(data=tmp_path / "missing.csv", schema="curve", workspace=tmp_path)
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "data_read_error"
    assert result.error.action
    assert str(tmp_path) not in result.error.message


def test_cli_validate_uses_service_error_sanitization_without_changing_exit_code(
    tmp_path: Path, capsys
) -> None:
    missing = tmp_path / "missing.csv"

    assert main(["validate", str(missing), "--schema", "curve"]) == 2

    assert str(tmp_path) not in capsys.readouterr().err
