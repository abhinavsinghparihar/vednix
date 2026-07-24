"""Optional bearer-token gate (Phase 5, audit-ready auth seam).

Vednix's default is a single-user local app: no auth UI, no accounts, nothing
to phish. But the moment someone runs it on a LAN/Tailscale box, an open
read-write API is a real threat. So: VEDNIX_AUTH_TOKEN set → every /api/* route
and the WebSocket require `Authorization: Bearer <token>` (browsers can't put
headers on a WebSocket upgrade, so `?token=` is accepted as the WS fallback).

Hard-won constraint: this MUST be an ASGI middleware, not @app.middleware("http")
— the "http" decorator variant never sees websocket scopes, which would have
left /ws/chat wide open while looking protected.
"""

from __future__ import annotations

import json
from starlette.types import ASGIApp, Receive, Scope, Send

OPEN_PATHS = ("/api/health",)  # exposes nothing private; keeps LB probes simple


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, *, token: str, open_paths: tuple[str, ...] = OPEN_PATHS) -> None:
        self.app = app
        self.token = token
        self.open_paths = open_paths

    def _provided(self, scope: Scope) -> str | None:
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path: str = scope["path"]
        if not (path.startswith("/api") or path.startswith("/ws")) or path in self.open_paths:
            return await self.app(scope, receive, send)
        if self._provided(scope) != self.token:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401, "reason": "unauthorized"})
                return
            body = json.dumps({"detail": "Unauthorized — provide Bearer token"}).encode()
            await send({
                "type": "http.response.start", "status": 401,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
