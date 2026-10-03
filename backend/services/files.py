"""
File-kind detection + bounded reads for the upload pipeline (Phase 4).
"""

from __future__ import annotations

import io
import warnings
import zipfile

from config import Settings

#: extension → logical kind (drives extraction strategy + UI chips)
KIND_BY_EXT: dict[str, str] = {
    ".pdf": "document", ".docx": "document",
    ".txt": "text", ".md": "text", ".csv": "sheet",
    ".xlsx": "sheet",
    ".pptx": "slides",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image", ".bmp": "image",
    ".json": "text", ".py": "text", ".js": "text", ".ts": "text", ".tsx": "text",
    ".html": "text", ".css": "text", ".sql": "text", ".log": "text", ".yaml": "text", ".yml": "text",
}

SUPPORTED_EXTENSIONS = frozenset(KIND_BY_EXT)
MIME_BY_EXT: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
}
IMAGE_FORMAT_BY_EXT = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG",
    ".webp": "WEBP", ".gif": "GIF", ".bmp": "BMP",
}
MAX_IMAGE_PIXELS = 20_000_000
VISION_MAX_EDGE = 2048
MAX_OFFICE_ENTRIES = 2_048
MAX_OFFICE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_OFFICE_MEMBER_BYTES = 25 * 1024 * 1024
MAX_OFFICE_COMPRESSION_RATIO = 300
OFFICE_REQUIRED_PARTS = {
    ".docx": {"[Content_Types].xml", "word/document.xml"},
    ".xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
    ".pptx": {"[Content_Types].xml", "ppt/presentation.xml"},
}


def _validated_image(data: bytes, expected_format: str | None = None) -> None:
    """Decode image headers safely and reject format spoofing and pixel bombs."""
    from PIL import Image

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if expected_format and image.format != expected_format:
                    raise ValueError("The file extension does not match its decoded image format.")
                if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("The image dimensions exceed Vednix's safe processing limit.")
                image.verify()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The image is corrupt, unsupported, or too large to process safely.") from exc


def normalize_image_for_vision(data: bytes) -> bytes:
    """Decode and downscale an image to a compact, orientation-correct JPEG."""
    from PIL import Image, ImageOps

    _validated_image(data)
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)  # animated formats use their first frame
            image = ImageOps.exif_transpose(source)
            image.thumbnail((VISION_MAX_EDGE, VISION_MAX_EDGE), Image.Resampling.LANCZOS)
            if "A" in image.getbands() or image.info.get("transparency") is not None:
                rgba = image.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = image.convert("RGB")
            output = io.BytesIO()
            rgb.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
            return output.getvalue()
    except Exception as exc:
        raise ValueError("The image could not be normalized for the verified vision provider.") from exc


def _validate_office_archive(filename: str, data: bytes) -> None:
    ext = file_extension(filename)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if not OFFICE_REQUIRED_PARTS[ext].issubset(names):
                raise ValueError("The file is not a valid Office Open XML document.")
            if len(entries) > MAX_OFFICE_ENTRIES:
                raise ValueError("The document contains too many internal components.")
            total = 0
            for entry in entries:
                if entry.file_size > MAX_OFFICE_MEMBER_BYTES:
                    raise ValueError("A document component exceeds the safe extraction limit.")
                total += entry.file_size
                if total > MAX_OFFICE_UNCOMPRESSED_BYTES:
                    raise ValueError("The document expands beyond the safe extraction limit.")
                if entry.file_size and (
                    entry.compress_size == 0
                    or entry.file_size / entry.compress_size > MAX_OFFICE_COMPRESSION_RATIO
                ):
                    raise ValueError("The document has a suspicious compression ratio.")
    except ValueError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("The file is not a valid Office Open XML document.") from exc


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


def validate_upload_content(filename: str, size: int, data: bytes, settings: Settings) -> None:
    """Validate extension, size, and basic file signatures before writing data."""
    validate_upload(filename, size, settings)
    ext = file_extension(filename)
    signatures = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".webp": len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        ".gif": data.startswith((b"GIF87a", b"GIF89a")),
        ".bmp": data.startswith(b"BM"),
        ".pdf": data.lstrip().startswith(b"%PDF-"),
    }
    if ext in signatures and not signatures[ext]:
        raise ValueError(f"'{filename}' does not contain a valid {ext[1:].upper()} file.")
    if ext in IMAGE_FORMAT_BY_EXT:
        try:
            _validated_image(data, IMAGE_FORMAT_BY_EXT[ext])
        except ValueError as exc:
            raise ValueError(f"'{filename}' is not a valid image: {exc}") from exc
    if ext in OFFICE_REQUIRED_PARTS:
        try:
            _validate_office_archive(filename, data)
        except ValueError as exc:
            raise ValueError(f"'{filename}' is not a safe Office Open XML document: {exc}") from exc
