"""Liveness/readiness and capability-validated model discovery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ai_engine.engine import EngineCore
from ai_engine.provider_error import ProviderError
from api.deps import get_core, get_providers
from api.schemas import HealthOut
from services.providers import REGISTRY, ProviderService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
async def health(
    core: EngineCore = Depends(get_core),
    providers: ProviderService = Depends(get_providers),
) -> HealthOut:
    """Cheap readiness based on persisted verification; no model fan-out probes."""
    if hasattr(core.llm, "status_snapshot"):
        state = await core.llm.status_snapshot()
        active_id = state.get("active_provider")
        active = REGISTRY.get(active_id)
        return HealthOut(
            status="ok",
            provider=active.label if active else "unavailable",
            default_model=str(state.get("active_model") or ""),
            assistant=core.settings.assistant_name,
            creator=core.settings.creator_name,
            backend_online=True,
            chat_available=bool(state.get("chat_available", False)),
            provider_configured=bool(state.get("provider_configured", False)),
            provider_verified=bool(state.get("provider_verified", False)),
            model_available=bool(state.get("model_available", False)),
            active_provider=active_id,
        )
    try:
        available = await core.llm.is_available()
    except Exception:
        available = False
    return HealthOut(
        status="ok", provider=getattr(core.llm, "active_label", "unavailable"),
        default_model=str(getattr(core.llm, "model", "")),
        assistant=core.settings.assistant_name, creator=core.settings.creator_name,
        backend_online=True, chat_available=available, provider_configured=available,
        provider_verified=available, model_available=available,
        active_provider=None,
    )


@router.get("/models")
async def models(
    provider: str | None = Query(default=None),
    task: str = Query(default="text"),
    force: bool = Query(default=False),
    core: EngineCore = Depends(get_core),
    providers: ProviderService = Depends(get_providers),
) -> dict:
    """List only live-discovered models that passed the requested task probe."""
    if provider:
        targets = [provider]
    else:
        configured = await providers.list_configured()
        enabled = {row["provider"] for row in configured if row["enabled"] and row["verified"]}
        targets = [item for item in await providers.get_priority() if item in enabled]

    failures: list[str] = []
    for target in targets:
        try:
            result = await providers.model_catalog(
                target, settings=core.settings, task=task, force=force,
            )
        except ProviderError as exc:
            failures.append(exc.message)
            if provider:
                raise HTTPException(status_code=exc.http_status or 502, detail=exc.message) from exc
            continue
        except ValueError as exc:
            failures.append(str(exc))
            if provider:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            continue
        row = await providers._row(target)
        preferred = row.model_override if row else None
        default = preferred if preferred in result["available"] else (
            result["available"][0] if result["available"] else ""
        )
        result.update({
            "default": default,
            "configured": True,
            "verified": bool(row and row.verified_at and row.status == "connected"),
            "enabled": bool(row and row.enabled),
            "model_available": bool(default),
            "chat_available": bool(default and row and row.enabled and row.status == "connected"),
            "error": None if result["available"] else f"No validated {task.replace('_', ' ')} models are available from {REGISTRY[target].label}.",
        })
        if provider or result["available"]:
            return result

    return {
        "provider": provider,
        "task": task,
        "models": [],
        "available": [],
        "default": "",
        "vision_available": [],
        "configured": bool(targets),
        "verified": False,
        "enabled": False,
        "model_available": False,
        "chat_available": False,
        "verified_only": True,
        "error": failures[-1] if failures else "No verified provider has a model available for this task.",
    }
