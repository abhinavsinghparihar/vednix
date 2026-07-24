"""
Async Ollama client.

♻️ PRESERVED INTERFACE from dev_ai/core/llm.py — same class name, same chat() /
chat_stream() contract — so the original's swap-ability promise holds: any
provider with this interface drops in (OpenRouter lands behind it in Phase 5).

Hardening over the original:
  - requests + raw threads  →  one shared httpx.AsyncClient (keep-alive, audit P3)
  - synchronous generator   →  async generator (kills audit BL1/BL3)
  - Ollama {"error": ...} frames now RAISE instead of vanishing (audit B8)
  - malformed NDJSON lines logged, not silently dropped (audit B8)
  - health probe cached for N seconds (audit P2: startup blocked the UI 2s)
  - model selectable per call (model selector support)
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from core.logging import get_logger

logger = get_logger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str,
        model: str,
        *,
        timeout: float = 300.0,
        health_ttl: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self._timeout = timeout
        self._health_ttl = health_ttl
        self._client = client or httpx.AsyncClient(
            base_url=self.host, timeout=httpx.Timeout(timeout, connect=3.0)
        )
        self._owns_client = client is None
        self._healthy_until = 0.0
        self._healthy = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- health ------------------------------------------------------------

    async def is_available(self) -> bool:
        if time.monotonic() < self._healthy_until:
            return self._healthy
        try:
            resp = await self._client.get("/api/tags")
            self._healthy = resp.status_code == 200
        except httpx.HTTPError:
            self._healthy = False
        self._healthy_until = time.monotonic() + self._health_ttl
        return self._healthy

    async def list_models(self) -> list[str]:
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return sorted(m.get("name", "") for m in models if m.get("name"))
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Could not list models at {self.host}: {exc}") from exc

    # --- chat --------------------------------------------------------------

    def _payload(self, messages: list[dict], temperature: float, model: str | None, stream: bool) -> dict[str, Any]:
        return {
            "model": model or self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature},
        }

    async def chat(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
    ) -> str:
        """Non-streaming call. Returns full response text. (Original interface.)"""
        try:
            resp = await self._client.post(
                "/api/chat", json=self._payload(messages, temperature, model, stream=False)
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Could not reach Ollama at {self.host}: {exc}") from exc
        except ValueError as exc:
            raise OllamaError(f"Ollama returned invalid JSON: {exc}") from exc
        if error := data.get("error"):
            raise OllamaError(str(error))
        return data.get("message", {}).get("content", "")

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Streaming call. Yields text chunks as they arrive. (Original interface.)

        Raises OllamaError on transport errors AND on Ollama error frames —
        the original silently dropped both (audit B8).
        """
        try:
            async with self._client.stream(
                "POST", "/api/chat", json=self._payload(messages, temperature, model, stream=True)
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("dropping malformed Ollama NDJSON line: %.120s", line)
                        continue
                    if error := chunk.get("error"):
                        raise OllamaError(str(error))
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        return
        except httpx.HTTPError as exc:
            raise OllamaError(f"Could not reach Ollama at {self.host}: {exc}") from exc
