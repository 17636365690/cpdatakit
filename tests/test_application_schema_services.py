from __future__ import annotations

import json
from pathlib import Path

from cpdatakit.application import (
    SchemaDiffRequest,
    ServiceResult,
    diff_schema_contracts,
)


def _write_schema(path: Path, *, optional: bool = False) -> Path:
    fields = [{"name": "value", "dtype": "float", "required": True, "unit": "1"}]
    if optional:
        fields.append({"name": "optional", "dtype": "float", "unit": "1"})
    path.write_text(
        json.dumps({"profile": "point", "schema_version": "1.0", "fields": fields}),
        encoding="utf-8",
    )
    return path


def test_schema_diff_service_returns_typed_diff_and_relative_artifact(tmp_path: Path) -> None:
    source = _write_schema(tmp_path / "source.json")
    target = _write_schema(tmp_path / "target.json", optional=True)
    output = tmp_path / "reports" / "diff.json"

    result = diff_schema_contracts(
        SchemaDiffRequest(
            source=source,
            target=target,
            format="json",
            output=output,
            workspace=tmp_path,
        )
    )

    assert isinstance(result, ServiceResult)
    assert result.ok
    assert result.value is not None
    assert result.value.diff["classification"] == "backward-compatible"
    assert result.value.rendered.endswith("\n")
    assert result.artifact == "reports/diff.json"
    assert output.exists()
    assert str(tmp_path) not in json.dumps(result.to_dict())


def test_schema_diff_service_renders_without_writing_when_output_is_absent(tmp_path: Path) -> None:
    source = _write_schema(tmp_path / "source.json")
    target = _write_schema(tmp_path / "target.json", optional=True)

    result = diff_schema_contracts(
        SchemaDiffRequest(source=source, target=target, format="markdown")
    )

    assert result.ok
    assert result.value is not None
    assert result.artifact is None
    assert result.value.rendered.startswith("# CPDataKit Schema Diff")


def test_schema_diff_service_preserves_existing_output_without_force(tmp_path: Path) -> None:
    source = _write_schema(tmp_path / "source.json")
    target = _write_schema(tmp_path / "target.json", optional=True)
    output = tmp_path / "diff.json"
    request = SchemaDiffRequest(source=source, target=target, output=output)

    assert diff_schema_contracts(request).ok
    output.write_text("sentinel", encoding="utf-8")
    result = diff_schema_contracts(request)

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "output_exists"
    assert output.read_text(encoding="utf-8") == "sentinel"


def test_schema_diff_service_sanitizes_bad_schema_errors(tmp_path: Path) -> None:
    source = _write_schema(tmp_path / "source.json")
    target = tmp_path / "bad.json"
    target.write_text('{"profile":"point","schema_version":"2.0","fields":[]}', encoding="utf-8")

    result = diff_schema_contracts(SchemaDiffRequest(source=source, target=target))

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "schema_error"
    assert str(tmp_path) not in result.error.message
