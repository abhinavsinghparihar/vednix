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
import re
import time
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_engine.cloud_client import AnthropicClient, CloudProviderError, OpenAICompatibleClient
from ai_engine.model_catalog import GEMINI_DEFAULT_MODEL, GEMINI_TEXT_MODELS, normalize_gemini_model
from ai_engine.ollama_client import OllamaClient, OllamaError
from core.crypto import KeyVault
from core.logging import get_logger
from memory.models import AppSetting, ProviderKey

logger = get_logger(__name__)

_LEGACY_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?:sk|rk)-[0-9A-Za-z_-]{16,}"),
    re.compile(r"(?:gsk_|or-v1-)[0-9A-Za-z_-]{16,}"),
)


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


ENGINE_LABEL = "Vednix Engine"  # the brand every user-facing label wears

REGISTRY: dict[str, ProviderSpec] = {p.id: p for p in [
    ProviderSpec(
        "ollama", ENGINE_LABEL, "ollama", "", "qwen2.5:3b",
        "https://ollama.com", "https://github.com/ollama/ollama/blob/main/docs/api.md",
        True, ("qwen2.5:3b", "qwen2.5:7b"), needs_key=False,
        blurb="Free, private, unlimited — the Vednix Engine runs models on this machine.",
    ),
    ProviderSpec(
        "openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1",
        "openai/gpt-oss-20b:free",
        "https://openrouter.ai/keys", "https://openrouter.ai/docs", True,
        (
            "openai/gpt-oss-20b:free",
            "google/gemma-3-27b-it:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "x-ai/grok-4.20",
        ),
        blurb="One key, hundreds of models — the easy cloud on-ramp.",
    ),
    ProviderSpec(
        "gemini", "Google Gemini", "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        GEMINI_DEFAULT_MODEL,
        "https://aistudio.google.com/apikey", "https://ai.google.dev/gemini-api/docs", True,
        GEMINI_TEXT_MODELS,
        blurb="Google Gemini text generation via its OpenAI-compatible chat API.",
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


def provider_catalog(settings=None) -> list[dict]:
    """Registry projected for the setup wizard (no keys or ciphertext)."""
    return [
        {
            "id": p.id, "label": p.label, "kind": p.kind, "needs_key": p.needs_key,
            "default_model": settings.gemini_model if p.id == "gemini" and settings else p.default_model,
            "key_url": p.key_url, "docs_url": p.docs_url,
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

    def _safe_status_detail(self, row: ProviderKey) -> str | None:
        detail = " ".join(str(row.status_detail or "").split())
        if not detail:
            return None
        key = self._decrypt(row)
        if key:
            detail = detail.replace(key, "[redacted]")
        for pattern in _LEGACY_SECRET_PATTERNS:
            detail = pattern.sub("[redacted]", detail)
        return detail[:300] or None

    def _public(self, r: ProviderKey, spec: ProviderSpec | None, priority: list[str]) -> dict:
        return {
            "provider": r.provider,
            "label": spec.label if spec else r.provider,
            "enabled": r.enabled,
            "configured": bool(r.key_ciphertext or r.base_url_override),
            "has_key": bool(r.key_ciphertext),
            "key_hint": r.key_hint or None,
            "verified": r.status == "connected" and r.verified_at is not None,
            "status": r.status,                      # unverified | connected | failed
            "status_detail": self._safe_status_detail(r),
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
        base_url = (base_url or "").strip() or None
        if spec.kind == "custom" and not base_url:
            # An existing custom endpoint may be saved/tested without resending
            # its URL; the DB value is checked below before rejecting.
            pass
        clean_model = (model or "").strip() or None
        if clean_model and provider == "gemini":
            clean_model = normalize_gemini_model(clean_model)
        if clean_model and spec.static_models and clean_model not in spec.static_models:
            raise ValueError(
                f"{spec.label} model '{clean_model}' is not in the supported text-chat model list."
            )
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is None and spec.needs_key and not api_key.strip():
                raise ValueError(f"{spec.label} requires an API key.")
            if row is None:
                row = ProviderKey(provider=provider, key_ciphertext="", enabled=False)
                db.add(row)
            if spec.kind == "custom" and not base_url and not row.base_url_override:
                raise ValueError("A custom endpoint needs its base URL (e.g. http://localhost:1234/v1).")
            if api_key.strip():
                key = api_key.strip()
                row.key_ciphertext = self._vault.encrypt(key)
                row.key_hint = KeyVault.fingerprint(key)
            if base_url is not None:
                row.base_url_override = base_url
            if clean_model is not None:
                row.model_override = clean_model
            # Any key/config save invalidates the prior verification. A provider
            # is never routable until its text-generation check succeeds again.
            row.enabled = False
            row.status = "unverified"
            row.status_detail = ""
            row.verified_at = None
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
            spec = REGISTRY.get(provider)
            if enabled and (row.status != "connected" or row.verified_at is None):
                raise ValueError("Verify this provider successfully before enabling it.")
            if enabled and spec and spec.needs_key and not self._decrypt(row):
                raise ValueError("The stored API key could not be decrypted. Save the key and verify again.")
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

    # --- Ollama default model (wizard's "select model → save") -------------------------

    async def get_ollama_default(self) -> str | None:
        async with self._sessions() as db:
            row = await db.get(AppSetting, "ollama_default_model")
            return row.value if row and row.value else None

    async def set_ollama_default(self, model: str) -> str:
        model = model.strip()
        if not model:
            raise ValueError("Model name is required.")
        async with self._sessions() as db:
            row = await db.get(AppSetting, "ollama_default_model")
            if row is None:
                db.add(AppSetting(key="ollama_default_model", value=model))
            else:
                row.value = model
            await db.commit()
        return model

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

    def build_client(
        self, provider: str, row: ProviderKey | None, *, settings,
        for_verification: bool = False,
    ) -> "object | None":
        """Build a provider client. Normal routing requires a successful,
        current verification; ``for_verification`` is used only by the test call."""
        spec = REGISTRY.get(provider)
        if spec is None:
            return None
        if spec.kind == "ollama":
            return OllamaClient(
                settings.ollama_host, settings.ollama_model,
                timeout=settings.llm_request_timeout, health_ttl=settings.llm_health_ttl,
            )
        if row is None or (not for_verification and (not row.enabled or row.status != "connected")):
            return None
        api_key = self._decrypt(row)
        if spec.needs_key and not api_key:
            return None
        base_url = row.base_url_override or spec.base_url
        if not base_url:
            return None
        default_model = settings.gemini_model if provider == "gemini" else spec.default_model
        model = row.model_override or default_model
        model = normalize_gemini_model(model) if provider == "gemini" else model
        # A legacy Gemini row can contain a realtime/music model saved by the
        # old unfiltered selector. Never send that to a text chat endpoint.
        if spec.static_models and model not in spec.static_models:
            model = default_model
        cls = AnthropicClient if spec.kind == "anthropic" else OpenAICompatibleClient
        return cls(
            api_key, model or "default",
            base_url=base_url, provider_name=spec.label,
            timeout=settings.llm_request_timeout, health_ttl=settings.llm_health_ttl,
            static_models=list(spec.static_models),
            supported_models=list(spec.static_models) if spec.static_models else None,
            vision=spec.vision,
        )

    async def mark_failed(self, provider: str, detail: str) -> None:
        """Persist runtime failures without storing upstream secrets or bodies."""
        if provider not in REGISTRY or provider == "ollama":
            return
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is not None:
                row.status = "failed"
                row.status_detail = " ".join(str(detail).split())[:300]
                row.enabled = False
                await db.commit()

    async def verify(self, provider: str, *, settings) -> dict:
        """Prove the provider can perform text generation (not just list models).

        Gemini verification intentionally uses the same configured model and
        chat-completions endpoint as a real turn. Keys are only decrypted for
        this backend-side call and are never included in the result.
        """
        spec = REGISTRY.get(provider)
        if spec is None:
            raise ValueError(f"Unknown provider '{provider}'.")
        import datetime as _dt

        detail = ""
        ok = False
        result_enabled = False
        models_preview: list[str] = []
        verification_model: str | None = None
        server_running: bool | None = None
        row: ProviderKey | None = None
        client = None
        if spec.kind == "ollama":
            client = self.build_client("ollama", None, settings=settings)
            selected_model = await self.get_ollama_default() or settings.ollama_model
            result_enabled = True
            try:
                running = await client.is_available()  # type: ignore[attr-defined]
                server_running = running
                models_preview = await client.list_models() if running else []  # type: ignore[attr-defined]
                ok = running and selected_model in models_preview
                result_enabled = ok
                verification_model = selected_model
                if not running:
                    detail = f"Ollama is unavailable at {settings.ollama_host}. Start it with `ollama serve`."
                elif not ok:
                    detail = f"Ollama is running, but `{selected_model}` is not installed. Run `ollama pull {selected_model}`."
            except OllamaError as exc:
                detail = str(exc)
            finally:
                await client.aclose()  # type: ignore[attr-defined]
        else:
            row = await self._row(provider)
            if row is None or (spec.needs_key and not row.key_ciphertext):
                detail = f"No {spec.label} API key is stored yet."
            elif spec.kind == "custom" and not (row.base_url_override or "").strip():
                detail = "No custom provider endpoint is configured."
            else:
                client = self.build_client(provider, row, settings=settings, for_verification=True)
                if client is None:
                    detail = f"{spec.label} is not configured for text generation. Check its key and endpoint."
                else:
                    verification_model = getattr(client, "model", None)
                    try:
                        probe = await client.chat(
                            [{"role": "user", "content": "Reply with exactly: VEDNIX_PROVIDER_OK"}],
                            0.0,
                            model=verification_model,
                        )  # type: ignore[attr-defined]
                        if not str(probe).strip():
                            raise CloudProviderError(f"{spec.label} returned an empty verification response.")
                        ok = True
                        try:
                            models_preview = await client.list_models()  # type: ignore[attr-defined]
                        except CloudProviderError:
                            # Text generation itself succeeded. If model listing
                            # is restricted, expose only the model just verified.
                            models_preview = []
                        if verification_model:
                            models_preview = [verification_model, *[
                                m for m in models_preview if m != verification_model
                            ]]
                    except CloudProviderError as exc:
                        detail = str(exc)
                    except Exception as exc:
                        # Do not return arbitrary exception strings (which may
                        # include request configuration) to the browser.
                        logger.warning("%s verification failed (%s)", provider, type(exc).__name__)
                        detail = f"{spec.label} verification failed unexpectedly. Check the backend logs and provider settings."
                    finally:
                        await client.aclose()  # type: ignore[attr-defined]

            if row is not None:
                async with self._sessions() as db:
                    db_row = await db.get(ProviderKey, row.id)
                    if db_row is not None:
                        was_connected = db_row.status == "connected"
                        db_row.status = "connected" if ok else "failed"
                        db_row.status_detail = "" if ok else detail[:300]
                        db_row.verified_at = _dt.datetime.now(_dt.timezone.utc) if ok else None
                        if ok:
                            # New/rotated keys are enabled after actual success;
                            # a deliberately disabled, already-verified provider
                            # stays disabled when someone merely re-tests it.
                            if not was_connected:
                                db_row.enabled = True
                            if provider == "gemini" and verification_model:
                                db_row.model_override = verification_model
                        else:
                            db_row.enabled = False
                        result_enabled = bool(db_row.enabled)
                        if row is not None:
                            row.enabled = result_enabled
                        await db.commit()
        return {
            "provider": provider,
            "connected": ok,
            "enabled": result_enabled,
            "verified": ok,
            "verification_model": verification_model,
            "running": server_running if provider == "ollama" else None,
            "model_available": ok,
            "detail": "" if ok else detail,
            "models": list(dict.fromkeys(models_preview))[:12],
        }


from services.resilient_llm import ResilientLLM  # noqa: E402  (registry/service must load first)
