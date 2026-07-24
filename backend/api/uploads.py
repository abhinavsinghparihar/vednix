"""Upload + extraction endpoints. Validate early, store once, extract on arrival."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from api.schemas import UploadOut
from core.rate_limit import RateLimiter
from api.deps import get_rate_limiter
from memory.models import UploadedFile as UploadedFileRow
from services.file_store import FileStore

router = APIRouter(prefix="/uploads", tags=["uploads"])

MAX_BATCH = 5


def _get_store(request: Request) -> FileStore:
    return request.app.state.files


def _out(row: UploadedFileRow) -> UploadOut:
    return UploadOut(
        id=row.id, name=row.name, kind=row.kind, mime=row.mime, size=row.size,
        extracted_chars=row.extracted_chars, created_at=row.created_at,
    )


@router.post("", response_model=list[UploadOut], status_code=201)
async def upload_files(
    request: Request,
    files: list[UploadFile],
    store: FileStore = Depends(_get_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> list[UploadOut]:
    if request.client and not await limiter.allow(f"upload:{request.client.host}"):
        raise HTTPException(status_code=429, detail="Too many uploads — slow down.")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"Max {MAX_BATCH} files per batch.")

    saved: list[UploadOut] = []
    for file in files:
        data = await file.read()
        try:
            row = await store.save(file.filename or "unnamed", file.content_type or "application/octet-stream", data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        saved.append(_out(row))
    return saved


@router.get("/{file_id}", response_model=UploadOut)
async def get_upload(file_id: str, store: FileStore = Depends(_get_store)) -> UploadOut:
    row = await store.get(file_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return _out(row)


@router.get("/{file_id}/text")
async def get_upload_text(file_id: str, store: FileStore = Depends(_get_store)) -> dict:
    """Extraction preview (useful for debugging 'what did Vednix actually read?')."""
    row = await store.get(file_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    text = await store.read_text(file_id)
    return {"id": row.id, "name": row.name, "chars": len(text or ""), "text": text or ""}
