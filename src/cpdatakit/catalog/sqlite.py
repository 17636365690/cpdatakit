"""Transactional SQLite catalog with explicit workspace path containment."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..exceptions import CatalogError

_CURRENT_SCHEMA_VERSION = 3
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: int
    name: str
    workspace: str


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    id: int
    project_id: int
    relative_path: str
    sha256: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    id: int
    project_id: int
    relative_path: str
    kind: str
    sha256: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SchemaRecord:
    id: int
    project_id: int
    name: str
    version: str
    relative_path: str | None
    sha256: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CatalogJobRecord:
    id: str
    project_id: int
    operation: str
    status: str
    started_at: str | None
    finished_at: str | None
    input_filename: str | None
    output_filename: str | None
    operation_log: tuple[str, ...]
    error: str | None


def _json_text(value: dict[str, Any], label: str) -> str:
    if not isinstance(value, dict):
        raise CatalogError(f"{label} must be an object")
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CatalogError(f"{label} must be JSON-compatible") from exc


class SQLiteCatalog:
    """Store catalog records without owning or deleting workspace source bytes."""

    def __init__(self, database: str | Path, workspace: str | Path) -> None:
        self.database = Path(database)
        self.workspace = Path(workspace)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _backup_path(self) -> Path:
        candidate = self.database.with_name(self.database.name + ".bak")
        if not candidate.exists():
            return candidate
        index = 1
        while True:
            candidate = self.database.with_name(f"{self.database.name}.bak.{index}")
            if not candidate.exists():
                return candidate
            index += 1

    def _migrate(self, connection: sqlite3.Connection) -> None:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > _CURRENT_SCHEMA_VERSION:
            raise CatalogError(
                f"Unsupported catalog schema version {current}; "
                f"maximum is {_CURRENT_SCHEMA_VERSION}"
            )
        if current == _CURRENT_SCHEMA_VERSION:
            return
        if self.database.exists() and self.database.stat().st_size > 0:
            try:
                shutil.copy2(self.database, self._backup_path())
            except OSError as exc:
                raise CatalogError(f"Cannot back up catalog before migration: {exc}") from exc
        connection.execute("BEGIN")
        try:
            if current < 1:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        workspace TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS datasets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        relative_path TEXT NOT NULL,
                        sha256 TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS artifacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        relative_path TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        sha256 TEXT NOT NULL
                    );
                    """
                )
                current = 1
            if current < 2:
                connection.execute(
                    "ALTER TABLE datasets ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                )
                connection.execute(
                    "ALTER TABLE artifacts ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                )
                current = 2
            if current < 3:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schemas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        version TEXT NOT NULL,
                        relative_path TEXT,
                        sha256 TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        operation TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        input_filename TEXT,
                        output_filename TEXT,
                        operation_log_json TEXT NOT NULL DEFAULT '[]',
                        error TEXT
                    );
                    """
                )
                current = 3
            connection.execute(f"PRAGMA user_version = {current}")
            connection.commit()
        except (sqlite3.DatabaseError, CatalogError):
            connection.rollback()
            raise

    def initialize(self) -> None:
        """Create or migrate the catalog, backing up non-empty databases first."""

        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            self._migrate(connection)
        except sqlite3.DatabaseError as exc:
            raise CatalogError(f"Cannot initialize catalog: {exc}") from exc
        finally:
            connection.close()

    def _relative_path(self, path: str | Path) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        try:
            relative = candidate.resolve(strict=False).relative_to(
                self.workspace.resolve(strict=False)
            )
        except (OSError, ValueError) as exc:
            raise CatalogError("Catalog paths must stay inside the workspace") from exc
        if not relative.parts:
            raise CatalogError("Catalog path must name a workspace entry")
        return relative.as_posix()

    @staticmethod
    def _validate_hash(value: str) -> str:
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise CatalogError("sha256 must be a 64-character hexadecimal digest")
        return value.lower()

    def create_project(self, name: str) -> ProjectRecord:
        if not isinstance(name, str) or not name.strip():
            raise CatalogError("Project name must be non-empty")
        connection = self._connect()
        try:
            row = connection.execute(
                "INSERT INTO projects (name, workspace) VALUES (?, ?)", (name, ".")
            )
            connection.commit()
            return ProjectRecord(int(row.lastrowid), name, ".")
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot create project: {exc}") from exc
        finally:
            connection.close()

    def get_project(self, project_id: int) -> ProjectRecord:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, name, workspace FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise CatalogError(f"Project does not exist: {project_id}")
        return ProjectRecord(int(row["id"]), row["name"], row["workspace"])

    def list_projects(self) -> tuple[ProjectRecord, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, name, workspace FROM projects ORDER BY id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(ProjectRecord(int(row["id"]), row["name"], row["workspace"]) for row in rows)

    def register_dataset(
        self,
        project_id: int,
        path: str | Path,
        *,
        sha256: str,
        metadata: dict[str, Any] | None = None,
    ) -> DatasetRecord:
        self.get_project(project_id)
        relative_path = self._relative_path(path)
        digest = self._validate_hash(sha256)
        metadata_text = _json_text(metadata or {}, "Dataset metadata")
        connection = self._connect()
        try:
            row = connection.execute(
                "INSERT INTO datasets (project_id, relative_path, sha256, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (project_id, relative_path, digest, metadata_text),
            )
            connection.commit()
            return DatasetRecord(
                int(row.lastrowid), project_id, relative_path, digest, json.loads(metadata_text)
            )
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot register dataset: {exc}") from exc
        finally:
            connection.close()

    def list_datasets(self, project_id: int) -> tuple[DatasetRecord, ...]:
        self.get_project(project_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, project_id, relative_path, sha256, metadata_json "
                "FROM datasets WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            DatasetRecord(
                int(row["id"]),
                int(row["project_id"]),
                row["relative_path"],
                row["sha256"],
                json.loads(row["metadata_json"]),
            )
            for row in rows
        )

    def register_artifact(
        self,
        project_id: int,
        path: str | Path,
        *,
        kind: str,
        sha256: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        self.get_project(project_id)
        if not isinstance(kind, str) or not kind.strip():
            raise CatalogError("Artifact kind must be non-empty")
        relative_path = self._relative_path(path)
        digest = self._validate_hash(sha256)
        metadata_text = _json_text(metadata or {}, "Artifact metadata")
        connection = self._connect()
        try:
            row = connection.execute(
                "INSERT INTO artifacts (project_id, relative_path, kind, sha256, metadata_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_id, relative_path, kind, digest, metadata_text),
            )
            connection.commit()
            return ArtifactRecord(
                int(row.lastrowid),
                project_id,
                relative_path,
                kind,
                digest,
                json.loads(metadata_text),
            )
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot register artifact: {exc}") from exc
        finally:
            connection.close()

    def list_artifacts(self, project_id: int) -> tuple[ArtifactRecord, ...]:
        self.get_project(project_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, project_id, relative_path, kind, sha256, metadata_json "
                "FROM artifacts WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            ArtifactRecord(
                int(row["id"]),
                int(row["project_id"]),
                row["relative_path"],
                row["kind"],
                row["sha256"],
                json.loads(row["metadata_json"]),
            )
            for row in rows
        )

    def register_schema(
        self,
        project_id: int,
        *,
        name: str,
        version: str,
        sha256: str,
        path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SchemaRecord:
        self.get_project(project_id)
        if not isinstance(name, str) or not name.strip():
            raise CatalogError("Schema name must be non-empty")
        if not isinstance(version, str) or not version.strip():
            raise CatalogError("Schema version must be non-empty")
        relative_path = self._relative_path(path) if path is not None else None
        digest = self._validate_hash(sha256)
        metadata_text = _json_text(metadata or {}, "Schema metadata")
        connection = self._connect()
        try:
            row = connection.execute(
                "INSERT INTO schemas "
                "(project_id, name, version, relative_path, sha256, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name, version, relative_path, digest, metadata_text),
            )
            connection.commit()
            return SchemaRecord(
                int(row.lastrowid),
                project_id,
                name,
                version,
                relative_path,
                digest,
                json.loads(metadata_text),
            )
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot register schema: {exc}") from exc
        finally:
            connection.close()

    def list_schemas(self, project_id: int) -> tuple[SchemaRecord, ...]:
        self.get_project(project_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, project_id, name, version, relative_path, sha256, metadata_json "
                "FROM schemas WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            SchemaRecord(
                int(row["id"]),
                int(row["project_id"]),
                row["name"],
                row["version"],
                row["relative_path"],
                row["sha256"],
                json.loads(row["metadata_json"]),
            )
            for row in rows
        )

    def register_job(
        self,
        project_id: int,
        *,
        job_id: str,
        operation: str,
        status: str,
        started_at: str | None = None,
        finished_at: str | None = None,
        input_filename: str | None = None,
        output_filename: str | None = None,
        operation_log: tuple[str, ...] = (),
        error: str | None = None,
    ) -> CatalogJobRecord:
        self.get_project(project_id)
        if not isinstance(job_id, str) or not job_id.strip():
            raise CatalogError("Job id must be non-empty")
        if not isinstance(operation, str) or not operation.strip():
            raise CatalogError("Job operation must be non-empty")
        if not isinstance(status, str) or not status.strip():
            raise CatalogError("Job status must be non-empty")
        log = tuple(str(item) for item in operation_log)
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO jobs "
                "(id, project_id, operation, status, started_at, finished_at, input_filename, "
                "output_filename, operation_log_json, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    project_id,
                    operation,
                    status,
                    started_at,
                    finished_at,
                    Path(input_filename).name if input_filename else None,
                    Path(output_filename).name if output_filename else None,
                    json.dumps(log, ensure_ascii=False),
                    error,
                ),
            )
            connection.commit()
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot register job: {exc}") from exc
        finally:
            connection.close()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> CatalogJobRecord:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, project_id, operation, status, started_at, finished_at, "
                "input_filename, "
                "output_filename, operation_log_json, error FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise CatalogError(f"Job does not exist: {job_id}")
        return CatalogJobRecord(
            row["id"],
            int(row["project_id"]),
            row["operation"],
            row["status"],
            row["started_at"],
            row["finished_at"],
            row["input_filename"],
            row["output_filename"],
            tuple(json.loads(row["operation_log_json"])),
            row["error"],
        )

    def list_jobs(self, project_id: int) -> tuple[CatalogJobRecord, ...]:
        self.get_project(project_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, project_id, operation, status, started_at, finished_at, "
                "input_filename, output_filename, operation_log_json, error "
                "FROM jobs WHERE project_id = ? ORDER BY rowid",
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CatalogJobRecord(
                row["id"],
                int(row["project_id"]),
                row["operation"],
                row["status"],
                row["started_at"],
                row["finished_at"],
                row["input_filename"],
                row["output_filename"],
                tuple(json.loads(row["operation_log_json"])),
                row["error"],
            )
            for row in rows
        )

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        started_at: str | None = None,
        finished_at: str | None = None,
        operation_log: tuple[str, ...] | None = None,
        error: str | None = None,
    ) -> CatalogJobRecord:
        current = self.get_job(job_id)
        if not isinstance(status, str) or not status.strip():
            raise CatalogError("Job status must be non-empty")
        log = current.operation_log if operation_log is None else tuple(operation_log)
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE jobs SET status = ?, started_at = ?, finished_at = ?, "
                "operation_log_json = ?, error = ? WHERE id = ?",
                (
                    status,
                    started_at if started_at is not None else current.started_at,
                    finished_at if finished_at is not None else current.finished_at,
                    json.dumps(log, ensure_ascii=False),
                    error,
                    job_id,
                ),
            )
            connection.commit()
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot update job: {exc}") from exc
        finally:
            connection.close()
        return self.get_job(job_id)

    def delete_dataset(self, dataset_id: int) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            connection.commit()
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise CatalogError(f"Cannot delete dataset record: {exc}") from exc
        finally:
            connection.close()
