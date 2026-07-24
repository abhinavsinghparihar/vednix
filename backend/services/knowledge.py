"""
Knowledge base (Phase 4): documents → chunks → FTS5 full-text retrieval, with
the retrieval injected into chat turns as cited context.

Why FTS5 and not a vector DB here: SQLite FTS5 is compiled into CPython's
sqlite3, needs zero services and zero downloads — true to Vednix's offline
creed. The ChromaDB slot stays open behind `KnowledgeService.search()` exactly
as the audit's preservation map planned (same seam, heavier engine later).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging import get_logger
from memory.models import KnowledgeChunk, KnowledgeDocument

logger = get_logger(__name__)

_WORD_RE = re.compile(r"\s+")


def chunk_text(content: str, chunk_chars: int = 900, overlap: int = 150) -> list[str]:
    """Sliding-window chunks on paragraph/whitespace boundaries."""
    content = _WORD_RE.sub(" ", content).strip()
    if not content:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(len(content), start + chunk_chars)
        if end < len(content):  # walk back to a word boundary
            boundary = content.rfind(" ", start + overlap, end)
            if boundary > start:
                end = boundary
        chunks.append(content[start:end].strip())
        start = end - overlap if end < len(content) else end
    return [c for c in chunks if c]


@dataclass
class SearchHit:
    chunk_id: int
    document_id: str
    title: str
    snippet: str
    score: float = 0.0


class KnowledgeService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, fts_enabled: bool = True) -> None:
        self._sessions = session_factory
        self.fts_enabled = fts_enabled

    async def add_document(self, title: str, content: str, *, uploaded_file_id: str | None = None,
                           chunk_chars: int = 900, overlap: int = 150) -> KnowledgeDocument:
        chunks = chunk_text(content, chunk_chars, overlap)
        doc = KnowledgeDocument(title=title, uploaded_file_id=uploaded_file_id, chunk_count=len(chunks))
        async with self._sessions() as session:
            session.add(doc)
            await session.flush()  # doc.id available
            for idx, body in enumerate(chunks):
                session.add(KnowledgeChunk(document_id=doc.id, idx=idx, content=body))
            await session.commit()
            if self.fts_enabled and chunks:
                rows = await self._fetch_chunk_ids(session, doc.id)
                async with self._sessions() as fts_session:
                    for chunk_id, body in rows:
                        await fts_session.execute(
                            text("INSERT INTO kb_fts(chunk_id, content) VALUES (:cid, :body)"),
                            {"cid": chunk_id, "body": body},
                        )
                    await fts_session.commit()
            # no refresh(): doc is fully populated post-commit (expire_on_commit=False)
            return doc

    async def _fetch_chunk_ids(self, session: AsyncSession, doc_id: str) -> list[tuple[int, str]]:
        rows = (await session.execute(
            select(KnowledgeChunk.id, KnowledgeChunk.content).where(KnowledgeChunk.document_id == doc_id)
        )).all()
        return [(int(r[0]), str(r[1])) for r in rows]

    async def list_documents(self, limit: int = 100) -> list[KnowledgeDocument]:
        async with self._sessions() as session:
            stmt = select(KnowledgeDocument).order_by(desc(KnowledgeDocument.created_at)).limit(limit)
            return list((await session.scalars(stmt)).all())

    async def delete_document(self, doc_id: str) -> bool:
        async with self._sessions() as session:
            ids = [int(r[0]) for r in (await session.execute(
                select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == doc_id)
            )).all()]
            if self.fts_enabled and ids:
                await session.execute(
                    text(f"DELETE FROM kb_fts WHERE chunk_id IN ({','.join(str(i) for i in ids)})")
                )
            result = await session.execute(
                delete(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def search(self, query: str, *, limit: int = 4) -> list[SearchHit]:
        """FTS5 first; LIKE fallback keeps search alive on sqlite builds w/o FTS5."""
        query = query.strip()
        if not query:
            return []
        if self.fts_enabled:
            try:
                return await self._search_fts(query, limit)
            except Exception:
                logger.exception("FTS5 search failed; falling back to LIKE")
        return await self._search_like(query, limit)

    async def _search_fts(self, query: str, limit: int) -> list[SearchHit]:
        # build a safe FTS5 query: word chars (Unicode-aware, keeps Devanagari)
        # joined by AND; anything that could break MATCH syntax is stripped
        raw_terms = re.split(r"\s+", query)
        terms = [t for t in (re.sub(r"[^\w\u0900-\u097F-]", "", r, flags=re.UNICODE) for r in raw_terms) if t][:6]
        if not terms:
            return []
        # OR semantics + bm25 ranking: chunks matching MORE terms rank higher —
        # the right default for natural-language retrieval questions
        fts_query = " OR ".join(f'"{t}"' for t in terms)
        sql = text(
            """
            SELECT k.id AS chunk_id, k.document_id, d.title,
                   snippet(kb_fts, 1, '«', '»', ' … ', 18) AS snippet,
                   bm25(kb_fts) AS score
            FROM kb_fts
            JOIN knowledge_chunks k ON k.id = kb_fts.chunk_id
            JOIN knowledge_documents d ON d.id = k.document_id
            WHERE kb_fts MATCH :q
            ORDER BY score
            LIMIT :limit
            """
        )
        async with self._sessions() as session:
            rows = (await session.execute(sql, {"q": fts_query, "limit": limit})).all()
        return [SearchHit(chunk_id=r[0], document_id=r[1], title=r[2], snippet=r[3], score=float(r[4])) for r in rows]

    async def _search_like(self, query: str, limit: int) -> list[SearchHit]:
        async with self._sessions() as session:
            stmt = (
                select(KnowledgeChunk, KnowledgeDocument.title)
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(KnowledgeChunk.content.ilike(f"%{query}%"))
                .order_by(desc(KnowledgeChunk.id))
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
        hits = []
        for chunk, title in rows:
            pos = chunk.content.lower().find(query.lower())
            start = max(0, pos - 60) if pos >= 0 else 0
            hits.append(SearchHit(
                chunk_id=chunk.id, document_id=chunk.document_id, title=title,
                snippet=chunk.content[start:start + 220].strip(),
            ))
        return hits
