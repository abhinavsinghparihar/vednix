"""
Vednix AI — FastAPI application.

Run:  uvicorn main:app --reload --port 8000    (from backend/)
or:   python main.py

create_app() accepts optional injected settings/LLM so tests never need a real
Ollama instance.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents import build_plugins
from agents.plugin_manager import PluginManager
from ai_engine.engine import EngineCore
from ai_engine.ollama_client import OllamaClient
from api import conversations, health, memories, ws_chat
from config import Settings, get_settings
from core.logging import get_logger, setup_logging
from core.rate_limit import RateLimiter
from memory.db import create_engine_and_session, init_schema
from memory.service import MemoryService

logger = get_logger(__name__)


def _ensure_sqlite_dir(database_url: str) -> None:
    """The old config created dirs at import time (audit C1); here it happens
    explicitly at startup, only where the URL actually points."""
    prefix = "sqlite+aiosqlite:///"
    if database_url.startswith(prefix):
        Path(database_url[len(prefix):]).parent.mkdir(parents=True, exist_ok=True)


def create_app(settings: Settings | None = None, llm_client=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        _ensure_sqlite_dir(settings.database_url)
        db_engine, session_factory = create_engine_and_session(settings.database_url)
        await init_schema(db_engine)

        app.state.settings = settings
        app.state.memory = MemoryService(session_factory)
        app.state.rate_limiter = RateLimiter(rate=120, per_seconds=60.0)
        llm = llm_client or OllamaClient(
            settings.ollama_host,
            settings.ollama_model,
            timeout=settings.llm_request_timeout,
            health_ttl=settings.llm_health_ttl,
        )
        app.state.core = EngineCore(
            settings=settings, llm=llm, plugins=PluginManager(build_plugins())
        )
        logger.info("Vednix AI backend ready (model=%s)", settings.ollama_model)
        try:
            yield
        finally:
            await llm.aclose()
            await db_engine.dispose()
            logger.info("Vednix AI backend stopped")

    app = FastAPI(title="Vednix AI", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path.startswith("/ws"):
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        if not await request.app.state.rate_limiter.allow(key):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)

    app.include_router(health.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(memories.router, prefix="/api")
    app.include_router(ws_chat.router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=True)
