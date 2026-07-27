"""System status — the Profile page's hardware/memory cards. Every number is
read live from the machine: the db on disk, the uploads dir, SQL counts,
real CPU facts, and Ollama's /api/ps for VRAM residency."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from api.deps import get_core, get_memory
from api.schemas import OllamaDefaultModelIn
from api.deps import get_providers
from services.providers import ResilientLLM

router = APIRouter(tags=["system"])


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
    if database_url.startswith(prefix):
        return Path(database_url[len(prefix):])
    return None


@router.get("/system/status")
async def system_status(request: Request, core=Depends(get_core), memory=Depends(get_memory)) -> dict:
    settings = core.settings
    db_path = _db_path(settings.database_url)
    db_bytes = 0
    if db_path and db_path.exists():
        # include WAL — it's live data not yet checkpointed into the main file
        db_bytes = db_path.stat().st_size + sum(
            p.stat().st_size for p in (db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm")) if p.exists()
        )
    try:
        load1 = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        load1 = None  # Windows has no getloadavg

    running: list[dict] = []
    if hasattr(core.llm, "ollama_ps"):
        running = await core.llm.ollama_ps()
    return {
        "db_bytes": db_bytes,
        "uploads_bytes": _dir_size(Path(settings.upload_dir)),
        "counts": await memory.stats(),
        "cpu": {"cores": os.cpu_count() or 0, "load1": load1},
        "ollama": {
            "running": await core.llm.is_available(),
            "models_running": running,
            "host": settings.ollama_host,
        },
        "active_provider": getattr(core.llm, "active_label", settings.llm_provider),
        "default_model": core.llm.model,
    }


@router.get("/providers/ollama/default-model")
async def get_default_model(core=Depends(get_core), providers=Depends(get_providers)) -> dict:
    saved = await providers.get_ollama_default()
    return {"model": saved or core.llm.model, "saved": bool(saved)}


@router.put("/providers/ollama/default-model")
async def set_default_model(body: OllamaDefaultModelIn, core=Depends(get_core),
                            providers=Depends(get_providers)) -> dict:
    """Persist + live-apply the wizard's model selection."""
    model = await providers.set_ollama_default(body.model)
    if isinstance(core.llm, ResilientLLM):
        core.llm.apply_ollama_default_now(model)
    return {"model": model, "saved": True}
