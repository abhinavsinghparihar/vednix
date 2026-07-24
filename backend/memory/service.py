"""
MemoryService — async data access for conversations, messages and long-term
memory. Long-term methods keep the original class's exact API (audit ♻️S4):
remember / search / all / forget — so any original caller ports 1:1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from memory.models import Conversation, MemoryItem, Message

DEFAULT_TITLE = "New chat"


class MemoryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    # --- conversations -----------------------------------------------------

    async def create_conversation(self, *, title: str = DEFAULT_TITLE, language: str = "auto") -> Conversation:
        async with self._sessions() as session:
            conv = Conversation(title=title, language=language)
            session.add(conv)
            await session.commit()
            # no refresh(): expire_on_commit=False and every field has a client-side
            # default, so the instance is fully populated; refresh was a redundant
            # SELECT that could only fail post-commit.
            return conv

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        async with self._sessions() as session:
            return await session.get(Conversation, conversation_id)

    async def list_conversations(self, *, limit: int = 200) -> Sequence[Conversation]:
        async with self._sessions() as session:
            stmt = (
                select(Conversation)
                .order_by(desc(Conversation.pinned), desc(Conversation.updated_at))
                .limit(limit)
            )
            return (await session.scalars(stmt)).all()

    async def update_conversation(self, conversation_id: str, **fields) -> Conversation | None:
        allowed = {"title", "pinned", "folder", "language", "model"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        async with self._sessions() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None:
                return None
            for key, value in updates.items():
                setattr(conv, key, value)
            conv.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return conv

    async def delete_conversation(self, conversation_id: str) -> bool:
        async with self._sessions() as session:
            result = await session.execute(
                delete(Conversation).where(Conversation.id == conversation_id)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def touch(self, conversation_id: str) -> None:
        async with self._sessions() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is not None:
                conv.updated_at = datetime.now(timezone.utc)
                await session.commit()

    async def message_count(self, conversation_id: str) -> int:
        async with self._sessions() as session:
            stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            return int((await session.scalar(stmt)) or 0)

    # --- messages ------------------------------------------------------------

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        plugins: str | None = None,
        attachments: str | None = None,
    ) -> Message:
        async with self._sessions() as session:
            msg = Message(
                conversation_id=conversation_id, role=role, content=content,
                plugins=plugins, attachments=attachments,
            )
            session.add(msg)
            conv = await session.get(Conversation, conversation_id)
            if conv is not None:
                conv.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return msg

    async def recent_history(self, conversation_id: str, *, max_turns: int) -> list[dict]:
        """Last N messages as Ollama-format dicts (chronological)."""
        async with self._sessions() as session:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(desc(Message.created_at))
                .limit(max_turns)
            )
            rows = list((await session.scalars(stmt)).all())
        rows.reverse()
        return [{"role": m.role, "content": m.content} for m in rows]

    async def list_messages(self, conversation_id: str, *, limit: int = 500) -> Sequence[Message]:
        async with self._sessions() as session:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
                .limit(limit)
            )
            return (await session.scalars(stmt)).all()

    # --- long-term memory (original API, async, finally used — audit D1) ----

    async def remember(self, content: str, kind: str = "note") -> int:
        async with self._sessions() as session:
            item = MemoryItem(kind=kind, content=content)
            session.add(item)
            await session.commit()
            # autoincrement PK is populated at INSERT (cursor.lastrowid); no refresh needed
            return item.id

    async def search(self, query: str, kind: str | None = None, limit: int = 10) -> list[MemoryItem]:
        stmt = select(MemoryItem).where(MemoryItem.content.ilike(f"%{query}%"))
        if kind:
            stmt = stmt.where(MemoryItem.kind == kind)
        stmt = stmt.order_by(desc(MemoryItem.created_at)).limit(limit)
        async with self._sessions() as session:
            return list((await session.scalars(stmt)).all())

    async def all(self, kind: str | None = None, limit: int = 100) -> list[MemoryItem]:
        stmt = select(MemoryItem)
        if kind:
            stmt = stmt.where(MemoryItem.kind == kind)
        stmt = stmt.order_by(desc(MemoryItem.created_at)).limit(limit)
        async with self._sessions() as session:
            return list((await session.scalars(stmt)).all())

    async def forget(self, item_id: int) -> bool:
        async with self._sessions() as session:
            result = await session.execute(delete(MemoryItem).where(MemoryItem.id == item_id))
            await session.commit()
            return (result.rowcount or 0) > 0

    async def get(self, item_id: int) -> MemoryItem | None:
        async with self._sessions() as session:
            return await session.get(MemoryItem, item_id)
