"""Liveness/readiness and operation-safe model discovery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ai_engine.engine import EngineCore
from ai_engine.ollama_client import OllamaError
from api.deps import get_core
from api.schemas import HealthOut

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
async def health(core: EngineCore = Depends(get_core)) -> HealthOut:
    """Backend liveness is separate from local Ollama and chat readiness."""
    if hasattr(core.llm, "status_snapshot"):
        state = await core.llm.status_snapshot()
        ollama = state.get("ollama", {})
        return HealthOut(
            status="ok",
            provider=getattr(core.llm, "active_label", state.get("active_provider", "unavailable")),
            ollama_available=bool(ollama.get("running", False)),
            default_model=str(state.get("active_model") or core.llm.model),
            assistant=core.settings.assistant_name,
            creator=core.settings.creator_name,
            backend_online=True,
            chat_available=bool(state.get("chat_available", False)),
            provider_configured=bool(state.get("provider_configured", False)),
            provider_verified=bool(state.get("provider_verified", False)),
            model_available=bool(state.get("model_available", False)),
            active_provider=state.get("active_provider"),
        )

    # Lightweight compatibility for injected test/stub clients implementing
    # the original LLM protocol rather than the production provider router.
    try:
        ollama_available = await core.llm.is_available()
    except Exception:
        ollama_available = False
    try:
        available = await core.llm.list_models_cached()
    except Exception:
        available = []
    model_available = core.llm.model in available
    return HealthOut(
        status="ok", provider=getattr(core.llm, "active_label", core.settings.llm_provider),
        ollama_available=ollama_available, default_model=core.llm.model,
        assistant=core.settings.assistant_name, creator=core.settings.creator_name,
        backend_online=True, chat_available=bool(ollama_available and model_available),
        provider_configured=True, provider_verified=ollama_available,
        model_available=model_available, active_provider=None,
    )


@router.get("/models")
async def models(provider: str | None = Query(default=None), core: EngineCore = Depends(get_core)) -> dict:
    """List models available for the requested provider's text-chat operation."""
    if hasattr(core.llm, "model_catalog"):
        return await core.llm.model_catalog(provider)
    try:
        available = await core.llm.list_models(provider=provider) if provider else await core.llm.list_models()
        default = core.llm.model if core.llm.model in available else (available[0] if available else core.llm.model)
        return {
            "provider": provider, "default": default, "available": available,
            "configured": True, "verified": await core.llm.is_available(),
            "model_available": default in available,
            "chat_available": await core.llm.is_available(), "error": None,
        }
    except (OllamaError, TypeError) as exc:
        return {
            "provider": provider, "default": core.llm.model, "available": [],
            "configured": False, "verified": False, "model_available": False,
            "chat_available": False, "error": str(exc),
        }
