"""Pydantic DTOs — every request validated before it touches the engine (audit SEC4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- REST: conversations -----------------------------------------------------

class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    language: Literal["auto", "hi", "hinglish", "en"] = "auto"


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    pinned: bool | None = None
    folder: str | None = Field(default=None, max_length=120)
    language: Literal["auto", "hi", "hinglish", "en"] | None = None
    model: str | None = Field(default=None, max_length=120)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    plugins: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    pinned: bool
    folder: str | None
    language: str
    model: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


# --- REST: long-term memory ----------------------------------------------------

class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    kind: Literal["note", "preference", "project", "task"] = "note"


class MemoryOut(BaseModel):
    id: int
    kind: str
    content: str
    created_at: datetime


# --- REST: health/models --------------------------------------------------------

class HealthOut(BaseModel):
    status: str
    ollama_available: bool
    default_model: str
    assistant: str


# --- WebSocket payloads ----------------------------------------------------------

class WSUserMessage(BaseModel):
    type: Literal["user_message"]
    content: str = Field(min_length=1)
    conversation_id: str | None = None
    client_id: str | None = None
    model: str | None = None
    language: Literal["auto", "hi", "hinglish", "en"] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class WSCancel(BaseModel):
    type: Literal["cancel"]


class WSPing(BaseModel):
    type: Literal["ping"]
