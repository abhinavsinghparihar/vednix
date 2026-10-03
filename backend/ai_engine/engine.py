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
  - vision routing: images use only a model with a successful provider-side
    capability probe, with a clear error when no compatible model is available
  - knowledge base: FTS5 hits are cited into the turn; sources ride the done frame
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol

from ai_engine.events import CoreState, EventBus, StateManager
from ai_engine.provider_error import ProviderError
from ai_engine.prompts import build_system_prompt
from agents.base import PluginContext
from core.logging import get_logger
from config import Settings

if TYPE_CHECKING:
    from services.file_store import FileStore
    from services.knowledge import KnowledgeService

logger = get_logger(__name__)


class LLMClient(Protocol):
    """Provider-neutral chat interface backed by server-side credentials."""

    model: str

    async def is_available(self, provider: str | None = None, *, task: str | tuple[str, ...] = "text") -> bool: ...
    async def chat(self, messages: list[dict], temperature: float, *, model: str | None = None, images: list[str] | None = None, provider: str | None = None, task: str | tuple[str, ...] = "text") -> str: ...
    def chat_stream(self, messages: list[dict], temperature: float, *, model: str | None = None, images: list[str] | None = None, provider: str | None = None, task: str | tuple[str, ...] = "text") -> AsyncIterator[str]: ...
    async def list_models_cached(self, ttl: float = 30.0, provider: str | None = None, *, task: str = "text") -> list[str]: ...


