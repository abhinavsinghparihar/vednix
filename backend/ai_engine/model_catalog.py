"""Curated model ids whose documented operation is text generation.

Gemini's `/models` endpoint also lists audio, music, embedding and live models.
Those names are not interchangeable with a text chat-completions model, so the
provider adapter intersects the live list with this text-chat allowlist.
"""

GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"

# Stable Gemini API models that support text input and text output. Live model
# discovery further narrows this list to models available to the configured key.
GEMINI_TEXT_MODELS: tuple[str, ...] = (
    GEMINI_DEFAULT_MODEL,
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)


def normalize_gemini_model(model: str) -> str:
    """Google's model-list API may prefix ids with `models/`; chat uses bare ids."""
    value = model.strip()
    return value.removeprefix("models/")
