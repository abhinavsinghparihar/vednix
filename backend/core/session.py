"""Session enforcement — ASGI middleware (NOT @app.middleware("http"): the
decorator variant never sees websocket scopes; BearerAuthMiddleware docstring
documents that hard-won lesson. Same pattern, same reason).

Rule set:
  * No accounts exist        → fully open (Vednix's single-user default; every
                               pre-auth test in the suite keeps passing).
  * ≥1 account exists        → /api/* and /ws/* require a valid access token
                               (`Authorization: Bearer …`; `?token=` fallback
                               for the WS upgrade, browsers can't set headers).
  * OPEN_PATHS               → the lock screen's own plumbing: health probe,
                               login/register/refresh, onboarding status (the
                               login page needs it to route), docs.

CSRF: the access token travels ONLY in the Authorization header (never a
cookie), so API writes are CSRF-immune by construction. The two cookie-based
endpoints (refresh, logout) demand the double-submit token — see
require_csrf() below, used inside the auth routes.
"""

from __future__ import annotations

import json

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Receive, Scope, Send

OPEN_PATHS = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    # logout authenticates via the refresh cookie + CSRF pair — it MUST work
    # even after the (20-minute) access token has expired
    "/api/auth/logout",
    "/api/onboarding/status",
)


def _token_from(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            text = value.decode("latin-1")
            if text.lower().startswith("bearer "):
                return text[7:].strip()
    query = scope.get("query_string", b"").decode("latin-1")
    for pair in query.split("&"):
        if pair.startswith("token="):
            return pair[6:]
    return None


class SessionMiddleware:
    def __init__(self, app: ASGIApp, *, open_paths: tuple[str, ...] = OPEN_PATHS) -> None:
        self.app = app
        self.open_paths = open_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path: str = scope["path"]
        if not (path.startswith("/api") or path.startswith("/ws")) or path in self.open_paths:
            return await self.app(scope, receive, send)

        users = scope["app"].state.users
        if not await users.auth_enabled():
            return await self.app(scope, receive, send)  # no accounts → open mode

        token = _token_from(scope)
        claims = None
        if token:
            try:
                claims = users.resolve_access_token(token)
            except ValueError:
                claims = None
        if claims is None:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401, "reason": "unauthorized"})
                return
            body = json.dumps({"detail": "Sign in required."}).encode()
            await send({
                "type": "http.response.start", "status": 401,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return

        scope["state_user"] = claims  # routes read via deps.current_user
        await self.app(scope, receive, send)


CSRF_COOKIE = "vednix_csrf"
CSRF_HEADER = "x-csrf-token"


def require_csrf(request: Request) -> None:
    """Double-submit check for the cookie-bearing auth endpoints (refresh /
    logout / session writes). The CSRF cookie is deliberately NOT httpOnly —
    the SPA reads it once and mirrors it into the X-CSRF-Token header."""
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or cookie != header:
        raise HTTPException(status_code=403, detail="CSRF check failed.")
