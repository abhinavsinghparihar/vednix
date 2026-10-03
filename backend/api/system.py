"""Workspace system status — storage, runtime and validated provider state."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from api.deps import get_core, get_memory
from services.providers import REGISTRY

router = APIRouter(tags=["system"])


@router.get("/system/identity")
async def creator_identity(core=Depends(get_core)) -> dict:
    """Public creator facts sourced from server configuration, never memory."""
    settings = core.settings
    return {
        "product": settings.assistant_name,
        "creator": settings.creator_name,
        "github_username": settings.creator_github_username,
        "linkedin_url": settings.creator_linkedin_url or None,
    }


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError:
        pass
    return total


def _db_path(database_url: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    return Path(database_url[len(prefix):]) if database_url.startswith(prefix) else None


@router.get("/research/status")
async def research_status(core=Depends(get_core)) -> dict:
    """Live check for the configured search backend; no LLM/model calls."""
    research = core.research
    if research is None:
        return {"available": False, "detail": "Search is not configured on this server."}
    available = await research.check_available()
    return {
        "available": available,
        "detail": "" if available else "The search service is not reachable or returned no results.",
    }


@router.get("/system/status")
async def system_status(request: Request, core=Depends(get_core), memory=Depends(get_memory)) -> dict:
    settings = core.settings
    db_path = _db_path(settings.database_url)
    db_bytes = 0
    if db_path and db_path.exists():
        db_bytes = db_path.stat().st_size + sum(
            path.stat().st_size for path in (
                db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm")
            ) if path.exists()
        )
    try:
        load1 = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        load1 = None

    if hasattr(core.llm, "status_snapshot"):
        provider_state = await core.llm.status_snapshot()
    else:
        try:
            ready = await core.llm.is_available()
        except Exception:
            ready = False
        provider_state = {
            "backend_online": True,
            "chat_available": ready,
            "provider_configured": ready,
            "provider_verified": ready,
            "model_available": ready,
            "providers": [],
            "active_provider": None,
            "active_model": getattr(core.llm, "model", ""),
        }
    return {
        "db_bytes": db_bytes,
        "uploads_bytes": _dir_size(Path(settings.upload_dir)),
        "counts": await memory.stats(),
        "cpu": {"cores": os.cpu_count() or 0, "load1": load1},
        "backend_online": bool(provider_state.get("backend_online", True)),
        "chat_available": bool(provider_state.get("chat_available", False)),
        "provider_configured": bool(provider_state.get("provider_configured", False)),
        "provider_verified": bool(provider_state.get("provider_verified", False)),
        "model_available": bool(provider_state.get("model_available", False)),
        "providers": provider_state.get("providers", []),
        "active_provider": provider_state.get("active_provider", "unavailable"),
        "active_provider_label": REGISTRY.get(provider_state.get("active_provider"), None).label
        if provider_state.get("active_provider") in REGISTRY else "unavailable",
        "default_model": provider_state.get("active_model", ""),
    }
