"""Shared FastAPI dependencies — single source of app-level services."""

from __future__ import annotations

from fastapi import Request

from ai_engine.engine import EngineCore
from core.rate_limit import RateLimiter
from memory.service import MemoryService


def get_memory(request: Request) -> MemoryService:
    return request.app.state.memory


def get_core(request: Request) -> EngineCore:
    return request.app.state.core


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter
