"""Server-side adapters for Gemini, Groq, and OpenAI-compatible AI providers.

All providers use OpenAI-compatible model discovery and chat completions over
HTTPS with Bearer authentication only. Catalog entries are only candidates:
ProviderService performs real, low-token capability probes before exposing a
model as usable.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, AsyncIterator

import httpx

from ai_engine.model_catalog import ModelCapabilities, ModelInfo, normalize_gemini_model
from ai_engine.provider_error import ProviderError
from core.logging import get_logger

logger = get_logger(__name__)

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z_-]{16,}"),
    re.compile(r"(?:sk|rk|xai|nvapi|pplx|csk)-[0-9A-Za-z_-]{16,}"),
)

# A tiny, fixed, harmless JPEG used to prove the normalized format that
# Vednix actually sends for every supported image extension.
_CAPABILITY_TEST_JPEG = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/ALLAB//Z"
)


def _redact(value: object, api_key: str) -> str:
    text = str(value or "")
    if api_key:
        text = text.replace(api_key, "[redacted]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return " ".join(text.split())[:300]


def _provider_error(provider: str, response: httpx.Response, api_key: str, model: str | None = None) -> ProviderError:
    status = response.status_code
    detail = ""
    try:
        body = response.json()
        error = body.get("error", body) if isinstance(body, dict) else body
        detail = _redact(error.get("message", "") if isinstance(error, dict) else error, api_key)
    except (ValueError, AttributeError):
        detail = ""
    return ProviderError.from_http(provider, status, detail, model_id=model)


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        )
    return ""


_NON_CHAT_MODEL = re.compile(
    r"(?:^|[-_/])(prompt[-_]?guard|whisper|distil[-_]?whisper|speech|tts|audio|"
    r"embedding|embed|moderation|classifier|classification|rerank(?:er)?|"
    r"reward|safeguard|safety[-_]?classifier|transcri(?:be|ption)|"
    r"image[-_]?generation|dall[-_]?e|babbage|davinci|ocr)(?:$|[-_/])",
    re.IGNORECASE,
)


def _non_chat_reason(model_id: str, item: dict[str, Any]) -> str | None:
    """Conservative metadata/name exclusion before a real chat/stream probe."""
    state = str(item.get("state") or item.get("status") or "").lower()
    if item.get("active", True) is False or item.get("deprecated") is True or item.get("retired") is True:
        return "The provider reports this model as inactive or deprecated."
    if state in {"inactive", "deprecated", "retired", "disabled", "deleted"}:
        return "The provider reports this model as inactive or deprecated."
    model_type = str(item.get("type") or item.get("model_type") or "").strip().lower()
    if model_type in {"embedding", "embeddings", "image", "audio", "tts", "stt", "moderation", "rerank", "transcribe"}:
        return "This is a specialized non-chat model (for example, audio, embeddings, moderation, or classification)."
    if _NON_CHAT_MODEL.search(model_id.lower()):
        return "This is a specialized non-chat model (for example, audio, embeddings, moderation, or classification)."
    return None


class OpenAICompatibleClient:
    """Common chat-completions transport for provider-specific adapters."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        provider: str,
        provider_name: str,
        base_url: str,
        timeout: float = 90.0,
        client: httpx.AsyncClient | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=8.0),
            headers=headers,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _models_request(self) -> httpx.Response:
        return await self._client.get("/models")

    def _parse_model_entries(self, payload: Any) -> list[ModelInfo]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("data") if "data" in payload else payload.get("models", [])
        else:
            items = []
        models: list[ModelInfo] = []
        for item in items or []:
            if not isinstance(item, dict) or not (item.get("id") or item.get("name")):
                continue
            model_id = str(item.get("id") or item.get("name")).strip()
            reason = _non_chat_reason(model_id, item)
            supports_chat = reason is None
            top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
            models.append(ModelInfo(
                id=model_id,
                provider=self.provider,
                displayName=str(item.get("name") or item.get("display_name") or item.get("displayName") or model_id),
                capabilities=ModelCapabilities(text=supports_chat),
                contextWindow=_positive_int(
                    item.get("context_window")
                    or item.get("context_length")
                    or item.get("max_model_len")
                    or item.get("inputTokenLimit")
                ),
                maxOutputTokens=_positive_int(
                    item.get("max_completion_tokens")
                    or item.get("max_output_tokens")
                    or item.get("outputTokenLimit")
                    or top_provider.get("max_completion_tokens")
                ),
                available=False,
                reason=reason or "Awaiting a live chat and streaming capability check.",
                checkedCapabilities=(),
            ))
        return models

    async def discover_models(self) -> list[ModelInfo]:
        try:
            response = await self._models_request()
            if not 200 <= response.status_code < 300:
                raise _provider_error(self.provider_name, response, self._api_key)
            return self._parse_model_entries(response.json())
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _redact(exc, self._api_key) or "network error"
            raise ProviderError(
                self.provider_name, f"Could not retrieve the live model catalog: {reason}.",
                category="temporary", retryable=True,
            ) from exc
        except ValueError as exc:
            raise ProviderError(self.provider_name, "The provider returned invalid model catalog data.") from exc

    def _payload(
        self,
        messages: list[dict],
        temperature: float,
        model: str,
        *,
        stream: bool,
        images: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        prepared = [dict(message) for message in messages]
        if images:
            for index in range(len(prepared) - 1, -1, -1):
                if prepared[index].get("role") == "user":
                    text = prepared[index].get("content", "")
                    if isinstance(text, list):
                        parts = list(text)
                    else:
                        parts = [{"type": "text", "text": str(text)}]
                    parts.extend(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image if image.startswith("data:image/")
                                else f"data:image/png;base64,{image}"
                            },
                        }
                        for image in images[:3]
                    )
                    prepared[index]["content"] = parts
                    break
        payload: dict[str, Any] = {
            "model": model,
            "messages": prepared,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    async def chat(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        selected = model or self.model
        try:
            response = await self._client.post(
                "/chat/completions",
                json=self._payload(
                    messages, temperature, selected, stream=False, images=images,
                    max_tokens=max_tokens,
                ),
            )
            if not 200 <= response.status_code < 300:
                raise _provider_error(self.provider_name, response, self._api_key, selected)
            payload = response.json()
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _redact(exc, self._api_key) or "network error"
            raise ProviderError(
                self.provider_name, f"Could not reach the provider: {reason}.",
                category="temporary", retryable=True, model_id=selected,
            ) from exc
        except ValueError as exc:
            raise ProviderError(self.provider_name, "The provider returned invalid chat data.", model_id=selected) from exc

        if error := payload.get("error"):
            detail = _redact(error.get("message", "") if isinstance(error, dict) else error, self._api_key)
            raise ProviderError(self.provider_name, detail or "The provider rejected this request.", model_id=selected)
        choices = payload.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        text = _text_from_content((message or {}).get("content"))
        if not text.strip():
            raise ProviderError(self.provider_name, "The provider returned no text response.", model_id=selected)
        return text

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float,
        *,
        model: str | None = None,
        images: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        selected = model or self.model
        try:
            async with self._client.stream(
                "POST", "/chat/completions",
                json=self._payload(
                    messages, temperature, selected, stream=True, images=images,
                    max_tokens=max_tokens,
                ),
            ) as response:
                if not 200 <= response.status_code < 300:
                    body = (await response.aread()).decode("utf-8", "replace")
                    error_response = httpx.Response(
                        response.status_code, content=body, headers=dict(response.headers),
                        request=response.request,
                    )
                    raise _provider_error(self.provider_name, error_response, self._api_key, selected)
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if error := event.get("error"):
                        detail = _redact(error.get("message", "") if isinstance(error, dict) else error, self._api_key)
                        raise ProviderError(self.provider_name, detail or "The provider rejected this request.", model_id=selected)
                    choices = event.get("choices") or []
                    if not choices or not isinstance(choices[0], dict):
                        continue
                    delta = choices[0].get("delta") or {}
                    text = _text_from_content(delta.get("content"))
                    if text:
                        yield text
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _redact(exc, self._api_key) or "network error"
            raise ProviderError(
                self.provider_name, f"Streaming request failed: {reason}.",
                category="temporary", retryable=True, model_id=selected,
            ) from exc

    async def probe_text(self, model_id: str) -> float:
        start = time.perf_counter()
        await self.chat(
            [{"role": "user", "content": "Reply with the single character 1."}],
            0.0, model=model_id, max_tokens=2,
        )
        return (time.perf_counter() - start) * 1000

    async def probe_stream(self, model_id: str, *, images: list[str] | None = None) -> float:
        """Prove the exact streaming path used by Vednix returns visible text."""
        start = time.perf_counter()
        async for chunk in self.chat_stream(
            [{"role": "user", "content": "Reply with the single character 1."}],
            0.0, model=model_id, images=images, max_tokens=2,
        ):
            if chunk.strip():
                return (time.perf_counter() - start) * 1000
        raise ProviderError(
            self.provider_name,
            "The model accepted chat but produced no streamed text response.",
            category="streaming_unsupported", model_id=model_id,
        )

    async def probe_vision(self, model_id: str) -> None:
        image = f"data:image/jpeg;base64,{_CAPABILITY_TEST_JPEG}"
        await self.chat(
            [{"role": "user", "content": "Look at this image. Reply with the single character 1."}],
            0.0, model=model_id, images=[image], max_tokens=2,
        )

    async def probe_tools(self, model_id: str) -> None:
        """Validate the provider/model tool schema without executing a tool."""
        selected = model_id
        payload = {
            "model": selected,
            "messages": [{"role": "user", "content": "Use the ping tool."}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "A capability check; never executed.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
            "tool_choice": {"type": "function", "function": {"name": "ping"}},
            "max_tokens": 1,
            "temperature": 0,
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
            if not 200 <= response.status_code < 300:
                raise _provider_error(self.provider_name, response, self._api_key, selected)
            result = response.json()
            choices = result.get("choices") or []
            message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
            if not message.get("tool_calls"):
                raise ProviderError(
                    self.provider_name,
                    "The model accepted the request but did not demonstrate tool calling.",
                    category="capability", model_id=selected,
                )
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _redact(exc, self._api_key) or "network error"
            raise ProviderError(
                self.provider_name, f"Tool capability check failed: {reason}.",
                category="temporary", retryable=True, model_id=selected,
            ) from exc


class GeminiClient(OpenAICompatibleClient):
    """Gemini adapter: Google-compatible endpoints with Bearer auth only."""

    def __init__(self, api_key: str, model: str, *, timeout: float = 90.0,
                 client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            api_key, model, provider="gemini", provider_name="Google Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            timeout=timeout, client=client,
        )

    async def discover_models(self) -> list[ModelInfo]:
        rows: list[dict] = []
        page_token: str | None = None
        try:
            while True:
                params: dict[str, Any] = {}
                if page_token:
                    params["pageToken"] = page_token
                response = await self._client.get("/models", params=params or None)
                if not 200 <= response.status_code < 300:
                    raise _provider_error(self.provider_name, response, self._api_key)
                payload = response.json()
                if isinstance(payload, dict):
                    entries = payload.get("models") if "models" in payload else payload.get("data", [])
                    if isinstance(entries, list):
                        rows.extend(entries)
                    page_token = payload.get("nextPageToken")
                elif isinstance(payload, list):
                    rows.extend(payload)
                    page_token = None
                else:
                    page_token = None
                if not page_token:
                    break
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            reason = _redact(exc, self._api_key) or "network error"
            raise ProviderError(
                self.provider_name, f"Could not retrieve Google's live model catalog: {reason}.",
                category="temporary", retryable=True,
            ) from exc
        except ValueError as exc:
            raise ProviderError(self.provider_name, "Google returned invalid model catalog data.") from exc

        models: list[ModelInfo] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            raw_id = raw.get("baseModelId") or raw.get("id") or raw.get("name")
            if not raw_id:
                continue
            model_id = normalize_gemini_model(str(raw_id))
            metadata_reason = _non_chat_reason(model_id, raw)
            if "supportedGenerationMethods" in raw:
                methods = {str(method).lower() for method in raw.get("supportedGenerationMethods", [])}
                supports_text = "generatecontent" in methods and metadata_reason is None
                reason = metadata_reason or (
                    None if supports_text else "Google does not list generateContent support for this model."
                )
            else:
                supports_text = metadata_reason is None
                reason = metadata_reason
            models.append(ModelInfo(
                id=model_id,
                provider="gemini",
                displayName=str(raw.get("displayName") or raw.get("display_name") or raw.get("name") or model_id),
                capabilities=ModelCapabilities(text=supports_text),
                contextWindow=_positive_int(raw.get("inputTokenLimit") or raw.get("context_window")),
                maxOutputTokens=_positive_int(raw.get("outputTokenLimit") or raw.get("max_completion_tokens")),
                available=False,
                reason=reason or "Awaiting a live chat and streaming capability check.",
                checkedCapabilities=("text_metadata",) if supports_text else (),
            ))
        return models


class GroqClient(OpenAICompatibleClient):
    """Groq adapter using its live OpenAI-compatible models and chat APIs."""

    def __init__(self, api_key: str, model: str = "", *, timeout: float = 90.0,
                 client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            api_key, model, provider="groq", provider_name="Groq",
            base_url="https://api.groq.com/openai/v1", timeout=timeout, client=client,
        )


def _positive_int(value: object) -> int | None:
    try:
        result = int(value)  # type: ignore[arg-type]
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None
