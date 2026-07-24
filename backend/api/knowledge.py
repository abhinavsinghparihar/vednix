"""Knowledge base endpoints (Phase 4): index uploads/pasted text, search, manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.schemas import KnowledgeDocOut
from config import Settings
from memory.models import KnowledgeDocument
from services.file_store import FileStore
from services.knowledge import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class AddKnowledgeBody(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    uploaded_file_id: str | None = None
    text: str | None = Field(default=None, max_length=400_000)


def _out(doc: KnowledgeDocument) -> KnowledgeDocOut:
    return KnowledgeDocOut(
        id=doc.id, title=doc.title, chunk_count=doc.chunk_count,
        uploaded_file_id=doc.uploaded_file_id, created_at=doc.created_at,
    )


def get_knowledge(request: Request) -> KnowledgeService:
    return request.app.state.knowledge


def get_files(request: Request) -> FileStore:
    return request.app.state.files


def get_settings_from_state(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/documents", response_model=KnowledgeDocOut, status_code=201)
async def add_document(
    body: AddKnowledgeBody,
    knowledge: KnowledgeService = Depends(get_knowledge),
    files: FileStore = Depends(get_files),
    settings: Settings = Depends(get_settings_from_state),
) -> KnowledgeDocOut:
    title = (body.title or "").strip()
    if body.uploaded_file_id:
        record = await files.get(body.uploaded_file_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Upload not found")
        content = await files.read_text(record.id)
        if not content:
            raise HTTPException(
                status_code=422,
                detail=f"No readable text in '{record.name}' — images and scanned PDFs can't join the text knowledge base.",
            )
        title = title or record.name
        doc = await knowledge.add_document(
            title, content, uploaded_file_id=record.id,
            chunk_chars=settings.kb_chunk_chars, overlap=settings.kb_chunk_overlap,
        )
        return _out(doc)
    if body.text and body.text.strip():
        if not title:
            raise HTTPException(status_code=422, detail="A title is required for pasted text.")
        doc = await knowledge.add_document(
            title, body.text, chunk_chars=settings.kb_chunk_chars, overlap=settings.kb_chunk_overlap
        )
        return _out(doc)
    raise HTTPException(status_code=422, detail="Provide either uploaded_file_id or text.")


@router.get("/documents", response_model=list[KnowledgeDocOut])
async def list_documents(knowledge: KnowledgeService = Depends(get_knowledge)) -> list[KnowledgeDocOut]:
    return [_out(d) for d in await knowledge.list_documents()]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, knowledge: KnowledgeService = Depends(get_knowledge)) -> None:
    if not await knowledge.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")


@router.get("/search")
async def search_knowledge(q: str, knowledge: KnowledgeService = Depends(get_knowledge)) -> dict:
    hits = await knowledge.search(q)
    return {"query": q, "hits": [
        {"document": h.title, "chunk_id": h.chunk_id, "snippet": h.snippet, "score": h.score} for h in hits
    ]}
