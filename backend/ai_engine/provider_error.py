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
    def authentication_error(self) -> bool:
        return self.category == "authentication"

    @property
    def unsupported_model(self) -> bool:
        return self.category in {"unsupported_model", "capability"}

    @classmethod
    def from_http(
        cls, provider: str, status: int, detail: str, *, model_id: str | None = None,
    ) -> "ProviderError":
        if status in (401, 403):
            return cls(
                provider,
                "API key was rejected or does not have permission. Reconnect this provider.",
                category="authentication", http_status=status, model_id=model_id,
            )
        if status == 404:
            return cls(
                provider, "The provider rejected this model or endpoint. Refresh the model list.",
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
            return cls(
                provider, detail or "The provider rejected this model for the current request.",
                category="capability" if model_id else "invalid_request",
                http_status=status, model_id=model_id,
            )
        return cls(
            provider, detail or f"Provider request failed (HTTP {status}).",
            category="provider_error", http_status=status, retryable=status >= 500,
            model_id=model_id,
        )
