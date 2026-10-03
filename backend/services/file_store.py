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
from services.files import MIME_BY_EXT, detect_kind, file_extension, normalize_image_for_vision, validate_upload_content

logger = get_logger(__name__)


def _read_bounded_text(path: Path, max_chars: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(max(0, max_chars) + 1)


class FileStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._dir = Path(settings.upload_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, filename: str, mime: str, data: bytes) -> UploadedFile:
        await asyncio.to_thread(validate_upload_content, filename, len(data), data, self._settings)
        kind = detect_kind(filename)
        mime = MIME_BY_EXT.get(file_extension(filename), mime)

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
                text = await asyncio.to_thread(
                    extract_text, blob_path, kind, filename,
                    max_chars=self._settings.file_context_max_chars,
                )
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
        return await asyncio.to_thread(
            _read_bounded_text, path, self._settings.file_context_max_chars,
        )

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

    async def read_image_data_url(self, file_id: str) -> str | None:
        """Normalize validated uploads to a bounded JPEG for tested provider input."""
        import base64

        record = await self.get(file_id)
        if record is None or record.kind != "image":
            return None
        ext = Path(record.name).suffix.lower()
        path = Path(record.path)
        if ext not in MIME_BY_EXT or not path.is_file():
            return None
        data = await asyncio.to_thread(path.read_bytes)
        jpeg = await asyncio.to_thread(normalize_image_for_vision, data)
        encoded = base64.b64encode(jpeg).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    async def read_all_text(self, file_id: str) -> tuple[UploadedFile, str] | None:
        record = await self.get(file_id)
        if record is None:
            return None
        text = await self.read_text(file_id)
        return (record, text or "")
