"""The API serves the built web apps online (callverse/api/web.py): API first, pages, redirect, real 404s."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from callverse.api.web import mount_web_apps


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    # Two tiny "builds": an index.html each, and one hashed file in the back office's assets/ folder.
    for name in ("front-office", "back-office"):
        (tmp_path / name / "assets").mkdir(parents=True)
        (tmp_path / name / "index.html").write_text(f"<html>{name}</html>", encoding="utf-8")
    (tmp_path / "back-office" / "assets" / "index-3f9a2c.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    assert mount_web_apps(app, tmp_path) == ["/back-office/", "/"]
    return TestClient(app)


def test_api_routes_come_first(client: TestClient) -> None:
    assert client.get("/api/ping").json() == {"ok": True}
    # A wrong API address stays a real 404, not the front office's page.
    assert client.get("/api/nothing-here").status_code == 404


def test_each_page_gets_its_app(client: TestClient) -> None:
    for path in ("/", "/portal/orders"):
        page = client.get(path)
        assert page.status_code == 200 and "front-office" in page.text
        assert page.headers["cache-control"] == "no-cache"  # a new version shows at once
    for path in ("/back-office/", "/back-office/centre"):
        page = client.get(path)
        assert page.status_code == 200 and "back-office" in page.text


def test_back_office_without_slash_redirects(client: TestClient) -> None:
    response = client.get("/back-office?x=1", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/back-office/?x=1"


def test_built_files_are_cached_and_missing_files_stay_404(client: TestClient) -> None:
    asset = client.get("/back-office/assets/index-3f9a2c.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert client.get("/assets/old-1234.js").status_code == 404


def test_unknown_websocket_is_closed(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/nothing-here"):
            pass


def test_nothing_is_mounted_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CALLVERSE_STATIC_DIR", raising=False)
    assert mount_web_apps(FastAPI()) == []
