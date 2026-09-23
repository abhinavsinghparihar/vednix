"""Cloud LLM clients implementing the same chat interface as Ollama.

OpenAI-compatible providers (including Google's Gemini API) use
``/chat/completions`` + SSE. Anthropic uses ``/v1/messages``. API keys stay in
server-side client headers; errors returned to API callers are sanitized and
never include request headers or secret values.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, AsyncIterator

import httpx

from ai_engine.ollama_client import OllamaError
from core.logging import get_logger

logger = get_logger(__name__)


class CloudProviderError(OllamaError):
    """A safe-to-display provider failure (also an OllamaError for old callers)."""


_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"sk-[0-9A-Za-z_-]{16,}"),
)


def _clean_error(value: object, api_key: str) -> str:
    """Redact credentials even if an upstream error unusually repeats one."""
    text = str(value or "").replace(api_key, "[redacted]") if api_key else str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return " ".join(text.split())[:300]


def _provider_http_error(provider: str, response: httpx.Response, api_key: str) -> CloudProviderError:
    """Convert upstream status/body into a useful message without echoing secrets."""
    status = response.status_code
    if status in (401, 403):
        detail = "API key rejected or missing permission. Check the provider key and access."
    elif status == 429:
        detail = "Provider rate limit or quota reached. Check the provider's quota and billing."
    elif status == 404:
        detail = "Provider endpoint or selected model was not found. Check the configured model."
    elif status == 400:
        message = ""
        try:
            data = response.json()
            error = data.get("error", data) if isinstance(data, dict) else {}
            message = _clean_error(error.get("message", "") if isinstance(error, dict) else error, api_key)
        except (ValueError, AttributeError):
            pass
        detail = message or "Provider rejected the request. Check the selected text model and request settings."
    elif status >= 500:
        detail = "Provider is temporarily unavailable. Try again shortly."
    else:
        detail = f"Provider request failed with HTTP {status}."
    return CloudProviderError(f"{provider}: {detail} (HTTP {status}).")


def _extract_openai_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        )
    return ""


def _canonical_model_id(model: str) -> str:
    """Gemini's model-list response may prefix names with ``models/``."""
    return model.strip().removeprefix("models/")


class _BaseCloudClient:
    """Shared HTTP, model-list and health behavior for cloud providers."""

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
        supported_models: list[str] | None = None,
        vision: bool = False,
        default_headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = _canonical_model_id(model)
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self._timeout = timeout
        self._health_ttl = health_ttl
        self._static_models = [_canonical_model_id(m) for m in (static_models or [])]
        self._supported_models = (
            {_canonical_model_id(m) for m in supported_models}
            if supported_models is not None else None
        )
        self._vision = vision
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=8.0),
            headers=default_headers or {},
        )
        self._owns_client = client is None
        self._healthy_until = 0.0
        self._healthy = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def supports_images(self, model: str | None = None) -> bool:
        return self._vision

    def supports_model(self, model: str | None) -> bool:
        if not model:
            return True
        return self._supported_models is None or _canonical_model_id(model) in self._supported_models

    # --- health / models -----------------------------------------------------

    async def _models_request(self) -> httpx.Response:
        raise NotImplementedError

    async def is_available(self) -> bool:
        """A successful provider response is required; 401 is not 'available'."""
        if time.monotonic() < self._healthy_until:
            return self._healthy
        try:
            response = await self._models_request()
            self._healthy = 200 <= response.status_code < 300
        except httpx.HTTPError:
            self._healthy = False
        self._healthy_until = time.monotonic() + self._health_ttl
        return self._healthy

    async def list_models(self) -> list[str]:
        try:
            response = await self._models_request()
            if not 200 <= response.status_code < 300:
                raise _provider_http_error(self.provider_name, response, self._api_key)
            data = response.json()
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _clean_error(exc, self._api_key)
            raise CloudProviderError(f"Could not reach {self.provider_name}: {reason or 'network error'}.") from exc
        except ValueError as exc:
            raise CloudProviderError(f"{self.provider_name} returned invalid model-list JSON.") from exc

        models = self._parse_models(data)
        # Model endpoints may include embeddings, image, speech, music and
        # realtime ids. For registered providers, only curated chat-capable ids
        # survive this intersection. Custom endpoints may report their own list.
        if self._supported_models is not None:
            models = [m for m in models if m in self._supported_models]
        return sorted(set(models))

    def _parse_models(self, data: Any) -> list[str]:
        return []

    async def list_models_cached(self, ttl: float = 120.0) -> list[str]:
        now = time.monotonic()
        if now < getattr(self, "_models_until", 0.0):
            return getattr(self, "_models_cache", [])
        try:
            models = await self.list_models()
        except CloudProviderError:
            models = []
        self._models_cache = models
        self._models_until = now + ttl
        return models


