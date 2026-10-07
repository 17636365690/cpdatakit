"""Reusable declarations must never copy experiment facts or hide a changed CSV."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from test_csv_workflow import OPTIONS, RAW, columns, import_csv
from test_web_multiformat import LocalClient, project

from cpdatakit.io import load_hdf5
from cpdatakit.web import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "workspace")
    value = LocalClient(app)
    token = value.get("/").text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    value.headers["X-CSRF-Token"] = token
    yield value
    app.state.jobs.shutdown()


def saved_settings():
    return {
        "options": deepcopy(OPTIONS),
        "columns": columns(),
        "source_columns": [
            {"index": 0, "source_name": "(s)", "dtype": "integer", "suggested_unit": "s"},
            {"index": 1, "source_name": "(N)", "dtype": "integer", "suggested_unit": "N"},
            {"index": 2, "source_name": "", "dtype": "integer", "suggested_unit": None},
            {"index": 3, "source_name": "(MPa)", "dtype": "integer", "suggested_unit": "MPa"},
            {"index": 4, "source_name": "(mm/mm)", "dtype": "float", "suggested_unit": "mm/mm"},
        ],
    }


def preview(client, pid, settings, raw=RAW, options=None):
    return client.post(
        f"/api/projects/{pid}/csv-preview",
        data={
            "options_json": json.dumps(OPTIONS if options is None else options),
            "settings_json": json.dumps(settings),
        },
        files={"file": ("second.csv", raw, "text/csv")},
    )


def test_download_settings_contains_reusable_contract_without_source_facts(client):
    pid = project(client)
    result = import_csv(
        client, pid, conventions="First experiment only; Pt pseudo reference"
    ).json()
    response = client.get(f"/api/projects/{pid}/csv-imports/{result['dataset_id']}/settings")
    assert response.status_code == 200, response.text
    assert "settings.json" in response.headers["content-disposition"]
    settings = response.json()
    assert set(settings) == {"options", "columns", "source_columns"}
    assert settings["options"] == OPTIONS
    assert settings["source_columns"] == saved_settings()["source_columns"]
    assert settings["columns"][1] == {
        "index": 1,
        "source_name": "(N)",
        "include": True,
        "target": "force",
        "dtype": "float",
        "input_unit": "N",
        "output_unit": "kN",
        "role": "measured_quantity",
    }
    assert "First experiment" not in response.text
    assert "source_sha256" not in response.text
    assert "specimen.csv" not in response.text
    assert "samples" not in response.text


def test_same_structure_reuses_declarations_but_binds_new_bytes_and_facts(client):
    pid = project(client)
    raw = RAW.replace(b"1;200;8;40;0.01", b"2;300;9;60;0.02")
    response = preview(client, pid, saved_settings(), raw)
    assert response.status_code == 200, response.text
    value = response.json()
    assert "settings_review" in value
    review = value["settings_review"]
    assert review["matches"] is True
    assert review["changes"] == []
    assert review["columns"][1]["output_unit"] == "kN"
    assert review["columns"][1]["role"] == "measured_quantity"
    assert review["warnings"]
    response = client.post(
        f"/api/projects/{pid}/csv-import",
        data={
            "options_json": json.dumps(OPTIONS),
            "columns_json": json.dumps(review["columns"]),
            "source_sha256": value["source_sha256"],
            "confirmed": "true",
            "conventions": "Second experiment only; Ag/AgCl reference",
            "settings_json": json.dumps(saved_settings()),
        },
        files={"file": ("second.csv", raw, "text/csv")},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["manifest"]["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["manifest"]["source_sha256"] != hashlib.sha256(RAW).hexdigest()
    assert result["manifest"]["confirmed_source_definition"].startswith("Second experiment")
    assert result["manifest"]["settings_review"]["matches"] is True
    record = client.app.state.catalog.get_dataset(result["dataset_id"])
    data = load_hdf5(client.app.state.workspace / record.relative_path)
    assert data.data["force"].tolist() == [0.1, 0.3]
    assert data.metadata["units"]["force"] == "kN"


@pytest.mark.parametrize(
    ("raw", "options", "field"),
    [
        (RAW.replace(b"(N)", b"(kN)"), OPTIONS, "source_columns[1].suggested_unit"),
        (RAW.replace(b"(s);(N)", b"(N);(s)"), OPTIONS, "source_columns[0].source_name"),
        (RAW.replace(b"100;7", b"100.5;7"), OPTIONS, "source_columns[1].dtype"),
        (
            RAW.replace(b";(mm/mm)", b"").replace(b";0\r", b"\r").replace(b";0.01\r", b"\r"),
            OPTIONS,
            "source_columns.length",
        ),
        (RAW, {**OPTIONS, "encoding": "gb18030"}, "options.encoding"),
    ],
)
def test_changes_are_visible_and_never_silently_apply_saved_columns(client, raw, options, field):
    response = preview(client, project(client), saved_settings(), raw, options)
    assert response.status_code == 200, response.text
    value = response.json()
    assert "settings_review" in value
    review = value["settings_review"]
    assert review["matches"] is False
    assert review["columns"] == []
    assert field in {change["field"] for change in review["changes"]}


def test_legacy_settings_do_not_copy_facts_or_silently_bind_positions(client):
    settings = saved_settings()
    del settings["source_columns"]
    settings["confirmed_source_definition"] = "First experiment only"
    response = preview(client, project(client), settings)
    assert response.status_code == 200, response.text
    value = response.json()
    assert "settings_review" in value
    assert value["settings_review"]["matches"] is False
    assert value["settings_review"]["columns"] == []
    assert any(item["field"] == "source_columns" for item in value["settings_review"]["changes"])
    assert "First experiment only" not in response.text


@pytest.mark.parametrize(
    "settings",
    [
        None,
        [],
        {},
        {"options": [], "columns": columns()},
        {"options": OPTIONS, "columns": None},
        {**saved_settings(), "source_columns": []},
        {**saved_settings(), "source_columns": [None] * 5},
        {
            **saved_settings(),
            "source_columns": [
                {"index": 0, "source_name": [], "dtype": "float", "suggested_unit": None}
            ]
            * 5,
        },
        {**saved_settings(), "columns": [{"index": 0, "include": True}] * 5},
        {**saved_settings(), "unexpected": float("nan")},
        {
            **saved_settings(),
            "columns": [
                {**item, "output_unit": "not_a_unit"} if item.get("include") else item
                for item in columns()
            ],
        },
    ],
)
def test_malformed_settings_return_400_without_creating_data(client, settings):
    pid = project(client)
    response = preview(client, pid, settings)
    assert response.status_code == 400, response.text
    assert client.app.state.catalog.list_datasets(pid) == ()


def test_unknown_settings_fields_are_ignored_without_copying_their_values(client):
    settings = saved_settings()
    settings["unknown"] = {"secret": "must-not-copy"}
    settings["columns"][0]["unknown"] = "must-not-copy"
    response = preview(client, project(client), settings)
    assert response.status_code == 200, response.text
    value = response.json()
    assert "settings_review" in value
    assert value["settings_review"]["matches"] is True
    assert "must-not-copy" not in response.text
    assert value["settings_review"]["warnings"]


@pytest.mark.parametrize("part", ["source.csv", "manifest.json"])
def test_download_requires_unchanged_source_and_manifest(client, part):
    pid = project(client)
    result = import_csv(client, pid).json()
    url = f"/api/projects/{pid}/csv-imports/{result['dataset_id']}/settings"
    assert client.get(url).status_code == 200
    record = client.app.state.catalog.get_dataset(result["dataset_id"])
    path = (client.app.state.workspace / record.relative_path).parent / part
    path.write_bytes(b"changed")
    assert client.get(url).status_code == 404


def test_settings_cannot_be_exported_from_another_project(client):
    pid = project(client)
    result = import_csv(client, pid).json()
    assert (
        client.get(f"/api/projects/{pid}/csv-imports/{result['dataset_id']}/settings").status_code
        == 200
    )
    another = project(client)
    assert (
        client.get(
            f"/api/projects/{another}/csv-imports/{result['dataset_id']}/settings"
        ).status_code
        == 404
    )


def test_import_rechecks_malformed_settings_before_publishing(client):
    pid = project(client)
    response = import_csv(client, pid, settings_json='{"options": [], "columns": []}')
    assert response.status_code == 400
    assert client.app.state.catalog.list_datasets(pid) == ()


def test_oversize_settings_are_rejected_by_the_request_limit(client):
    pid = project(client)
    response = preview(client, pid, {**saved_settings(), "unknown": "x" * (1024 * 1024)})
    assert response.status_code == 413
    assert client.app.state.catalog.list_datasets(pid) == ()


def test_settings_export_checks_the_bytes_it_actually_reads(client, monkeypatch):
    from cpdatakit.web import csv_workflow

    pid = project(client)
    result = import_csv(client, pid).json()
    original_hash = csv_workflow.path_sha256

    def replace_after_hash(path):
        value = original_hash(path)
        if path.name == "source.csv":
            path.write_bytes(RAW.replace(b"(N)", b"(kN)"))
        return value

    monkeypatch.setattr(csv_workflow, "path_sha256", replace_after_hash)
    response = client.get(f"/api/projects/{pid}/csv-imports/{result['dataset_id']}/settings")
    if response.status_code == 200:
        # A single read that verifies its own bytes avoids the race entirely.
        assert response.json()["source_columns"][1]["suggested_unit"] == "N"
    else:
        assert response.status_code == 404


def test_deep_settings_json_is_a_review_error_not_a_server_error(client):
    pid = project(client)
    response = client.post(
        f"/api/projects/{pid}/csv-preview",
        data={"options_json": json.dumps(OPTIONS), "settings_json": "[" * 1500 + "]" * 1500},
        files={"file": ("second.csv", RAW, "text/csv")},
    )
    assert response.status_code == 400
