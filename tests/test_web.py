from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from cpdatakit.web import create_app


def _request(app, method: str, url: str, **kwargs: object) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        cookies = kwargs.pop("cookies", None)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
            cookies=cookies,
        ) as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(run())


def _csrf(home: httpx.Response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', home.text)
    assert match is not None
    return match.group(1)


def test_local_ui_health_and_home_use_only_bundled_assets(tmp_path: Path) -> None:
    app = create_app(tmp_path)

    health = _request(app, "GET", "/health")
    home = _request(app, "GET", "/")
    style = _request(app, "GET", "/static/style.css")
    script = _request(app, "GET", "/static/app.js")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert home.status_code == 200
    assert "CPDataKit local workbench" in home.text
    assert "csrf_token" in home.text
    assert "/static/style.css" in home.text
    assert "/static/app.js" in home.text
    assert "https://" not in home.text.lower()
    assert style.status_code == 200
    assert script.status_code == 200
    cookie = home.headers["set-cookie"].lower()
    assert "cpdatakit_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_local_ui_rejects_non_local_host_headers(tmp_path: Path) -> None:
    app = create_app(tmp_path)

    response = _request(app, "GET", "/health", headers={"host": "evil.example"})

    assert response.status_code == 400
    assert "host" in response.json()["detail"].lower()


def test_local_ui_requires_csrf_for_project_creation(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    home = _request(app, "GET", "/")
    csrf = _csrf(home)
    cookies = home.cookies

    missing_csrf = _request(
        app,
        "POST",
        "/api/projects",
        cookies=cookies,
        data={"name": "study"},
    )
    created = _request(
        app,
        "POST",
        "/api/projects",
        cookies=cookies,
        data={"name": "study", "csrf_token": csrf},
    )

    assert missing_csrf.status_code == 403
    assert created.status_code == 201
    assert created.json()["name"] == "study"


def test_local_ui_upload_inspection_normalizes_filename_and_enforces_size(tmp_path: Path) -> None:
    app = create_app(tmp_path, max_upload_bytes=32)
    home = _request(app, "GET", "/")
    csrf = _csrf(home)
    project = _request(
        app,
        "POST",
        "/api/projects",
        cookies=home.cookies,
        headers={"X-CSRF-Token": csrf},
        data={"name": "study"},
    ).json()
    project_id = project["id"]
    curve = b"step,strain,stress\n0,0.0,0.0\n"

    inspected = _request(
        app,
        "POST",
        f"/api/projects/{project_id}/inspect",
        cookies=home.cookies,
        headers={"X-CSRF-Token": csrf},
        data={"schema": "curve"},
        files={"file": ("../curve.csv", curve, "text/csv")},
    )
    oversized = _request(
        app,
        "POST",
        f"/api/projects/{project_id}/inspect",
        cookies=home.cookies,
        headers={"X-CSRF-Token": csrf},
        data={"schema": "curve"},
        files={"file": ("large.csv", b"x" * 33, "text/csv")},
    )

    assert inspected.status_code == 200
    payload = inspected.json()
    assert payload["status"] == "succeeded"
    assert payload["value"]["file"]["filename"] == "curve.csv"
    assert (tmp_path / "projects" / str(project_id) / "uploads" / "curve.csv").exists()
    assert "../" not in json.dumps(payload)
    assert oversized.status_code == 413
    assert not list((tmp_path / "projects" / str(project_id) / "uploads").glob(".*.upload"))