class OpenAICompatibleClient(_BaseCloudClient):
    """OpenAI / OpenRouter / Gemini / Groq / Mistral / Together / Fireworks."""

    kind = "openai"

    def __init__(self, api_key: str, model: str, **kw: Any) -> None:
        super().__init__(api_key, model, **kw)
        self._client.headers["Authorization"] = f"Bearer {api_key}"
        # Accepted by OpenRouter; harmless for other compatible endpoints.
        self._client.headers["X-Title"] = "Vednix AI"

    async def _models_request(self) -> httpx.Response:
        return await self._client.get("/models")

    def _parse_models(self, data: Any) -> list[str]:
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted({
            _canonical_model_id(str(item.get("id", "")))
            for item in items
            if isinstance(item, dict) and item.get("id")
        })

    def _payload(
        self,
        messages: list[dict],
        temperature: float,
        model: str | None,
        stream: bool,
        images: list[str] | None,
    ) -> dict[str, Any]:
        if images and self._vision:
            messages = [dict(message) for message in messages]
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    text = messages[i].get("content", "")
                    messages[i]["content"] = [
                        {"type": "text", "text": text},
                        *(
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                            for b64 in images
                        ),
                    ]
                    break
        return {
            "model": _canonical_model_id(model or self.model),
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

    async def chat(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
    ) -> str:
        selected = _canonical_model_id(model or self.model)
        if not self.supports_model(selected):
            raise CloudProviderError(
                f"{self.provider_name}: `{selected}` is not a supported text-chat model. "
                f"Use {self.model} or choose a listed model."
            )
        try:
            response = await self._client.post(
                "/chat/completions",
                json=self._payload(messages, temperature, selected, False, images),
            )
            if not 200 <= response.status_code < 300:
                raise _provider_http_error(self.provider_name, response, self._api_key)
            data = response.json()
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _clean_error(exc, self._api_key)
            raise CloudProviderError(f"Could not reach {self.provider_name}: {reason or 'network error'}.") from exc
        except ValueError as exc:
            raise CloudProviderError(f"{self.provider_name} returned invalid chat JSON.") from exc

        if err := data.get("error"):
            if isinstance(err, dict):
                err = err.get("message", "request rejected")
            message = _clean_error(err, self._api_key)
            raise CloudProviderError(f"{self.provider_name}: {message or 'request rejected'}.")
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise CloudProviderError(f"{self.provider_name} returned no text response.")
        text = _extract_openai_text((choices[0].get("message") or {}).get("content"))
        if not text.strip():
            raise CloudProviderError(f"{self.provider_name} returned an empty text response.")
        return text

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
    ) -> AsyncIterator[str]:
        selected = _canonical_model_id(model or self.model)
        if not self.supports_model(selected):
            raise CloudProviderError(
                f"{self.provider_name}: `{selected}` is not a supported text-chat model. "
                f"Use {self.model} or choose a listed model."
            )
        try:
            async with self._client.stream(
                "POST", "/chat/completions",
                json=self._payload(messages, temperature, selected, True, images),
            ) as response:
                if not 200 <= response.status_code < 300:
                    body = (await response.aread()).decode("utf-8", "replace")
                    error_response = httpx.Response(
                        response.status_code,
                        content=body,
                        headers=dict(response.headers),
                        request=response.request,
                    )
                    raise _provider_http_error(self.provider_name, error_response, self._api_key)
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if err := chunk.get("error"):
                        if isinstance(err, dict):
                            err = err.get("message", "request rejected")
                        message = _clean_error(err, self._api_key)
                        raise CloudProviderError(f"{self.provider_name}: {message or 'request rejected'}.")
                    choices = chunk.get("choices") or []
                    delta = (choices[0].get("delta") or {}) if choices and isinstance(choices[0], dict) else {}
                    text = _extract_openai_text(delta.get("content"))
                    if text:
                        yield text
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _clean_error(exc, self._api_key)
            raise CloudProviderError(f"Could not reach {self.provider_name}: {reason or 'network error'}.") from exc


