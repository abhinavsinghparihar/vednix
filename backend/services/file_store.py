"""
Upload storage + extraction cache (Phase 4).

Blobs live under data/uploads/<id><ext>; extracted text caches at
data/uploads/<id>.txt so chat turns never re-parse. All parsing runs off the
event loop. Every byte is validated before it hits disk (core/security-grade).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Settings
from core.logging import get_logger
from memory.models import UploadedFile
from services.extractors import ExtractionError, extract_text
from services.files import detect_kind, file_extension, validate_upload

logger = get_logger(__name__)


class FileStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._dir = Path(settings.upload_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, filename: str, mime: str, data: bytes) -> UploadedFile:
        validate_upload(filename, len(data), self._settings)
        kind = detect_kind(filename)

        # id generated here, NOT via the column default: the default only fires at
        # INSERT time, so the blob/text paths below would otherwise be "None.<ext>"
        # and every upload would overwrite the previous one (found on disk).
        record = UploadedFile(
            id=uuid.uuid4().hex, name=filename, mime=mime, kind=kind, size=len(data), path=""
        )
        blob_path = self._dir / f"{record.id}{file_extension(filename)}"
        record.path = str(blob_path)

        await asyncio.to_thread(blob_path.write_bytes, data)

        # text-bearing kinds: extract eagerly, cache, count (images skip)
        if kind not in ("image",):
            try:
                text = await asyncio.to_thread(extract_text, blob_path, kind, filename)
                text_path = self._dir / f"{record.id}.txt"
                await asyncio.to_thread(text_path.write_text, text, "utf-8")
                record.text_path = str(text_path)
                record.extracted_chars = len(text)
            except ExtractionError as exc:
                # not fatal: file stored, chat gets a clear reason instead of content
                logger.warning("extraction failed for %s: %s", filename, exc)

        async with self._sessions() as session:
            session.add(record)
            await session.commit()
            # refresh() deliberately omitted: expire_on_commit=False means every
            # field (client-side id, timestamps) is already loaded — a redundant
            # SELECT is one more way to fail after commit.
            return record

    async def get(self, file_id: str) -> UploadedFile | None:
        async with self._sessions() as session:
            return await session.get(UploadedFile, file_id)

    async def read_text(self, file_id: str) -> str | None:
        record = await self.get(file_id)
        if record is None:
            return None
        if not record.text_path:
            return None
        path = Path(record.text_path)
        if not path.exists():
            return None
        return await asyncio.to_thread(path.read_text, "utf-8")

    async def read_blob_base64(self, file_id: str) -> str | None:
        import base64

        record = await self.get(file_id)
        if record is None:
            return None
        path = Path(record.path)
        if not path.exists():
            return None
        data = await asyncio.to_thread(path.read_bytes)
        return base64.b64encode(data).decode("ascii")

    async def read_all_text(self, file_id: str) -> tuple[UploadedFile, str] | None:
        record = await self.get(file_id)
        if record is None:
            return None
        text = await self.read_text(file_id)
        return (record, text or "")
