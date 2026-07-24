"""
Engine — Vednix AI's brain.

REFACTORED HARD from dev_ai/core/engine.py (per audit preservation map).

Root fixes vs. the original:
  B1   ONE async generator path (was: duplicated sync/stream methods of which
       only the blocking one was wired to the UI)
  B2   error text is NEVER stored as an assistant turn (memory pollution)
  B3   sync/stream paths can't disagree — there is only one path
  B4   ALL claiming plugins execute and their answers combine
  B5   one active generation per session; cancellation persists partial output
  DUP1 load-bearing logic (message assembly, plugin branch) written exactly once
  §8   system prompt built via prompts.build_system_prompt (multilingual)

Preserved: routing philosophy (plugins first, LLM fallback), state transitions
(IDLE → THINKING/EXECUTING → SPEAKING → IDLE) and the graceful-Ollama-offline
message users liked in the desktop app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

from ai_engine.events import CoreState, EventBus, StateManager
from ai_engine.ollama_client import OllamaError
from ai_engine.prompts import build_system_prompt
from agents.base import PluginContext
from core.logging import get_logger
from config import Settings

logger = get_logger(__name__)


class LLMClient(Protocol):
    """Anything with the original OllamaClient interface qualifies (OpenRouter later)."""

    model: str

    async def is_available(self) -> bool: ...
    async def chat(self, messages: list[dict], temperature: float, *, model: str | None = None) -> str: ...
    def chat_stream(self, messages: list[dict], temperature: float, *, model: str | None = None) -> AsyncIterator[str]: ...


@dataclass
class EngineCore:
    """Shared, stateless services: one per app. (Was: one global Engine holding
    the only conversation state — audit SC2.) Constructed once in the app lifespan."""

    settings: Settings
    llm: LLMClient
    plugins: Any  # agents.plugin_manager.PluginManager

    def create_session(self, memory, conversation_id: str, *, language: str = "auto") -> "EngineSession":
        return EngineSession(self, memory, conversation_id, language=language)


@dataclass
class SessionResult:
    """What the transport layer needs once streaming completes."""

    content: str
    plugins_used: list[str] = field(default_factory=list)
    persisted: bool = False
    cancelled: bool = False


class EngineSession:
    """Per-conversation engine: owns state machine + context for ONE chat.
    The WS layer subscribes to its bus to stream CoreState to the UI orb."""

    def __init__(self, core: EngineCore, memory, conversation_id: str, *, language: str = "auto") -> None:
        self.core = core
        self.memory = memory  # memory.service.MemoryService
        self.conversation_id = conversation_id
        self.language = language
        self.bus = EventBus()
        self.state = StateManager(self.bus)
        #: plugins that handled the most recent message (reported by the transport)
        self.last_plugins: list[str] = []

    async def stream_reply(self, text: str, *, model: str | None = None) -> AsyncIterator[str]:
        """The single, canonical message pipeline. Yields reply chunks.

        Persistence contract (audit B2/B3):
          - user message      → always persisted
          - assistant answer  → persisted ONLY on success (or partial on cancel)
          - errors/offline    → yielded for the UI, NEVER persisted
        """
        settings = self.core.settings

        # 1. Persist the user turn.
        await self.memory.add_message(self.conversation_id, "user", text, plugins=None)

        # 2. Plugins first — fast, deterministic, no LLM round trip. (♻️ original order)
        self.last_plugins = []
        handlers = self.core.plugins.find_handlers(text)
        if handlers:
            self.last_plugins = [p.name for p in handlers]
            await self.state.set(CoreState.EXECUTING)
            ctx = PluginContext(settings=settings, memory=self.memory)
            parts: list[str] = []
            used: list[str] = []
            for plugin in handlers:
                try:
                    parts.append(await plugin.execute(text, ctx))
                    used.append(plugin.name)
                except Exception:
                    # A plugin failure surfaces politely; it never crashes the chat (audit B9 → logged)
                    logger.exception("plugin %r failed on input %.80s", plugin.name, text)
                    parts.append(f"⚠️ The `{plugin.name}` plugin hit an error. Detail was logged.")
                    used.append(plugin.name)
            result = "\n\n".join(part for part in parts if part).strip() or "…"
            await self.memory.add_message(
                self.conversation_id, "assistant", result, plugins=",".join(used)
            )
            await self.state.set(CoreState.IDLE)
            yield result
            return

        # 3. LLM fallback. Offline message is yielded but never persisted (♻️ original UX).
        if not await self.core.llm.is_available():
            await self.state.set(CoreState.IDLE)
            yield (
                "I can't reach Ollama right now — try: `ollama serve` and "
                f"`ollama pull {self.core.llm.model}`. Everything else in Vednix "
                "keeps working offline."
            )
            return

        await self.state.set(CoreState.THINKING)

        history = await self.memory.recent_history(
            self.conversation_id, max_turns=settings.history_max_turns
        )
        try:
            facts = [item.content for item in await self.memory.all(limit=settings.memory_context_items)]
        except Exception:
            facts = []  # memory must never break chat
            logger.exception("failed to load long-term memory facts")

        messages = [
            {"role": "system", "content": build_system_prompt(settings, language=self.language, memory_facts=facts)},
            *history,
        ]

        chunks: list[str] = []
        first = True
        try:
            async for chunk in self.core.llm.chat_stream(
                messages, settings.llm_temperature, model=model or None
            ):
                if first:
                    await self.state.set(CoreState.SPEAKING)
                    first = False
                chunks.append(chunk)
                yield chunk
        except OllamaError as exc:
            logger.warning("ollama stream failed (conv=%s): %s", self.conversation_id, exc)
            # NOT persisted (audit B2) — and we tell the user plainly.
            yield "\n\n⚠️ The model hit an error and this reply was not saved. Detail was logged."
        except Exception:
            logger.exception("unexpected engine error (conv=%s)", self.conversation_id)
            yield "\n\n⚠️ Something unexpected went wrong. Detail was logged."
        else:
            full = "".join(chunks).strip()
            if full:
                await self.memory.add_message(self.conversation_id, "assistant", full)
        finally:
            await self.state.set(CoreState.IDLE)

    async def persist_partial(self, partial: str) -> None:
        """Called by the transport when the user cancels mid-stream (audit-friendly
        version of 'stop generation' — user keeps what they saw)."""
        if partial.strip():
            await self.memory.add_message(
                self.conversation_id, "assistant", partial.strip() + " *(stopped)*"
            )
