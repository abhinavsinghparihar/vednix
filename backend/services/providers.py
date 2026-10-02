"""Encrypted Gemini/Groq account configuration and live model validation.

Provider catalog metadata is deliberately small and static; model identifiers
and model capabilities are always sourced from each provider's official API and
verified with a real, low-token request before being marked usable.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_engine.cloud_client import GeminiClient, GroqClient, OpenAICompatibleClient
from ai_engine.model_catalog import ModelCapabilities, ModelInfo, ModelTask, normalize_gemini_model
from ai_engine.provider_error import ProviderError
from core.crypto import KeyVault
from core.logging import get_logger
from memory.models import AppSetting, ProviderKey, ProviderModel

logger = get_logger(__name__)

_VALIDATION_TTL = timedelta(hours=6)
_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z_-]{16,}"),
)
_SUPPORTED_TASKS: set[str] = {
    "text", "vision", "audio_input", "audio_output", "image_generation", "video", "tools",
}


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    kind: str
    base_url: str
    key_url: str
    docs_url: str
    blurb: str


ENGINE_LABEL = "Vednix AI"
REGISTRY: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        id="gemini",
        label="Google Gemini",
        kind="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key_url="https://aistudio.google.com/apikey",
        docs_url="https://ai.google.dev/gemini-api/docs",
        blurb="Connect Gemini with a key stored securely on this server.",
    ),
    "groq": ProviderSpec(
        id="groq",
        label="Groq",
        kind="groq",
        base_url="https://api.groq.com/openai/v1",
        key_url="https://console.groq.com/keys",
        docs_url="https://console.groq.com/docs",
        blurb="Connect Groq for fast hosted model inference.",
    ),
}
DEFAULT_PRIORITY = ["gemini", "groq"]


def provider_catalog(settings=None) -> list[dict[str, Any]]:
    """Provider setup metadata only; model data is fetched live per provider."""
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "kind": spec.kind,
            "needs_key": True,
            "key_url": spec.key_url,
            "docs_url": spec.docs_url,
            "blurb": spec.blurb,
            "capabilities": ["text", "vision", "tools"],
        }
        for spec in REGISTRY.values()
    ]


class ProviderService:
    """The sole boundary for provider keys, model catalogs, and validation."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: KeyVault) -> None:
        self._sessions = sessions
        self._vault = vault

    async def _row(self, provider: str) -> ProviderKey | None:
        async with self._sessions() as db:
            return (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()

    def _decrypt(self, row: ProviderKey) -> str:
        if not row.key_ciphertext:
            return ""
        try:
            return self._vault.decrypt(row.key_ciphertext)
        except (ValueError, TypeError):
            return ""

    def _safe_detail(self, row: ProviderKey) -> str | None:
        detail = " ".join(str(row.status_detail or "").split())
        if not detail:
            return None
        key = self._decrypt(row)
        if key:
            detail = detail.replace(key, "[redacted]")
        for pattern in _SECRET_PATTERNS:
            detail = pattern.sub("[redacted]", detail)
        return detail[:300] or None

    def _public(self, row: ProviderKey, priority: list[str]) -> dict[str, Any]:
        spec = REGISTRY.get(row.provider)
        return {
            "provider": row.provider,
            "label": spec.label if spec else row.provider,
            "enabled": bool(row.enabled),
            "configured": bool(row.key_ciphertext),
            "has_key": bool(row.key_ciphertext),
            "key_hint": row.key_hint or None,
            "verified": row.status == "connected" and row.verified_at is not None,
            "status": row.status,
            "status_detail": self._safe_detail(row),
            "model_override": row.model_override,
            "priority": priority.index(row.provider) if row.provider in priority else None,
            "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        }

    async def list_configured(self) -> list[dict[str, Any]]:
        async with self._sessions() as db:
            rows = (await db.execute(select(ProviderKey))).scalars().all()
        priority = await self.get_priority()
        result = [self._public(row, priority) for row in rows if row.provider in REGISTRY]
        result.sort(key=lambda item: item["priority"] if item["priority"] is not None else 99)
        return result

    async def upsert_key(
        self,
        provider: str,
        *,
        api_key: str = "",
        base_url: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Encrypt a new key or update model selection; never echo plaintext."""
        if provider not in REGISTRY:
            raise ValueError(f"Unknown provider '{provider}'.")
        if base_url and base_url.strip().rstrip("/") != REGISTRY[provider].base_url:
            raise ValueError("Custom provider endpoints are not supported.")

        key = api_key.strip()
        selected_model = (model or "").strip() or None
        if selected_model and provider == "gemini":
            selected_model = normalize_gemini_model(selected_model)
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is None and not key:
                raise ValueError(f"{REGISTRY[provider].label} requires an API key.")
            if row is None:
                row = ProviderKey(provider=provider, key_ciphertext="", enabled=False)
                db.add(row)
            if key:
                row.key_ciphertext = self._vault.encrypt(key)
                row.key_hint = KeyVault.fingerprint(key)
            elif not self._decrypt(row):
                raise ValueError("No usable stored key exists. Enter the provider key again.")
            if selected_model is not None:
                row.model_override = selected_model
            # A key or model change invalidates all prior provider and model verification.
            row.enabled = False
            row.status = "unverified"
            row.status_detail = ""
            row.verified_at = None
            await db.execute(delete(ProviderModel).where(ProviderModel.provider == provider))
            await db.commit()
            priority = await self.get_priority()
            return self._public(row, priority)

    async def remove_key(self, provider: str) -> bool:
        if provider not in REGISTRY:
            return False
        async with self._sessions() as db:
            result = await db.execute(delete(ProviderKey).where(ProviderKey.provider == provider))
            await db.execute(delete(ProviderModel).where(ProviderModel.provider == provider))
            await db.commit()
            return bool(result.rowcount)

    async def set_enabled(self, provider: str, enabled: bool) -> bool:
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is None or provider not in REGISTRY:
                return False
            if enabled and (row.status != "connected" or row.verified_at is None):
                raise ValueError("Verify this provider and selected model successfully before enabling it.")
            if enabled and not self._decrypt(row):
                raise ValueError("The stored API key could not be decrypted. Save the key and verify again.")
            row.enabled = enabled
            await db.commit()
            return True

    async def get_priority(self) -> list[str]:
        async with self._sessions() as db:
            row = await db.get(AppSetting, "provider_priority")
        if row:
            try:
                value = json.loads(row.value)
                order = [item for item in value if item in REGISTRY]
            except (json.JSONDecodeError, TypeError):
                order = []
            order = list(dict.fromkeys(order))
            return order + [provider for provider in DEFAULT_PRIORITY if provider not in order]
        return list(DEFAULT_PRIORITY)

    async def set_priority(self, order: list[str]) -> list[str]:
        clean = list(dict.fromkeys(provider for provider in order if provider in REGISTRY))
        clean.extend(provider for provider in DEFAULT_PRIORITY if provider not in clean)
        async with self._sessions() as db:
            row = await db.get(AppSetting, "provider_priority")
            if row is None:
                db.add(AppSetting(key="provider_priority", value=json.dumps(clean)))
            else:
                row.value = json.dumps(clean)
            await db.commit()
        return clean

    def build_client(
        self,
        provider: str,
        row: ProviderKey | None,
        *,
        settings,
        for_verification: bool = False,
    ) -> OpenAICompatibleClient | None:
        spec = REGISTRY.get(provider)
        if spec is None or row is None:
            return None
        if not for_verification and (
            not row.enabled or row.status != "connected" or row.verified_at is None
        ):
            return None
        api_key = self._decrypt(row)
        if not api_key:
            return None
        model = row.model_override or ""
        kwargs = {"timeout": settings.llm_request_timeout}
        if provider == "gemini":
            return GeminiClient(api_key, model, **kwargs)
        if provider == "groq":
            return GroqClient(api_key, model, **kwargs)
        return None

    async def _model_record(self, provider: str, model_id: str) -> ProviderModel | None:
        async with self._sessions() as db:
            return (
                await db.execute(select(ProviderModel).where(
                    ProviderModel.provider == provider, ProviderModel.model_id == model_id,
                ))
            ).scalar_one_or_none()

    @staticmethod
    def _record_fresh(record: ProviderModel | None) -> bool:
        if record is None or record.checked_at is None:
            return False
        checked = record.checked_at
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - checked < _VALIDATION_TTL

    async def _save_model(self, info: ModelInfo) -> None:
        checked_at = datetime.now(timezone.utc)
        capabilities = asdict(info.capabilities)
        payload = {"capabilities": capabilities, "checkedCapabilities": list(info.checkedCapabilities)}
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderModel).where(
                    ProviderModel.provider == info.provider, ProviderModel.model_id == info.id,
                ))
            ).scalar_one_or_none()
            if row is None:
                row = ProviderModel(provider=info.provider, model_id=info.id)
                db.add(row)
            row.display_name = info.displayName
            row.capabilities = json.dumps(payload)
            row.context_window = info.contextWindow
            row.max_output_tokens = info.maxOutputTokens
            row.available = info.available
            row.reason = (info.reason or "")[:300]
            row.latency_ms = info.latencyMs
            row.checked_at = checked_at
            await db.commit()

    def _cached_info(
        self, candidate: ModelInfo, record: ProviderModel, *, task: str | None = None,
    ) -> ModelInfo:
        try:
            payload = json.loads(record.capabilities or "{}")
            raw_caps = payload.get("capabilities", {})
            caps = ModelCapabilities(**{
                name: bool(raw_caps.get(name, False))
                for name in ModelCapabilities.__dataclass_fields__
            })
            checked = tuple(payload.get("checkedCapabilities", []))
        except (ValueError, TypeError, AttributeError):
            caps, checked = candidate.capabilities, ()
        # Capability evidence must still be compatible with the provider's live
        # metadata. The validated cache never adds support the fresh catalog lacks.
        if not candidate.capabilities.text:
            caps = replace(caps, text=False, vision=False, tools=False)
        return replace(
            candidate,
            displayName=candidate.displayName or record.display_name,
            capabilities=caps,
            contextWindow=candidate.contextWindow or record.context_window,
            maxOutputTokens=candidate.maxOutputTokens or record.max_output_tokens,
            available=(
                bool(record.available) if task is None
                else task in checked and caps.supports(task)
            ),
            reason=(None if task and task in checked and caps.supports(task) else record.reason or None),
            latencyMs=record.latency_ms,
            checkedCapabilities=checked,
        )

    async def _probe_candidate(
        self,
        client: OpenAICompatibleClient,
        candidate: ModelInfo,
        task: ModelTask,
    ) -> ModelInfo:
        if task not in {"text", "vision", "tools"}:
            return replace(
                candidate, available=False,
                reason=f"{task.replace('_', ' ')} capability checks are not implemented for these adapters.",
            )
        if not candidate.capabilities.text:
            return replace(
                candidate, available=False,
                reason=candidate.reason or "Provider metadata does not list text generation for this model.",
            )
        probe = {
            "text": client.probe_text,
            "vision": client.probe_vision,
            "tools": client.probe_tools,
        }[task]
        try:
            measured = await probe(candidate.id)
            latency = measured if task == "text" else None
            capabilities = replace(
                candidate.capabilities,
                text=True,
                vision=candidate.capabilities.vision or task == "vision",
                tools=candidate.capabilities.tools or task == "tools",
            )
            checked = tuple(sorted(set(candidate.checkedCapabilities) | {task, "text"}))
            result = replace(
                candidate, capabilities=capabilities, available=True, reason=None,
                latencyMs=latency, checkedCapabilities=checked,
            )
        except ProviderError as exc:
            if exc.authentication_error or exc.retryable:
                raise
            capabilities = candidate.capabilities
            if task == "text":
                capabilities = replace(capabilities, text=False, vision=False, tools=False)
            elif task == "vision":
                capabilities = replace(capabilities, vision=False)
            elif task == "tools":
                capabilities = replace(capabilities, tools=False)
            result = replace(
                candidate, capabilities=capabilities, available=False,
                reason=exc.message[:300],
                checkedCapabilities=tuple(sorted(set(candidate.checkedCapabilities) | {task})),
            )
        await self._save_model(result)
        return result

    def _record_info(self, record: ProviderModel) -> ModelInfo:
        try:
            payload = json.loads(record.capabilities or "{}")
            caps = ModelCapabilities(**{
                name: bool(payload.get("capabilities", {}).get(name, False))
                for name in ModelCapabilities.__dataclass_fields__
            })
            checked = tuple(payload.get("checkedCapabilities", []))
        except (ValueError, TypeError, AttributeError):
            caps, checked = ModelCapabilities(), ()
        return ModelInfo(
            id=record.model_id,
            provider=record.provider,
            displayName=record.display_name or record.model_id,
            capabilities=caps,
            contextWindow=record.context_window,
            maxOutputTokens=record.max_output_tokens,
            available=bool(record.available),
            reason=record.reason or None,
            latencyMs=record.latency_ms,
            checkedCapabilities=checked,
        )

    async def get_validated_model(
        self, provider: str, model_id: str, *, task: str = "text",
    ) -> ModelInfo | None:
        """Return only a recent, successful capability check (no network call)."""
        if task not in _SUPPORTED_TASKS:
            return None
        record = await self._model_record(provider, model_id)
        if not self._record_fresh(record):
            return None
        info = self._record_info(record)
        if task not in info.checkedCapabilities or not info.capabilities.supports(task):
            return None
        return replace(info, available=True, reason=None)

    async def cached_models(self, provider: str, *, task: str = "text") -> list[ModelInfo]:
        if task not in _SUPPORTED_TASKS:
            return []
        async with self._sessions() as db:
            rows = (await db.execute(select(ProviderModel).where(
                ProviderModel.provider == provider,
                ProviderModel.available.is_(True),
            ))).scalars().all()
        result = []
        for row in rows:
            if not self._record_fresh(row):
                continue
            info = self._record_info(row)
            if task in info.checkedCapabilities and info.capabilities.supports(task):
                result.append(replace(info, available=True, reason=None))
        return sorted(result, key=lambda item: (item.latencyMs or float("inf"), item.id))

    async def model_catalog(
        self,
        provider: str,
        *,
        settings,
        task: str = "text",
        force: bool = False,
    ) -> dict[str, Any]:
        if provider not in REGISTRY:
            raise ValueError(f"Unknown provider '{provider}'.")
        if task not in _SUPPORTED_TASKS:
            raise ValueError(f"Unknown model task '{task}'.")
        row = await self._row(provider)
        if row is None or not self._decrypt(row):
            raise ValueError(f"{REGISTRY[provider].label} is not configured with a usable API key.")
        client = self.build_client(provider, row, settings=settings, for_verification=True)
        if client is None:
            raise ValueError(f"{REGISTRY[provider].label} could not create a provider client.")
        try:
            candidates = await client.discover_models()
            returned: list[ModelInfo] = []
            rejected: list[dict[str, Any]] = []
            if task in {"text", "vision", "tools"}:
                for candidate in candidates:
                    if not candidate.capabilities.text:
                        continue
                    record = None if force else await self._model_record(provider, candidate.id)
                    if self._record_fresh(record):
                        validated = self._cached_info(candidate, record, task=task)
                        if task not in validated.checkedCapabilities:
                            validated = await self._probe_candidate(client, candidate, task)
                    else:
                        validated = await self._probe_candidate(client, candidate, task)
                    if validated.available and validated.capabilities.supports(task):
                        returned.append(validated)
                    else:
                        rejected.append({
                            "id": candidate.id,
                            "displayName": candidate.displayName,
                            "reason": validated.reason or f"Model failed the {task} capability check.",
                        })
            return {
                "provider": provider,
                "task": task,
                "models": [model.public() for model in returned],
                "available": [model.id for model in returned],
                "rejected": rejected[:50],
                "discovered": len(candidates),
                "capability": task,
                "verified_only": True,
            }
        finally:
            await client.aclose()

    async def validate_model(
        self, provider: str, model_id: str, *, settings, task: str = "text", force: bool = True,
    ) -> ModelInfo:
        if provider not in REGISTRY:
            raise ValueError(f"Unknown provider '{provider}'.")
        if task not in _SUPPORTED_TASKS:
            raise ValueError(f"Unknown model task '{task}'.")
        model_id = normalize_gemini_model(model_id) if provider == "gemini" else model_id.strip()
        row = await self._row(provider)
        if row is None or not self._decrypt(row):
            raise ValueError(f"{REGISTRY[provider].label} is not configured with a usable API key.")
        client = self.build_client(provider, row, settings=settings, for_verification=True)
        if client is None:
            raise ValueError(f"{REGISTRY[provider].label} could not create a provider client.")
        try:
            candidates = await client.discover_models()
            candidate = next((item for item in candidates if item.id == model_id), None)
            if candidate is None:
                raise ProviderError(
                    REGISTRY[provider].label,
                    "This model is not present in the provider's current live model catalog.",
                    category="unsupported_model", model_id=model_id,
                )
            if not force:
                record = await self._model_record(provider, model_id)
                if self._record_fresh(record):
                    info = self._cached_info(candidate, record, task=task)
                    if task in info.checkedCapabilities:
                        return info
            return await self._probe_candidate(client, candidate, task)
        finally:
            await client.aclose()

    async def verify(self, provider: str, *, settings) -> dict[str, Any]:
        """Validate the provider key and one live-listed text model."""
        if provider not in REGISTRY:
            raise ValueError(f"Unknown provider '{provider}'.")
        row = await self._row(provider)
        spec = REGISTRY[provider]
        if row is None or not self._decrypt(row):
            return {
                "provider": provider, "connected": False, "verified": False,
                "enabled": False, "verification_model": None, "models": [],
                "detail": f"No usable {spec.label} API key is stored yet.",
            }
        was_connected = row.status == "connected"
        was_enabled = row.enabled
        client = self.build_client(provider, row, settings=settings, for_verification=True)
        if client is None:
            detail = f"Could not initialize the {spec.label} provider adapter."
            return await self._save_verification(row, False, detail, None, False)
        success: ModelInfo | None = None
        detail = ""
        try:
            candidates = await client.discover_models()
            if row.model_override:
                selected = normalize_gemini_model(row.model_override) if provider == "gemini" else row.model_override
                candidate = next((item for item in candidates if item.id == selected), None)
                if candidate is None:
                    detail = "The selected model is not present in the provider's live model catalog. Refresh models and choose a listed model."
                else:
                    success = await self._probe_candidate(client, candidate, "text")
                    if not success.available:
                        detail = success.reason or "The selected model failed the text-generation capability check."
            else:
                for candidate in candidates:
                    if not candidate.capabilities.text:
                        continue
                    result = await self._probe_candidate(client, candidate, "text")
                    if result.available:
                        success = result
                        break
                    detail = result.reason or "The provider model failed the text-generation check."
                if success is None and not detail:
                    detail = f"{spec.label} returned no models that advertise text generation."
        except ProviderError as exc:
            detail = exc.message
        except Exception as exc:
            logger.warning("%s verification failed (%s)", provider, type(exc).__name__)
            detail = f"Could not verify {spec.label}. Check the backend logs and provider settings."
        finally:
            await client.aclose()

        if success is not None and success.available:
            async with self._sessions() as db:
                db_row = await db.get(ProviderKey, row.id)
                if db_row is not None:
                    db_row.model_override = success.id
                    db_row.status = "connected"
                    db_row.status_detail = ""
                    db_row.verified_at = datetime.now(timezone.utc)
                    # A successful first verification activates the provider;
                    # re-testing a deliberately disabled provider doesn't.
                    db_row.enabled = True if not was_connected else was_enabled
                    enabled = bool(db_row.enabled)
                    await db.commit()
            return {
                "provider": provider, "connected": True, "verified": True,
                "enabled": enabled, "verification_model": success.id,
                "models": [success.id], "detail": "",
            }
        return await self._save_verification(row, False, detail, row.model_override, False)

    async def _save_verification(
        self, row: ProviderKey, ok: bool, detail: str, model: str | None, enabled: bool,
    ) -> dict[str, Any]:
        clean = self._redact_text(detail, self._decrypt(row))[:300]
        async with self._sessions() as db:
            db_row = await db.get(ProviderKey, row.id)
            if db_row is not None:
                db_row.status = "connected" if ok else "failed"
                db_row.status_detail = "" if ok else clean
                db_row.verified_at = datetime.now(timezone.utc) if ok else None
                db_row.enabled = enabled if ok else False
                await db.commit()
        return {
            "provider": row.provider, "connected": ok, "verified": ok,
            "enabled": enabled if ok else False, "verification_model": model,
            "models": [model] if ok and model else [], "detail": "" if ok else clean,
        }

    @staticmethod
    def _redact_text(text: str, key: str = "") -> str:
        value = " ".join(str(text or "").split())
        if key:
            value = value.replace(key, "[redacted]")
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub("[redacted]", value)
        return value[:300]

    async def mark_model_unavailable(
        self, provider: str, model_id: str, *, task: str, reason: str,
    ) -> None:
        """Cache a real runtime rejection so routing stops retrying that pair."""
        if provider not in REGISTRY:
            return
        record = await self._model_record(provider, model_id)
        if record is None:
            return
        info = self._record_info(record)
        caps = info.capabilities
        if task == "vision":
            caps = replace(caps, vision=False)
        elif task == "tools":
            caps = replace(caps, tools=False)
        else:
            caps = replace(caps, text=False, vision=False, tools=False)
        provider_row = await self._row(provider)
        key = self._decrypt(provider_row) if provider_row is not None else ""
        await self._save_model(replace(
            info, capabilities=caps, available=False,
            reason=self._redact_text(reason, key),
            checkedCapabilities=tuple(sorted(set(info.checkedCapabilities) | {task})),
        ))

    async def mark_failed(self, provider: str, detail: str, *, disable: bool = True) -> None:
        if provider not in REGISTRY:
            return
        async with self._sessions() as db:
            row = (
                await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
            ).scalar_one_or_none()
            if row is not None:
                row.status_detail = self._redact_text(detail, self._decrypt(row))
                if disable:
                    row.status = "failed"
                    row.enabled = False
                    row.verified_at = None
                await db.commit()


from services.resilient_llm import ResilientLLM  # noqa: E402 - public service export
