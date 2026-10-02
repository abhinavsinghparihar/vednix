"""Capability-aware Gemini/Groq chat routing with pre-token failover."""

from __future__ import annotations

from typing import AsyncIterator

from ai_engine.cloud_client import OpenAICompatibleClient
from ai_engine.model_catalog import ModelInfo, ModelTask, normalize_gemini_model
from ai_engine.provider_error import ProviderError
from core.logging import get_logger
from memory.models import ProviderKey
from services.providers import REGISTRY, ProviderService

logger = get_logger(__name__)


class ResilientLLM:
    """One chat interface over encrypted, verified providers.

    Automatic requests try configured providers in priority order. Failover is
    permitted only before the first response token; an explicitly selected
    provider/model is strict and never silently changes to another provider.
    """

    def __init__(self, service: ProviderService, settings) -> None:
        self._service = service
        self._settings = settings
        self._client_cache: dict[str, tuple[float, OpenAICompatibleClient]] = {}
        self._active_provider = "unavailable"
        self._active_model = ""
        self.last_handoff: str | None = None

    @staticmethod
    def _version(row: ProviderKey | None) -> float:
        return row.updated_at.timestamp() if row and row.updated_at else 0.0

    @property
    def model(self) -> str:
        return self._active_model

    @property
    def active_label(self) -> str:
        if self._active_provider in REGISTRY:
            return REGISTRY[self._active_provider].label
        return "unavailable"

    @property
    def active_provider(self) -> str:
        return self._active_provider

    async def _close_cached(self, provider: str) -> None:
        cached = self._client_cache.pop(provider, None)
        if cached:
            try:
                await cached[1].aclose()
            except Exception:
                pass

    async def _client_for(self, provider: str) -> OpenAICompatibleClient | None:
        if provider not in REGISTRY:
            return None
        row = await self._service._row(provider)
        if (
            row is None or not row.enabled or row.status != "connected"
            or row.verified_at is None or not self._service._decrypt(row)
        ):
            await self._close_cached(provider)
            return None
        version = self._version(row)
        cached = self._client_cache.get(provider)
        if cached and cached[0] == version:
            return cached[1]
        await self._close_cached(provider)
        client = self._service.build_client(provider, row, settings=self._settings)
        if client is not None:
            self._client_cache[provider] = (version, client)
        return client

    async def _candidates(self, preferred: str | None = None) -> list[tuple[str, OpenAICompatibleClient]]:
        if preferred:
            if preferred not in REGISTRY:
                raise ProviderError("Vednix", f"Unknown provider '{preferred}'.", category="configuration")
            client = await self._client_for(preferred)
            if client is None:
                raise ProviderError("Vednix", await self.unavailable_message(preferred), category="configuration")
            return [(preferred, client)]
        result: list[tuple[str, OpenAICompatibleClient]] = []
        for provider in await self._service.get_priority():
            client = await self._client_for(provider)
            if client is not None:
                result.append((provider, client))
        if not result:
            raise ProviderError("Vednix", await self.unavailable_message(), category="configuration")
        return result

    async def unavailable_message(self, provider: str | None = None) -> str:
        if provider and provider not in REGISTRY:
            return f"Unknown provider '{provider}'. Choose Gemini or Groq in Settings."
        if provider:
            spec = REGISTRY[provider]
            row = await self._service._row(provider)
            if row is None or not row.key_ciphertext:
                return f"{spec.label} is not configured. Add its API key in Settings → AI Providers."
            if not self._service._decrypt(row):
                return f"The saved {spec.label} key could not be decrypted. Enter the key again in Settings."
            if row.status != "connected" or row.verified_at is None:
                detail = self._service._safe_detail(row)
                return detail or f"{spec.label} is not verified. Test the connection in Settings → AI Providers."
            if not row.enabled:
                return f"{spec.label} is disabled. Enable it in Settings → AI Providers."
            return f"{spec.label} has no recently validated model for this task. Refresh and validate its model list."
        rows = await self._service.list_configured()
        if not rows:
            return "No AI provider is configured. Add a Gemini or Groq API key in Settings → AI Providers."
        if not any(row["verified"] and row["enabled"] for row in rows):
            return "No provider is verified and enabled. Test a Gemini or Groq connection in Settings → AI Providers."
        return "No verified provider has a usable model for this request. Refresh model validation in Settings → AI Providers."

    async def _row_for(self, provider: str) -> ProviderKey | None:
        return await self._service._row(provider)

    async def _validated(
        self,
        provider: str,
        model_id: str,
        task: ModelTask,
        *,
        force: bool = False,
    ) -> ModelInfo:
        model_id = normalize_gemini_model(model_id) if provider == "gemini" else model_id.strip()
        if not force:
            cached = await self._service.get_validated_model(provider, model_id, task=task)
            if cached is not None:
                return cached
        try:
            info = await self._service.validate_model(
                provider, model_id, settings=self._settings, task=task, force=True,
            )
        except ProviderError:
            raise
        except ValueError as exc:
            raise ProviderError(
                REGISTRY.get(provider).label if provider in REGISTRY else provider,
                str(exc), category="configuration", model_id=model_id,
            ) from exc
        if not info.available or not info.capabilities.supports(task):
            raise ProviderError(
                REGISTRY[provider].label,
                info.reason or f"Model `{model_id}` failed the {task} capability check.",
                category="capability", model_id=model_id,
            )
        return info

    async def _choose_model(
        self,
        provider: str,
        client: OpenAICompatibleClient,
        requested: str | None,
        *,
        task: ModelTask,
        strict: bool,
    ) -> str:
        row = await self._row_for(provider)
        desired = (requested or (row.model_override if row else None) or client.model or "").strip()
        if provider == "gemini" and desired:
            desired = normalize_gemini_model(desired)

        if desired:
            try:
                return (await self._validated(provider, desired, task)).id
            except ProviderError as exc:
                if strict:
                    raise
                logger.info("Skipping %s model %s for %s: %s", provider, desired, task, exc.message)

        if strict and desired:
            raise ProviderError(
                REGISTRY[provider].label,
                f"Model `{desired}` is not validated for {task}. Refresh the live model list and select a usable model.",
                category="capability", model_id=desired,
            )

        cached = await self._service.cached_models(provider, task=task)
        if cached:
            return cached[0].id

        try:
            catalog = await self._service.model_catalog(provider, settings=self._settings, task=task)
        except ProviderError:
            raise
        except ValueError as exc:
            raise ProviderError(REGISTRY[provider].label, str(exc), category="configuration") from exc
        if catalog["models"]:
            return str(catalog["models"][0]["id"])
        raise ProviderError(
            REGISTRY[provider].label,
            f"{REGISTRY[provider].label} has no validated {task.replace('_', ' ')} model available.",
            category="capability",
        )

    async def is_available(self, provider: str | None = None) -> bool:
        try:
            candidates = await self._candidates(provider)
        except ProviderError:
            return False
        for name, client in candidates:
            try:
                model = await self._choose_model(name, client, None, task="text", strict=provider is not None)
                self._active_provider = name
                self._active_model = model
                return True
            except ProviderError as exc:
                if provider is not None:
                    return False
                logger.info("Provider %s is not ready for text: %s", name, exc.message)
        return False

    async def chat_available(self, provider: str | None = None) -> bool:
        return await self.is_available(provider=provider)

    async def model_catalog(self, provider: str | None = None, *, task: str = "text") -> dict:
        if provider is None:
            candidates = await self._candidates()
            provider = candidates[0][0]
        return await self._service.model_catalog(provider, settings=self._settings, task=task)

    async def list_models(
        self, provider: str | None = None, *, task: str = "text",
    ) -> list[str]:
        if provider is None:
            candidates = await self._candidates()
            provider = candidates[0][0]
        result = await self._service.model_catalog(provider, settings=self._settings, task=task)
        return list(result["available"])

    async def list_models_cached(
        self, ttl: float = 30.0, provider: str | None = None, *, task: str = "text",
    ) -> list[str]:
        # The service's successful capability rows are cached for hours. Chat
        # requests do not refresh every model; only explicit discovery does.
        if provider is None:
            candidates = await self._candidates()
            if not candidates:
                return []
            provider = candidates[0][0]
        return [info.id for info in await self._service.cached_models(provider, task=task)]

    async def supports_images(self, model: str | None = None, provider: str | None = None) -> bool:
        if provider:
            if not model:
                row = await self._row_for(provider)
                model = row.model_override if row else None
            return bool(model and await self._service.get_validated_model(provider, model, task="vision"))
        if model:
            for name, _client in await self._candidates():
                if await self._service.get_validated_model(name, model, task="vision"):
                    return True
            return False
        return False

    async def status_snapshot(self) -> dict:
        """Cheap persisted state only; health endpoints never probe every model."""
        rows = await self._service.list_configured()
        provider_states: list[dict] = []
        for row in rows:
            provider = row["provider"]
            if provider not in REGISTRY:
                continue
            model = row.get("model_override") or ""
            info = await self._service.get_validated_model(provider, model, task="text") if model else None
            model_available = info is not None
            chat_available = bool(row["enabled"] and row["verified"] and model_available)
            provider_states.append({
                "provider": provider,
                "label": REGISTRY[provider].label,
                "configured": row["configured"],
                "verified": row["verified"],
                "enabled": row["enabled"],
                "status": row["status"],
                "status_detail": row["status_detail"],
                "model": model,
                "model_available": model_available,
                "chat_available": chat_available,
            })

        active = next((state for state in provider_states if state["chat_available"]), None)
        if active:
            self._active_provider = active["provider"]
            self._active_model = active["model"]
        return {
            "backend_online": True,
            "chat_available": any(item["chat_available"] for item in provider_states),
            "active_provider": self._active_provider if active else "unavailable",
            "active_model": self._active_model,
            "provider_configured": bool(rows),
            "provider_verified": bool(active and active["verified"]),
            "model_available": bool(active and active["model_available"]),
            "providers": provider_states,
        }

    async def _mark_error(self, provider: str, error: ProviderError, model: str, task: ModelTask) -> None:
        if error.authentication_error:
            await self._service.mark_failed(provider, error.message, disable=True)
        elif error.retryable:
            await self._service.mark_failed(provider, error.message, disable=False)
        elif error.unsupported_model:
            await self._service.mark_model_unavailable(
                provider, model, task=task, reason=error.message,
            )

    async def chat(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
        provider: str | None = None,
    ) -> str:
        task: ModelTask = "vision" if images else "text"
        candidates = await self._candidates(provider)
        errors: list[str] = []
        for name, client in candidates:
            try:
                selected = await self._choose_model(
                    name, client, model, task=task, strict=provider is not None,
                )
                response = await client.chat(
                    messages, temperature, model=selected, images=images,
                )
                if not response.strip():
                    raise ProviderError(REGISTRY[name].label, "The provider returned an empty response.", model_id=selected)
                self._active_provider = name
                self._active_model = selected
                return response
            except ProviderError as exc:
                await self._mark_error(name, exc, model or client.model, task)
                if provider is not None:
                    raise
                errors.append(f"{REGISTRY[name].label}: {exc.message}")
        detail = "; ".join(errors)[:500]
        raise ProviderError(
            "Vednix", "No compatible provider could answer this request. " + detail,
            category="temporary" if errors else "configuration", retryable=bool(errors),
        )

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
        provider: str | None = None,
    ) -> AsyncIterator[str]:
        task: ModelTask = "vision" if images else "text"
        self.last_handoff = None
        candidates = await self._candidates(provider)
        errors: list[str] = []
        for name, client in candidates:
            label = REGISTRY[name].label
            try:
                selected = await self._choose_model(
                    name, client, model, task=task, strict=provider is not None,
                )
            except ProviderError as exc:
                if provider is not None:
                    raise
                errors.append(f"{label}: {exc.message}")
                continue

            started = False
            try:
                async for chunk in client.chat_stream(
                    messages, temperature, model=selected, images=images,
                ):
                    if not chunk:
                        continue
                    if not started:
                        started = True
                        self._active_provider = name
                        self._active_model = selected
                        if errors:
                            model_note = f" using `{selected}`" if model and selected != model else ""
                            self.last_handoff = (
                                f"⚡ Earlier provider unavailable — answered by **{label}**{model_note}.\n\n"
                            )
                            yield self.last_handoff
                    yield chunk
                if not started:
                    raise ProviderError(label, "The provider returned an empty response.", model_id=selected)
                self._active_provider = name
                self._active_model = selected
                return
            except ProviderError as exc:
                await self._mark_error(name, exc, selected, task)
                if started:
                    raise ProviderError(
                        label,
                        f"The provider failed after its response started: {exc.message}",
                        category=exc.category, http_status=exc.http_status,
                        retryable=exc.retryable, model_id=selected,
                    ) from exc
                if provider is not None:
                    raise
                errors.append(f"{label}: {exc.message}")

        if provider is not None:
            raise ProviderError("Vednix", await self.unavailable_message(provider), category="configuration")
        detail = "; ".join(errors)[:500]
        message = "No compatible provider could answer this request."
        if detail:
            message += " " + detail
        else:
            message += " Add and verify a Gemini or Groq API key in Settings → AI Providers."
        raise ProviderError("Vednix", message, category="provider_error", retryable=bool(errors))

    async def aclose(self) -> None:
        for provider in list(self._client_cache):
            await self._close_cached(provider)
