"""Explicit CSV review and atomic registration of its source/data/schema bundle."""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Annotated

from fastapi import File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from .._atomic import publish_directory
from ..application.csv_intake import prepare_csv, preview_csv
from ..application.data_access import path_sha256
from ..exceptions import CatalogError, CPDataKitError, DataValidationError
from ..io import write_hdf5
from ..schema import schema_to_dict
from ..validation import validate_dataset
from .uploads import UploadPublication, cleanup_upload_staging
from .workbench import project_directory

logger = logging.getLogger(__name__)


def _json_object(text: str, expected: type):
    if len(text) > 1024 * 1024:
        raise DataValidationError("导入设置过大。请减少字段数量。")
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise DataValidationError("导入设置无效。请重新预览文件。") from exc
    if not isinstance(value, expected):
        raise DataValidationError("导入设置类型无效。请重新预览文件。")
    return value


def install_csv_workflow(app, *, require_csrf):
    from .app import _json_error, _safe_upload_name

    def read_source(file):
        payload = file.file.read(app.state.upload_limit + 1)
        if len(payload) > app.state.upload_limit:
            raise DataValidationError("文件超过本地上传大小限制。")
        return payload

    def invalid(exc):
        return _json_error(
            400, "csv_review_required", str(exc), "请核对文件解析设置及表格中的字段、单位和用途。"
        )

    @app.post("/api/projects/{project_id}/csv-preview")
    def preview(
        request: Request,
        project_id: int,
        file: Annotated[UploadFile, File()],
        options_json: Annotated[str, Form()] = "{}",
        csrf_token_form: Annotated[str | None, Form(alias="csrf_token")] = None,
    ) -> Response:
        try:
            error = require_csrf(request, csrf_token_form)
            if error is not None:
                return error
            project_directory(app, project_id)
            result = preview_csv(
                read_source(file),
                _json_object(options_json, dict),
                max_bytes=app.state.upload_limit,
            )
            return JSONResponse(result)
        except DataValidationError as exc:
            return invalid(exc)
        except (CPDataKitError, OSError, ValueError):
            return _json_error(
                400,
                "csv_preview_failed",
                "无法预览该文件。请检查项目和文件。",
                "重新选择文件并确认编码、分隔符和表头行。",
            )
        finally:
            file.file.close()

    @app.post("/api/projects/{project_id}/csv-import")
    def import_reviewed(
        request: Request,
        project_id: int,
        file: Annotated[UploadFile, File()],
        options_json: Annotated[str, Form()] = "{}",
        columns_json: Annotated[str, Form()] = "[]",
        source_sha256: Annotated[str, Form()] = "",
        confirmed: Annotated[bool, Form()] = False,
        conventions: Annotated[str, Form()] = "",
        csrf_token_form: Annotated[str | None, Form(alias="csrf_token")] = None,
    ) -> Response:
        staged = None
        published = False
        target = None
        try:
            error = require_csrf(request, csrf_token_form)
            if error is not None:
                return error
            root = project_directory(app, project_id)
            if not confirmed or not conventions.strip() or len(conventions) > 4000:
                raise DataValidationError(
                    "请填写数据定义与来源说明。确认字段、单位和排除项后导入。"
                )
            if len(source_sha256) != 64:
                raise DataValidationError("请先预览当前文件。再确认导入。")
            payload = read_source(file)
            name = _safe_upload_name(file.filename)
            prepared = prepare_csv(
                payload,
                _json_object(options_json, dict),
                _json_object(columns_json, list),
                source_name=name,
                source_sha256=source_sha256,
                max_bytes=app.state.upload_limit,
            )
            schema = replace(
                prepared.schema,
                conventions={
                    **dict(prepared.schema.conventions),
                    "confirmed_source_definition": conventions.strip(),
                },
            )
            validation = validate_dataset(prepared.value, schema)
            if not validation.valid:
                raise DataValidationError("已确认的数据仍有校验错误。请检查字段取值。")
            uploads = root / "uploads"
            if uploads.is_symlink() or not uploads.resolve().is_relative_to(root):
                raise DataValidationError("项目上传目录不可用。")
            uploads.mkdir(exist_ok=True)
            staged = Path(tempfile.mkdtemp(prefix=".csv-import-", dir=uploads))
            target = uploads / ("csv-" + uuid.uuid4().hex)
            (staged / "source.csv").write_bytes(payload)
            prepared.value.source = staged / "source.csv"
            manifest = {**prepared.manifest, "confirmed_source_definition": conventions.strip()}
            (staged / "schema.json").write_text(
                json.dumps(schema_to_dict(schema), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (staged / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            write_hdf5(
                prepared.value,
                staged / "data.h5",
                schema,
                validation,
                source_description=f"CSV import: {name}; {conventions.strip()}",
                operation_log=["Explicit CSV import", json.dumps(manifest, ensure_ascii=False)],
            )
            metadata = {
                "csv_import": True,
                "source_name": name,
                "source_sha256": source_sha256,
                "manifest_sha256": path_sha256(staged / "manifest.json"),
                "schema_sha256": path_sha256(staged / "schema.json"),
            }
            data_hash = path_sha256(staged / "data.h5")
            publication = UploadPublication(staged, target, app.state.workspace)
            publish_directory(staged, target)
            published = True
            publication.published = True
            publication.verify()
            dataset, stored_schema = app.state.catalog.register_csv_import(
                project_id,
                data_path=target / "data.h5",
                data_sha256=data_hash,
                schema_path=target / "schema.json",
                schema_sha256=metadata["schema_sha256"],
                schema_name=schema.profile,
                metadata=metadata,
            )
            # Keep committed records as evidence if an external writer changed
            # the bundle during registration, but never report an intact import.
            publication.verify()
            return JSONResponse(
                {
                    "status": "succeeded",
                    "operation": "csv_import",
                    "dataset_id": dataset.id,
                    "schema_selector": f"schema:{stored_schema.id}",
                    "filename": f"{name} · 已确认数据",
                    "schema_name": stored_schema.name,
                    "validation": validation.to_dict(),
                    "value": {
                        "record_count": len(prepared.value.data),
                        "fields": list(prepared.value.data),
                        "validation": validation.to_dict(),
                    },
                    "provenance": {"source_sha256": source_sha256},
                    "manifest": manifest,
                },
                status_code=201,
            )
        except DataValidationError as exc:
            return invalid(exc)
        except (CPDataKitError, OSError, ValueError):
            logger.exception("CSV import could not be completed")
            result = _json_error(
                400 if not published else 500,
                "csv_import_failed",
                "CSV 导入未完成。原始内容与已生成文件已保留。"
                if published
                else "CSV 导入未完成。请检查声明和工作区。",
                "请重新预览并检查导入设置。登记失败时先检查工作区中的导入目录。",
            )
            return result
        finally:
            file.file.close()
            if staged is not None and staged.exists() and not published:
                cleanup_upload_staging(staged)

    @app.get("/api/projects/{project_id}/csv-imports/{dataset_id}/{part}")
    def import_record(project_id: int, dataset_id: int, part: str) -> Response:
        try:
            root = project_directory(app, project_id)
            record = app.state.catalog.get_dataset(dataset_id)
            if record.project_id != project_id or not record.metadata.get("csv_import"):
                raise CatalogError("Not a CSV import")
            filename, key = {
                "source": ("source.csv", "source_sha256"),
                "schema": ("schema.json", "schema_sha256"),
                "manifest": ("manifest.json", "manifest_sha256"),
            }[part]
            directory = (app.state.workspace / record.relative_path).parent
            path = directory / filename
            if (
                path.is_symlink()
                or not path.resolve().is_relative_to(root)
                or path_sha256(path) != record.metadata[key]
            ):
                raise CatalogError("Import record has changed")
            return FileResponse(
                path,
                filename=filename,
                media_type="application/json" if part != "source" else "text/csv",
            )
        except (CPDataKitError, OSError, KeyError):
            return _json_error(
                404,
                "import_record_unavailable",
                "导入记录不可用或已经变更。",
                "请检查项目中的原始导入目录。",
            )
