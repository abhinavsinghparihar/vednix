"""Shared async fixtures. Test doubles are injected explicitly by unit tests."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio

from agents import build_plugins
from agents.plugin_manager import PluginManager
from ai_engine.engine import EngineCore
from ai_engine.provider_error import ProviderError
from config import Settings
from memory.db import create_engine_and_session, init_schema
from memory.service import MemoryService
from services.file_store import FileStore
from services.knowledge import KnowledgeService


class FakeLLM:
    """Unit-test stub; production routing never constructs or imports this class."""

    model = "test-model"

    def __init__(self, *, offline: bool = False, fail_chat: bool = False) -> None:
        self.offline = offline
        self.fail_chat = fail_chat
        self.calls: list[list[dict]] = []
        self.temperatures: list[float] = []
        self.last_images: list[str] | None = None
        self.last_model: str | None = None

    async def is_available(self, provider: str | None = None) -> bool:
        return not self.offline

    async def aclose(self) -> None:
        return None

    async def chat(
        self, messages: list[dict], temperature: float, *, model: str | None = None,
        images: list[str] | None = None, provider: str | None = None,
    ) -> str:
        self.calls.append(messages)
        self.last_images = images
        self.last_model = model
        if self.fail_chat:
            raise ProviderError("Test provider", "injected test failure")
        return "Test Conversation Title"

    async def chat_stream(
        self, messages: list[dict], temperature: float, *, model: str | None = None,
        images: list[str] | None = None, provider: str | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append(messages)
        self.temperatures.append(temperature)
        self.last_images = images
        self.last_model = model
        if self.fail_chat:
            raise ProviderError("Test provider", "injected test failure")
            yield  # pragma: no cover - keeps this an async generator
        for chunk in ["Hello ", "from ", "Vednix!"]:
            yield chunk

    async def list_models_cached(
        self, ttl: float = 30.0, provider: str | None = None, *, task: str = "text",
    ) -> list[str]:
        if task == "vision":
            return []
        return ["test-model"]

    async def supports_images(self, model: str | None = None, provider: str | None = None) -> bool:
        return False


class SlowLLM(FakeLLM):
    """Streams a partial answer and waits so tests can exercise cancellation."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()

    async def chat_stream(
        self, messages, temperature, *, model=None, images=None, provider=None,
    ) -> AsyncIterator[str]:
        self.calls.append(messages)
        self.last_images = images
        self.last_model = model
        yield "partial "
        await self.gate.wait()
        yield "rest"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        upload_dir=str(tmp_path / "uploads"),
    )


@pytest_asyncio.fixture
async def db(settings):
    engine, session_factory = create_engine_and_session(settings.database_url)
    await init_schema(engine)
    yield engine, session_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def memory(db) -> MemoryService:
    return MemoryService(db[1])


@pytest_asyncio.fixture
async def files_store(db, settings):
    return FileStore(db[1], settings)


@pytest_asyncio.fixture
async def knowledge(db):
    return KnowledgeService(db[1], fts_enabled=True)


@pytest.fixture
def core(settings):
    def core_for(llm, **kwargs) -> EngineCore:
        return EngineCore(settings=settings, llm=llm, plugins=PluginManager(build_plugins()), **kwargs)
    return core_for
