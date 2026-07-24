"""Conversation CRUD — the missing core of the original (audit B7/SC2/U3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_memory
from api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from memory.models import Conversation, Message
from memory.service import MemoryService

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _conv_out(c: Conversation) -> ConversationOut:
    return ConversationOut(
        id=c.id, title=c.title, pinned=c.pinned, folder=c.folder, language=c.language,
        model=c.model, created_at=c.created_at, updated_at=c.updated_at,
    )


def _msg_out(m: Message) -> MessageOut:
    return MessageOut(id=m.id, role=m.role, content=m.content, plugins=m.plugins, created_at=m.created_at)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(memory: MemoryService = Depends(get_memory)) -> list[ConversationOut]:
    return [_conv_out(c) for c in await memory.list_conversations()]


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate, memory: MemoryService = Depends(get_memory)
) -> ConversationOut:
    conv = await memory.create_conversation(title=body.title or "New chat", language=body.language)
    return _conv_out(conv)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str, memory: MemoryService = Depends(get_memory)
) -> ConversationDetail:
    conv = await memory.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await memory.list_messages(conversation_id)
    return ConversationDetail(**_conv_out(conv).model_dump(), messages=[_msg_out(m) for m in messages])


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str, body: ConversationUpdate, memory: MemoryService = Depends(get_memory)
) -> ConversationOut:
    conv = await memory.update_conversation(conversation_id, **body.model_dump(exclude_unset=True))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_out(conv)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str, memory: MemoryService = Depends(get_memory)
) -> None:
    if not await memory.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
