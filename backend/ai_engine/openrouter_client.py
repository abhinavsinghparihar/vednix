"""OpenRouter provider — drops in behind the *exact* interface the original
dev_ai Ollama client defined (audit ♻️S2): chat() / chat_stream() /
is_available() / list_models() / list_models_cached() / aclose() / .model

Why a whole second client instead of if/else inside OllamaClient: providers
have different wire contracts (NDJSON vs SSE, /api/tags vs /models, per-model
images shape). One client per contract keeps each implementation small and
independently testable; the ENGINE never sees the difference.

Failure doctrine is identical to Ollama's: network/API errors surface as
OllamaError so the engine's single error path (guidance-unpersisted) keeps
working — an OpenRouter outage degrades exactly like an Ollama outage.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from ai_engine.ollama_client import OllamaError
from core.logging import get_logger

logger = get_logger(__name__)


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 300.0,
        health_ttl: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._health_ttl = health_ttl
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}", "X-OpenRouter-Title": "Vednix AI"},
        )
        self._owns_client = client is None
        self._healthy_until = 0.0
        self._healthy = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- health / models -----------------------------------------------------

    async def is_available(self) -> bool:
        if not self.api_key:
            self._healthy = False
            return False
        if time.monotonic() < self._healthy_until:
            return self._healthy
        try:
            resp = await self._client.get("/models")
            self._healthy = resp.status_code == 200
        except httpx.HTTPError:
            self._healthy = False
        self._healthy_until = time.monotonic() + self._health_ttl
        return self._healthy

    async def list_models(self) -> list[str]:
        if not self.api_key:
            raise OllamaError("OpenRouter key missing — set VEDNIX_OPENROUTER_API_KEY.")
        try:
            resp = await self._client.get("/models")
            resp.raise_for_status()
            rows = resp.json().get("data", [])
            return sorted(r.get("id", "") for r in rows if r.get("id"))
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Could not list OpenRouter models: {exc}") from exc

    async def list_models_cached(self, ttl: float = 30.0) -> list[str]:
        now = time.monotonic()
        if now < getattr(self, "_models_until", 0.0):
            return getattr(self, "_models_cache", [])
        try:
            models = await self.list_models()
        except OllamaError:
            models = []
        self._models_cache = models
        self._models_until = now + ttl
        return models

    # --- chat ----------------------------------------------------------------

    def _payload(
        self,
        messages: list[dict],
        temperature: float,
        model: str | None,
        stream: bool,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        if images:
            # OpenAI-compatible vision contract: parts array on the final user message
            messages = [dict(m) for m in messages]
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    parts: list[dict] = [{"type": "text", "text": str(messages[i]["content"])}]
                    parts += [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                        for b64 in images
                    ]
                    messages[i]["content"] = parts
                    break
        return {
            "model": model or self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
        }

    async def chat(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
    ) -> str:
        if not self.api_key:
            raise OllamaError("OpenRouter key missing — set VEDNIX_OPENROUTER_API_KEY.")
        try:
            resp = await self._client.post(
                "/chat/completions", json=self._payload(messages, temperature, model, False, images)
            )
            if resp.status_code != 200:
                raise OllamaError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise OllamaError(f"OpenRouter unreachable at {self.base_url}: {exc}") from exc
        if data.get("error"):
            raise OllamaError(f"OpenRouter error: {data['error']}")
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise OllamaError("Malformed OpenRouter response") from exc

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """SSE: 'data: {…}' lines, terminated by 'data: [DONE]'."""
        if not self.api_key:
            raise OllamaError("OpenRouter key missing — set VEDNIX_OPENROUTER_API_KEY.")
        try:
            async with self._client.stream(
                "POST", "/chat/completions",
                json=self._payload(messages, temperature, model, True, images),
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise OllamaError(f"OpenRouter HTTP {resp.status_code}: {body[:200]}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        data = json.loads(payload)
                    except ValueError:
                        logger.warning("dropping malformed SSE line: %.120s", line)
                        continue
                    if data.get("error"):
                        raise OllamaError(f"OpenRouter stream error: {data['error']}")
                    try:
                        delta = data["choices"][0].get("delta") or {}
                        content = delta.get("content")
                    except (KeyError, IndexError, TypeError):
                        content = None
                    if content:
                        yield str(content)
        except httpx.HTTPError as exc:
            raise OllamaError(f"OpenRouter unreachable at {self.base_url}: {exc}") from exc
