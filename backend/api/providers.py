"""Provider setup, encrypted-key management, live model discovery and checks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ai_engine.provider_error import ProviderError
from api.deps import get_core, get_providers
from api.schemas import ModelValidateIn, PriorityIn, ProviderKeyIn, ProviderToggleIn
from services.providers import ProviderService, provider_catalog

router = APIRouter(tags=["providers"])


def _provider_http_error(exc: ProviderError) -> HTTPException:
    status = exc.http_status or (401 if exc.authentication_error else 502)
    return HTTPException(status_code=status, detail=exc.message)


@router.get("/catalog")
async def catalog() -> dict:
    """Small product/provider metadata; models are never hardcoded here."""
    return {"providers": provider_catalog()}


@router.get("")
async def configured(providers: ProviderService = Depends(get_providers)) -> dict:
    return {
        "providers": await providers.list_configured(),
        "priority": await providers.get_priority(),
    }


@router.put("/{provider}/key", status_code=200)
async def upsert(
    provider: str,
    body: ProviderKeyIn,
    providers: ProviderService = Depends(get_providers),
) -> dict:
    """Encrypt a key and return only its hint/status — never the key itself."""
    try:
        return await providers.upsert_key(provider, api_key=body.api_key, model=body.model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{provider}/key", status_code=204)
async def remove(provider: str, providers: ProviderService = Depends(get_providers)) -> None:
    if not await providers.remove_key(provider):
        raise HTTPException(status_code=404, detail="Nothing is stored for this provider.")


@router.post("/{provider}/verify")
async def verify(
    provider: str,
    providers: ProviderService = Depends(get_providers),
    core=Depends(get_core),
) -> dict:
    try:
        return await providers.verify(provider, settings=core.settings)
    except ProviderError as exc:
        raise _provider_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{provider}/models")
async def models(
    provider: str,
    task: str = Query(default="text"),
    force: bool = Query(default=False),
    providers: ProviderService = Depends(get_providers),
    core=Depends(get_core),
) -> dict:
    """Fetch the provider's live list and return only models validated for task."""
    try:
        return await providers.model_catalog(
            provider, settings=core.settings, task=task, force=force,
        )
    except ProviderError as exc:
        raise _provider_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{provider}/models/validate")
async def validate_model(
    provider: str,
    body: ModelValidateIn,
    providers: ProviderService = Depends(get_providers),
    core=Depends(get_core),
) -> dict:
    try:
        info = await providers.validate_model(
            provider, body.model_id, settings=core.settings, task=body.task, force=True,
        )
        return info.public()
    except ProviderError as exc:
        raise _provider_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{provider}/toggle")
async def toggle(
    provider: str,
    body: ProviderToggleIn,
    providers: ProviderService = Depends(get_providers),
) -> dict:
    try:
        ok = await providers.set_enabled(provider, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Provider is not configured.")
    return {"ok": True, "enabled": body.enabled}


@router.put("/priority")
async def priority(
    body: PriorityIn,
    providers: ProviderService = Depends(get_providers),
) -> dict:
    return {"priority": await providers.set_priority(body.order)}
