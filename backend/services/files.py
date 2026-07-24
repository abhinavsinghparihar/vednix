"""
File-kind detection + bounded reads for the upload pipeline (Phase 4).
"""

from __future__ import annotations

from config import Settings

#: extension → logical kind (drives extraction strategy + UI chips)
KIND_BY_EXT: dict[str, str] = {
    ".pdf": "document", ".docx": "document", ".doc": "document",
    ".txt": "text", ".md": "text", ".csv": "sheet",
    ".xlsx": "sheet", ".xls": "sheet",
    ".pptx": "slides", ".ppt": "slides",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image", ".bmp": "image",
    ".json": "text", ".py": "text", ".js": "text", ".ts": "text", ".tsx": "text",
    ".html": "text", ".css": "text", ".sql": "text", ".log": "text", ".yaml": "text", ".yml": "text",
}

SUPPORTED_EXTENSIONS = frozenset(KIND_BY_EXT)


def detect_kind(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return KIND_BY_EXT.get(ext, "unsupported")


def file_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_upload(filename: str, size: int, settings: Settings) -> None:
    """Raise ValueError with a user-facing reason before a byte is stored."""
    if size <= 0:
        raise ValueError("The file is empty.")
    if size > settings.upload_max_mb * 1024 * 1024:
        raise ValueError(f"'{filename}' is larger than {settings.upload_max_mb} MB.")
    if detect_kind(filename) == "unsupported":
        raise ValueError(
            f"'{filename}' uses an unsupported type. Supported: PDF, DOCX, TXT/MD/code, "
            "CSV, XLSX, PPTX, PNG/JPG/WebP/GIF/BMP."
        )
