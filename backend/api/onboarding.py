"""First-run account and provider onboarding."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_core, get_memory, get_onboarding, get_providers, get_users
from api.schemas import ModeChoiceIn
from services.onboarding import OnboardingService
from services.providers import REGISTRY, ProviderService

router = APIRouter(tags=["onboarding"])


@router.get("/status")
async def status(
    onboarding: OnboardingService = Depends(get_onboarding),
    users=Depends(get_users),
    providers: ProviderService = Depends(get_providers),
    core=Depends(get_core),
) -> dict:
    result = await onboarding.status()
    rows = await providers.list_configured()
    snapshot = await core.llm.status_snapshot() if hasattr(core.llm, "status_snapshot") else {}
    active_id = snapshot.get("active_provider")
    return {
        **result,
        "auth_enabled": await users.auth_enabled(),
        "providers": rows,
        "active_provider": REGISTRY[active_id].label if active_id in REGISTRY else "unavailable",
        "chat_available": bool(snapshot.get("chat_available", False)),
    }


@router.post("/mode")
async def choose_mode(
    body: ModeChoiceIn,
    onboarding: OnboardingService = Depends(get_onboarding),
) -> dict:
    try:
        return await onboarding.choose_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/complete")
async def complete(onboarding: OnboardingService = Depends(get_onboarding)) -> dict:
    return await onboarding.complete()


@router.post("/wipe-data")
async def wipe_data(memory=Depends(get_memory)) -> dict:
    """Delete conversations and long-term memories; leave uploaded user files intact."""
    return await memory.wipe_chats_and_memories()