class AnthropicClient(_BaseCloudClient):
    """Claude via /v1/messages and Anthropic's native SSE event format."""

    kind = "anthropic"

    def __init__(self, api_key: str, model: str, **kw: Any) -> None:
        super().__init__(api_key, model, **kw)
        self._client.headers["x-api-key"] = api_key
        self._client.headers["anthropic-version"] = "2023-06-01"

    async def _models_request(self) -> httpx.Response:
        return await self._client.get("/v1/models")

    def _parse_models(self, data: Any) -> list[str]:
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted({
            str(item.get("id", ""))
            for item in items
            if isinstance(item, dict) and item.get("id")
        })

    def _payload(
        self,
        messages: list[dict],
        temperature: float,
        model: str | None,
        stream: bool,
        images: list[str] | None,
    ) -> dict[str, Any]:
        system = ""
        rest: list[dict] = []
        for message in messages:
            if message.get("role") == "system":
                system = (system + "\n\n" + message.get("content", "")).strip()
            else:
                rest.append(dict(message))
        if images and self._vision:
            for i in range(len(rest) - 1, -1, -1):
                if rest[i].get("role") == "user":
                    text = rest[i].get("content", "")
                    rest[i]["content"] = [
                        *(
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
                            for b64 in images
                        ),
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
        selected = model or self.model
        if not self.supports_model(selected):
            raise CloudProviderError(f"{self.provider_name}: `{selected}` is not a supported text-chat model.")
        try:
            response = await self._client.post(
                "/v1/messages", json=self._payload(messages, temperature, selected, False, images)
            )
            if not 200 <= response.status_code < 300:
                raise _provider_http_error(self.provider_name, response, self._api_key)
            data = response.json()
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _clean_error(exc, self._api_key)
            raise CloudProviderError(f"Could not reach {self.provider_name}: {reason or 'network error'}.") from exc
        except ValueError as exc:
            raise CloudProviderError(f"{self.provider_name} returned invalid chat JSON.") from exc
        if data.get("type") == "error":
            message = _clean_error(data.get("error", {}).get("message", "request rejected"), self._api_key)
            raise CloudProviderError(f"{self.provider_name}: {message or 'request rejected'}.")
        blocks = data.get("content") or []
        text = "".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
        if not text.strip():
            raise CloudProviderError(f"{self.provider_name} returned an empty text response.")
        return text

    async def chat_stream(self, messages: list[dict], temperature: float, *,
                          model: str | None = None, images: list[str] | None = None) -> AsyncIterator[str]:
        selected = model or self.model
        if not self.supports_model(selected):
            raise CloudProviderError(f"{self.provider_name}: `{selected}` is not a supported text-chat model.")
        try:
            async with self._client.stream(
                "POST", "/v1/messages",
                json=self._payload(messages, temperature, selected, True, images),
            ) as response:
                if not 200 <= response.status_code < 300:
                    body = (await response.aread()).decode("utf-8", "replace")
                    error_response = httpx.Response(
                        response.status_code,
                        content=body,
                        headers=dict(response.headers),
                        request=response.request,
                    )
                    raise _provider_http_error(self.provider_name, error_response, self._api_key)
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    try:
                        chunk = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    event_type = chunk.get("type")
                    if event_type == "content_block_delta":
                        text = chunk.get("delta", {}).get("text")
                        if text:
                            yield str(text)
                    elif event_type == "message_stop":
                        return
                    elif event_type == "error":
                        message = _clean_error(chunk.get("error", {}).get("message", "request rejected"), self._api_key)
                        raise CloudProviderError(f"{self.provider_name}: {message or 'request rejected'}.")
        except CloudProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _clean_error(exc, self._api_key)
            raise CloudProviderError(f"Could not reach {self.provider_name}: {reason or 'network error'}.") from exc
