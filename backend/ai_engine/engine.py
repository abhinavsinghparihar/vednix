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

Phase 4 additions on top of that same single pipeline:
  - chat attachments: extracted file text, budgeted, injected into the LLM turn
  - vision routing: images auto-pick a vision-capable local model, or the user
    gets a precise `ollama pull …` instruction instead of a silent failure
  - knowledge base: FTS5 hits are cited into the turn; sources ride the done frame
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol

from ai_engine.events import CoreState, EventBus, StateManager
from ai_engine.ollama_client import OllamaError
from ai_engine.prompts import build_system_prompt
from agents.base import PluginContext
from core.logging import get_logger
from config import Settings

if TYPE_CHECKING:
    from services.file_store import FileStore
    from services.knowledge import KnowledgeService

logger = get_logger(__name__)


class LLMClient(Protocol):
    """Anything with the original OllamaClient interface qualifies (OpenRouter later)."""

    model: str

    async def is_available(self) -> bool: ...
    async def chat(self, messages: list[dict], temperature: float, *, model: str | None = None, images: list[str] | None = None) -> str: ...
    def chat_stream(self, messages: list[dict], temperature: float, *, model: str | None = None, images: list[str] | None = None) -> AsyncIterator[str]: ...
    async def list_models_cached(self, ttl: float = 30.0) -> list[str]: ...


@dataclass
class AttachmentRef:
    """Resolved upload handed to the engine (already validated + stored)."""

    id: str
    name: str
    kind: str
    size: int


