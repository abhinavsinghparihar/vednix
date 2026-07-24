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
from agents.research import ResearchService
from ai_engine.engine import EngineCore
from ai_engine.ollama_client import OllamaClient
from ai_engine.openrouter_client import OpenRouterClient
from api import conversations, health, knowledge, memories, uploads, ws_chat
from config import Settings, get_settings
from core.auth import BearerAuthMiddleware
from core.logging import get_logger, setup_logging
from core.rate_limit import build_rate_limiter
from memory.db import create_engine_and_session, init_schema
from memory.service import MemoryService
from services.file_store import FileStore
from services.knowledge import KnowledgeService

logger = get_logger(__name__)


def _build_llm(settings: Settings):
    """Provider selection — same interface either way (audit ♻️S2), so the
    engine, vision routing and model selector never know the difference."""
    if settings.llm_provider.lower() == "openrouter":
        return OpenRouterClient(
            settings.openrouter_api_key,
            settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            timeout=settings.llm_request_timeout,
            health_ttl=settings.llm_health_ttl,
        )
    return OllamaClient(
        settings.ollama_host,
        settings.ollama_model,
        timeout=settings.llm_request_timeout,
        health_ttl=settings.llm_health_ttl,
    )


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
        fts_enabled = await init_schema(db_engine)

        app.state.settings = settings
        app.state.memory = MemoryService(session_factory)
        app.state.rate_limiter = await build_rate_limiter(settings.redis_url, rate=120, per_seconds=60.0)
        app.state.files = FileStore(session_factory, settings)
        app.state.knowledge = KnowledgeService(session_factory, fts_enabled=fts_enabled)
        llm = llm_client or _build_llm(settings)
        # Research agent: constructed whenever a SearXNG URL exists; an empty URL
        # disables internet search cleanly (honest "disabled on this server" reply).
        research = None
        if settings.searxng_url.strip():
            research = ResearchService(
                searxng_url=settings.searxng_url,
                llm=llm,
                max_results=settings.search_max_results,
                fetch_pages=settings.search_fetch_pages,
                page_chars=settings.search_page_chars,
                timeout=settings.search_timeout,
                max_iterations=settings.agents_max_iterations,
                max_subquestions=settings.agents_max_subquestions,
            )
        app.state.core = EngineCore(
            settings=settings, llm=llm, plugins=PluginManager(build_plugins()),
            files=app.state.files, knowledge=app.state.knowledge, research=research,
        )
        app.state.research = research
        logger.info(
            "Vednix AI backend ready (model=%s, fts5=%s, db=%s, uploads=%s)",
            settings.ollama_model, fts_enabled, settings.database_url, settings.upload_dir,
        )
        try:
            yield
        finally:
            await llm.aclose()
            if research is not None:
                await research.aclose()
            await db_engine.dispose()
            logger.info("Vednix AI backend stopped")

    app = FastAPI(title="Vednix AI", version="0.1.0", lifespan=lifespan)
    if settings.auth_token:
        app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)
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
    app.include_router(uploads.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(ws_chat.router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=True)
