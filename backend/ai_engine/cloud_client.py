"""Cloud LLM clients — drop-in implementations of the engine's LLMClient
Protocol (the same contract OllamaClient has honored since the rewrite):

    model · is_available() · chat() · chat_stream() · list_models_cached() · aclose()

Two wire shapes cover the whole provider registry:
  * OpenAI-compatible  — /chat/completions + SSE (OpenRouter, Gemini, Groq,
    OpenAI, Mistral, Together, Fireworks, and any custom/compatible endpoint
    like LM Studio or vLLM).
  * Anthropic          — /v1/messages with its own event stream.

Error honesty: every transport/API failure raises CloudProviderError, which
IS-A OllamaError — the engine's single `except OllamaError` path therefore
keeps working verbatim ("reply hit an error and was not saved"), no matter
which provider was active.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from ai_engine.ollama_client import OllamaError
from core.logging import get_logger

logger = get_logger(__name__)


class CloudProviderError(OllamaError):
    """Provider-flavored OllamaError (engine catch path stays unchanged)."""


def _sse_lines() -> str:
    return "event-stream"


class _BaseCloudClient:
    """Shared mechanics: owned httpx client, model cache, vision passthrough."""

    kind = "base"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str,
        provider_name: str,
        timeout: float = 300.0,
        health_ttl: float = 10.0,
        static_models: list[str] | None = None,
        vision: bool = False,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self._timeout = timeout
        self._health_ttl = health_ttl
        self._static_models = list(static_models or [])
        self._vision = vision
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=8.0),
            headers=default_headers or {},
        )
        self._healthy_until = 0.0
        self._healthy = False

    async def aclose(self) -> None:
        await self._client.aclose()

    def supports_images(self, model: str | None = None) -> bool:
        return self._vision

    # --- health / models -----------------------------------------------------

    async def _models_request(self) -> httpx.Response:
        raise NotImplementedError

    async def is_available(self) -> bool:
        if time.monotonic() < self._healthy_until:
            return self._healthy
        try:
            resp = await self._models_request()
            self._healthy = resp.status_code < 500  # 401 still means "reachable"
        except httpx.HTTPError:
            self._healthy = False
        self._healthy_until = time.monotonic() + self._health_ttl
        return self._healthy

    async def list_models(self) -> list[str]:
        try:
            resp = await self._models_request()
            if resp.status_code in (401, 403):
                raise CloudProviderError(f"{self.provider_name}: API key rejected (401/403).")
            resp.raise_for_status()
            return self._parse_models(resp.json())
        except CloudProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise CloudProviderError(f"Could not reach {self.provider_name}: {exc}") from exc

    def _parse_models(self, data: Any) -> list[str]:
        return []

    async def list_models_cached(self, ttl: float = 120.0) -> list[str]:
        now = time.monotonic()
        if now < getattr(self, "_models_until", 0.0):
            return getattr(self, "_models_cache", self._static_models)
        try:
            models = await self.list_models()
        except CloudProviderError:
            models = []
        if not models:
            models = self._static_models  # key pending/quota/limited listing — defaults still work
        self._models_cache = models
        self._models_until = now + ttl
        return models


class OpenAICompatibleClient(_BaseCloudClient):
    """OpenAI / OpenRouter / Gemini(OpenAI-mode) / Groq / Mistral / Together /
    Fireworks / custom compatible endpoints."""

    kind = "openai"

    def __init__(self, api_key: str, model: str, **kw: Any) -> None:
        super().__init__(api_key, model, **kw)
        self._client.headers["Authorization"] = f"Bearer {api_key}"
        # OpenRouter ranking headers are harmless elsewhere
        self._client.headers["X-Title"] = "Vednix AI"

    async def _models_request(self) -> httpx.Response:
        return await self._client.get("/models")

    def _parse_models(self, data: Any) -> list[str]:
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted(i.get("id", "") for i in items if i.get("id"))

    # --- payloads ------------------------------------------------------------

    def _payload(self, messages: list[dict], temperature: float, model: str | None,
                 stream: bool, images: list[str] | None) -> dict[str, Any]:
        if images and self._vision:
            messages = [dict(m) for m in messages]
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    text = messages[i].get("content", "")
                    messages[i]["content"] = [
                        {"type": "text", "text": text},
                        *({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                          for b64 in images),
                    ]
                    break
        return {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

    async def chat(self, messages: list[dict], temperature: float, *,
                   model: str | None = None, images: list[str] | None = None) -> str:
        try:
            resp = await self._client.post(
                "/chat/completions",
                json=self._payload(messages, temperature, model, False, images),
            )
            if resp.status_code in (401, 403):
                raise CloudProviderError(f"{self.provider_name}: API key rejected.")
            resp.raise_for_status()
            data = resp.json()
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            raise CloudProviderError(f"Could not reach {self.provider_name}: {exc}") from exc
        except ValueError as exc:
            raise CloudProviderError(f"{self.provider_name} returned invalid JSON: {exc}") from exc
        if err := (data.get("error") or {}):
            if isinstance(err, dict) and err.get("message"):
                raise CloudProviderError(str(err["message"]))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")

    async def chat_stream(self, messages: list[dict], temperature: float, *,
                          model: str | None = None, images: list[str] | None = None) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST", "/chat/completions",
                json=self._payload(messages, temperature, model, True, images),
            ) as resp:
                if resp.status_code in (401, 403):
                    raise CloudProviderError(f"{self.provider_name}: API key rejected.")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if err := chunk.get("error"):
                        raise CloudProviderError(str(err.get("message", err)))
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            raise CloudProviderError(f"Could not reach {self.provider_name}: {exc}") from exc


class AnthropicClient(_BaseCloudClient):
    """Claude via /v1/messages (its own SSE shape: content_block_delta events)."""

    kind = "anthropic"

    def __init__(self, api_key: str, model: str, **kw: Any) -> None:
        super().__init__(api_key, model, **kw)
        self._client.headers["x-api-key"] = api_key
        self._client.headers["anthropic-version"] = "2023-06-01"

    async def _models_request(self) -> httpx.Response:
        return await self._client.get("/v1/models")

    def _parse_models(self, data: Any) -> list[str]:
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted(i.get("id", "") for i in items if i.get("id"))

    def _payload(self, messages: list[dict], temperature: float, model: str | None,
                 stream: bool, images: list[str] | None) -> dict[str, Any]:
        system = ""
        rest: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                system = (system + "\n\n" + m.get("content", "")).strip()
            else:
                rest.append(dict(m))
        if images and self._vision:
            for i in range(len(rest) - 1, -1, -1):
                if rest[i].get("role") == "user":
                    text = rest[i].get("content", "")
                    rest[i]["content"] = [
                        *({"type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": b64}}
                          for b64 in images),
                        {"type": "text", "text": text},
                    ]
                    break
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": rest,
            "max_tokens": 4096,
            "temperature": temperature,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        return payload

    async def chat(self, messages: list[dict], temperature: float, *,
                   model: str | None = None, images: list[str] | None = None) -> str:
        try:
            resp = await self._client.post(
                "/v1/messages", json=self._payload(messages, temperature, model, False, images)
            )
            if resp.status_code in (401, 403):
                raise CloudProviderError("Anthropic: API key rejected.")
            resp.raise_for_status()
            data = resp.json()
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            raise CloudProviderError(f"Could not reach Anthropic: {exc}") from exc
        except ValueError as exc:
            raise CloudProviderError(f"Anthropic returned invalid JSON: {exc}") from exc
        if data.get("type") == "error":
            raise CloudProviderError(str(data.get("error", {}).get("message", "Anthropic error")))
        blocks = data.get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    async def chat_stream(self, messages: list[dict], temperature: float, *,
                          model: str | None = None, images: list[str] | None = None) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST", "/v1/messages",
                json=self._payload(messages, temperature, model, True, images),
            ) as resp:
                if resp.status_code in (401, 403):
                    raise CloudProviderError("Anthropic: API key rejected.")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    try:
                        chunk = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    ctype = chunk.get("type")
                    if ctype == "content_block_delta":
                        text = chunk.get("delta", {}).get("text")
                        if text:
                            yield text
                    elif ctype == "message_stop":
                        return
                    elif ctype == "error":
                        raise CloudProviderError(str(chunk.get("error", {}).get("message", "Anthropic error")))
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            raise CloudProviderError(f"Could not reach Anthropic: {exc}") from exc
