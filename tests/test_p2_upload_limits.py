"""Upload limits must protect the parser's real temporary files before routing."""

import asyncio
import tempfile
from typing import Annotated

import httpx
import pytest
from fastapi import File, UploadFile
from starlette.requests import ClientDisconnect
from test_web import _csrf, _request

from cpdatakit.web import create_app


@pytest.fixture
def app(tmp_path):
    value = create_app(tmp_path / "workspace", max_upload_bytes=32)
    yield value
    value.state.close()


@pytest.fixture
def spool_files(monkeypatch):
    import starlette.formparsers as parsers

    files = []

    class ObservedSpool(tempfile.SpooledTemporaryFile):
        written = 0

        def write(self, data):
            count = super().write(data)
            self.written += count
            return count

    def create(*args, **kwargs):
        result = ObservedSpool(*args, **kwargs)
        files.append(result)
        return result

    monkeypatch.setattr(parsers, "SpooledTemporaryFile", create)
    return files


def seed(app):
    home = _request(app, "GET", "/")
    created = _request(
        app,
        "POST",
        "/api/projects",
        cookies=home.cookies,
        headers={"X-CSRF-Token": _csrf(home)},
        data={"name": "limits"},
    )
    assert created.status_code == 201
    return home, created.json()["id"]


def multipart(files, fields=()):
    chunks = []
    for name, value in fields:
        chunks.append(f'--bound\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode() + b"\r\n")
    for name, filename, value in files:
        chunks.append(
            (
                f'--bound\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n\r\n'
            ).encode()
        )
        chunks.append(value + b"\r\n")
    chunks.append(b"--bound--\r\n")
    return b"".join(chunks)


def streamed(app, path, body, home, *, length=None, token=True, disconnect=False, cancelled=False):
    async def run():
        async def chunks():
            chunk_size = 16384 if len(body) > 1024 * 1024 else 16
            for offset in range(0, len(body), chunk_size):
                yield body[offset : offset + chunk_size]
            if disconnect:
                raise ClientDisconnect()
            if cancelled:
                raise asyncio.CancelledError()

        headers = {"Content-Type": "multipart/form-data; boundary=bound"}
        if length is not None:
            headers["Content-Length"] = str(length)
        if token:
            headers["X-CSRF-Token"] = _csrf(home)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            cookies=home.cookies,
        ) as client:
            return await client.post(path, content=chunks(), headers=headers)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "endpoint", ["inspect", "csv-preview", "csv-import", "schemas", "inspect-zarr"]
)
@pytest.mark.parametrize("length", [None, 1, "correct"])
def test_oversized_upload_stops_spooling_before_body_is_materialized(
    app, spool_files, endpoint, length
):
    home, project = seed(app)
    body = multipart(
        [
            (
                "files" if endpoint == "inspect-zarr" else "file",
                "data.zarr/x" if endpoint == "inspect-zarr" else "data.csv",
                b"x" * (2 * 1024 * 1024),
            )
        ]
    )
    response = streamed(
        app,
        f"/api/projects/{project}/{endpoint}",
        body,
        home,
        length=len(body) if length == "correct" else length,
    )
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "upload_too_large"
    assert sum(item.written for item in spool_files) <= 32
    assert all(item.closed for item in spool_files)
    assert not list((app.state.workspace / "projects" / str(project) / "uploads").iterdir())


