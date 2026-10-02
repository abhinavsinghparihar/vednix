"""
Vednix AI — FastAPI application.

Run:  uvicorn main:app --reload --port 8000 (from backend/)

create_app() accepts optional injected settings/LLM so tests can use a fully
controlled provider transport without real keys or external calls.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from agents import build_plugins
from agents.plugin_manager import PluginManager
from agents.research import ResearchService
from ai_engine.engine import EngineCore
from api import admin, auth, conversations, health, knowledge, memories, onboarding, providers, system, uploads, ws_chat
from config import Settings, get_settings
from core.auth import BearerAuthMiddleware
from core.crypto import KeyVault, load_or_create_secret
from core.logging import get_logger, setup_logging
from core.rate_limit import RateLimiter, build_rate_limiter
from core.session import SessionMiddleware
from memory.db import create_engine_and_session, init_schema
from memory.service import MemoryService
from services.file_store import FileStore
from services.knowledge import KnowledgeService
from services.onboarding import OnboardingService
from services.providers import ProviderService, ResilientLLM
from services.users import UserService

logger = get_logger(__name__)


def _build_llm(settings: Settings, providers: ProviderService) -> ResilientLLM:
    """Build one capability-aware router over the encrypted provider store."""
    return ResilientLLM(providers, settings)


def _data_dir(settings: Settings) -> Path:
    """Where machine-local secrets live: alongside the sqlite db (or ./data)."""
    prefix = "sqlite+aiosqlite:///"
    if settings.database_url.startswith(prefix):
        return Path(settings.database_url[len(prefix):]).parent
    return Path("./data")


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create local directories explicitly at startup, never at import time."""
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
        app.state.auth_rate_limiter = RateLimiter(rate=10, per_seconds=60.0)
        app.state.files = FileStore(session_factory, settings)
        app.state.knowledge = KnowledgeService(session_factory, fts_enabled=fts_enabled)

        # Existing auth/session and encrypted provider-key storage remain server-side.
        secret = load_or_create_secret(_data_dir(settings))
        app.state.secret = secret
        app.state.users = UserService(session_factory, secret)
        app.state.providers = ProviderService(session_factory, KeyVault(secret))
        app.state.onboarding = OnboardingService(session_factory)

        llm = llm_client or _build_llm(settings, app.state.providers)
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
            "Vednix AI backend ready (providers=Gemini/Groq, fts5=%s, db=%s, uploads=%s)",
            fts_enabled, settings.database_url, settings.upload_dir,
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

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if request.url.path.startswith("/api/providers/") and request.url.path.endswith("/key"):
            errors = [{key: value for key, value in error.items() if key != "input"} for error in errors]
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})

    app.add_middleware(SessionMiddleware)
    if settings.auth_token:
        app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)
    app.add_middleware(GZipMiddleware, minimum_size=512)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
        allow_credentials=True,
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
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(providers.router, prefix="/api/providers")
    app.include_router(onboarding.router, prefix="/api/onboarding")
    app.include_router(admin.router, prefix="/api/admin")
    app.include_router(system.router, prefix="/api")
    app.include_router(ws_chat.router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=s.dev_reload)
