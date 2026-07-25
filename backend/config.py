"""
Central configuration for Vednix AI backend.

Replaces dev_ai/config.py. Differences from the original:
  - 12-factor: every value overridable via environment variables (.env supported)
  - No import-time side effects (audit C1 fixed: data dir created in lifespan, not at import)
  - Pydantic-validated settings with sane offline-first defaults
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent


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

    # --- LLM provider (Phase 5): offline default stays Ollama ---
    llm_provider: str = "ollama"  # ollama | openrouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-oss-20b:free"

    # --- Internet research (Phase 5): SearXNG, self-hostable = offline-creed ---
    searxng_url: str = "http://localhost:8080"
    search_max_results: int = 5
    search_fetch_pages: int = 3  # top pages fetched & quoted into the turn
    search_page_chars: int = 6000
    search_timeout: float = 12.0

    # --- Multi-agent deep research (Phase 6): bounded loops, honest cost ---
    agents_max_iterations: int = 2      # critique→refine rounds (cap guarantees termination)
    agents_max_subquestions: int = 4    # planner fan-out cap per turn

    # --- Infra switches (Phase 5): all opt-in, local defaults unchanged ---
    redis_url: str = ""  # empty → in-process rate limiting
    auth_token: str = ""  # empty → open local mode (single-user default)

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    # auto-reload watches the source tree — great for hacking, wasteful (and
    # process-forking) in normal runs. Off by default; VEDNIX_DEV_RELOAD=1.
    dev_reload: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"  # both loopback forms

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/vednix.db"

    # --- Guards ---
    max_message_chars: int = 32_000  # audit SEC4: unbounded input went straight to the model
    history_max_turns: int = 40  # max messages fed back as context (was hardcoded 20 RAM-only)
    memory_context_items: int = 5  # long-term facts injected into the system prompt

    # --- Files & knowledge (Phase 4) ---
    upload_dir: str = "./data/uploads"
    upload_max_mb: int = 15
    file_context_max_chars: int = 16_000  # per-file budget injected into the LLM turn
    vision_model_keywords: str = "vision,vl,minicpm-v,moondream,gemma3"  # matched against model names
    kb_chunk_chars: int = 900
    kb_chunk_overlap: int = 150
    kb_context_chunks: int = 4

    # --- Persona ---
    assistant_name: str = "Vednix AI"
    creator_name: str = "Abhinav Singh"  # creator signature, surfaced via /api/health

    @model_validator(mode="after")
    def _absolutize_local_paths(self) -> "Settings":
        """Anchor relative paths to the backend root.

        The SQLite file and upload dir must be identical no matter which
        directory the server is launched from — otherwise two processes
        started from different CWDs silently read/write *different* database
        files (observed live: split-brain persistence, orphaned uploads).
        Absolute paths (tests, deployments) pass through untouched.
        """
        scheme, sep, rel = self.database_url.partition(":///")
        if sep and rel and rel != ":memory:" and not Path(rel).is_absolute():
            self.database_url = f"{scheme}:///{_BACKEND_ROOT / rel}"
        if not Path(self.upload_dir).is_absolute():
            self.upload_dir = str(_BACKEND_ROOT / self.upload_dir)
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def vision_keywords_list(self) -> list[str]:
        return [k.strip().lower() for k in self.vision_model_keywords.split(",") if k.strip()]

    def is_vision_model(self, model_name: str) -> bool:
        name = model_name.lower()
        return any(k in name for k in self.vision_keywords_list)

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
