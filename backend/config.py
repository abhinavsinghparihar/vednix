"""
Central configuration for Vednix AI backend.

Replaces dev_ai/config.py. Differences from the original:
  - 12-factor: every value overridable via environment variables (.env supported)
  - No import-time side effects (audit C1 fixed: data dir created in lifespan, not at import)
  - Pydantic-validated settings with sane offline-first defaults
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VEDNIX_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM (Ollama) ---
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    llm_temperature: float = 0.7
    llm_request_timeout: float = 300.0
    llm_health_ttl: float = 10.0  # seconds to cache the Ollama health probe (audit P2/P3)

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/vednix.db"

    # --- Guards ---
    max_message_chars: int = 32_000  # audit SEC4: unbounded input went straight to the model
    history_max_turns: int = 40  # max messages fed back as context (was hardcoded 20 RAM-only)
    memory_context_items: int = 5  # long-term facts injected into the system prompt

    # --- Persona ---
    assistant_name: str = "Vednix AI"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def default_system_prompt(self) -> str:
        return (
            f"You are {self.assistant_name}, a premium local-first AI workspace running "
            "fully offline on the user's own machine via Ollama. You are concise, precise "
            "and capable — a competent digital companion (think JARVIS), not a generic "
            "chatbot. When you are not sure, say so plainly instead of inventing facts. "
            "Format answers in clean Markdown (headings, tables, fenced code blocks with "
            "language tags) whenever it helps readability."
        )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor — import this everywhere instead of constructing Settings
    ad hoc, so tests can override via environment before first call."""
    return Settings()
