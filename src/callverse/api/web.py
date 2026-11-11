"""Serve the two built React apps from the API itself (used online, on the Hugging Face Space).

In development, Vite serves each app on its own port (5173 and 5174) and forwards /api and /ws to this
backend. Online there is one address and one port, so the backend also hands out the built files:

    /               the front office (customers, the advisors' desk, the phone line)
    /back-office/   the back office (managers: the contact centre, AI monitoring, ...)
    /api, /ws, /docs, /mcp   the API, unchanged (its routes are matched first)

``mount_web_apps`` does nothing unless ``CALLVERSE_STATIC_DIR`` names a folder with the two builds:

    <CALLVERSE_STATIC_DIR>/front-office/index.html   (frontend/front-office/dist)
    <CALLVERSE_STATIC_DIR>/back-office/index.html    (frontend/back-office/dist, built with
                                                      BACK_OFFICE_BASE=/back-office/)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path, PurePath

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketClose

BACK_OFFICE_PATH = "/back-office"
# First part of the addresses that belong to the API: an unknown address there stays a real 404, instead
# of getting the front office's web page.
API_PREFIXES = ("api", "ws", "mcp", "docs", "redoc", "openapi.json")

log = logging.getLogger(__name__)


class SinglePageApp(StaticFiles):
    """The built files of one React app.

    React picks the page from the address (/centre, /monitoring, /portal...), and these pages are not files.
    So an address that is not a file gets index.html, and the app shows the right page, also after a reload
    or from a shared link. A missing file with an extension (an old .js file) still gets a 404.
    """

    def __init__(self, directory: Path, reserved: tuple[str, ...] = ()) -> None:
        super().__init__(directory=directory, html=True)
        self.reserved = reserved  # first parts of addresses that are never pages of this app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # A WebSocket to an unknown address (the real ones, /ws/..., are API routes): close it.
        if scope["type"] == "websocket":
            await WebSocketClose()(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            parts = PurePath(path).parts
            is_page = not PurePath(path).suffix and not (parts and parts[0] in self.reserved)
            if error.status_code != 404 or not is_page:
                raise
            response = await super().get_response("index.html", scope)
        # Built files have a content hash in their name (assets/index-3f9a2c.js): the browser may keep them
        # for a year. Everything else (index.html) is checked again each time, so a new version shows at once.
        hashed = PurePath(path).parts[:1] == ("assets",)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if hashed else "no-cache"
        return response


async def _back_office_slash(request: Request) -> Response:
    """/back-office -> /back-office/ (the app's files are inside that folder)."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"{BACK_OFFICE_PATH}/{query}")


def mount_web_apps(app: FastAPI, static_dir: str | Path | None = None) -> list[str]:
    """Serve the built apps found in ``static_dir`` (default: the CALLVERSE_STATIC_DIR variable).

    Call it after every API route: the front office is mounted at "/", which catches every address, so a
    route added later would never be reached. Returns the mounted paths (empty in development).
    """
    folder = static_dir or os.environ.get("CALLVERSE_STATIC_DIR")
    if not folder:
        return []
    back, front = Path(folder) / "back-office", Path(folder) / "front-office"
    mounted = []
    if (back / "index.html").is_file():
        app.add_route(BACK_OFFICE_PATH, _back_office_slash, include_in_schema=False)
        app.mount(BACK_OFFICE_PATH, SinglePageApp(back), name="back-office")
        mounted.append(f"{BACK_OFFICE_PATH}/")
    if (front / "index.html").is_file():
        reserved = (*API_PREFIXES, BACK_OFFICE_PATH.strip("/"))
        app.mount("/", SinglePageApp(front, reserved=reserved), name="front-office")
        mounted.append("/")
    if not mounted:
        log.warning("CALLVERSE_STATIC_DIR=%s has no front-office/ or back-office/ build", folder)
    return mounted
