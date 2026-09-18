"""
Persistence models.

The original only had `MemoryItem` (and it was never used — audit D1). Vednix
adds the missing core of any real chat product: persisted Conversations and
Messages (audit B7: closing the app used to erase everything).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    folder: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="auto")  # auto|hi|hinglish|en
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)  # per-chat model override
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    plugins: Mapped[str | None] = mapped_column(String(200), nullable=True)  # csv of plugin names
    attachments: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of attachment refs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conv_created", "conversation_id", "created_at"),)


class UploadedFile(Base):
    """A file the user dropped into Vednix (chat attachment or KB source)."""

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(24))  # document|sheet|slides|image|text|other
    size: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(500))  # absolute path of stored blob
    text_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # extracted text cache
    extracted_chars: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    uploaded_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class MemoryItem(Base):
    """Long-term memory — the original's table, finally reachable (audit D1)."""

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24), default="note")  # note|preference|project|task
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class User(Base):
    """Local account. Vednix runs open (single-user, no login) until the FIRST
    account is registered — from that moment the API locks to sessions, which
    is exactly the OS lock-screen semantic the product sells. Passwords are
    PBKDF2 digests (core/tokens.hash_password), never reversible."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # optional, local-first
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="owner")  # owner|member — role-ready
    avatar_color: Mapped[str] = mapped_column(String(16), default="gold")  # monogram chip tint
    theme: Mapped[str] = mapped_column(String(16), default="system")  # system|dark|light
    language: Mapped[str] = mapped_column(String(16), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class EmailOTP(Base):
    """One-time email login challenge. Only a digest is persisted."""
    __tablename__ = "email_otps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), index=True)
    code_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuthSession(Base):
    """A signed-in device. Stores only the refresh-token DIGEST — a db leak
    yields nothing replayable. Revocation = one row flip (Security → devices)."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_label: Mapped[str] = mapped_column(String(160), default="This device")
    remember: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class ProviderKey(Base):
    """A cloud AI provider configuration row. `key_ciphertext` is Fernet
    (core/crypto.KeyVault) — plaintext NEVER touches the db, logs, or any
    API response. `key_hint` is the only client-visible echo (`…a1b2`)."""

    __tablename__ = "provider_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # registry id
    key_ciphertext: Mapped[str] = mapped_column(Text)  # "" for key-less rows (custom local)
    key_hint: Mapped[str] = mapped_column(String(12), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    base_url_override: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_override: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="unverified")  # connected|failed|unverified
    status_detail: Mapped[str] = mapped_column(String(300), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AppSetting(Base):
    """Tiny typed key-value table for app-level state that is data, not
    config: onboarding completion, run mode (free|cloud|demo), provider
    priority order, demo-mode flag. Server-owned, survives restarts."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
