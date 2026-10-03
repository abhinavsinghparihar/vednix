"""Provider-neutral model metadata and task capability filtering.

Provider catalogs are candidate inputs only. ``chat``, ``streaming``, vision,
and tool capabilities become true only after the corresponding live request
has succeeded through the exact adapter path used by Vednix.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ModelTask = Literal[
    "text", "vision", "document_input", "audio_input", "audio_output",
    "image_generation", "video", "tools",
]


@dataclass(frozen=True)
class ModelCapabilities:
    # ``text`` is retained as a provider-metadata/backwards-compatibility field.
    # Chat and streaming are separate verified requirements for the Chat UI.
    text: bool = False
    chat: bool = False
    streaming: bool = False
    vision: bool = False
    imageInput: bool = False
    documentInput: bool = False
    tools: bool = False
    toolCalling: bool = False
    structuredOutput: bool = False
    reasoning: bool = False
    audioInput: bool = False
    audioOutput: bool = False
    imageGeneration: bool = False
    video: bool = False

    def supports(self, task: ModelTask) -> bool:
        chat_stream = self.text and self.chat and self.streaming
        if task == "text":
            return chat_stream
        if task == "vision":
            return chat_stream and self.vision and self.imageInput
        if task == "document_input":
            # Vednix extracts safe text from supported documents before sending
            # it as ordinary text; this is not a claim of native PDF ingestion.
            return chat_stream and self.documentInput
        if task == "audio_input":
            return self.audioInput
        if task == "audio_output":
            return self.audioOutput
        if task == "image_generation":
            return self.imageGeneration
        if task == "video":
            return self.video
        if task == "tools":
            return chat_stream and self.tools and self.toolCalling
        return False


@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider: str
    displayName: str
    capabilities: ModelCapabilities
    contextWindow: int | None = None
    maxOutputTokens: int | None = None
    available: bool = False
    reason: str | None = None
    latencyMs: float | None = None
    checkedCapabilities: tuple[str, ...] = ()

    def public(self) -> dict:
        value = asdict(self)
        value["checkedCapabilities"] = list(self.checkedCapabilities)
        return value


def normalize_gemini_model(model: str) -> str:
    """Normalize the resource-name prefix returned by the official Gemini API."""
    return model.strip().removeprefix("models/")
