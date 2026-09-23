"""AI provider routes — catalog (public registry data), configured keys
(hints only, NEVER ciphertext), verify (real network proof), enable/disable,
priority order, and Ollama's live status for the setup wizard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_core, get_providers
from api.schemas import PriorityIn, ProviderKeyIn, ProviderToggleIn
from services.providers import ProviderService, provider_catalog

router = APIRouter(tags=["providers"])


@router.get("/catalog")
async def catalog(core=Depends(get_core)) -> dict:
    """Setup-wizard data: public provider and text-model metadata only."""
    return {"providers": provider_catalog(core.settings)}


@router.get("")
async def configured(providers: ProviderService = Depends(get_providers)) -> dict:
    priority = await providers.get_priority()
    return {"providers": await providers.list_configured(), "priority": priority}


@router.put("/{provider}/key", status_code=200)
async def upsert(provider: str, body: ProviderKeyIn,
                 providers: ProviderService = Depends(get_providers)) -> dict:
    """Store (or rotate) a key. Request body carries it ONCE; the response
    carries only the fingerprint. Plaintext retention time: microseconds."""
    try:
        return await providers.upsert_key(
            provider, api_key=body.api_key, base_url=body.base_url, model=body.model
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{provider}/key", status_code=204)
async def remove(provider: str, providers: ProviderService = Depends(get_providers)) -> None:
    ok = await providers.remove_key(provider)
    if not ok:
        raise HTTPException(status_code=404, detail="Nothing stored for this provider.")


@router.post("/{provider}/verify")
async def verify(provider: str, providers: ProviderService = Depends(get_providers),
                 core=Depends(get_core)) -> dict:
    """The green-check moment in the wizard: a real, timed API round-trip."""
    try:
        return await providers.verify(provider, settings=core.settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{provider}/toggle")
async def toggle(provider: str, body: ProviderToggleIn,
                 providers: ProviderService = Depends(get_providers)) -> dict:
    try:
        ok = await providers.set_enabled(provider, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Provider is not configured.")
    return {"ok": True, "enabled": body.enabled}


@router.put("/priority")
async def priority(body: PriorityIn, providers: ProviderService = Depends(get_providers)) -> dict:
    return {"priority": await providers.set_priority(body.order)}


@router.get("/ollama/status")
async def ollama_status(providers: ProviderService = Depends(get_providers),
                        core=Depends(get_core)) -> dict:
    """The wizard's auto-detector: is Ollama serving, and what's installed."""
    result = await providers.verify("ollama", settings=core.settings)
    return {
        "running": bool(result["running"]),
        "models": result["models"],
        "default_model": result["verification_model"],
        "model_available": result["model_available"],
        "chat_available": result["model_available"],
        "detail": result["detail"],
    }
