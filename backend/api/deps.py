"""Shared FastAPI dependencies — single source of app-level services."""

from __future__ import annotations

from fastapi import HTTPException, Request

from ai_engine.engine import EngineCore
from core.rate_limit import RateLimiter
from memory.service import MemoryService
from services.onboarding import OnboardingService
from services.providers import ProviderService
from services.users import UserService


def get_memory(request: Request) -> MemoryService:
    return request.app.state.memory


def get_core(request: Request) -> EngineCore:
    return request.app.state.core


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_auth_limiter(request: Request) -> RateLimiter:
    """Dedicated tight bucket for credential endpoints (brute-force surface)."""
    return request.app.state.auth_rate_limiter


def get_users(request: Request) -> UserService:
    return request.app.state.users


def get_providers(request: Request) -> ProviderService:
    return request.app.state.providers


def get_onboarding(request: Request) -> OnboardingService:
    return request.app.state.onboarding


def current_user(request: Request) -> dict:
    """JWT claims stamped by SessionMiddleware (403s itself when the API is
    in open mode but a route still asks — open-mode routes must not ask)."""
    claims = getattr(request.state, "user", None) or request.scope.get("state_user")
    if claims is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return claims
