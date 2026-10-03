"""Pydantic DTOs — every request is validated before reaching the engine."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    language: Literal["auto", "hi", "hinglish", "en"] = "auto"


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    pinned: bool | None = None
    folder: str | None = Field(default=None, max_length=120)
    language: Literal["auto", "hi", "hinglish", "en"] | None = None
    model: str | None = Field(default=None, max_length=200)


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


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    kind: Literal["note", "preference", "project", "task"] = "note"


class MemoryOut(BaseModel):
    id: int
    kind: str
    content: str
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    provider: str = "unavailable"
    default_model: str
    assistant: str
    creator: str = "Abhinav Singh"
    backend_online: bool = True
    chat_available: bool = False
    provider_configured: bool = False
    provider_verified: bool = False
    model_available: bool = False
    active_provider: str | None = None


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


class WSUserMessage(BaseModel):
    type: Literal["user_message"]
    content: str = Field(min_length=1)
    conversation_id: str | None = None
    client_id: str | None = None
    model: str | None = Field(default=None, max_length=200)
    provider: Literal["gemini", "groq"] | None = None
    language: Literal["auto", "hi", "hinglish", "en"] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    attachments: list[str] = Field(default_factory=list, max_length=5)
    internet: bool = False
    multi_agent: bool = False


class WSCancel(BaseModel):
    type: Literal["cancel"]


class WSPing(BaseModel):
    type: Literal["ping"]


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


class EmailOTPRequestIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class EmailOTPVerifyIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    code: str = Field(min_length=6, max_length=6)
    remember: bool = True


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


class ProviderKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=512)
    model: str | None = Field(default=None, max_length=200)


class ProviderToggleIn(BaseModel):
    enabled: bool


class PriorityIn(BaseModel):
    order: list[str] = Field(min_length=1, max_length=8)


class ModelValidateIn(BaseModel):
    model_id: str = Field(min_length=1, max_length=200)
    task: Literal[
        "text", "vision", "document_input", "audio_input", "audio_output", "image_generation", "video", "tools",
    ] = "text"


class ModeChoiceIn(BaseModel):
    mode: Literal["cloud"]
