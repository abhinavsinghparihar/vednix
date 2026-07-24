"""
Document → plain-text extractors (Phase 4). The chatbot brief's readers:
PDF · Word · Excel · CSV · PowerPoint · text/code — one uniform interface.

Design: pure functions `extract(path) -> str`, registered by kind. Runs in a
thread (`asyncio.to_thread` at call sites) so a 200-page PDF never stalls the
event loop (audit BL-grade discipline). Extractors fail with ExtractionError
carrying a user-safe reason; raw tracebacks go to the log.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.logging import get_logger

logger = get_logger(__name__)


class ExtractionError(RuntimeError):
    pass


# --- text / code / markdown ----------------------------------------------------

def _extract_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ExtractionError(f"Could not read the file: {exc}") from exc


# --- CSV ------------------------------------------------------------------------

def _extract_csv(path: Path) -> str:
    rows: list[str] = []
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.reader(handle)
            for i, row in enumerate(reader):
                if i >= 500:
                    rows.append(f"… ({i}+ rows truncated)")
                    break
                rows.append(" | ".join(cell.strip() for cell in row))
    except csv.Error as exc:
        raise ExtractionError(f"Could not parse the CSV: {exc}") from exc
    return "\n".join(rows)


# --- XLSX ------------------------------------------------------------------------

def _extract_xlsx(path: Path) -> str:
    try:
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        parts: list[str] = []
        for sheet in workbook.worksheets[:5]:
            parts.append(f"## Sheet: {sheet.title}")
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i >= 300:
                    parts.append("… (rows truncated)")
                    break
                cells = ["" if c is None else str(c) for c in row]
                if any(cells):
                    parts.append(" | ".join(cells))
        workbook.close()
        return "\n".join(parts)
    except Exception as exc:
        raise ExtractionError(f"Could not parse the spreadsheet: {exc}") from exc


# --- DOCX ------------------------------------------------------------------------

def _extract_docx(path: Path) -> str:
    try:
        import docx

        document = docx.Document(path)
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(parts)
    except Exception as exc:
        raise ExtractionError(f"Could not parse the Word document: {exc}") from exc


# --- PPTX ------------------------------------------------------------------------

def _extract_pptx(path: Path) -> str:
    try:
        from pptx import Presentation

        deck = Presentation(path)
        parts: list[str] = []
        for i, slide in enumerate(deck.slides, 1):
            texts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame and (t := shape.text_frame.text.strip()):
                    texts.append(t)
            if texts:
                parts.append(f"## Slide {i}\n" + "\n".join(texts))
        return "\n\n".join(parts)
    except Exception as exc:
        raise ExtractionError(f"Could not parse the presentation: {exc}") from exc


# --- PDF --------------------------------------------------------------------------

def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for i, page in enumerate(reader.pages[:60], 1):
            try:
                text = page.extract_text() or ""
            except Exception:  # corrupt page — skip, don't lose the document
                logger.warning("pdf page %d of %s failed to extract", i, path.name)
                continue
            if text.strip():
                parts.append(text.strip())
        if not parts:
            raise ExtractionError(
                "No readable text found — this PDF is probably scanned images. "
                "Attach it as an image (or convert pages) and use a vision model."
            )
        return "\n\n".join(parts)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not parse the PDF: {exc}") from exc


EXTRACTORS = {
    "text": _extract_text,
    "sheet": _extract_xlsx,
    "document": _extract_docx,
    "slides": _extract_pptx,
}


def extract_text(path: Path, kind: str, filename: str) -> str:
    """Dispatch by kind with extension-aware refinement (csv vs xlsx, pdf vs docx)."""
    if kind == "image":
        raise ExtractionError("Images are analyzed by a vision model — there is no text layer.")
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".csv":
        return _extract_csv(path)
    extractor = EXTRACTORS.get(kind, _extract_text)
    return extractor(path)
