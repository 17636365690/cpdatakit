"""Conversion must preserve portable origin receipts without inventing old history."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from itertools import pairwise

import h5py
import pytest
from test_csv_workflow import client as client

from cpdatakit.application import ConvertRequest, ReportRequest, build_report, convert_and_write
from cpdatakit.application.csv_intake import prepare_csv
from cpdatakit.exceptions import DataReadError, DataValidationError
from cpdatakit.formats._metadata import decode_metadata, encode_metadata
from cpdatakit.io import load_dataset, write_hdf5
from cpdatakit.schema import schema_sha256
from cpdatakit.validation import validate_dataset


def confirmed_csv(tmp_path):
    raw = "\ufeffForce;Note;ID\r\n1000;excluded;001\r\n2500;私有;002\r\n".encode()
    source = tmp_path / "工程.csv"
    source.write_bytes(raw)
    prepared = prepare_csv(
        raw,
        {"delimiter": ";"},
        [
            {
                "index": 0,
                "include": True,
                "target": "force",
                "dtype": "float",
                "input_unit": "N",
                "output_unit": "kN",
                "role": "measured",
            },
            {"index": 1, "include": False},
            {
                "index": 2,
                "include": True,
                "target": "id",
                "dtype": "string",
                "input_unit": None,
                "output_unit": None,
                "role": "identifier",
            },
        ],
        source_name=source.name,
    )
    prepared.value.source = source
    return prepared, source


def initial_hdf5(tmp_path):
    prepared, source = confirmed_csv(tmp_path)
    output = tmp_path / "first.h5"
    write_hdf5(
        prepared.value,
        output,
        prepared.schema,
        validate_dataset(prepared.value, prepared.schema),
        source_description="试验来源: 已确认 N→kN",
        operation_log=["explicit CSV import"],
    )
    return prepared, source, output


def test_second_conversion_and_report_retain_complete_csv_receipt(tmp_path):
    prepared, source, first = initial_hdf5(tmp_path)
    first_provenance = load_dataset(first).metadata["provenance"]
    second = tmp_path / "second.h5"
    result = convert_and_write(ConvertRequest(first, prepared.schema, second))
    assert result.ok, result.error
    loaded = load_dataset(second)
    provenance = loaded.metadata["provenance"]
    assert provenance.get("csv_import") == prepared.manifest
    assert (
        provenance["csv_import"]["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert provenance["csv_import"]["excluded_columns"] == [{"index": 1, "source_name": "Note"}]
    assert provenance["source_description"] == "试验来源: 已确认 N→kN"
    assert provenance["operation_log"] == [
        "explicit CSV import",
        "load",
        "normalize",
        "validate",
        "convert",
    ]
    assert provenance["input_sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert loaded.data["force"].tolist() == [1.0, 2.5]
    assert loaded.data["id"].tolist() == ["001", "002"]
    assert loaded.metadata["units"]["force"] == "kN"
    assert (
        len(provenance["lineage"]["receipts"]) == len(first_provenance["lineage"]["receipts"]) + 1
    )
    assert provenance["lineage"]["receipts"][-1]["schema_sha256"] == schema_sha256(prepared.schema)
    assert str(tmp_path) not in json.dumps(provenance, ensure_ascii=False)
    report_path = tmp_path / "report.json"
    report = build_report(ReportRequest(second, prepared.schema, report_path, format="json"))
    assert report.ok, report.error
    assert json.loads(report_path.read_text())["provenance"]["csv_import"] == prepared.manifest


def test_direct_read_write_appends_once_and_does_not_mutate_parent(tmp_path):
    prepared, _, first = initial_hdf5(tmp_path)
    value = load_dataset(first)
    before = deepcopy(value.metadata)
    output = tmp_path / "copy.h5"
    write_hdf5(
        value,
        output,
        prepared.schema,
        validate_dataset(value, prepared.schema),
        operation_log=["copy verified data"],
    )
    assert value.metadata == before
    provenance = load_dataset(output).metadata["provenance"]
    assert provenance["operation_log"] == ["explicit CSV import", "copy verified data"]
    assert load_dataset(output).metadata["field_mapping"] == before["field_mapping"]
    assert provenance["lineage"]["receipts"][-1]["field_mapping"] == {}


@pytest.mark.parametrize("mutation", ["manifest", "operation", "parent", "head", "mirror"])
def test_corrupted_embedded_receipt_is_rejected_on_read(tmp_path, mutation):
    _, _, path = initial_hdf5(tmp_path)
    with h5py.File(path, "r+") as handle:
        provenance = json.loads(handle.attrs["provenance_json"])
        assert "lineage" in provenance, "writer discarded the origin receipt"
        receipts = provenance["lineage"]["receipts"]
        if mutation == "manifest":
            receipts[0]["provenance"]["csv_import"]["options"]["delimiter"] = ","
        elif mutation == "operation":
            receipts[-1]["operation_log"] = ["silently changed"]
        elif mutation == "parent":
            receipts[-1]["parent_sha256"] = "0" * 64
        elif mutation == "head":
            provenance["lineage"]["head_sha256"] = "0" * 64
        else:
            provenance["csv_import"]["record_count"] = 900
        handle.attrs["provenance_json"] = json.dumps(provenance)
    with pytest.raises(DataReadError, match=r"[Pp]rovenance|[Ll]ineage|receipt"):
        load_dataset(path)


def test_legacy_file_remains_readable_and_report_marks_unknown_history(tmp_path):
    prepared, _, path = initial_hdf5(tmp_path)
    with h5py.File(path, "r+") as handle:
        handle.attrs["provenance_json"] = json.dumps({"source_description": "old file"})
    assert load_dataset(path).data["force"].tolist() == [1.0, 2.5]
    target = tmp_path / "legacy-report.json"
    result = build_report(ReportRequest(path, prepared.schema, target, format="json"))
    assert result.ok
    assert (
        json.loads(target.read_text())["provenance"].get("history_status") == "historical_unknown"
    )


def test_metadata_envelope_rejects_corrupted_chain_before_export(tmp_path):
    _, _, path = initial_hdf5(tmp_path)
    metadata = load_dataset(path).metadata
    assert "lineage" in metadata["provenance"]
    metadata["provenance"]["lineage"]["head_sha256"] = "0" * 64
    with pytest.raises(DataValidationError, match=r"[Pp]rovenance|[Ll]ineage|receipt"):
        encode_metadata(metadata)
    payload = json.dumps({"version": 1, "metadata": metadata})
    with pytest.raises(DataReadError, match=r"[Pp]rovenance|[Ll]ineage|receipt"):
        decode_metadata(payload)


def test_chain_growth_is_flat_and_excessive_history_fails_without_output(tmp_path):
    prepared, _, first = initial_hdf5(tmp_path)
    value = load_dataset(first)
    last = value.metadata["provenance"]
    assert "lineage" in last
    from cpdatakit.provenance import build_provenance

    lengths = []
    for _ in range(12):
        last = build_provenance(first, parent_provenance=last, operation_log=["copy"])
        lengths.append(len(json.dumps(last)))
    assert max(b - a for a, b in pairwise(lengths)) < 2000
    with pytest.raises(DataValidationError, match=r"limit|maximum|exceeds"):
        for _ in range(100):
            last = build_provenance(first, parent_provenance=last, operation_log=["copy"])
    value.metadata["provenance"] = {"source_description": "x" * 2_000_000}
    output = tmp_path / "oversize.h5"
    with pytest.raises(DataValidationError, match=r"limit|maximum|exceeds"):
        write_hdf5(value, output, prepared.schema, validate_dataset(value, prepared.schema))
    assert not output.exists()


def test_legacy_metadata_roundtrip_does_not_rewrite_user_provenance():
    original = {"provenance": {"source_description": "old user text", "custom": 17}}
    assert decode_metadata(encode_metadata(original)) == original


def test_parquet_service_preserves_prior_chain_and_adds_conversion(tmp_path):
    from cpdatakit.formats import ParquetReader

    prepared, _, first = initial_hdf5(tmp_path)
    output = tmp_path / "result.parquet"
    result = convert_and_write(
        ConvertRequest(first, prepared.schema, output, output_format="parquet")
    )
    assert result.ok, result.error
    provenance = ParquetReader().load(output).metadata["provenance"]
    assert provenance["csv_import"] == prepared.manifest
    assert provenance["operation_log"] == [
        "explicit CSV import",
        "load",
        "normalize",
        "validate",
        "convert",
    ]
    assert provenance["lineage"]["receipts"][-1]["parameters"]["output_format"] == "parquet"


def test_service_records_mapping_parameters_and_exact_mapping_file_hash(tmp_path):
    prepared, _, first = initial_hdf5(tmp_path)
    mapping = tmp_path / "mapping.json"
    payload = {
        "mappings": [
            {"source": "force", "target": "force", "input_unit": "kN", "output_unit": "kN"},
            {"source": "id", "target": "id"},
        ],
        "drop_unmapped": False,
    }
    mapping.write_text(json.dumps(payload), encoding="utf-8")
    result = convert_and_write(
        ConvertRequest(first, prepared.schema, tmp_path / "mapped.h5", mapping=mapping)
    )
    assert result.ok, result.error
    provenance = load_dataset(tmp_path / "mapped.h5").metadata["provenance"]
    receipt = provenance["lineage"]["receipts"][-1]
    assert receipt["mapping_sha256"] == hashlib.sha256(mapping.read_bytes()).hexdigest()
    assert receipt["parameters"]["drop_unmapped"] is False
    assert receipt["parameters"]["mappings"][0]["input_unit"] == "kN"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"parent_provenance": []},
        {"operation_log": "copy"},
        {"parameters": ["not an object"]},
    ],
)
def test_malformed_receipt_inputs_are_rejected_instead_of_silently_coerced(kwargs):
    from cpdatakit.provenance import build_provenance

    with pytest.raises(DataValidationError):
        build_provenance(None, **kwargs)


@pytest.mark.parametrize("location", ["root", "envelope"])
def test_hdf5_v2_rejects_corrupted_receipts_in_either_copy(tmp_path, location):
    from test_hdf5_v2 import SCHEMA, _value

    from cpdatakit.io import load_hdf5_v2, write_hdf5_v2
    from cpdatakit.provenance import build_provenance
    from cpdatakit.schemas import resolve_schema_v2

    value = _value()
    value.metadata["provenance"] = build_provenance(None, operation_log=["synthetic fixture"])
    path = tmp_path / "v2.h5"
    write_hdf5_v2(value, path, resolve_schema_v2(SCHEMA))
    with h5py.File(path, "r+") as handle:
        if location == "root":
            payload = json.loads(handle.attrs["provenance_json"])
            payload["lineage"]["head_sha256"] = "0" * 64
            handle.attrs["provenance_json"] = json.dumps(payload)
        else:
            payload = json.loads(handle["metadata"].attrs["metadata_json"])
            payload["provenance"]["lineage"]["head_sha256"] = "0" * 64
            handle["metadata"].attrs["metadata_json"] = json.dumps(payload)
    with pytest.raises(DataReadError, match=r"[Pp]rovenance|[Ll]ineage|receipt"):
        load_hdf5_v2(path)


def test_web_import_embeds_exact_final_manifest_including_confirmed_definition(client):
    from test_csv_workflow import import_csv, project

    pid = project(client)
    result = import_csv(client, pid, conventions="已确认的试验定义")
    assert result.status_code == 201, result.text
    record = client.app.state.catalog.get_dataset(result.json()["dataset_id"])
    path = client.app.state.workspace / record.relative_path
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    assert load_dataset(path).metadata["provenance"]["csv_import"] == manifest


def test_legacy_csv_manifest_does_not_invent_missing_conversion_history(tmp_path):
    prepared, _, first = initial_hdf5(tmp_path)
    with h5py.File(first, "r+") as handle:
        handle.attrs["provenance_json"] = json.dumps({"csv_import": prepared.manifest})
    output = tmp_path / "legacy-converted.h5"
    result = convert_and_write(ConvertRequest(first, prepared.schema, output))
    assert result.ok, result.error
    provenance = load_dataset(output).metadata["provenance"]
    assert provenance["csv_import"] == prepared.manifest
    assert provenance["history_status"] == "historical_unknown"


@pytest.mark.parametrize("output_format", ["parquet", "hdf5", "direct-hdf5"])
def test_no_mapping_conversion_does_not_claim_prior_mapping_again(tmp_path, output_format):
    from cpdatakit.formats import ParquetReader

    prepared, _, first = initial_hdf5(tmp_path)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {"source": "force", "target": "force", "input_unit": "kN", "output_unit": "kN"},
                    {"source": "id", "target": "id"},
                ]
            }
        ),
        encoding="utf-8",
    )
    mapped = tmp_path / "mapped.parquet"
    result = convert_and_write(
        ConvertRequest(first, prepared.schema, mapped, mapping=mapping, output_format="parquet")
    )
    assert result.ok, result.error
    previous = ParquetReader().load(mapped)
    previous_receipts = deepcopy(previous.metadata["provenance"]["lineage"]["receipts"])
    output = tmp_path / ("copy.parquet" if output_format == "parquet" else "copy.h5")
    if output_format == "direct-hdf5":
        write_hdf5(
            previous,
            output,
            prepared.schema,
            validate_dataset(previous, prepared.schema),
            operation_log=["copy"],
        )
    else:
        result = convert_and_write(
            ConvertRequest(mapped, prepared.schema, output, output_format=output_format)
        )
        assert result.ok, result.error
    loaded = ParquetReader().load(output) if output_format == "parquet" else load_dataset(output)
    receipts = loaded.metadata["provenance"]["lineage"]["receipts"]
    assert receipts[:-1] == previous_receipts
    assert loaded.metadata["field_mapping"] == previous.metadata["field_mapping"]
    assert receipts[-1]["field_mapping"] == {}
    assert receipts[-1]["mapping_sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert receipts[-1]["parameters"].get("mappings", []) == []
    assert loaded.data["force"].tolist() == [1.0, 2.5]
