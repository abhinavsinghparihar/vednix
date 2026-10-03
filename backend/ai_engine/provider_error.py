"""Provider failures with safe, user-facing classification for routing and UI."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """A sanitized provider error; never attach request headers or API keys."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        category: str = "provider_error",
        http_status: int | None = None,
        retryable: bool = False,
        model_id: str | None = None,
    ) -> None:
        self.provider = provider
        self.message = message
        self.category = category
        self.http_status = http_status
        self.retryable = retryable
        self.model_id = model_id
        super().__init__(f"{provider}: {message}")

    @property
    def code(self) -> str:
        """Stable internal classification; frontend messages never expose internals."""
        return {
            "authentication": "INVALID_API_KEY",
            "permission_denied": "PERMISSION_DENIED",
            "unsupported_model": "MODEL_NOT_FOUND",
            "capability": "MODEL_NOT_COMPATIBLE",
            "streaming_unsupported": "STREAMING_UNSUPPORTED",
            "vision_unsupported": "VISION_UNSUPPORTED",
            "tool_calling_unsupported": "TOOL_CALLING_UNSUPPORTED",
            "rate_limit": "RATE_LIMITED",
            "timeout": "PROVIDER_TIMEOUT",
            "temporary": "PROVIDER_UNAVAILABLE",
            "invalid_request": "INVALID_REQUEST",
            "search_unavailable": "SEARCH_UNAVAILABLE",
            "multi_agent_unavailable": "MULTI_AGENT_UNAVAILABLE",
        }.get(self.category, "PROVIDER_UNAVAILABLE" if self.retryable else "PROVIDER_ERROR")

    @property
    def authentication_error(self) -> bool:
        return self.category in {"authentication", "permission_denied"}

    @property
    def unsupported_model(self) -> bool:
        return self.category in {
            "unsupported_model", "capability", "streaming_unsupported",
            "vision_unsupported", "tool_calling_unsupported",
        }

    @classmethod
    def from_http(
        cls, provider: str, status: int, detail: str, *, model_id: str | None = None,
    ) -> "ProviderError":
        """Classify common Gemini/OpenAI-compatible errors without returning raw bodies."""
        hint = " ".join(str(detail or "").lower().replace("_", " ").split())

        if any(term in hint for term in ("invalid api key", "api key not valid", "api_key_invalid", "key is invalid")):
            return cls(
                provider,
                "API key was rejected as invalid. Check the provider console and reconnect.",
                category="authentication", http_status=status, model_id=model_id,
            )
        if status in (401, 403):
            if status == 403 and any(term in hint for term in ("quota", "rate limit", "resource exhausted")):
                return cls(
                    provider, "Rate limit or quota reached. Try again later or check provider billing.",
                    category="rate_limit", http_status=status, retryable=True, model_id=model_id,
                )
            if status == 403:
                return cls(
                    provider,
                    "Permission denied. Check that this API is enabled for the project and that the key's restrictions allow server-side use.",
                    category="permission_denied", http_status=status, model_id=model_id,
                )
            return cls(
                provider, "API key was rejected. Check that the saved provider key is valid and reconnect.",
                category="authentication", http_status=status, model_id=model_id,
            )
        if status == 404:
            return cls(
                provider,
                "The model was not found or is no longer available to this provider key. Refresh verified models.",
                category="unsupported_model", http_status=status, model_id=model_id,
            )
        if status == 429:
            return cls(
                provider, "Rate limit or quota reached. Vednix will try another available provider.",
                category="rate_limit", http_status=status, retryable=True, model_id=model_id,
            )
        if status >= 500:
            return cls(
                provider, "Provider is temporarily unavailable. Vednix will try another provider.",
                category="temporary", http_status=status, retryable=True, model_id=model_id,
            )
        if status == 400:
            if any(term in hint for term in ("streaming not supported", "does not support streaming", "stream is not supported")):
                category, message = "streaming_unsupported", "This model does not support Vednix streaming."
            elif any(term in hint for term in ("image input", "vision", "images are not supported")):
                category, message = "vision_unsupported", "This model does not support image input."
            elif any(term in hint for term in ("tool calling", "function calling", "tools are not supported")):
                category, message = "tool_calling_unsupported", "This model does not support tool calling."
            elif any(term in hint for term in ("model not found", "unknown model", "no such model")):
                category, message = "unsupported_model", "The model was not found or is no longer available. Refresh verified models."
            elif model_id:
                category, message = "capability", "The model rejected Vednix's chat request format and is not compatible."
            else:
                category, message = "invalid_request", "The provider rejected this request format. Check the request and model configuration."
            return cls(provider, message, category=category, http_status=status, model_id=model_id)
        return cls(
            provider, "The provider rejected the request. Check its current API and model permissions.",
            category="provider_error", http_status=status, retryable=status >= 500, model_id=model_id,
        )
