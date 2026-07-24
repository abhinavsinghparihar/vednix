"""Liveness/readiness + model discovery (feeds the frontend model selector)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ai_engine.ollama_client import OllamaError
from api.deps import get_core
from ai_engine.engine import EngineCore
from api.schemas import HealthOut

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
async def health(request: Request, core: EngineCore = Depends(get_core)) -> HealthOut:
    return HealthOut(
        status="ok",
        provider=core.settings.llm_provider,
        ollama_available=await core.llm.is_available(),
        default_model=core.llm.model,
        assistant=core.settings.assistant_name,
    )


@router.get("/models")
async def models(core: EngineCore = Depends(get_core)) -> dict:
    try:
        available = await core.llm.list_models()
    except OllamaError:
        available = []
    return {"default": core.llm.model, "available": available}