@dataclass
class EngineCore:
    """Shared, stateless services: one per app. (Was: one global Engine holding
    the only conversation state — audit SC2.) Constructed once in the app lifespan."""

    settings: Settings
    llm: LLMClient
    plugins: Any  # agents.plugin_manager.PluginManager
    files: "FileStore | None" = None
    knowledge: "KnowledgeService | None" = None
    research: Any = None  # agents.research.ResearchService (Phase 5; None = internet off)

    def create_session(self, memory, conversation_id: str, *, language: str = "auto") -> "EngineSession":
        return EngineSession(self, memory, conversation_id, language=language)


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
        #: plugins + knowledge sources of the most recent message (done frame)
        self.last_plugins: list[str] = []
        self.last_kb_sources: list[str] = []
        self.last_sources: list[dict] = []  # web citations (Phase 5): [{title, url}]
        self.last_steps: list[dict] = []    # agent trace (Phase 6): [{step, detail}]

    async def persist_partial(self, partial: str) -> None:
        """Transport calls this on cancel — user keeps what they saw (audit B5)."""
        if partial.strip():
            await self.memory.add_message(
                self.conversation_id, "assistant", partial.strip() + " *(stopped)*"
            )

    # --- the single pipeline ------------------------------------------------

    async def stream_reply(
        self,
        text: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        attachments: list[AttachmentRef] | None = None,
        internet: bool = False,
        multi_agent: bool = False,
        provider: str | None = None,
    ) -> AsyncIterator[str]:
        """The canonical message pipeline. Yields reply chunks.

        Persistence contract (audit B2/B3):
          - user message      → always persisted (with attachment refs)
          - assistant answer  → persisted ONLY on success (or partial on cancel)
          - errors/guidance   → yielded for the UI, NEVER persisted
        """
        settings = self.core.settings
        attachments = attachments or []
        self.last_plugins = []
        self.last_kb_sources = []
        self.last_sources = []
        self.last_steps = []

        attachments_json = (
            json.dumps([{"id": a.id, "name": a.name, "kind": a.kind, "size": a.size} for a in attachments])
            if attachments else None
        )
        await self.memory.add_message(self.conversation_id, "user", text, attachments=attachments_json)

        # 2. Plugins first (♻️ original order) — but file-bearing messages are
        #    LLM intent (plugins can't see files), so attachments skip routing.
        handlers = [] if attachments else self.core.plugins.find_handlers(text)
        if handlers:
            self.last_plugins = [p.name for p in handlers]
            await self.state.set(CoreState.EXECUTING)
            ctx = PluginContext(settings=settings, memory=self.memory)
            parts: list[str] = []
            for plugin in handlers:
                try:
                    parts.append(await plugin.execute(text, ctx))
                except Exception:
                    logger.exception("plugin %r failed on input %.80s", plugin.name, text)
                    parts.append(f"⚠️ The `{plugin.name}` plugin hit an error. Detail was logged.")
            result = "\n\n".join(part for part in parts if part).strip() or "…"
            await self.memory.add_message(
                self.conversation_id, "assistant", result, plugins=",".join(self.last_plugins)
            )
            await self.state.set(CoreState.IDLE)
            yield result
            return

        # 3. LLM path. Offline notice is yielded but never persisted (♻️ original UX).
        if not await self.core.llm.is_available():
            await self.state.set(CoreState.IDLE)
            yield (
                "I can't reach Ollama right now — try: `ollama serve` and "
                f"`ollama pull {self.core.llm.model}`. Everything else in Vednix "
                "keeps working offline."
            )
            return

        # 3w. Internet research (Phase 5/6): LangGraph agent over SearXNG. The final
        #     synthesis stays in THIS pipeline (audit B3) — agents only retrieve and
        #     cite. multi_agent upgrades depth to the planner/critic loop; every graph
        #     step is published to the bus so the UI can show the orchestration live.
        web_block = ""
        if internet or multi_agent:
            from agents.research import ResearchUnavailable

            if self.core.research is None:
                yield (
                    "Internet research is disabled on this server "
                    "(set VEDNIX_SEARXNG_URL to a SearXNG instance)."
                )
                return
            await self.state.set(CoreState.SEARCHING)

            async def report_step(step: str, detail: str) -> None:
                entry = {"step": step, "detail": detail}
                self.last_steps.append(entry)
                await self.bus.publish("agent_step", entry)

            try:
                web = await self.core.research.run(
                    text, depth="deep" if multi_agent else "quick", on_step=report_step
                )
                web_block = web.block
                self.last_sources = [{"title": s.title, "url": s.url} for s in web.sources]
            except ResearchUnavailable as exc:
                await self.state.set(CoreState.IDLE)
                yield f"🌐 {exc}"
                return
            except Exception:
                logger.exception("research agent failed (conv=%s)", self.conversation_id)
                await self.state.set(CoreState.IDLE)
                yield "⚠️ Web research failed unexpectedly. Detail was logged."
                return

        await self.state.set(CoreState.THINKING)

        # 3a. Resolve file context + images, and route vision correctly.
        llm_user_content, images, routed_model, no_vision = await self._enrich_with_files(
            text, attachments, model
        )
        if no_vision:
            await self.state.set(CoreState.IDLE)
            active = getattr(self.core.llm, "active_label", "Ollama")
            if active == "Ollama":
                yield (
                    "Images need a vision-capable model. Quick fix:\n\n"
                    "```bash\nollama pull llama3.2-vision\n```\n\n"
                    "Then attach the image again — Vednix auto-routes to it."
                )
            else:
                yield (
                    f"Your active provider ({active}) has no vision-capable model "
                    "in its list. Pick a vision model in the model selector, or "
                    "switch to a local Ollama vision model."
                )
            return
        effective_model = routed_model or model or None
        if routed_model:
            yield f"🖼 *Routed images to `{routed_model}`*\n\n"

        # 3b. Knowledge base retrieval (FTS5 → cited context block).
        kb_block = ""
        if self.core.knowledge is not None:
            try:
                hits = await self.core.knowledge.search(text, limit=settings.kb_context_chunks)
            except Exception:
                hits = []
                logger.exception("knowledge search failed (non-fatal)")
            if hits:
                self.last_kb_sources = sorted({h.title for h in hits})[:4]
                excerpt = "\n".join(f'- from "{h.title}": {h.snippet.replace("«","").replace("»","")}' for h in hits)
                kb_block = (
                    "Relevant knowledge-base excerpts (use them if they help, and "
                    f"mention the source document by name):\n{excerpt}\n\n"
                )

        history = await self.memory.recent_history(
            self.conversation_id, max_turns=settings.history_max_turns
        )
        try:
            facts = [item.content for item in await self.memory.all(limit=settings.memory_context_items)]
        except Exception:
            facts = []
            logger.exception("failed to load long-term memory facts")

        messages = [
            {"role": "system", "content": build_system_prompt(settings, language=self.language, memory_facts=facts)},
            *history,
        ]
        # Enrich the just-persisted user turn for the model (display stays clean).
        context_block = web_block + kb_block
        if (context_block or llm_user_content != text) and messages and messages[-1]["role"] == "user":
            messages[-1] = {"role": "user", "content": f"{context_block}{llm_user_content}"}

        chunks: list[str] = []
        first = True
        effective_temperature = temperature if temperature is not None else settings.llm_temperature
        try:
            stream_options = {"model": effective_model, "images": images or None}
            if provider:
                stream_options["provider"] = provider
            async for chunk in self.core.llm.chat_stream(messages, effective_temperature, **stream_options):
                if first:
                    await self.state.set(CoreState.SPEAKING)
                    first = False
                chunks.append(chunk)
                yield chunk
        except OllamaError as exc:
            logger.warning("ollama stream failed (conv=%s): %s", self.conversation_id, exc)
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

    async def _enrich_with_files(
        self,
        text: str,
        attachments: list[AttachmentRef],
        requested_model: str | None,
    ) -> tuple[str, list[str], str | None, bool]:
        """Returns (llm_user_content, images_b64, routed_model, no_vision_model).

        - Text-bearing files become budgeted `### File:` blocks above the question.
        - Images ride as base64 on the final user message; if the requested model
          can't see, the first available local vision model takes over
          (routed_model) — or no_vision_model=True surfaces the exact fix.
        """
        settings = self.core.settings
        if not attachments or self.core.files is None:
            return text, [], None, False

        blocks: list[str] = []
        image_ids: list[str] = []
        for att in attachments:
            if att.kind == "image":
                image_ids.append(att.id)
                continue
            content = await self.core.files.read_text(att.id)
            if content:
                truncated = content[: settings.file_context_max_chars]
                marker = (
                    f"\n…(truncated to {settings.file_context_max_chars:,} of {len(content):,} chars)"
                    if len(content) > len(truncated) else ""
                )
                blocks.append(f"### File: {att.name}\n{truncated}{marker}")
            else:
                blocks.append(f"### File: {att.name}\n(no readable text could be extracted)")

        enriched = text
        if blocks:
            enriched = "\n\n".join(blocks) + "\n\n" + text

        images: list[str] = []
        routed_model: str | None = None
        no_vision = False
        if image_ids:
            desired = requested_model or self.core.llm.model

            async def can_see(m: str) -> bool:
                """Client-aware vision check (cloud providers answer from their
                registry flag via the router; bare stubs/ollama fall back to
                the keyword list — audit-compatible either way)."""
                checker = getattr(self.core.llm, "supports_images", None)
                if checker is not None:
                    result = checker(m)
                    if inspect.isawaitable(result):
                        result = await result
                    if result:
                        return True
                return settings.is_vision_model(m)

            if await can_see(desired):
                pass  # requested/default model can already see
            else:
                available = await self.core.llm.list_models_cached()
                vision_models = []
                for m in available:
                    if await can_see(m):
                        vision_models.append(m)
                if not vision_models:
                    return enriched, [], None, True
                routed_model = vision_models[0]
            for image_id in image_ids[:3]:  # cap: 3 images per turn
                blob = await self.core.files.read_blob_base64(image_id)
                if blob:
                    images.append(blob)
        return enriched, images, routed_model, no_vision


@dataclass
class SessionResult:  # kept for transport-layer typing clarity
    content: str
    plugins_used: list[str] = field(default_factory=list)
    persisted: bool = False
    cancelled: bool = False
