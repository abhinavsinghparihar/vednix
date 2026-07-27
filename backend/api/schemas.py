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
    attachments: list[dict] | None = None
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
    provider: str = "ollama"
    ollama_available: bool
    default_model: str
    assistant: str
    creator: str = "Abhinav Singh"


# --- REST: uploads & knowledge (Phase 4) -----------------------------------------

class UploadOut(BaseModel):
    id: str
    name: str
    kind: str
    mime: str
    size: int
    extracted_chars: int
    created_at: datetime


class KnowledgeDocOut(BaseModel):
    id: str
    title: str
    chunk_count: int
    uploaded_file_id: str | None
    created_at: datetime


# --- WebSocket payloads ----------------------------------------------------------

class WSUserMessage(BaseModel):
    type: Literal["user_message"]
    content: str = Field(min_length=1)
    conversation_id: str | None = None
    client_id: str | None = None
    model: str | None = None
    language: Literal["auto", "hi", "hinglish", "en"] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    attachments: list[str] = Field(default_factory=list, max_length=5)  # uploaded file ids
    internet: bool = False  # Phase 5: run web research (SearXNG) before the LLM turn
    multi_agent: bool = False  # Phase 6: planner→researcher→critic loop (implies web research)


class WSCancel(BaseModel):
    type: Literal["cancel"]


class WSPing(BaseModel):
    type: Literal["ping"]


# --- REST: auth (Phase 7: onboarding + accounts) ------------------------------

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=120)
    email: str | None = Field(default=None, max_length=255)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember: bool = False
    device_label: str = Field(default="", max_length=160)


class ProfileUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    avatar_color: str | None = Field(default=None, max_length=16)
    theme: Literal["system", "dark", "light"] | None = None
    language: Literal["auto", "hi", "hinglish", "en"] | None = None


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    email: str | None
    role: str
    avatar_color: str
    theme: str
    language: str
    created_at: datetime


class SessionOut(BaseModel):
    id: str
    device_label: str
    remember: bool
    current: bool
    last_seen_at: datetime
    created_at: datetime


# --- REST: AI providers (Phase 7) ----------------------------------------------

class ProviderKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=512)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=160)


class ProviderToggleIn(BaseModel):
    enabled: bool


class PriorityIn(BaseModel):
    order: list[str] = Field(min_length=1, max_length=16)


# --- REST: onboarding (Phase 7) --------------------------------------------------

class ModeChoiceIn(BaseModel):
    mode: Literal["free", "cloud", "demo"]


class DemoToggleIn(BaseModel):
    active: bool
