"""
Input validation / sanitization helpers (audit SEC4/SEC7).

These run before anything touches the model, a plugin, or the database.
"""

from __future__ import annotations

from config import get_settings


class InputTooLong(ValueError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Message exceeds the {limit}-character limit.")
        self.limit = limit


def validate_user_text(text: object) -> str:
    """Return a clean, safe-to-process user message or raise ValueError.

    Rules: must be a string, non-empty after trimming, within the configured
    length budget. No content censorship — this is a local, user-owned tool.
    """
    if not isinstance(text, str):
        raise ValueError("Message content must be a string.")
    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        raise ValueError("Message is empty.")
    limit = get_settings().max_message_chars
    if len(cleaned) > limit:
        raise InputTooLong(limit)
    return cleaned


def safe_error_message(exc: Exception) -> str:
    """Public-facing error text. Never echo raw exception internals to a client
    (audit SEC7: the old app f-stringed raw exceptions into the UI)."""
    return "Something went wrong on Vednix's side. The technical detail was logged."