@pytest.mark.parametrize(
    "credentials,code", [("session", "invalid_session"), ("header", "csrf_required")]
)
def test_bad_credentials_reject_without_starting_file_parser(app, spool_files, credentials, code):
    home, project = seed(app)
    headers = {"X-CSRF-Token": _csrf(home) if credentials == "session" else "invalid"}
    response = _request(
        app,
        "POST",
        f"/api/projects/{project}/inspect",
        cookies={} if credentials == "session" else home.cookies,
        headers=headers,
        files={"file": ("large.csv", b"x" * (2 * 1024 * 1024))},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == code
    assert not spool_files


def test_missing_header_keeps_bounded_form_csrf_fallback_and_next_request_works(app, spool_files):
    home, project = seed(app)
    path = f"/api/projects/{project}/inspect"
    response = streamed(
        app, path, multipart([("file", "large.csv", b"x" * 65536)]), home, token=False
    )
    assert response.status_code == 413
    assert sum(item.written for item in spool_files) <= 32
    curve = b"step,strain,stress\n0,0,0\n"
    response = streamed(
        app,
        path,
        multipart([("file", "curve.csv", curve)], [("csrf_token", _csrf(home))]),
        home,
        token=False,
    )
    assert response.status_code == 200, response.text
    assert (
        app.state.workspace / "projects" / str(project) / "uploads" / "curve.csv"
    ).read_bytes() == curve
    assert all(item.closed for item in spool_files)


def test_zarr_aggregate_limit_applies_before_spooling_later_files(app, spool_files):
    home, project = seed(app)
    body = multipart([("files", "sample.zarr/a", b"a" * 24), ("files", "sample.zarr/b", b"b" * 24)])
    response = streamed(app, f"/api/projects/{project}/inspect-zarr", body, home)
    assert response.status_code == 413
    assert sum(item.written for item in spool_files) <= 32
    assert all(item.closed for item in spool_files)


def test_unexpected_second_file_cannot_consume_another_upload_budget(app, spool_files):
    home, project = seed(app)
    body = multipart([("file", "a.csv", b"a" * 20), ("ignored", "b.csv", b"b" * 20)])
    response = streamed(app, f"/api/projects/{project}/csv-preview", body, home)
    assert response.status_code == 413
    assert all(item.closed for item in spool_files)


def test_disconnect_closes_partially_spooled_files(app, spool_files):
    home, project = seed(app)
    body = multipart([("file", "data.csv", b"step,strain,stress\n0,0,0\n")])[:-13]
    response = streamed(app, f"/api/projects/{project}/inspect", body, home, disconnect=True)
    assert response.status_code == 400
    assert spool_files and all(item.closed for item in spool_files)


def test_missing_final_boundary_never_publishes_partial_upload(app, spool_files):
    home, project = seed(app)
    body = multipart([("file", "data.csv", b"step,strain,stress\n0,0,0\n")])[:-11]
    response = streamed(app, f"/api/projects/{project}/inspect", body, home)
    assert response.status_code == 400
    assert all(item.closed for item in spool_files)
    assert not app.state.catalog.list_datasets(project)


def test_zarr_count_limit_closes_all_spools(app, spool_files):
    home, project = seed(app)
    body = multipart([("files", f"sample.zarr/{index}", b"") for index in range(1001)])
    response = streamed(app, f"/api/projects/{project}/inspect-zarr", body, home)
    assert response.status_code == 413
    assert len(spool_files) <= 1000
    assert all(item.closed for item in spool_files)


@pytest.mark.parametrize("bad_part", ["one-field", "aggregate-fields", "header"])
def test_form_and_header_budgets_reject_without_publishing(app, spool_files, bad_part):
    home, project = seed(app)
    if bad_part == "one-field":
        body = multipart([], [("options_json", "x" * (1024 * 1024 + 1))])
    elif bad_part == "aggregate-fields":
        body = multipart([], [(str(index), "x" * (768 * 1024)) for index in range(3)])
    else:
        body = (
            b'--bound\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n'
            + b"".join(b"X-Field: " + b"a" * 1200 + b"\r\n" for _ in range(7))
            + b"\r\na\r\n--bound--\r\n"
        )
    response = streamed(app, f"/api/projects/{project}/csv-preview", body, home)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"
    assert all(item.closed for item in spool_files)
    assert not app.state.catalog.list_datasets(project)


def test_cancellation_closes_partial_file(app, spool_files):
    home, project = seed(app)
    body = multipart([("file", "data.csv", b"step,strain,stress\n0,0,0\n")])[:-13]

    async def run():
        entered = asyncio.Event()

        async def content():
            yield body
            entered.set()
            await asyncio.Event().wait()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            cookies=home.cookies,
        ) as client:
            task = asyncio.create_task(
                client.post(
                    f"/api/projects/{project}/inspect",
                    content=content(),
                    headers={
                        "Content-Type": "multipart/form-data; boundary=bound",
                        "X-CSRF-Token": _csrf(home),
                    },
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())
    assert spool_files and all(item.closed for item in spool_files)


def test_unicode_form_csrf_is_a_rejection_not_an_internal_error(app, spool_files):
    home, project = seed(app)
    body = multipart(
        [("file", "data.csv", b"step,strain,stress\n0,0,0\n")], [("csrf_token", "令牌")]
    )
    response = streamed(app, f"/api/projects/{project}/inspect", body, home, token=False)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_required"
    assert all(item.closed for item in spool_files)


def test_single_oversized_receive_frame_never_spools_payload(app, spool_files):
    home, project = seed(app)
    body = multipart([("file", "data.csv", b"x" * (2 * 1024 * 1024))])
    response = _request(
        app,
        "POST",
        f"/api/projects/{project}/inspect",
        cookies=home.cookies,
        headers={
            "Content-Type": "multipart/form-data; boundary=bound",
            "X-CSRF-Token": _csrf(home),
            "Content-Length": "1",
        },
        content=body,
    )
    assert response.status_code == 413
    assert sum(item.written for item in spool_files) <= 32
    assert all(item.closed for item in spool_files)


@pytest.mark.parametrize("case,status", [("oversized-length", 413), ("bad-token", 403)])
def test_header_rejection_does_not_receive_body(app, case, status):
    home, project = seed(app)

    async def run():
        async def content():
            raise AssertionError("Rejected request must not be received")
            yield b""  # pragma: no cover

        headers = {
            "Content-Type": "multipart/form-data; boundary=bound",
            "X-CSRF-Token": _csrf(home),
        }
        if case == "oversized-length":
            headers["Content-Length"] = "4194304"
        else:
            headers["X-CSRF-Token"] = "bad"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            cookies=home.cookies,
        ) as client:
            return await client.post(
                f"/api/projects/{project}/inspect", content=content(), headers=headers
            )

    response = asyncio.run(run())
    assert response.status_code == status


