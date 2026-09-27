"""Catalog failures and concurrent partial job updates have stable contracts."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from cpdatakit.catalog import CatalogError, SQLiteCatalog


@pytest.fixture
def catalog(tmp_path):
    result = SQLiteCatalog(tmp_path / "catalog.sqlite3", tmp_path)
    result.initialize()
    project = result.create_project("study")
    result.register_job(project.id, job_id="work", operation="inspect", status="queued")
    return result


READS = [
    ("get_project", (1,)),
    ("list_projects", ()),
    ("list_datasets", (1,)),
    ("list_artifacts", (1,)),
    ("list_schemas", (1,)),
    ("get_job", ("work",)),
    ("list_jobs", (1,)),
    ("get_dataset", (1,)),
    ("get_artifact", (1,)),
    ("get_schema", (1,)),
    ("count_resources", (1,)),
]


@pytest.mark.parametrize("method, args", READS)
@pytest.mark.parametrize("phase", ["connect", "query"])
def test_all_reads_translate_database_errors(catalog, monkeypatch, method, args, phase):
    original = catalog._connect

    def failed_connection():
        if phase == "connect":
            raise sqlite3.DatabaseError("injected database failure")
        connection = original()
        # A real SQLite authorizer rejects reads at the execution boundary.
        resource = method.removeprefix("get_").removeprefix("list_")
        table = "datasets" if method == "count_resources" else resource.rstrip("s") + "s"
        connection.set_authorizer(
            lambda action, name, *args: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_READ and name == table
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    monkeypatch.setattr(catalog, "_connect", failed_connection)
    with pytest.raises(CatalogError) as caught:
        getattr(catalog, method)(*args)
    assert isinstance(caught.value.__cause__, sqlite3.DatabaseError)


def test_connections_enable_wal_and_wait_for_busy_writers(catalog):
    connection = catalog._connect()
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_two_real_threads_preserve_independent_job_fields(catalog, monkeypatch):
    original = catalog._connect
    ready = {name: threading.Event() for name in ("catalog-test_0", "catalog-test_1")}
    release = threading.Event()
    paused = set()

    def traced_connection():
        connection = original()

        def trace(statement):
            name = threading.current_thread().name
            if name not in ready or name in paused:
                return
            sql = statement.upper()
            if sql.startswith("BEGIN IMMEDIATE") or sql.startswith("UPDATE JOBS"):
                paused.add(name)
                ready[name].set()
                release.wait(10)

        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(catalog, "_connect", traced_connection)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="catalog-test") as executor:
        first = executor.submit(
            catalog.update_job,
            "work",
            status="running",
            started_at="start",
            operation_log=("progress",),
        )
        second = executor.submit(
            catalog.update_job, "work", status="running", finished_at="finish", result={"rows": 2}
        )
        try:
            assert all(event.wait(5) for event in ready.values())
        finally:
            release.set()
        first.result(timeout=10)
        second.result(timeout=10)
    stored = catalog.get_job("work")
    assert stored.started_at == "start"
    assert stored.finished_at == "finish"
    assert stored.operation_log == ("progress",)
    assert stored.result == {"rows": 2}


def test_failed_job_update_rolls_back_the_transaction(catalog, monkeypatch):
    original = catalog._connect

    def restricted_connection():
        connection = original()
        connection.set_authorizer(
            lambda action, *args: (
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_UPDATE else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(catalog, "_connect", restricted_connection)
        with pytest.raises(CatalogError):
            catalog.update_job("work", status="running", started_at="discard")
    stored = catalog.get_job("work")
    assert stored.status == "queued"
    assert stored.started_at is None


def test_missing_job_update_retains_domain_error(catalog):
    with pytest.raises(CatalogError, match="Job does not exist"):
        catalog.update_job("missing", status="running")
    assert catalog.get_job("work").status == "queued"


@pytest.mark.parametrize("phase", ["open", "configure"])
def test_native_connection_failure_is_wrapped_and_closed(catalog, monkeypatch, phase):
    original = sqlite3.connect
    opened = []

    def connection_failure(*args, **kwargs):
        if phase == "open":
            raise sqlite3.OperationalError("injected open failure")
        connection = original(*args, **kwargs)
        connection.set_authorizer(lambda *args: sqlite3.SQLITE_DENY)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connection_failure)
    with pytest.raises(CatalogError) as caught:
        catalog.list_projects()
    assert isinstance(caught.value.__cause__, sqlite3.DatabaseError)
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
