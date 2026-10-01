from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from test_web_multiformat import LocalClient, project, wait_job

from cpdatakit.io import load_hdf5
from cpdatakit.web import create_app

RAW = b"(s);(N);;(MPa);(mm/mm)\r\n0;100;7;20;0\r\n1;200;8;40;0.01\r\n"
OPTIONS = {
    "delimiter": ";",
    "header_row": 1,
    "unit_row": 0,
    "decimal": ".",
    "encoding": "utf-8-sig",
}


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "workspace")
    client = LocalClient(app)
    token = client.get("/").text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    client.headers["X-CSRF-Token"] = token
    yield client
    app.state.jobs.shutdown()


def columns():
    return [
        {
            "index": 0,
            "include": True,
            "target": "time",
            "dtype": "float",
            "input_unit": "s",
            "output_unit": "s",
            "role": "time",
        },
        {
            "index": 1,
            "include": True,
            "target": "force",
            "dtype": "float",
            "input_unit": "N",
            "output_unit": "kN",
            "role": "measured_quantity",
        },
        {"index": 2, "include": False},
        {
            "index": 3,
            "include": True,
            "target": "reported_stress",
            "dtype": "float",
            "input_unit": "MPa",
            "output_unit": "MPa",
            "role": "measured_quantity",
        },
        {
            "index": 4,
            "include": True,
            "target": "reported_strain",
            "dtype": "float",
            "input_unit": "dimensionless",
            "output_unit": "dimensionless",
            "role": "measured_quantity",
        },
    ]


def import_csv(client, pid, **overrides):
    data = {
        "options_json": json.dumps(OPTIONS),
        "columns_json": json.dumps(columns()),
        "source_sha256": hashlib.sha256(RAW).hexdigest(),
        "confirmed": "true",
        "conventions": "Reported source quantities; stress/strain definitions not inferred.",
    }
    data.update(overrides)
    return client.post(
        f"/api/projects/{pid}/csv-import",
        data=data,
        files={"file": ("specimen.csv", RAW, "text/csv")},
    )


def test_original_csv_preview_import_and_report_preserve_source_and_units(client):
    pid = project(client)
    preview = client.post(
        f"/api/projects/{pid}/csv-preview",
        data={"options_json": json.dumps(OPTIONS)},
        files={"file": ("specimen.csv", RAW, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["record_count"] == 2
    assert len(preview.json()["columns"]) == 5
    response = import_csv(client, pid)
    assert response.status_code == 201, response.text
    value = response.json()
    catalog = client.app.state.catalog
    dataset = catalog.get_dataset(value["dataset_id"])
    path = client.app.state.workspace / dataset.relative_path
    loaded = load_hdf5(path)
    assert list(loaded.data) == ["time", "force", "reported_stress", "reported_strain"]
    np.testing.assert_array_equal(loaded.data["force"], [0.1, 0.2])
    assert loaded.metadata["units"]["force"] == "kN"
    assert (path.parent / "source.csv").read_bytes() == RAW
    manifest = json.loads((path.parent / "manifest.json").read_text())
    assert manifest["source_sha256"] == hashlib.sha256(RAW).hexdigest()
    report = wait_job(
        client,
        client.post(
            f"/api/projects/{pid}/report",
            data={
                "dataset_id": value["dataset_id"],
                "schema": value["schema_selector"],
                "output": "report.html",
            },
        ),
    )
    assert report["status"] == "succeeded", report
    assert report["result"]["value"]["report"]["validation"]["valid"] is True


@pytest.mark.parametrize(
    "changes", [{"confirmed": "false"}, {"source_sha256": "0" * 64}, {"conventions": ""}]
)
def test_csv_confirmation_cannot_publish_unreviewed_or_different_source(client, changes):
    pid = project(client)
    response = import_csv(client, pid, **changes)
    assert response.status_code == 400, response.text
    assert client.app.state.catalog.list_datasets(pid) == ()
    assert client.app.state.catalog.list_schemas(pid) == ()


def test_csv_unknown_unit_remains_unconfirmed_and_preserves_empty_catalog(client):
    pid = project(client)
    choices = columns()
    choices[1]["input_unit"] = ""
    response = import_csv(client, pid, columns_json=json.dumps(choices))
    assert response.status_code == 400, response.text
    assert client.app.state.catalog.list_datasets(pid) == ()


def test_csv_preview_and_import_require_csrf(client):
    pid = project(client)
    client.headers.clear()
    for route in ("csv-preview", "csv-import"):
        response = client.post(f"/api/projects/{pid}/{route}", files={"file": ("a.csv", RAW)})
        assert response.status_code == 403


def test_csv_import_does_not_claim_success_if_bundle_changes_during_registration(
    client, monkeypatch
):
    pid = project(client)
    register = client.app.state.catalog.register_csv_import

    def changed(*args, **kwargs):
        result = register(*args, **kwargs)
        kwargs["data_path"].write_bytes(b"changed after registration")
        return result

    monkeypatch.setattr(client.app.state.catalog, "register_csv_import", changed)
    response = import_csv(client, pid)
    assert response.status_code == 500
    records = client.app.state.catalog.list_datasets(pid)
    assert len(records) == 1  # Preserve committed evidence, never remove another writer's bytes.
    rejected = client.post(
        f"/api/projects/{pid}/validate",
        data={"dataset_id": records[0].id, "schema": records[0].metadata["schema_selector"]},
    )
    assert rejected.status_code == 404


def test_csv_review_downloads_original_and_declarations_with_project_and_hash_checks(client):
    pid = project(client)
    result = import_csv(client, pid).json()
    url = f"/api/projects/{pid}/csv-imports/{result['dataset_id']}"
    assert client.get(url + "/source").content == RAW
    assert client.get(url + "/schema").json()["profile"] == "imported-csv"
    assert client.get(url + "/manifest").json()["source_sha256"] == hashlib.sha256(RAW).hexdigest()
    another = project(client)
    assert (
        client.get(f"/api/projects/{another}/csv-imports/{result['dataset_id']}/source").status_code
        == 404
    )
    record = client.app.state.catalog.get_dataset(result["dataset_id"])
    source = (client.app.state.workspace / record.relative_path).parent / "source.csv"
    source.write_bytes(b"different source")
    assert client.get(url + "/source").status_code == 404