def test_deceptive_length_cannot_bypass_total_request_byte_budget(app, spool_files):
    home, project = seed(app)
    # An epilogue has no file payload for the per-file limiter to count.
    body = multipart([("file", "data.csv", b"x")]) + b"x" * (4 * 1024 * 1024)
    response = _request(
        app,
        "POST",
        f"/api/projects/{project}/inspect",
        cookies=home.cookies,
        headers={
            "Content-Type": "multipart/form-data; boundary=bound",
            "X-CSRF-Token": _csrf(home),
            "Content-Length": "1",
        },
        content=body,
    )
    assert response.status_code == 413
    assert not spool_files
    assert not app.state.catalog.list_datasets(project)


def test_cancel_after_complete_multipart_closes_rolled_spool(tmp_path, spool_files):
    app = create_app(tmp_path / "cancel-completed", max_upload_bytes=2 * 1024 * 1024)
    home = _request(app, "GET", "/")

    async def run():
        entered = asyncio.Event()

        @app.post("/cancel-completed")
        async def receive(file: Annotated[UploadFile, File()]):
            entered.set()
            await asyncio.Event().wait()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            cookies=home.cookies,
        ) as client:
            task = asyncio.create_task(
                client.post(
                    "/cancel-completed",
                    headers={"X-CSRF-Token": _csrf(home)},
                    files={"file": ("data.csv", b"x" * (1024 * 1024 + 1))},
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            assert spool_files and all(item._rolled for item in spool_files)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    try:
        asyncio.run(run())
        assert all(item.closed for item in spool_files)
    finally:
        app.state.close()


@pytest.mark.parametrize("prefix", [" ", "\t", " \t"])
def test_multipart_media_type_whitespace_cannot_skip_preparse_budget(app, spool_files, prefix):
    home, project = seed(app)
    body = multipart([("file", "data.csv", b"x" * 4096)])
    response = _request(
        app,
        "POST",
        f"/api/projects/{project}/inspect",
        cookies=home.cookies,
        headers={
            "Content-Type": prefix + "multipart/form-data; boundary=bound",
            "X-CSRF-Token": _csrf(home),
        },
        content=body,
    )
    assert response.status_code == 413
    assert sum(item.written for item in spool_files) <= 32
    assert all(item.closed for item in spool_files)
