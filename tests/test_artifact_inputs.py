"""Continue real conversion workflows from their immutable result snapshots."""

import asyncio
import json
import os
import sqlite3

import httpx
import pytest
from test_artifact_versions import queue
from test_web_workflows import _csrf, _request, _seed_curve, _wait_for_job

from cpdatakit.application.data_access import path_sha256
from cpdatakit.exceptions import CatalogError
from cpdatakit.schema import load_schema, schema_to_dict
from cpdatakit.web import create_app
from cpdatakit.web.artifacts import register_snapshot


@pytest.fixture
def workflow(tmp_path):
    app = create_app(tmp_path / "workspace")
    try:
        home, project = _seed_curve(app, tmp_path)
        yield app, home, project
    finally:
        app.state.jobs.shutdown()


def promote(app, home, project, artifact_id, **kwargs):
    return _request(
        app,
        "POST",
        f"/api/projects/{project}/artifacts/{artifact_id}/use-as-input",
        cookies=home.cookies,
        headers={"X-CSRF-Token": _csrf(home)},
        **kwargs,
    )


def converted(workflow, *, selector="curve"):
    app, home, project = workflow
    source = app.state.catalog.list_datasets(project)[0]
    queue(
        app,
        home,
        project,
        "convert",
        {"dataset_id": source.id, "schema": selector, "output": "result.h5"},
    )
    return app.state.catalog.list_artifacts(project)[-1]


def project_schema(workflow):
    app, home, project = workflow
    schema = schema_to_dict(load_schema("curve"))
    schema["profile"] = "mapped-curve"
    response = _request(
        app,
        "POST",
        f"/api/projects/{project}/schemas",
        cookies=home.cookies,
        headers={"X-CSRF-Token": _csrf(home)},
        files={"file": ("custom.json", json.dumps(schema).encode(), "application/json")},
    )
    assert response.status_code == 201, response.text
    return response.json()["selector"]


