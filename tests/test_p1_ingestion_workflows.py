"""User-facing ingestion must not validate or publish rounded source integers."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from cpdatakit.application import (
    ConvertRequest,
    DatasetRequest,
    convert_and_write,
    validate_and_summarize,
)
from cpdatakit.application.csv_intake import prepare_csv
from cpdatakit.cli import main
from cpdatakit.exceptions import DataReadError
from cpdatakit.io import load_dataset, write_hdf5
from cpdatakit.validation import validate_dataset
from cpdatakit.web import create_app


@pytest.fixture
def nullable_integer_schema(tmp_path: Path) -> Path:
    path = tmp_path / "measurement-schema.json"
    path.write_text(
        json.dumps(
            {
                "profile": "measurement",
                "schema_version": "1.0",
                "fields": [
                    {
                        "name": "value",
                        "dtype": "integer",
                        "allow_missing": True,
                        "unit": "dimensionless",
                    },
                    {"name": "label", "dtype": "string"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _nullable_source(tmp_path: Path, extension: str) -> Path:
    path = tmp_path / f"measurement.{extension}"
    if extension == "csv":
        path.write_text("value,label\n9007199254740993,试样甲\n,试样乙\n", encoding="utf-8")
    else:
        path.write_text(
            '[{"value":9007199254740993,"label":"试样甲"},{"value":null,"label":"试样乙"}]',
            encoding="utf-8",
        )
    return path


@pytest.mark.parametrize("extension", ["csv", "json"])
def test_nullable_integer_is_exact_before_service_validation(
    tmp_path: Path, nullable_integer_schema: Path, extension: str
) -> None:
    source = _nullable_source(tmp_path, extension)
    original_hash = hashlib.sha256(source.read_bytes()).digest()

    loaded = load_dataset(source)
    # int conversion exposes a rounded float without relying on NumPy scalar equality.
    assert int(loaded.data["value"].iloc[0]) == 9007199254740993
    assert pd.isna(loaded.data["value"].iloc[1])
    assert loaded.data["label"].tolist() == ["试样甲", "试样乙"]
    checked = validate_and_summarize(DatasetRequest(data=source, schema=nullable_integer_schema))
    assert checked.ok, checked.to_dict()
    assert checked.value is not None and checked.value.validation.valid
    assert hashlib.sha256(source.read_bytes()).digest() == original_hash


@pytest.mark.parametrize("extension", ["csv", "json"])
def test_conversion_never_publishes_a_rounded_nullable_integer(
    tmp_path: Path, nullable_integer_schema: Path, extension: str
) -> None:
    source = _nullable_source(tmp_path, extension)
    original_hash = hashlib.sha256(source.read_bytes()).digest()
    output = tmp_path / "output" / "measurement.h5"

    converted = convert_and_write(
        ConvertRequest(data=source, schema=nullable_integer_schema, output=output)
    )

    if converted.ok:
        restored = load_dataset(output)
        assert int(restored.data["value"].iloc[0]) == 9007199254740993
        assert pd.isna(restored.data["value"].iloc[1])
        assert restored.data["label"].tolist() == ["试样甲", "试样乙"]
    else:
        assert converted.error is not None and converted.error.action
        assert any(
            word in converted.error.message.lower()
            for word in ("loss", "precision", "nullable", "missing", "object")
        ), converted.to_dict()
        assert not output.exists()
        assert not list(output.parent.glob("*"))
    assert hashlib.sha256(source.read_bytes()).digest() == original_hash


@pytest.mark.parametrize("extension", ["csv", "json"])
def test_cli_rejects_mixed_numbers_before_reporting_rounded_data_as_valid(
    tmp_path: Path, nullable_integer_schema: Path, capsys, extension: str
) -> None:
    schema_payload = json.loads(nullable_integer_schema.read_text(encoding="utf-8"))
    schema_payload["fields"][0]["dtype"] = "float"
    nullable_integer_schema.write_text(json.dumps(schema_payload), encoding="utf-8")
    source = tmp_path / f"mixed.{extension}"
    source.write_text(
        "value,label\n9007199254740993,a\n0.5,b\n"
        if extension == "csv"
        else '[{"value":9007199254740993,"label":"a"},{"value":0.5,"label":"b"}]',
        encoding="utf-8",
    )
    output = tmp_path / "mixed.h5"

    status = main(
        ["convert", str(source), "--schema", str(nullable_integer_schema), "--output", str(output)]
    )

    assert status == 2
    displayed = capsys.readouterr()
    assert any(word in displayed.err.lower() for word in ("precision", "loss")), displayed
    assert not output.exists()


def test_json_tensor_rejects_mixed_numeric_precision_loss_at_read_boundary(tmp_path: Path) -> None:
    source = tmp_path / "tensor.json"
    source.write_text('[{"tensor":[[9007199254740993,0.5],[1,2]]}]', encoding="utf-8")

    with pytest.raises(DataReadError, match=r"(?i)precision|loss"):
        load_dataset(source)


def test_explicit_csv_intake_preserves_integer_and_literal_string_contract(tmp_path: Path) -> None:
    raw = b"value,label\n9007199254740993,NA\n42,001\n"
    prepared = prepare_csv(
        raw,
        {},
        [
            {
                "index": 0,
                "target": "value",
                "dtype": "integer",
                "include": True,
                "role": "measured",
                "input_unit": "dimensionless",
                "output_unit": "dimensionless",
            },
            {
                "index": 1,
                "target": "label",
                "dtype": "string",
                "include": True,
                "role": "label",
                "input_unit": None,
                "output_unit": None,
            },
        ],
        source_name="declared.csv",
    )
    output = tmp_path / "declared.h5"
    validation = validate_dataset(prepared.value, prepared.schema)
    assert validation.valid
    write_hdf5(prepared.value, output, prepared.schema, validation)

    restored = load_dataset(output)
    assert restored.data["value"].tolist() == [9007199254740993, 42]
    assert restored.data["label"].tolist() == ["NA", "001"]
    assert prepared.manifest["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_routine_curve_cli_conversion_remains_compatible(tmp_path: Path) -> None:
    source = tmp_path / "curve.csv"
    source.write_text("step,strain,stress\n0,0,0\n1,0.01,123.25\n", encoding="utf-8")
    output = tmp_path / "curve.h5"

    assert main(["convert", str(source), "--schema", "curve", "--output", str(output)]) == 0

    restored = load_dataset(output)
    assert restored.data["step"].tolist() == [0, 1]
    assert restored.data["strain"].tolist() == [0.0, 0.01]
    assert restored.data["stress"].tolist() == [0.0, 123.25]


def test_legacy_csv_keeps_padded_boolean_text_instead_of_changing_truth_value(
    tmp_path: Path,
) -> None:
    source = tmp_path / "padded-bools.csv"
    source.write_text('flag,label\n" true ",a\nfalse,b\n', encoding="utf-8")

    restored = load_dataset(source)

    assert restored.data["flag"].tolist() == [" true ", "false"]


def test_web_import_explains_precision_rejection_without_registering_dataset(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "workspace")

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            home = await client.get("/")
            token = home.text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
            client.headers["X-CSRF-Token"] = token
            created = await client.post("/api/projects", data={"name": "Precision check"})
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]
            uploaded = await client.post(
                f"/api/projects/{project_id}/inspect",
                data={"schema": "curve"},
                files={
                    "file": (
                        "mixed.csv",
                        b"step,strain,stress\n0,0,9007199254740993\n1,0.01,0.5\n",
                        "text/csv",
                    )
                },
            )
            assert uploaded.status_code == 400, uploaded.text
            error = uploaded.json()["error"]
            assert error["action"]
            assert any(word in error["message"].lower() for word in ("precision", "loss"))
            project = await client.get(f"/api/projects/{project_id}")
            assert project.json()["datasets"] == []
            assert project.json()["artifacts"] == []

    try:
        asyncio.run(run())
    finally:
        app.state.jobs.shutdown()
