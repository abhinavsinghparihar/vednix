"""Long-term memory API — searchable, manageable from the UI's Memory panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_memory
from api.schemas import MemoryCreate, MemoryOut
from memory.models import MemoryItem
from memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


def _out(item: MemoryItem) -> MemoryOut:
    return MemoryOut(id=item.id, kind=item.kind, content=item.content, created_at=item.created_at)


@router.get("", response_model=list[MemoryOut])
async def search_memory(
    query: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    memory: MemoryService = Depends(get_memory),
) -> list[MemoryOut]:
    items = await memory.search(query, kind=kind, limit=limit) if query else await memory.all(kind=kind, limit=limit)
    return [_out(i) for i in items]


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(body: MemoryCreate, memory: MemoryService = Depends(get_memory)) -> MemoryOut:
    item_id = await memory.remember(body.content, kind=body.kind)
    item = await memory.get(item_id)
    if item is None:  # pragma: no cover — parent transaction committed above
        raise HTTPException(status_code=500, detail="Memory write failed")
    return _out(item)


@router.delete("/{item_id}", status_code=204)
async def delete_memory(item_id: int, memory: MemoryService = Depends(get_memory)) -> None:
    if not await memory.forget(item_id):
        raise HTTPException(status_code=404, detail="Memory item not found")
