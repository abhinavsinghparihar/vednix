"""Onboarding routes — first-run state, mode choice, demo gate, and static
product data the wizard shows (recommended local models with honest
RAM/disk/speed/quality figures — the user's hardware does the choosing)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_core, get_onboarding, get_users
from api.schemas import DemoToggleIn, ModeChoiceIn
from services.onboarding import OnboardingService

router = APIRouter(tags=["onboarding"])

# Honest hardware math (q4_K_M-ish quantization): disk ≈ params × 0.6GB,
# comfortable RAM ≈ disk + ~2GB working set. Speed/quality are qualitative
# ladder positions, not benchmark cosplay.
RECOMMENDED_MODELS = [
    {"tag": "qwen2.5:3b", "tier": "Tiny", "best_for": "Fast · lightweight",
     "ram_gb": 4, "disk_gb": 2, "speed": "Very fast", "quality": "Good",
     "pull": "ollama pull qwen2.5:3b"},
    {"tag": "qwen2.5:7b", "tier": "Balanced", "best_for": "Recommended for most",
     "ram_gb": 8, "disk_gb": 5, "speed": "Fast", "quality": "Great",
     "pull": "ollama pull qwen2.5:7b"},
    {"tag": "deepseek-coder-v2:lite", "tier": "Coding", "best_for": "Code generation & review",
     "ram_gb": 12, "disk_gb": 9, "speed": "Fast", "quality": "Great at code",
     "pull": "ollama pull deepseek-coder-v2:lite"},
    {"tag": "qwen2.5:14b", "tier": "Reasoning", "best_for": "Deeper answers",
     "ram_gb": 16, "disk_gb": 9, "speed": "Medium", "quality": "Excellent",
     "pull": "ollama pull qwen2.5:14b"},
    {"tag": "llama3.1:8b", "tier": "Llama", "best_for": "Meta's all-rounder",
     "ram_gb": 8, "disk_gb": 5, "speed": "Fast", "quality": "Great",
     "pull": "ollama pull llama3.1:8b"},
    {"tag": "gemma3:4b", "tier": "Gemma", "best_for": "Google's efficient small",
     "ram_gb": 6, "disk_gb": 3, "speed": "Very fast", "quality": "Good",
     "pull": "ollama pull gemma3:4b"},
    {"tag": "mistral:7b", "tier": "Mistral", "best_for": "Classic open favorite",
     "ram_gb": 8, "disk_gb": 4, "speed": "Fast", "quality": "Great",
     "pull": "ollama pull mistral:7b"},
]


@router.get("/status")
async def status(onboarding: OnboardingService = Depends(get_onboarding),
                 users=Depends(get_users), core=Depends(get_core)) -> dict:
    """Everything the wizard and the route guard need in ONE call."""
    state = await onboarding.status()
    ollama_running = await core.llm.is_available()
    active = getattr(core.llm, "active_label", "Ollama")
    return {
        **state,
        "auth_enabled": await users.auth_enabled(),
        "ollama_running": ollama_running,
        "active_provider": active,
    }


@router.post("/mode")
async def choose_mode(body: ModeChoiceIn,
                      onboarding: OnboardingService = Depends(get_onboarding)) -> dict:
    return await onboarding.choose_mode(body.mode)


@router.post("/complete")
async def complete(onboarding: OnboardingService = Depends(get_onboarding)) -> dict:
    return await onboarding.complete()


@router.post("/demo")
async def demo(body: DemoToggleIn,
               onboarding: OnboardingService = Depends(get_onboarding)) -> dict:
    return await onboarding.reset_demo(body.active)


@router.get("/local-models")
async def local_models() -> dict:
    return {"models": RECOMMENDED_MODELS}
