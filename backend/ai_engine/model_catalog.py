"""Provider-neutral model metadata and task capability filtering.

The model identifiers and limits come from each provider's live API. A model
is marked usable only after the server-side adapter validates the operation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ModelTask = Literal[
    "text", "vision", "audio_input", "audio_output", "image_generation", "video", "tools",
]


@dataclass(frozen=True)
class ModelCapabilities:
    text: bool = False
    vision: bool = False
    audioInput: bool = False
    audioOutput: bool = False
    imageGeneration: bool = False
    video: bool = False
    tools: bool = False

    def supports(self, task: ModelTask) -> bool:
        if task == "text":
            return self.text
        if task == "vision":
            return self.text and self.vision
        if task == "audio_input":
            return self.audioInput
        if task == "audio_output":
            return self.audioOutput
        if task == "image_generation":
            return self.imageGeneration
        if task == "video":
            return self.video
        if task == "tools":
            return self.text and self.tools
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
