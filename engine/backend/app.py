from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.routing import Match

from backend import __version__
from backend.agent.turns import TurnRegistry
from backend.auth import ALLOWED_ORIGIN_PATTERN, TOKEN_HEADER, TokenAuthMiddleware
from backend.config import ConfigError
from backend.interactions import InteractionRegistry
from backend.llm.base import LLM
from backend.llm.fake import FakeLLM
from backend.routes import catalog, chat, health, interactions, models, sessions
from backend.routes import settings as settings_routes
from backend.session_log import SessionLogCorruptError
from backend.session_store import SessionStore
from backend.settings_service import SettingsService
from backend.tools.executor import Executor
from backend.tools.openshell import OpenShellStatus, detect_openshell


def create_app(
    token: str,
    session_store: SessionStore,
    settings: SettingsService,
    model_name: Callable[[], str] = lambda: "fake",
    gui_dir: Path | None = None,
    llm: LLM | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
    executor: Executor | None = None,
    detect_sandbox: Callable[[], OpenShellStatus] = detect_openshell,
) -> FastAPI:
    if not token:
        raise ValueError("create_app requires a non-empty token")
    if gui_dir is not None and not gui_dir.is_dir():
        raise ValueError(f"gui_dir is not a directory: {gui_dir}")

    app = FastAPI(title="AI Desktop engine", version=__version__)
    app.state.session_store = session_store
    app.state.settings = settings
    # Called per new session (not frozen at startup) so history shows the model then in use.
    app.state.model_name = model_name
    app.state.llm = llm if llm is not None else FakeLLM()
    # A fixed executor is for tests; otherwise each turn picks one from the current settings.
    app.state.executor = executor
    app.state.detect_sandbox = detect_sandbox
    app.state.interactions = InteractionRegistry()
    app.state.turns = TurnRegistry(app.state.interactions)
    # Outbound transport for provider model lists; tests inject a mock, None means the network.
    app.state.http_transport = http_transport
    app.add_exception_handler(RequestValidationError, _validation_error_response)
    app.add_exception_handler(ConfigError, _config_error_response)
    app.add_exception_handler(SessionLogCorruptError, _session_log_corrupt_response)

    for module in (health, sessions, chat, interactions, settings_routes, models, catalog):
        app.include_router(module.router)

    # Mounted last so API routes win; static files are the only unauthenticated surface.
    api_routes = list(app.routes)
    if gui_dir is not None:
        app.mount("/", StaticFiles(directory=gui_dir, html=True), name="gui")

    def is_public(request: Request) -> bool:
        if gui_dir is None or request.method not in ("GET", "HEAD"):
            return False
        return all(route.matches(request.scope)[0] == Match.NONE for route in api_routes)

    # Added in this order so CORS is outermost: rejected requests still carry CORS headers.
    app.add_middleware(TokenAuthMiddleware, token=token, is_public=is_public)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ALLOWED_ORIGIN_PATTERN,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[TOKEN_HEADER, "Content-Type"],
    )
    return app


def _validation_error_response(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default body echoes each rejected input, which would leak an API key sent in
    # a bad request. Only where and why is reported.
    problems = [{"loc": list(error["loc"]), "msg": error["msg"]} for error in exc.errors()]
    return JSONResponse({"detail": problems}, status_code=422)


def _config_error_response(_request: Request, exc: ConfigError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=500)


def _session_log_corrupt_response(_request: Request, exc: SessionLogCorruptError) -> JSONResponse:
    # The message names the file, never its directory, so no local path reaches the client.
    return JSONResponse({"detail": str(exc)}, status_code=500)
