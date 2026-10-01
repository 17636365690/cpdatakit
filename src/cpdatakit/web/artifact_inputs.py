"""Bind verified conversion snapshots as reusable project inputs.

Check identity before and after inspection. These checks do not lock out an
external process writing after the last check; consumers verify the stored
digest again before starting an operation.
"""

from pathlib import Path
from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import JSONResponse, Response

from ..application.data_access import inspect_input, path_sha256
from ..exceptions import CatalogError, CPDataKitError
from ..formats import ReadLimits
from .workbench import project_directory, select_schema


def _snapshot_path(workspace: Path, root: Path, relative_path: str) -> Path:
    path = workspace / relative_path
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CatalogError("Result is outside this project") from exc
    if not relative.parts or relative.parts[0] != ".artifacts":
        raise ValueError("Result is not an immutable snapshot; convert it again first")
    for candidate in (path, *path.parents):
        if candidate == workspace:
            break
        if candidate.is_symlink() or candidate.is_junction():
            raise CatalogError("Result contains a linked directory or file")
    resolved = path.resolve()
    if not resolved.is_relative_to(root / ".artifacts"):
        raise CatalogError("Result is outside this project's snapshots")
    if not (resolved.is_file() or (resolved.is_dir() and resolved.suffix.lower() == ".zarr")):
        raise CatalogError("Result data is missing")
    if resolved.is_dir():
        for entry in resolved.rglob("*"):
            if (
                entry.is_symlink()
                or entry.is_junction()
                or not entry.resolve().is_relative_to(root)
            ):
                raise CatalogError("Result contains a linked directory or file")
    return resolved


def install_artifact_inputs(app, *, require_csrf):
    """Install the CSRF-protected result-to-input operation."""
    from .app import _json_error

    @app.post("/api/projects/{project_id}/artifacts/{artifact_id}/use-as-input")
    def use_as_input(
        request: Request,
        project_id: int,
        artifact_id: int,
        csrf_token_form: Annotated[str | None, Form(alias="csrf_token")] = None,
    ) -> Response:
        error = require_csrf(request, csrf_token_form)
        if error is not None:
            return error
        catalog = app.state.catalog
        try:
            root = project_directory(app, project_id)
            artifact = catalog.get_artifact(artifact_id)
            if artifact.project_id != project_id:
                raise CatalogError("Result does not belong to this project")
            if artifact.kind != "convert":
                return _json_error(
                    400,
                    "artifact_not_data",
                    "Only converted data can be used as input.",
                    "Choose a conversion result.",
                )
            path = _snapshot_path(app.state.workspace, root, artifact.relative_path)
            if path_sha256(path) != artifact.sha256:
                return _json_error(
                    409,
                    "artifact_changed",
                    "Saved result has changed since registration.",
                    "Regenerate the conversion result before continuing.",
                )
        except (CPDataKitError, OSError):
            return _json_error(
                404,
                "artifact_not_found",
                "Result is missing or outside this project.",
                "Refresh the project results and choose an unchanged conversion.",
            )
        except ValueError:
            return _json_error(
                400,
                "artifact_not_snapshot",
                "This result has no immutable snapshot.",
                "Run the conversion again to save a reusable result.",
            )

        selector = artifact.metadata.get("schema")
        try:
            if not isinstance(selector, str) or not selector:
                raise CatalogError("Result has no original schema")
            select_schema(app, project_id, selector)
        except (CPDataKitError, OSError):
            return _json_error(
                409,
                "artifact_schema_unavailable",
                "The conversion's original schema is unavailable.",
                "Restore that schema or convert the source again with a confirmed schema.",
            )
        try:
            if path.suffix.lower() not in {".h5", ".hdf5", ".nc", ".netcdf", ".zarr", ".parquet"}:
                raise ValueError("Unsupported conversion format")
            inspect_input(
                path,
                None,
                ReadLimits(max_records=10**9, max_bytes=app.state.preview_limit),
            )
        except (CPDataKitError, OSError, ValueError):
            return _json_error(
                400,
                "artifact_unreadable",
                "Saved result cannot be inspected within the read limits.",
                "Check the conversion file and the workbench preview size limit.",
            )
        try:
            path = _snapshot_path(app.state.workspace, root, artifact.relative_path)
            if path_sha256(path) != artifact.sha256:
                raise CatalogError("Result changed during inspection")
            select_schema(app, project_id, selector)
        except (CPDataKitError, OSError, ValueError):
            return _json_error(
                409,
                "artifact_changed",
                "Saved result or its original schema changed during inspection.",
                "Regenerate the conversion result before continuing.",
            )
        try:
            dataset = catalog.register_artifact_input(
                project_id, artifact.id, schema_selector=selector
            )
        except CatalogError:
            return _json_error(
                409,
                "artifact_binding_failed",
                "Result could not be registered as project input.",
                "Refresh the project and retry the operation.",
            )
        return JSONResponse(
            {
                "dataset_id": dataset.id,
                "schema_selector": selector,
                "artifact_id": artifact.id,
                "filename": path.name,
            }
        )
