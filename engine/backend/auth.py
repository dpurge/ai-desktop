import re
import secrets
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN_HEADER = "X-AD-Token"

# The Tauri webview and local dev pages only; any other web page must not reach the engine.
ALLOWED_ORIGIN_PATTERN = (
    r"^(tauri://localhost"
    r"|https?://tauri\.localhost"
    r"|https?://(localhost|127\.0\.0\.1)(:\d+)?)$"
)
_ALLOWED_ORIGIN = re.compile(ALLOWED_ORIGIN_PATTERN)


def is_origin_allowed(origin: str | None) -> bool:
    # Non-browser clients (curl, tests) send no Origin; the token still protects them.
    return origin is None or _ALLOWED_ORIGIN.match(origin) is not None


class TokenAuthMiddleware:
    """Origin gate for every request, plus the token check for non-public requests."""

    def __init__(self, app: ASGIApp, token: str, is_public: Callable[[Request], bool]) -> None:
        self._app = app
        self._token = token
        self._is_public = is_public

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request = Request(scope)
        rejection = self._rejection(request)
        if rejection is None:
            await self._app(scope, receive, send)
        else:
            await rejection(scope, receive, send)

    def _rejection(self, request: Request) -> JSONResponse | None:
        if not is_origin_allowed(request.headers.get("origin")):
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        if request.method == "OPTIONS" or self._is_public(request):
            return None
        supplied = request.headers.get(TOKEN_HEADER, "")
        if not secrets.compare_digest(supplied.encode(), self._token.encode()):
            return JSONResponse({"detail": "Missing or invalid token"}, status_code=401)
        return None
