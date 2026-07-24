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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conv_created", "conversation_id", "created_at"),)


class MemoryItem(Base):
    """Long-term memory — the original's table, finally reachable (audit D1)."""

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24), default="note")  # note|preference|project|task
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
