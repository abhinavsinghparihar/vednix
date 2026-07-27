"""AI provider management — registry, encrypted key storage, verification,
priority routing with automatic fallback (the spec's core promise:

    1. Ollama   → if available, use automatically
    2..N cloud  → in user-defined priority order
    fallback    → Ollama down ⇒ next provider takes over mid-session, no
                  interruption (failover happens BEFORE the first token).

Registry is static product data (endpoints, docs links, default models);
everything user-owned lives in provider_keys (Fernet ciphertext) and
app_settings (priority order).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_engine.cloud_client import AnthropicClient, CloudProviderError, OpenAICompatibleClient
from ai_engine.ollama_client import OllamaClient, OllamaError
from core.crypto import KeyVault
from core.logging import get_logger
from memory.models import AppSetting, ProviderKey

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Registry — one entry per setup-wizard card. `verify_path` is the cheap,
# read-only call used by both health checks and the "Test connection" button.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    kind: str                      # ollama | openai | anthropic | custom
    base_url: str
    default_model: str
    key_url: str                   # official "get your API key" page
    docs_url: str                  # official API docs
    vision: bool
    static_models: tuple[str, ...]
    needs_key: bool = True
    blurb: str = ""


REGISTRY: dict[str, ProviderSpec] = {p.id: p for p in [
    ProviderSpec(
        "ollama", "Ollama", "ollama", "", "qwen2.5:3b",
        "https://ollama.com", "https://github.com/ollama/ollama/blob/main/docs/api.md",
        True, ("qwen2.5:3b", "qwen2.5:7b"), needs_key=False,
        blurb="Free, offline, 100% private — models run on this machine.",
    ),
    ProviderSpec(
        "openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1",
        "openai/gpt-oss-20b:free",
        "https://openrouter.ai/keys", "https://openrouter.ai/docs", True,
        ("openai/gpt-oss-20b:free", "google/gemma-3-27b-it:free", "meta-llama/llama-3.3-70b-instruct:free"),
        blurb="One key, hundreds of models — the easy cloud on-ramp.",
    ),
    ProviderSpec(
        "gemini", "Google Gemini", "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.0-flash",
        "https://aistudio.google.com/apikey", "https://ai.google.dev/gemini-api/docs", True,
        ("gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"),
        blurb="Fast and generous free tier from Google AI Studio.",
    ),
    ProviderSpec(
        "groq", "Groq", "openai", "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
        "https://console.groq.com/keys", "https://console.groq.com/docs", False,
        ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"),
        blurb="Absurdly fast inference — LPU hardware.",
    ),
    ProviderSpec(
        "openai", "OpenAI", "openai", "https://api.openai.com/v1",
        "gpt-4o-mini",
        "https://platform.openai.com/api-keys", "https://platform.openai.com/docs", True,
        ("gpt-4o-mini", "gpt-4o", "o4-mini"),
        blurb="The original cloud AI API.",
    ),
    ProviderSpec(
        "anthropic", "Anthropic Claude", "anthropic", "https://api.anthropic.com",
        "claude-3-5-haiku-latest",
        "https://console.anthropic.com/settings/keys", "https://docs.anthropic.com", True,
        ("claude-3-5-haiku-latest", "claude-sonnet-4-20250514", "claude-3-5-sonnet-latest"),
        blurb="Careful, nuanced reasoning — Claude models.",
    ),
    ProviderSpec(
        "mistral", "Mistral AI", "openai", "https://api.mistral.ai/v1",
        "mistral-small-latest",
        "https://console.mistral.ai/api-keys", "https://docs.mistral.ai", False,
        ("mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"),
        blurb="European lab, strong open-weight flagships.",
    ),
    ProviderSpec(
        "together", "Together AI", "openai", "https://api.together.xyz/v1",
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "https://api.together.xyz/settings/api-keys", "https://docs.together.ai", False,
        ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"),
        blurb="Open models at production scale.",
    ),
    ProviderSpec(
        "fireworks", "Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "https://app.fireworks.ai/settings/users/api-keys", "https://docs.fireworks.ai", False,
        ("accounts/fireworks/models/llama-v3p3-70b-instruct",
         "accounts/fireworks/models/deepseek-v3"),
        blurb="Fine-tuning + fast serving for open models.",
    ),
    ProviderSpec(
        "custom", "OpenAI-Compatible", "custom", "",
        "",
        "", "https://platform.openai.com/docs/api-reference", False, (), needs_key=False,
        blurb="LM Studio, vLLM, text-gen-webui… any /v1-compatible endpoint.",
    ),
]}

DEFAULT_PRIORITY: list[str] = [
    "ollama", "openrouter", "gemini", "groq", "openai",
    "anthropic", "mistral", "together", "fireworks", "custom",
]


def provider_catalog() -> list[dict]:
    """Registry projected for the setup wizard (no secrets involved)."""
    return [
        {
            "id": p.id, "label": p.label, "kind": p.kind, "needs_key": p.needs_key,
            "default_model": p.default_model, "key_url": p.key_url, "docs_url": p.docs_url,
            "vision": p.vision, "models": list(p.static_models), "blurb": p.blurb,
            "base_url": p.base_url,
        }
        for p in REGISTRY.values()
    ]


# --------------------------------------------------------------------------
# Service — the only place ciphertext is handled.
# --------------------------------------------------------------------------

class ProviderService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: KeyVault) -> None:
        self._sessions = sessions
        self._vault = vault

    # --- key CRUD ------------------------------------------------------------

    async def list_configured(self) -> list[dict]:
        """Rows WITHOUT ciphertext — this exact shape crosses the API."""
        async with self._sessions() as db:
            rows = (await db.execute(select(ProviderKey))).scalars().all()
        priority = await self.get_priority()
        out = []
        for r in rows:
            spec = REGISTRY.get(r.provider)
            out.append(self._public(r, spec, priority))
        out.sort(key=lambda d: priority.index(d["provider"]) if d["provider"] in priority else 99)
        return out

    @staticmethod
    def _public(r: ProviderKey, spec: ProviderSpec | None, priority: list[str]) -> dict:
        return {
            "provider": r.provider,
            "label": spec.label if spec else r.provider,
            "enabled": r.enabled,
            "has_key": bool(r.key_ciphertext),
            "key_hint": r.key_hint or None,
            "status": r.status,                      # unverified | connected | failed
            "status_detail": r.status_detail or None,
            "model_override": r.model_override,
            "base_url_override": r.base_url_override,
            "priority": priority.index(r.provider) if r.provider in priority else None,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
        }

    async def upsert_key(
        self, provider: str, *, api_key: str = "", base_url: str | None = None,
        model: str | None = None,
    ) -> dict:
        spec = REGISTRY.get(provider)
        if spec is None:
            raise ValueError(f"Unknown provider '{provider}'.")
        if spec.needs_key and not api_key.strip():
            raise ValueError(f"{spec.label} requires an API key.")
        base_url = (base_url or "").strip() or None
        if spec.kind == "custom" and not base_url:
            raise ValueError("A custom endpoint needs its base URL (e.g. http://localhost:1234/v1).")
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is None:
                row = ProviderKey(provider=provider)
                db.add(row)
            if api_key.strip():
                key = api_key.strip()
                row.key_ciphertext = self._vault.encrypt(key)
                row.key_hint = KeyVault.fingerprint(key)
            row.status = "unverified"
            row.status_detail = ""
            if base_url is not None:
                row.base_url_override = base_url
            if model is not None and model.strip():
                row.model_override = model.strip()
            await db.commit()
            priority = await self.get_priority()
            return self._public(row, spec, priority)

    async def remove_key(self, provider: str) -> bool:
        async with self._sessions() as db:
            res = await db.execute(delete(ProviderKey).where(ProviderKey.provider == provider))
            await db.commit()
            return res.rowcount > 0

    async def set_enabled(self, provider: str, enabled: bool) -> bool:
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is None:
                return False
            row.enabled = enabled
            await db.commit()
            return True

    # --- priority ---------------------------------------------------------------

    async def get_priority(self) -> list[str]:
        async with self._sessions() as db:
            row = await db.get(AppSetting, "provider_priority")
        if row:
            try:
                order = [p for p in json.loads(row.value) if p in REGISTRY]
            except (json.JSONDecodeError, TypeError):
                order = []
            # registry newcomers always tail-append (never silently dropped)
            order += [p for p in DEFAULT_PRIORITY if p not in order]
            return order
        return list(DEFAULT_PRIORITY)

    async def set_priority(self, order: list[str]) -> list[str]:
        clean = [p for p in order if p in REGISTRY]
        clean += [p for p in DEFAULT_PRIORITY if p not in clean]
        async with self._sessions() as db:
            row = await db.get(AppSetting, "provider_priority")
            if row is None:
                db.add(AppSetting(key="provider_priority", value=json.dumps(clean)))
            else:
                row.value = json.dumps(clean)
            await db.commit()
        return clean

    # --- verification (the "Test connection" button) --------------------------------

    async def _row(self, provider: str) -> ProviderKey | None:
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            return row

    def _decrypt(self, row: ProviderKey) -> str:
        if not row.key_ciphertext:
            return ""
        try:
            return self._vault.decrypt(row.key_ciphertext)
        except ValueError:
            return ""

    def build_client(self, provider: str, row: ProviderKey | None, *, settings) -> "object | None":
        """Construct a live LLM client for a provider row (or None when the
        provider isn't usable: disabled, missing key, unknown id)."""
        spec = REGISTRY.get(provider)
        if spec is None:
            return None
        if spec.kind == "ollama":
            return OllamaClient(
                settings.ollama_host, settings.ollama_model,
                timeout=settings.llm_request_timeout, health_ttl=settings.llm_health_ttl,
            )
        if row is None or not row.enabled:
            return None
        api_key = self._decrypt(row)
        if spec.needs_key and not api_key:
            return None
        base_url = row.base_url_override or spec.base_url
        if not base_url:
            return None
        model = row.model_override or spec.default_model
        cls = AnthropicClient if spec.kind == "anthropic" else OpenAICompatibleClient
        return cls(
            api_key, model or "default",
            base_url=base_url, provider_name=spec.label,
            timeout=settings.llm_request_timeout, health_ttl=settings.llm_health_ttl,
            static_models=list(spec.static_models), vision=spec.vision,
        )

    async def verify(self, provider: str, *, settings) -> dict:
        """Real network proof: list one page of models. Marks the row
        connected/failed — the row update is part of the contract (the
        settings UI renders status from the row, not from this call)."""
        spec = REGISTRY.get(provider)
        if spec is None:
            raise ValueError(f"Unknown provider '{provider}'.")
        import datetime as _dt

        detail, ok, models_preview = "", False, []
        if spec.kind == "ollama":
            client = self.build_client("ollama", None, settings=settings)
            try:
                models_preview = await client.list_models()  # type: ignore[attr-defined]
                ok = True
            except OllamaError as exc:
                detail = str(exc)
            finally:
                await client.aclose()  # type: ignore[attr-defined]
        else:
            row = await self._row(provider)
            if row is None or not row.key_ciphertext:
                detail = "No API key stored yet."
            else:
                client = self.build_client(provider, row, settings=settings)
                if client is None:
                    detail = "Provider is disabled."
                else:
                    try:
                        models_preview = await client.list_models()  # type: ignore[attr-defined]
                        ok = True
                    except CloudProviderError as exc:
                        detail = str(exc)
                    finally:
                        await client.aclose()  # type: ignore[attr-defined]
            if row is not None:
                async with self._sessions() as db:
                    db_row = await db.get(ProviderKey, row.id)
                    if db_row is not None:
                        db_row.status = "connected" if ok else "failed"
                        db_row.status_detail = "" if ok else detail[:300]
                        db_row.verified_at = (
                            _dt.datetime.now(_dt.timezone.utc) if ok else db_row.verified_at
                        )
                        await db.commit()
        return {
            "provider": provider, "connected": ok, "detail": "" if ok else detail,
            "models": models_preview[:12],
        }


# --------------------------------------------------------------------------
# ResilientLLM — one LLMClient facade over the whole priority chain.
# Engine, autotitle, vision routing and the model selector see ONE object.
# --------------------------------------------------------------------------

class ResilientLLM:
    """Priority router with pre-first-token failover.

    Fault model honored honestly: if a provider dies *before its first token*,
    the turn moves to the next candidate and the user sees a one-line handoff
    notice. A provider dying *mid-stream* cannot be replayed (partial text is
    already on the user's screen) — that surfaces as the engine's standard
    'reply hit an error' path.
    """

    def __init__(
        self,
        ollama: OllamaClient,
        service: ProviderService,
        settings,
        pinned: tuple[str, object] | None = None,
    ) -> None:
        self._ollama = ollama
        self._service = service
        self._settings = settings
        # env-forced first candidate (legacy VEDNIX_LLM_PROVIDER=openrouter path)
        self._pinned = pinned
        self._cloud_cache: dict[str, tuple[float, object]] = {}  # provider → (row version, client)
        self._active_label = pinned[0] if pinned else "Ollama"
        self.last_handoff: str | None = None  # one-line notice for the current turn

    # -- client cache (rebuilt when a row's updated_at changes) -------------

    @staticmethod
    def _version(row: ProviderKey | None) -> float:
        return row.updated_at.timestamp() if row and row.updated_at else 0.0

    async def _client_for(self, provider: str) -> "object | None":
        if provider == "ollama":
            return self._ollama
        row = await self._service._row(provider)
        if row is None:
            self._cloud_cache.pop(provider, None)
            return None
        version = self._version(row)
        cached = self._cloud_cache.get(provider)
        if cached and cached[0] == version:
            return cached[1]
        client = self._service.build_client(provider, row, settings=self._settings)
        if cached:
            try:
                await cached[1].aclose()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._cloud_cache.pop(provider, None)
        if client is not None:
            self._cloud_cache[provider] = (version, client)
        return client

    async def _candidates(self) -> "list[tuple[str, object]]":
        out: list[tuple[str, object]] = []
        if self._pinned is not None:
            out.append(self._pinned)
        order = await self._service.get_priority()
        for provider in order:
            client = await self._client_for(provider)
            if client is not None:
                out.append((provider, client))
        return out

    # -- LLMClient Protocol -----------------------------------------------------

    @property
    def model(self) -> str:
        # the model the FIRST candidate would actually serve — health checks
        # and the engine's vision decision read the truth, not a stale flag
        if self._pinned is not None:
            return getattr(self._pinned[1], "model", self._ollama.model)
        return self._ollama.model

    @property
    def active_label(self) -> str:
        return self._active_label

    async def supports_images(self, model: str | None = None) -> bool:
        """Would the FIRST candidate provider see images with this model?
        Ollama answers via the settings keyword list; cloud clients know
        their own registry flag. Engine duck-types this (stubs may omit it)."""
        for provider, client in await self._candidates():
            checker = getattr(client, "supports_images", None)
            if checker is not None:
                return bool(checker(model))
            return self._settings.is_vision_model(model or self._ollama.model)
        return self._settings.is_vision_model(model or self._ollama.model)

    async def list_models(self) -> list[str]:
        """Uncached live list from the first reachable provider (the REST
        /api/models contract — mirrors list_models_cached's routing)."""
        for provider, client in await self._candidates():
            if provider == "ollama":
                if await client.is_available():
                    self._active_label = "Ollama"
                    try:
                        return await client.list_models()
                    except OllamaError:
                        continue
            else:
                self._active_label = getattr(client, "provider_name", provider)
                try:
                    return await client.list_models()
                except OllamaError:
                    return getattr(client, "_static_models", [])  # key fine, listing limited
        raise OllamaError("No provider could list models.")

    async def is_available(self) -> bool:
        for provider, client in await self._candidates():
            if provider == "ollama":
                if await client.is_available():  # type: ignore[attr-defined]
                    return True
            else:
                return True  # a configured, enabled cloud provider counts as available
        return False

    async def list_models_cached(self, ttl: float = 30.0) -> list[str]:
        """Models the ACTIVE (first reachable) provider can actually serve —
        the model selector only ever offers real choices."""
        for provider, client in await self._candidates():
            if provider == "ollama":
                if await client.is_available():  # type: ignore[attr-defined]
                    self._active_label = "Ollama"
                    return await client.list_models_cached(ttl)  # type: ignore[attr-defined]
            else:
                self._active_label = getattr(client, "provider_name", provider)
                return await client.list_models_cached()  # type: ignore[attr-defined]
        return []

    async def chat(self, messages: list[dict], temperature: float, *,
                   model: str | None = None, images: list[str] | None = None) -> str:
        errors: list[str] = []
        for provider, client in await self._candidates():
            if provider == "ollama" and not await client.is_available():  # type: ignore[attr-defined]
                errors.append("Ollama: offline")
                continue
            try:
                result = await client.chat(messages, temperature, model=model, images=images)  # type: ignore[attr-defined]
                self._active_label = getattr(client, "provider_name", "Ollama")
                return result
            except OllamaError as exc:
                errors.append(f"{getattr(client, 'provider_name', provider)}: {exc}")
                continue
        raise OllamaError("All providers failed — " + "; ".join(errors)[:300])

    async def chat_stream(self, messages: list[dict], temperature: float, *,
                          model: str | None = None, images: list[str] | None = None) -> AsyncIterator[str]:
        errors: list[str] = []
        self.last_handoff = None
        for provider, client in await self._candidates():
            if provider == "ollama" and not await client.is_available():  # type: ignore[attr-defined]
                errors.append("Ollama: offline")
                continue
            label = getattr(client, "provider_name", "Ollama")
            started = False
            try:
                async for chunk in client.chat_stream(  # type: ignore[attr-defined]
                    messages, temperature, model=model, images=images
                ):
                    if not started:
                        started = True
                        self._active_label = label
                        if errors and label != "Ollama":
                            self.last_handoff = (
                                f"⚡ Ollama unreachable — answered by **{label}** instead.\n\n"
                            )
                            yield self.last_handoff
                    yield chunk
                return
            except OllamaError as exc:
                if started:
                    raise  # mid-stream failure: replay would duplicate visible text
                errors.append(f"{label}: {exc}")
                continue
        raise OllamaError(
            "No AI provider is reachable. Start Ollama (ollama serve) or add a "
            "cloud key in Settings → AI Providers. (" + "; ".join(errors)[:240] + ")"
        )

    async def aclose(self) -> None:
        await self._ollama.aclose()
        if self._pinned is not None:
            try:
                await self._pinned[1].aclose()  # type: ignore[attr-defined]
            except Exception:
                pass
        for _, client in self._cloud_cache.values():
            try:
                await client.aclose()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._cloud_cache.clear()