class AttachmentLimitExceeded(ValueError):
    """A supported request exceeded the current model-adapter image limit."""


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
        self.last_error: dict[str, str] | None = None

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
        self.last_error = None

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

        # 3. LLM path. Capability-bound inputs route through verified models;
        # search itself is handled by the app-owned retrieval graph below.
        needs_vision = any(item.kind == "image" for item in attachments)
        needs_documents = any(item.kind != "image" for item in attachments)
        # Search is an app-owned retrieval graph (not a provider function-call
        # payload) and needs verified text chat. Documents are extracted to
        # bounded text; composite inputs must satisfy each real model capability.
        required_capabilities = tuple(
            task for enabled, task in (
                (needs_documents, "document_input"),
                (needs_vision, "vision"),
            ) if enabled
        ) or ("text",)
        # An explicit provider choice stays strict for attachments too; only
        # automatic priority mode may route/fail over across providers.
        selected_provider = provider
        required_task: str | tuple[str, ...] = (
            required_capabilities[0] if len(required_capabilities) == 1 else required_capabilities
        )
        availability = self.core.llm.is_available
        try:
            try:
                ready = await availability(provider=selected_provider, task=required_task)
            except TypeError:  # compatibility with injected test/stub clients
                ready = await availability(provider=selected_provider)
        except Exception:
            ready = False
        if not ready:
            await self.state.set(CoreState.IDLE)
            if needs_vision:
                scope = f"{selected_provider} has no" if selected_provider else "No enabled provider has a"
                message = f"{scope} verified, streaming image-input model. Remove the image or verify a compatible vision model in Settings."
                self.last_error = {"code": "VISION_UNAVAILABLE", "message": message}
            elif needs_documents:
                scope = f"{selected_provider} has no" if selected_provider else "No enabled provider has a"
                message = f"{scope} verified model for extracted document text. Verify a text chat model in Settings."
                self.last_error = {"code": "DOCUMENT_INPUT_UNAVAILABLE", "message": message}
            else:
                unavailable = getattr(self.core.llm, "unavailable_message", None)
                if unavailable is not None:
                    try:
                        message = await unavailable(selected_provider)
                    except Exception:
                        message = "No verified Gemini or Groq provider is available. Check Settings → AI Providers."
                else:
                    message = "No verified Gemini or Groq provider is available. Check Settings → AI Providers."
                self.last_error = {"code": "PROVIDER_UNAVAILABLE", "message": message}
            yield message
            return

        # 3w. Internet research (Phase 5/6): LangGraph agent over SearXNG. The final
        #     synthesis stays in THIS pipeline (audit B3) — agents only retrieve and
        #     cite. multi_agent upgrades depth to the planner/critic loop; every graph
        #     step is published to the bus so the UI can show the orchestration live.
        web_block = ""
        if internet or multi_agent:
            from agents.research import ResearchUnavailable

            if self.core.research is None:
                yield "🌐 Search is unavailable on this server; answering from model knowledge instead.\n\n"
            else:
                await self.state.set(CoreState.SEARCHING)

                async def report_step(step: str, detail: str) -> None:
                    entry = {"step": step, "detail": detail}
                    self.last_steps.append(entry)
                    await self.bus.publish("agent_step", entry)

                try:
                    research_options = {
                        "depth": "deep" if multi_agent else "quick", "on_step": report_step,
                    }
                    try:
                        if "provider" in inspect.signature(self.core.research.run).parameters:
                            research_options["provider"] = selected_provider
                    except (TypeError, ValueError):
                        pass  # injected research services may have a legacy callable signature
                    web = await self.core.research.run(text, **research_options)
                    web_block = web.block
                    self.last_sources = [{"title": s.title, "url": s.url} for s in web.sources]
                except ResearchUnavailable:
                    await self.state.set(CoreState.THINKING)
                    yield "🌐 Search is temporarily unavailable; answering from model knowledge instead.\n\n"
                except Exception:
                    logger.exception("research agent failed (conv=%s)", self.conversation_id)
                    await self.state.set(CoreState.THINKING)
                    yield "🌐 Search failed; answering from model knowledge instead.\n\n"

        await self.state.set(CoreState.THINKING)

        # 3a. Resolve file context + images, and route vision correctly.
        try:
            llm_user_content, images, routed_model, no_vision = await self._enrich_with_files(
                text, attachments, model, provider=selected_provider
            )
        except AttachmentLimitExceeded:
            await self.state.set(CoreState.IDLE)
            message = "Attach no more than three images to one message, then try again."
            self.last_error = {"code": "IMAGE_LIMIT_EXCEEDED", "message": message}
            yield message
            return
        except Exception:
            logger.exception("could not read chat attachments (conv=%s)", self.conversation_id)
            await self.state.set(CoreState.IDLE)
            message = "Vednix could not read one of the attached files. Re-upload it and try again."
            self.last_error = {"code": "ATTACHMENT_READ_FAILED", "message": message}
            yield message
            return
        if no_vision:
            await self.state.set(CoreState.IDLE)
            scope = f"{selected_provider} has no" if selected_provider else "No enabled provider has a"
            message = (
                f"{scope} model with a successful image-input check. "
                "Refresh the live vision model list in Settings, remove the image, or verify another provider."
            )
            self.last_error = {"code": "VISION_UNAVAILABLE", "message": message}
            yield message
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
            if selected_provider:
                stream_options["provider"] = selected_provider
            try:
                params = inspect.signature(self.core.llm.chat_stream).parameters
                if "task" in params:
                    stream_options["task"] = required_task
            except (TypeError, ValueError):
                pass  # test doubles/third-party adapters may expose no signature
            async for chunk in self.core.llm.chat_stream(messages, effective_temperature, **stream_options):
                if first:
                    await self.state.set(CoreState.SPEAKING)
                    first = False
                chunks.append(chunk)
                yield chunk
        except ProviderError as exc:
            label = exc.provider if exc.provider not in {"", "Vednix"} else getattr(self.core.llm, "active_label", "AI provider")
            logger.warning("provider stream failed (provider=%s, conv=%s): %s", label, self.conversation_id, exc.message)
            self.last_error = {"code": exc.code, "message": exc.message}
            yield f"\n\n⚠️ {label} could not complete this reply: {exc.message} This reply was not saved."
        except Exception:
            logger.exception("unexpected engine error (conv=%s)", self.conversation_id)
            self.last_error = {"code": "PROVIDER_UNAVAILABLE", "message": "The AI provider could not complete this reply."}
            yield "\n\n⚠️ The AI provider could not complete this reply. Please try again. This reply was not saved."
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
        *,
        provider: str | None = None,
    ) -> tuple[str, list[str], str | None, bool]:
        """Return enriched text, images, an optional validated model route,
        and whether an explicitly selected provider has no validated vision model.
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
            if len(image_ids) > 3:
                raise AttachmentLimitExceeded("At most three images can be routed in one message.")
            desired = requested_model or self.core.llm.model
            checker = getattr(self.core.llm, "supports_images", None)
            can_see = False
            if checker is not None and desired:
                try:
                    result = checker(desired, provider=provider)
                except TypeError:
                    result = checker(desired)
                if inspect.isawaitable(result):
                    result = await result
                can_see = bool(result)
            if not can_see:
                try:
                    vision_models = await self.core.llm.list_models_cached(
                        provider=provider, task="vision"
                    )
                except TypeError:  # compatibility with injected test clients
                    vision_models = await self.core.llm.list_models_cached()
                if not vision_models:
                    return enriched, [], None, True
                routed_model = vision_models[0]
            for image_id in image_ids[:3]:  # cap: 3 images per turn
                image = await self.core.files.read_image_data_url(image_id)
                if not image:
                    raise ValueError("An attached image could not be read from storage.")
                images.append(image)
        return enriched, images, routed_model, no_vision


@dataclass
class SessionResult:  # kept for transport-layer typing clarity
    content: str
    plugins_used: list[str] = field(default_factory=list)
    persisted: bool = False
    cancelled: bool = False
