"""FastAPI factory: security middleware (§8), RFC 9457 errors (§5.1), REST, WS, and the static SPA."""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from hibiscus_station import __version__
from hibiscus_station.api.routes import build_mock_router, build_router
from hibiscus_station.api.security import COOKIE, LocalAuth
from hibiscus_station.api.ws import EventHub, build_ws_router
from hibiscus_station.errors import StationError
from hibiscus_station.oscompat import register_web_mimetypes
from hibiscus_station.programs.api_detectors import build_detectors_router
from hibiscus_station.programs.api_programs import build_programs_router
from hibiscus_station.programs.api_trajectories import build_trajectories_router
from hibiscus_station.station import Station

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
DEV_STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "dist"


def default_static_dir() -> Path:
    """The UI: ``$HIBISCUS_STATION_STATIC``, else (a source checkout) ``web/dist`` from
    ``pnpm build``, else the copy shipped in the wheel."""
    if env := os.environ.get("HIBISCUS_STATION_STATIC"):
        return Path(env).expanduser()
    if (DEV_STATIC_DIR / "index.html").is_file():
        return DEV_STATIC_DIR
    return STATIC_DIR


PUBLIC_PATHS = {"/auth"}


def problem_response(err: StationError, request_id: str) -> JSONResponse:
    return JSONResponse(
        err.problem(request_id), status_code=err.status, media_type="application/problem+json"
    )


def create_app(
    station: Station, auth: LocalAuth, *, static_dir: Path | None = None, manage_lifecycle: bool = True
) -> FastAPI:
    hub = EventHub()
    station.owner.add_listener(hub.publish)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        import asyncio

        hub.bind(asyncio.get_running_loop())
        if manage_lifecycle:
            station.start()
        try:
            yield
        finally:
            if manage_lifecycle:
                station.shutdown()

    app = FastAPI(
        title="Hibiscus Station",
        version=__version__,
        description=(
            "Local robot agent API (docs/spec/station.md §5). Bound to 127.0.0.1 unless LAN mode is "
            "enabled with a fixed token and allowed host names (§8.1)."
        ),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.station = station
    app.state.auth = auth
    app.state.events = hub

    @app.middleware("http")
    async def security(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or secrets.token_hex(8)
        if not auth.host_ok(request.headers.get("host")):
            return problem_response(StationError("forbidden_host", "host not allowed"), rid)
        path = request.url.path
        if path.startswith("/api/"):
            if not (
                auth.cookie_ok(request.cookies.get(COOKIE))
                or auth.bearer_ok(request.headers.get("authorization"))
            ):
                return problem_response(
                    StationError("unauthenticated", "open Station from its launch URL"), rid
                )
            if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-station") != "1":
                return problem_response(StationError("csrf", "missing X-Station: 1 header", status=403), rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "no-referrer"
        return response

    @app.exception_handler(StationError)
    async def station_error(request: Request, exc: StationError) -> JSONResponse:
        return problem_response(exc, request.headers.get("x-request-id", ""))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": [str(x) for x in e.get("loc", [])],
                "msg": str(e.get("msg", "")),
                "type": str(e.get("type", "")),
            }
            for e in exc.errors()
        ]
        return problem_response(
            StationError("validation_failed", "request validation failed", errors=errors), ""
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "validation_failed"}.get(exc.status_code, "internal_error")
        return problem_response(StationError(code, str(exc.detail), status=exc.status_code), "")

    @app.exception_handler(Exception)
    async def internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return problem_response(StationError("internal_error", f"{type(exc).__name__}"), "")

    @app.get("/auth", include_in_schema=False)
    def bootstrap(t: str = "") -> Response:
        if not auth.token_ok(t):
            return problem_response(StationError("unauthenticated", "invalid or expired launch link"), "")
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, auth.new_cookie(), httponly=True, samesite="strict", path="/")
        return resp

    app.include_router(build_router())
    app.include_router(build_trajectories_router())
    app.include_router(build_detectors_router())
    app.include_router(build_programs_router())
    if station.mock:
        app.include_router(build_mock_router())
    app.include_router(build_ws_router(hub))

    def openapi() -> dict[str, Any]:
        """REST schema plus the WebSocket message schemas (spec §5.3, §5.4) under components."""
        if app.openapi_schema is None:
            from fastapi.openapi.utils import get_openapi

            from hibiscus_station.api.schemas import ws_schemas

            doc = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            comps = doc.setdefault("components", {}).setdefault("schemas", {})
            for name, schema in ws_schemas().items():
                comps.setdefault(name, schema)  # shared models (Status, Job...) keep the REST copy
            app.openapi_schema = doc
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]

    register_web_mimetypes()  # Windows: .js is often text/plain in the registry
    sdir = static_dir or default_static_dir()
    index = sdir / "index.html"
    if index.is_file():
        assets = sdir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> Response:
            if full_path.startswith(("api/", "ws")):
                raise StarletteHTTPException(404, "not found")
            candidate = (sdir / full_path).resolve()
            if full_path and candidate.is_file() and sdir.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index)
    else:

        @app.get("/", include_in_schema=False)
        def no_spa() -> dict[str, Any]:
            return {
                "station": __version__,
                "ui": "not bundled: build the UI (web: pnpm build) before building the wheel",
                "api": "/api/v1/status",
            }

    return app
