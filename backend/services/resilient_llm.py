"""Provider-aware chat router.

Explicit provider selection is strict: a selected Gemini provider either
answers with Gemini or returns its actual safe error. Automatic mode follows
the stored priority order and can fail over before the first visible token;
when it switches, the handoff (and any fallback model change) is shown.
"""

from __future__ import annotations

from typing import AsyncIterator

from ai_engine.cloud_client import CloudProviderError
from ai_engine.ollama_client import OllamaClient, OllamaError
from core.logging import get_logger
from memory.models import ProviderKey
from services.providers import ENGINE_LABEL, REGISTRY, ProviderService

logger = get_logger(__name__)


class ResilientLLM:
    """One LLM interface over local Ollama and verified cloud providers."""

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
        self._pinned = pinned
        self._pinned_verified = False
        self._pinned_error: str | None = None
        self._cloud_cache: dict[str, tuple[float, object]] = {}
        self._active_label = pinned[0] if pinned else ENGINE_LABEL
        self._active_model = getattr(pinned[1], "model", ollama.model) if pinned else ollama.model
        self.last_handoff: str | None = None

    @staticmethod
    def _version(row: ProviderKey | None) -> float:
        return row.updated_at.timestamp() if row and row.updated_at else 0.0

    async def _client_for(self, provider: str) -> object | None:
        if provider == "ollama":
            try:
                saved_default = await self._service.get_ollama_default()
                if saved_default:
                    self._ollama.model = saved_default
            except Exception:
                logger.exception("Ollama default-model lookup failed (non-fatal)")
            return self._ollama

        row = await self._service._row(provider)
        if row is None or not row.enabled or row.status != "connected" or row.verified_at is None:
            await self._close_cached(provider)
            return None
        version = self._version(row)
        cached = self._cloud_cache.get(provider)
        if cached and cached[0] == version:
            return cached[1]

        client = self._service.build_client(provider, row, settings=self._settings)
        await self._close_cached(provider)
        if client is not None:
            self._cloud_cache[provider] = (version, client)
        return client

    async def _close_cached(self, provider: str) -> None:
        cached = self._cloud_cache.pop(provider, None)
        if cached:
            try:
                await cached[1].aclose()  # type: ignore[attr-defined]
            except Exception:
                pass

    def _mark_provider_verified(self, provider: str) -> None:
        if provider == "openrouter" and self._pinned is not None:
            self._pinned_verified = True
            self._pinned_error = None

    async def _mark_provider_failed(self, provider: str, detail: str) -> None:
        if provider == "openrouter" and self._pinned is not None:
            self._pinned_verified = False
            self._pinned_error = " ".join(str(detail).split())[:300]
        else:
            await self._service.mark_failed(provider, detail)

    async def _candidates(self, preferred: str | None = None) -> list[tuple[str, object]]:
        """Resolve providers; an explicit choice never silently changes provider."""
        if preferred:
            if preferred not in REGISTRY:
                return []
            if preferred == "ollama":
                return [(preferred, await self._client_for(preferred))]  # type: ignore[list-item]
            if preferred == "openrouter" and self._pinned is not None:
                return [(preferred, self._pinned[1])]
            client = await self._client_for(preferred)
            return [(preferred, client)] if client is not None else []

        out: list[tuple[str, object]] = []
        if self._pinned is not None and self._pinned_error is None:
            out.append(("openrouter", self._pinned[1]))
        for provider in await self._service.get_priority():
            if provider == "openrouter" and self._pinned is not None:
                continue
            client = await self._client_for(provider)
            if client is not None:
                out.append((provider, client))
        return out

    @property
    def model(self) -> str:
        """The most recently resolved active/default model."""
        return self._active_model

    @property
    def active_label(self) -> str:
        return self._active_label

    async def _ollama_inventory(self) -> tuple[bool, list[str], str]:
        selected = self._ollama.model
        try:
            running = await self._ollama.is_available()
            models = await self._ollama.list_models_cached() if running else []
        except OllamaError:
            running, models = False, []
        if models and selected not in models:
            selected = models[0]
        return running, models, selected

    async def ollama_available(self) -> bool:
        """True only when the configured Ollama host responds, not when cloud works."""
        return await self._ollama.is_available()

    async def is_available(self, provider: str | None = None) -> bool:
        for name, client in await self._candidates(provider):
            if name == "ollama":
                running, models, selected = await self._ollama_inventory()
                if running and selected in models:
                    self._active_label = ENGINE_LABEL
                    self._active_model = selected
                    return True
            else:
                # Cloud clients only enter the candidate list after a successful
                # text-generation verification and explicit enablement.
                self._active_label = getattr(client, "provider_name", REGISTRY[name].label)
                self._active_model = getattr(client, "model", self._active_model)
                return True
        return False

    async def unavailable_message(self, provider: str | None = None) -> str:
        if provider and provider != "ollama":
            spec = REGISTRY.get(provider)
            label = spec.label if spec else provider
            row = await self._service._row(provider) if spec else None
            if row is None:
                return f"{label} is not configured. Add its provider key in Settings → AI Providers."
            if not row.key_ciphertext and spec and spec.needs_key:
                return f"{label} has no API key stored. Add a key in Settings → AI Providers."
            if row.status != "connected" or row.verified_at is None:
                status_detail = self._service._safe_status_detail(row)
                if status_detail:
                    return f"{label} is not verified: {status_detail}"
                return f"{label} is not verified yet. Test the connection in Settings → AI Providers."
            if not row.enabled:
                return f"{label} is disabled. Enable it in Settings → AI Providers."
            return f"{label} is not available for chat right now. Test its connection and retry."
        if provider == "ollama":
            running, models, selected = await self._ollama_inventory()
            if not running:
                return f"Ollama is unavailable at {self._settings.ollama_host}. Start it with `ollama serve`."
            if not models:
                return "Ollama is running, but no model is installed. Run `ollama pull qwen2.5:3b`."
            return f"Ollama model `{selected}` is not available. Choose an installed model in Settings."
        return (
            "No verified chat provider is available. Ollama may be offline, or no cloud provider "
            "has a verified, enabled key. Check Settings → AI Providers."
        )

    async def model_catalog(self, provider: str | None = None) -> dict:
        """Return model choices scoped to the provider and text-chat operation."""
        if provider and provider not in REGISTRY:
            return {
                "provider": provider, "default": "", "available": [],
                "configured": False, "verified": False, "model_available": False,
                "chat_available": False, "error": f"Unknown provider '{provider}'.",
            }

        if provider == "ollama":
            running, models, default = await self._ollama_inventory()
            model_available = bool(running and default in models)
            self._active_label = ENGINE_LABEL
            self._active_model = default
            error = None
            if not running:
                error = f"Ollama is unavailable at {self._settings.ollama_host}."
            elif not models:
                error = "Ollama is running, but no model is installed."
            elif not model_available:
                error = f"The configured Ollama model `{default}` is not installed."
            return {
                "provider": "ollama", "default": default, "available": models,
                "configured": True, "verified": running, "enabled": True,
                "model_available": model_available, "chat_available": model_available,
                "error": error,
            }

        if provider:
            if provider == "openrouter" and self._pinned is not None:
                return await self._cloud_model_catalog(provider, client=self._pinned[1])
            return await self._cloud_model_catalog(provider)

        # Automatic selection uses the first verified provider that can serve a
        # text model, not the hard-coded Ollama default in production. A legacy
        # env-pinned OpenRouter key can supply its model choice before first use,
        # but is not reported as verified/chat-ready until a real chat succeeds.
        pinned_pending: dict | None = None
        for name, client in await self._candidates():
            if name == "ollama":
                running, models, default = await self._ollama_inventory()
                if running and models:
                    model_available = default in models
                    self._active_label = ENGINE_LABEL
                    self._active_model = default
                    return {
                        "provider": name, "default": default, "available": models,
                        "configured": True, "verified": running, "enabled": True,
                        "model_available": model_available, "chat_available": model_available,
                        "error": None if model_available else f"Ollama model `{default}` is not installed.",
                    }
                continue
            result = await self._cloud_model_catalog(name, client=client)
            if result["chat_available"]:
                return result
            if name == "openrouter" and self._pinned is not None and result["model_available"]:
                pinned_pending = result

        if pinned_pending is not None:
            return pinned_pending

        running, models, default = await self._ollama_inventory()
        self._active_label = "unavailable"
        self._active_model = self._ollama.model
        return {
            "provider": None, "default": self._ollama.model, "available": [],
            "configured": bool(await self._service.list_configured()),
            "verified": running, "enabled": False, "model_available": False,
            "chat_available": False,
            "error": await self.unavailable_message(),
        }

    async def _cloud_model_catalog(self, provider: str, *, client: object | None = None) -> dict:
        spec = REGISTRY[provider]
        row = await self._service._row(provider)
        if provider == "openrouter" and self._pinned is not None and client is self._pinned[1]:
            pinned_client = client
            default = getattr(pinned_client, "model", REGISTRY[provider].default_model)
            # The env-pinned legacy path is deliberately restricted to exactly
            # its configured model; catalog/health requests need not probe the
            # provider over the network before a chat has been attempted.
            supports_model = getattr(pinned_client, "supports_model", lambda _model: True)
            available = [default] if default and supports_model(default) else []
            self._active_label = getattr(pinned_client, "provider_name", "OpenRouter (env)")
            self._active_model = default
            error = self._pinned_error
            return self._cloud_catalog_result(
                provider, default, available, True, self._pinned_verified, True,
                bool(default and getattr(pinned_client, "supports_model", lambda _model: True)(default)), error,
            )
        configured = bool(row and (row.key_ciphertext or row.base_url_override))
        verified = bool(row and row.status == "connected" and row.verified_at is not None)
        enabled = bool(row and row.enabled)
        if row is None:
            error = f"{spec.label} is not configured. Add its key in Settings → AI Providers."
            default = self._default_model(provider, None)
            self._active_label = spec.label
            self._active_model = default
            return self._cloud_catalog_result(provider, default, [], configured, verified, enabled, False, error)
        if not verified:
            error = row.status_detail or f"{spec.label} has not passed a text-generation verification."
            default = self._default_model(provider, row)
            self._active_label = spec.label
            self._active_model = default
            return self._cloud_catalog_result(provider, default, [], configured, verified, enabled, False, error)
        if not enabled:
            error = f"{spec.label} is verified but disabled. Enable it in Settings → AI Providers."
            default = self._default_model(provider, row)
            self._active_label = spec.label
            self._active_model = default
            return self._cloud_catalog_result(provider, default, [], configured, verified, enabled, False, error)

        client = client or await self._client_for(provider)
        if client is None:
            error = f"{spec.label} is not ready for chat. Test the provider connection again."
            default = self._default_model(provider, row)
            return self._cloud_catalog_result(provider, default, [], configured, verified, enabled, False, error)
        default = getattr(client, "model", self._default_model(provider, row))
        warning = None
        try:
            available = await client.list_models_cached()  # type: ignore[attr-defined]
        except CloudProviderError as exc:
            # Verification already generated text using this model. Preserve
            # that one proven option if the optional list-model endpoint is
            # unavailable; never expose the rest of the provider's raw catalog.
            available = []
            warning = str(exc)
        supports_model = getattr(client, "supports_model", None)
        if default and (supports_model is None or supports_model(default)) and default not in available:
            available.insert(0, default)
        available = list(dict.fromkeys(available))
        model_available = bool(default and default in available)
        self._active_label = getattr(client, "provider_name", spec.label)
        self._active_model = default
        return self._cloud_catalog_result(
            provider, default, available, configured, verified, enabled, model_available,
            warning if not model_available else None,
        )

    @staticmethod
    def _cloud_catalog_result(
        provider: str, default: str, available: list[str], configured: bool,
        verified: bool, enabled: bool, model_available: bool, error: str | None,
    ) -> dict:
        return {
            "provider": provider, "default": default, "available": available,
            "configured": configured, "verified": verified, "enabled": enabled,
            "model_available": model_available,
            "chat_available": bool(enabled and verified and model_available),
            "error": error,
        }

    def _default_model(self, provider: str, row: ProviderKey | None) -> str:
        spec = REGISTRY[provider]
        default = self._settings.gemini_model if provider == "gemini" else spec.default_model
        model = (row.model_override if row else None) or default
        if provider == "gemini":
            model = model.removeprefix("models/")
        if spec.static_models and model not in spec.static_models:
            return default
        return model

    async def chat_available(self, provider: str | None = None) -> bool:
        return await self.is_available(provider=provider)

    async def status_snapshot(self) -> dict:
        """Safe online/config/verification/model/chat state for health UIs."""
        ollama_running, ollama_models, ollama_model = await self._ollama_inventory()
        ollama_model_available = bool(ollama_running and ollama_model in ollama_models)
        provider_rows = await self._service.list_configured()
        rows_by_id = {item["provider"]: item for item in provider_rows}
        providers: list[dict] = [{
            "provider": "ollama", "label": ENGINE_LABEL, "configured": True,
            "verified": ollama_running, "enabled": True,
            "status": "connected" if ollama_running else "unavailable",
            "status_detail": None if ollama_running else f"Ollama is unavailable at {self._settings.ollama_host}.",
            "model": ollama_model, "model_available": ollama_model_available,
            "chat_available": ollama_model_available,
        }]
        for row in provider_rows:
            if row["provider"] == "ollama":
                continue
            provider_id = row["provider"]
            default = self._default_model(provider_id, None)
            configured_row = await self._service._row(provider_id)
            if configured_row is not None:
                default = self._default_model(provider_id, configured_row)
            verified = bool(row["verified"])
            enabled = bool(row["enabled"])
            spec = REGISTRY[provider_id]
            has_usable_key = bool(
                configured_row and (not spec.needs_key or self._service._decrypt(configured_row))
            )
            supported = not spec.static_models or default in spec.static_models
            model_available = verified and has_usable_key and bool(default) and supported
            chat_available = False
            if enabled and model_available:
                chat_available = await self._client_for(provider_id) is not None
            providers.append({
                "provider": provider_id, "label": row["label"],
                "configured": row["configured"], "verified": verified,
                "enabled": enabled, "status": row["status"],
                "status_detail": row["status_detail"], "model": default,
                "model_available": model_available,
                "chat_available": chat_available,
            })
        selection = await self.model_catalog()
        if self._pinned is not None:
            pinned_model = getattr(self._pinned[1], "model", "")
            pinned_supports_model = getattr(self._pinned[1], "supports_model", lambda _model: True)
            pinned_state = {
                "provider": "openrouter", "label": getattr(self._pinned[1], "provider_name", "OpenRouter (env)"),
                "configured": True, "verified": self._pinned_verified, "enabled": True,
                "status": "connected" if self._pinned_verified else ("failed" if self._pinned_error else "unverified"),
                "status_detail": self._pinned_error, "model": pinned_model,
                "model_available": bool(pinned_model and pinned_supports_model(pinned_model)),
                "chat_available": self._pinned_verified,
            }
            existing = next((item for item in providers if item["provider"] == "openrouter"), None)
            if existing is None:
                providers.append(pinned_state)
            else:
                existing.update(pinned_state)
        chat_available = any(p["chat_available"] for p in providers)
        return {
            "backend_online": True,
            "chat_available": chat_available,
            "active_provider": selection["provider"] or "unavailable",
            "active_model": selection["default"],
            "provider_configured": bool(selection["configured"]),
            "provider_verified": bool(selection["verified"]),
            "model_available": bool(selection["model_available"]),
            "providers": providers,
            "ollama": {
                "running": ollama_running, "models": ollama_models,
                "default_model": ollama_model,
                "model_available": ollama_model_available,
                "chat_available": ollama_model_available,
            },
        }

    def apply_ollama_default_now(self, model: str) -> None:
        self._ollama.model = model
        if self._active_label == ENGINE_LABEL:
            self._active_model = model

    async def ollama_ps(self) -> list[dict]:
        try:
            return await self._ollama.ps()
        except OllamaError:
            return []

    async def list_models(self, provider: str | None = None) -> list[str]:
        catalog = await self.model_catalog(provider)
        return catalog["available"]

    async def list_models_cached(self, ttl: float = 30.0) -> list[str]:
        # Cloud and Ollama adapters cache their own list; this keeps the engine's
        # vision-routing protocol while preserving provider scope.
        catalog = await self.model_catalog()
        return catalog["available"]

    async def supports_images(self, model: str | None = None, provider: str | None = None) -> bool:
        for name, client in await self._candidates(provider):
            if name == "ollama":
                return self._settings.is_vision_model(model or self._ollama.model)
            checker = getattr(client, "supports_images", None)
            return bool(checker(model)) if checker is not None else False
        return self._settings.is_vision_model(model or self._ollama.model)

    async def _effective_model(
        self, provider: str, client: object, requested: str | None, *, strict: bool,
    ) -> str:
        if provider == "ollama":
            models = await client.list_models()  # type: ignore[attr-defined]
            default = getattr(client, "model", self._ollama.model)
            if default not in models and models:
                default = models[0]
            if requested:
                if requested in models:
                    return requested
                if strict:
                    raise OllamaError(f"Ollama model `{requested}` is not installed. Choose an installed model.")
            if not models:
                raise OllamaError("Ollama is running, but no model is installed.")
            return default

        selected = (requested or getattr(client, "model", "")).removeprefix("models/")
        supports_model = getattr(client, "supports_model", None)
        if selected and (supports_model is None or supports_model(selected)):
            return selected
        if strict and requested:
            label = getattr(client, "provider_name", provider)
            raise OllamaError(
                f"{label} does not support `{requested}` for text chat. Refresh the model list and choose a supported model."
            )
        default = getattr(client, "model", "")
        if default and (supports_model is None or supports_model(default)):
            return default
        raise OllamaError(f"{getattr(client, 'provider_name', provider)} has no supported text-chat model configured.")

    async def chat(
        self, messages: list[dict], temperature: float, *, model: str | None = None,
        images: list[str] | None = None, provider: str | None = None,
    ) -> str:
        errors: list[str] = []
        targets = await self._candidates(provider)
        if not targets:
            raise OllamaError(await self.unavailable_message(provider))
        for name, client in targets:
            try:
                if name == "ollama" and not await client.is_available():  # type: ignore[attr-defined]
                    raise OllamaError(f"{ENGINE_LABEL} is not running.")
                effective_model = await self._effective_model(name, client, model, strict=provider is not None)
                response = await client.chat(
                    messages, temperature, model=effective_model, images=images
                )  # type: ignore[attr-defined]
                if not str(response).strip():
                    raise OllamaError(f"{getattr(client, 'provider_name', ENGINE_LABEL)} returned an empty response.")
                self._active_label = getattr(client, "provider_name", ENGINE_LABEL)
                self._active_model = effective_model
                if name != "ollama":
                    self._mark_provider_verified(name)
                return response
            except OllamaError as exc:
                if name != "ollama":
                    await self._mark_provider_failed(name, str(exc))
                if provider is not None:
                    raise
                errors.append(f"{getattr(client, 'provider_name', ENGINE_LABEL)}: {exc}")
        raise OllamaError("No AI provider could answer. " + "; ".join(errors)[:400])

    async def chat_stream(
        self, messages: list[dict], temperature: float, *, model: str | None = None,
        images: list[str] | None = None, provider: str | None = None,
    ) -> AsyncIterator[str]:
        errors: list[str] = []
        self.last_handoff = None
        targets = await self._candidates(provider)
        if not targets:
            raise OllamaError(await self.unavailable_message(provider))

        for name, client in targets:
            try:
                if name == "ollama" and not await client.is_available():  # type: ignore[attr-defined]
                    raise OllamaError(f"{ENGINE_LABEL} is not running.")
                effective_model = await self._effective_model(name, client, model, strict=provider is not None)
            except OllamaError as exc:
                if provider is not None:
                    raise
                errors.append(f"{getattr(client, 'provider_name', ENGINE_LABEL)}: {exc}")
                continue

            label = getattr(client, "provider_name", ENGINE_LABEL)
            started = False
            try:
                async for chunk in client.chat_stream(
                    messages, temperature, model=effective_model, images=images
                ):  # type: ignore[attr-defined]
                    if not chunk:
                        continue
                    if not started:
                        started = True
                        self._active_label = label
                        self._active_model = effective_model
                        if name != "ollama":
                            self._mark_provider_verified(name)
                        if errors and label != ENGINE_LABEL:
                            changed_model = effective_model != model if model else False
                            model_note = f" using `{effective_model}`" if changed_model else ""
                            self.last_handoff = (
                                f"⚡ Earlier provider unavailable — answered by **{label}**{model_note}.\n\n"
                            )
                            yield self.last_handoff
                    yield chunk
                if not started:
                    raise OllamaError(f"{label} returned an empty response.")
                return
            except OllamaError as exc:
                if name != "ollama":
                    await self._mark_provider_failed(name, str(exc))
                if started:
                    # Visible partial output cannot be replayed safely.
                    raise CloudProviderError(f"{label} failed after starting its response: {exc}") from exc
                if provider is not None:
                    raise
                errors.append(f"{label}: {exc}")

        if provider is not None:
            raise OllamaError(await self.unavailable_message(provider))
        detail = "; ".join(errors)[:400]
        raise OllamaError(
            "No verified AI provider could answer. Check that Ollama has an installed model "
            "or configure and verify a cloud provider in Settings → AI Providers. "
            + (f"Details: {detail}" if detail else "")
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
