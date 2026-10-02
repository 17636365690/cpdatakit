"""The shared browser cookie jar must not invalidate another workspace."""

import asyncio

import httpx
from test_web import _csrf, _request

from cpdatakit.web import create_app


def test_two_ports_share_a_cookie_jar_and_both_workspaces_keep_working(tmp_path):
    apps = [create_app(tmp_path / "private-A"), create_app(tmp_path / "private-B")]

    async def run():
        jar = httpx.Cookies()
        clients = [
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=f"http://127.0.0.1:{49151 + index}"
            )
            for index, app in enumerate(apps)
        ]
        try:
            homes = []
            for client in clients:
                client.cookies = jar
                homes.append(await client.get("/"))
                jar.update(client.cookies)
            for index, client in enumerate(clients):
                client.cookies = jar
                response = await client.post(
                    "/api/projects",
                    data={"name": f"study-{index}"},
                    headers={"X-CSRF-Token": _csrf(homes[index])},
                )
                assert response.status_code == 201, response.text
                project = response.json()["id"]
                uploaded = await client.post(
                    f"/api/projects/{project}/inspect",
                    files={"file": ("data.csv", b"step,strain,stress\n0,0,0\n")},
                    headers={"X-CSRF-Token": _csrf(homes[index])},
                )
                assert uploaded.status_code == 200, uploaded.text
                jar.update(client.cookies)
            client = clients[0]
            client.cookies = jar
            await client.get("/")
            jar.update(client.cookies)
            clients[1].cookies = jar
            response = await clients[1].post(
                "/api/projects",
                data={"name": "still working"},
                headers={"X-CSRF-Token": _csrf(homes[1])},
            )
            assert response.status_code == 201
            assert len(jar) == 2
            assert all("private" not in cookie.name for cookie in jar.jar)
            forbidden = await client.post(
                "/api/projects",
                data={"name": "forbidden"},
                headers={"X-CSRF-Token": _csrf(homes[1])},
            )
            assert forbidden.status_code == 403
        finally:
            for client in clients:
                await client.aclose()

    try:
        asyncio.run(run())
    finally:
        for app in apps:
            app.state.close()


def test_workspace_restart_reuses_cookie_name_but_rejects_old_token(tmp_path):
    first = create_app(tmp_path)
    old = _request(first, "GET", "/")
    first.state.close()
    second = create_app(tmp_path)
    try:
        new = _request(second, "GET", "/")
        assert list(old.cookies.keys()) == list(new.cookies.keys())
        assert old.cookies != new.cookies
        stale = _request(
            second,
            "POST",
            "/api/projects",
            cookies=old.cookies,
            headers={"X-CSRF-Token": _csrf(old)},
            data={"name": "stale"},
        )
        assert stale.status_code == 403
        assert stale.json()["error"]["code"] == "invalid_session"
    finally:
        second.state.close()