def test_mapped_conversion_becomes_report_input_with_its_original_project_schema(workflow):
    app, home, project = workflow
    selector = project_schema(workflow)
    uploaded = _request(
        app,
        "POST",
        f"/api/projects/{project}/inspect",
        cookies=home.cookies,
        headers={"X-CSRF-Token": _csrf(home)},
        data={"schema": selector},
        files={
            "file": (
                "raw.csv",
                b"step,strain,load_pa\n0,0.01,100000000\n1,0.02,300000000\n",
                "text/csv",
            )
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    source = app.state.catalog.list_datasets(project)[-1]
    queue(
        app,
        home,
        project,
        "convert",
        {
            "dataset_id": source.id,
            "schema": selector,
            "output": "mapped.h5",
            "mapping_json": json.dumps(
                {
                    "mappings": [
                        {
                            "source": "load_pa",
                            "target": "stress",
                            "input_unit": "Pa",
                            "output_unit": "MPa",
                        }
                    ]
                }
            ),
        },
    )
    artifact = app.state.catalog.list_artifacts(project)[-1]
    response = promote(app, home, project, artifact.id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_selector"] == selector
    assert payload["artifact_id"] == artifact.id
    assert payload["filename"] == "mapped.h5"
    dataset = app.state.catalog.get_dataset(payload["dataset_id"])
    assert dataset.id != source.id
    assert dataset.relative_path == artifact.relative_path
    assert dataset.sha256 == artifact.sha256
    assert dataset.metadata["source_artifact_id"] == artifact.id
    assert dataset.metadata["schema"] == selector
    report_result = queue(
        app,
        home,
        project,
        "report",
        {
            "dataset_id": dataset.id,
            "schema": payload["schema_selector"],
            "output": "mapped-report.json",
            "format": "json",
        },
    )
    report = json.loads((app.state.workspace / report_result["artifact"]).read_text())
    assert report["validation"]["valid"] is True
    assert report["statistics"]["numeric_fields"]["stress"]["mean"] == 200.0
    assert report["schema"]["profile"] == "mapped-curve"


def test_repeated_and_concurrent_requests_reuse_one_dataset_and_survive_restart(workflow):
    app, home, project = workflow
    artifact = converted(workflow)

    async def simultaneous():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            cookies=home.cookies,
            headers={"X-CSRF-Token": _csrf(home)},
        ) as client:
            return await asyncio.gather(
                *[
                    client.post(f"/api/projects/{project}/artifacts/{artifact.id}/use-as-input")
                    for _ in range(8)
                ]
            )

    responses = asyncio.run(simultaneous())
    assert [reply.status_code for reply in responses] == [200] * 8
    ids = {reply.json()["dataset_id"] for reply in responses}
    assert len(ids) == 1
    assert len(app.state.catalog.list_datasets(project)) == 2
    assert promote(app, home, project, artifact.id).json()["dataset_id"] in ids
    workspace = app.state.workspace
    app.state.jobs.shutdown()
    restored = create_app(workspace)
    try:
        fresh_home = _request(restored, "GET", "/")
        assert promote(restored, fresh_home, project, artifact.id).json()["dataset_id"] in ids
        assert len(restored.state.catalog.list_datasets(project)) == 2
    finally:
        restored.state.jobs.shutdown()


def test_later_output_overwrite_does_not_replace_promoted_snapshot(workflow):
    app, home, project = workflow
    artifact = converted(workflow)
    snapshot = app.state.workspace / artifact.relative_path
    digest = path_sha256(snapshot)
    output = app.state.workspace / artifact.metadata["output_path"]
    output.write_bytes(b"a later unrelated output")
    reply = promote(app, home, project, artifact.id)
    assert reply.status_code == 200, reply.text
    dataset = app.state.catalog.get_dataset(reply.json()["dataset_id"])
    assert path_sha256(app.state.workspace / dataset.relative_path) == digest
    result = queue(
        app,
        home,
        project,
        "report",
        {
            "dataset_id": dataset.id,
            "schema": reply.json()["schema_selector"],
            "output": "retained.json",
            "format": "json",
        },
    )
    report = json.loads((app.state.workspace / result["artifact"]).read_text())
    assert report["validation"]["valid"] is True


def test_promoted_snapshot_is_checked_again_before_reuse_or_reporting(workflow):
    app, home, project = workflow
    artifact = converted(workflow)
    response = promote(app, home, project, artifact.id)
    assert response.status_code == 200, response.text
    payload = response.json()
    (app.state.workspace / artifact.relative_path).write_bytes(b"changed after promotion")
    assert promote(app, home, project, artifact.id).status_code == 409
    report = _request(
        app,
        "POST",
        f"/api/projects/{project}/report",
        cookies=home.cookies,
        headers={"X-CSRF-Token": _csrf(home)},
        data={
            "dataset_id": payload["dataset_id"],
            "schema": payload["schema_selector"],
            "output": "tampered-report.json",
            "format": "json",
        },
    )
    assert report.status_code == 400, report.text
    assert len(app.state.catalog.list_datasets(project)) == 2


@pytest.mark.parametrize("changed", ["snapshot", "schema"])
def test_changes_during_inspection_do_not_register_an_input(workflow, monkeypatch, changed):
    import cpdatakit.web.artifact_inputs as artifact_inputs

    app, home, project = workflow
    selector = project_schema(workflow)
    artifact = converted(workflow, selector=selector)
    schema = app.state.catalog.get_schema(int(selector.split(":")[1]))
    original_inspect = artifact_inputs.inspect_input

    def inspect_then_change(path, *args, **kwargs):
        result = original_inspect(path, *args, **kwargs)
        if changed == "snapshot":
            path.write_bytes(b"another writer replaced the inspected data")
        else:
            schema_path = app.state.workspace / schema.relative_path
            schema_path.write_text(schema_path.read_text() + " ")
        return result

    monkeypatch.setattr(artifact_inputs, "inspect_input", inspect_then_change)
    response = promote(app, home, project, artifact.id)
    assert response.status_code == 409, response.text
    assert len(app.state.catalog.list_datasets(project)) == 1


def test_promotion_requires_csrf(workflow):
    app, home, project = workflow
    artifact = converted(workflow)
    reply = _request(
        app,
        "POST",
        f"/api/projects/{project}/artifacts/{artifact.id}/use-as-input",
        cookies=home.cookies,
    )
    assert reply.status_code == 403
    assert len(app.state.catalog.list_datasets(project)) == 1


@pytest.mark.parametrize("problem", ["changed", "missing", "wrong-project", "path-escape"])
def test_unavailable_or_changed_snapshot_is_not_bound(workflow, problem):
    app, home, project = workflow
    artifact = converted(workflow)
    snapshot = app.state.workspace / artifact.relative_path
    if problem == "changed":
        snapshot.write_bytes(b"changed content")
    elif problem == "missing":
        snapshot.unlink()
    else:
        other = app.state.catalog.create_project("other")
        (app.state.workspace / "projects" / str(other.id)).mkdir()
        if problem == "wrong-project":
            project = other.id
        else:
            artifact = app.state.catalog.register_artifact(
                other.id,
                snapshot,
                kind="convert",
                sha256=artifact.sha256,
                metadata=artifact.metadata,
            )
            project = other.id
    before = app.state.catalog.list_datasets(project)
    response = promote(app, home, project, artifact.id)
    assert response.status_code in {400, 404, 409}, response.text
    assert response.json().get("error"), response.text
    assert app.state.catalog.list_datasets(project) == before


@pytest.mark.parametrize("kind", ["report", "compare", "plot"])
def test_non_conversion_results_cannot_become_inputs(workflow, kind):
    app, home, project = workflow
    source = app.state.workspace / "projects" / str(project) / "report.json"
    source.write_text('{"not": "data"}')
    artifact = register_snapshot(
        app.state.catalog,
        app.state.workspace,
        project,
        source,
        kind=kind,
        metadata={"schema": "curve"},
    )
    reply = promote(app, home, project, artifact.id)
    assert reply.status_code == 400, reply.text
    assert len(app.state.catalog.list_datasets(project)) == 1


def test_unreadable_conversion_artifact_is_not_registered_as_dataset(workflow):
    app, home, project = workflow
    source = app.state.workspace / "projects" / str(project) / "broken.h5"
    source.write_bytes(b"not HDF5")
    artifact = register_snapshot(
        app.state.catalog,
        app.state.workspace,
        project,
        source,
        kind="convert",
        metadata={"schema": "curve"},
    )
    reply = promote(app, home, project, artifact.id)
    assert reply.status_code == 400, reply.text
    assert len(app.state.catalog.list_datasets(project)) == 1


def test_mutable_legacy_output_requires_a_new_conversion_snapshot(workflow):
    app, home, project = workflow
    artifact = converted(workflow)
    mutable = app.state.catalog.register_artifact(
        project,
        app.state.workspace / artifact.metadata["output_path"],
        kind="convert",
        sha256=artifact.sha256,
        metadata={"schema": "curve"},
    )
    response = promote(app, home, project, mutable.id)
    assert response.status_code == 400, response.text
    assert len(app.state.catalog.list_datasets(project)) == 1


def test_csv_import_registration_rolls_back_schema_when_dataset_insert_fails(workflow):
    app, _, project = workflow
    catalog = app.state.catalog
    root = app.state.workspace / "projects" / str(project)
    data, schema = root / "data.h5", root / "schema.json"
    data.write_bytes(b"catalog stores hashes independently of parsing")
    schema.write_text("{}")
    before = catalog.list_datasets(project)
    with sqlite3.connect(catalog.database) as connection:
        connection.execute("""
            CREATE TRIGGER reject_import BEFORE INSERT ON datasets BEGIN
                SELECT RAISE(ABORT, 'injected dataset failure');
            END
        """)
    assert hasattr(catalog, "register_csv_import")
    with pytest.raises(CatalogError, match="injected dataset failure"):
        catalog.register_csv_import(
            project,
            data_path=data,
            data_sha256=path_sha256(data),
            schema_path=schema,
            schema_sha256=path_sha256(schema),
            schema_name="csv-import",
            metadata={"source": "csv"},
        )
    assert catalog.list_schemas(project) == ()
    assert catalog.list_datasets(project) == before


@pytest.mark.parametrize("problem", ["changed", "missing", "foreign", "unspecified"])
def test_unavailable_original_schema_is_never_replaced_by_another_schema(workflow, problem):
    app, home, project = workflow
    selector = project_schema(workflow)
    artifact = converted(workflow, selector=selector)
    schema = app.state.catalog.get_schema(int(selector.split(":")[1]))
    path = app.state.workspace / schema.relative_path
    if problem == "changed":
        path.write_text(path.read_text() + " ")
    elif problem == "missing":
        path.unlink()
    else:
        metadata = dict(artifact.metadata)
        if problem == "unspecified":
            metadata.pop("schema")
        else:
            other = app.state.catalog.create_project("other")
            foreign = app.state.catalog.register_schema(
                other.id,
                name="curve",
                version="1.0",
                path=path,
                sha256=schema.sha256,
            )
            metadata["schema"] = f"schema:{foreign.id}"
        artifact = app.state.catalog.register_artifact(
            project,
            app.state.workspace / artifact.relative_path,
            kind="convert",
            sha256=artifact.sha256,
            metadata=metadata,
        )
    response = promote(app, home, project, artifact.id)
    assert response.status_code == 409, response.text
    assert len(app.state.catalog.list_datasets(project)) == 1


@pytest.mark.parametrize("stage", ["before-promotion", "after-promotion"])
def test_linked_snapshot_directory_is_rejected_even_when_bytes_match(workflow, stage):
    app, home, project = workflow
    artifact = converted(workflow)
    snapshot = app.state.workspace / artifact.relative_path
    payload = None
    if stage == "after-promotion":
        response = promote(app, home, project, artifact.id)
        assert response.status_code == 200, response.text
        payload = response.json()
    original_directory = snapshot.parent
    held = original_directory.with_name(original_directory.name + "-held")
    original_directory.rename(held)
    try:
        try:
            original_directory.symlink_to(held, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                pytest.skip(f"Directory symbolic links unavailable: {exc}")
            import _winapi

            _winapi.CreateJunction(str(held), str(original_directory))
        response = promote(app, home, project, artifact.id)
        assert response.status_code in {400, 404, 409}, response.text
        assert response.json().get("error")
        if payload is not None:
            report = _request(
                app,
                "POST",
                f"/api/projects/{project}/report",
                cookies=home.cookies,
                headers={"X-CSRF-Token": _csrf(home)},
                data={
                    "dataset_id": payload["dataset_id"],
                    "schema": payload["schema_selector"],
                    "output": "linked.json",
                    "format": "json",
                },
            )
            if report.status_code == 202:
                _wait_for_job(app, report.json()["job_id"])
            assert report.status_code == 400, report.text
        assert len(app.state.catalog.list_datasets(project)) == (2 if payload else 1)
    finally:
        if original_directory.is_symlink():
            original_directory.unlink()
        elif original_directory.is_junction():
            original_directory.rmdir()
        held.rename(original_directory)
