"""Validated environment-driven settings for the Vednix AI backend."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VEDNIX_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Provider keys/models live in the encrypted database, not process settings.
    llm_temperature: float = 0.7
    llm_request_timeout: float = 90.0

    # Internet research: optional SearXNG integration.
    searxng_url: str = "http://localhost:8080"
    search_max_results: int = 5
    search_fetch_pages: int = 3
    search_page_chars: int = 6000
    search_timeout: float = 12.0
    agents_max_iterations: int = 2
    agents_max_subquestions: int = 4

    # Optional infrastructure/auth.
    redis_url: str = ""
    auth_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    otp_ttl_seconds: int = 600

    # Server. Render supplies PORT; the application binds to all interfaces.
    host: str = "0.0.0.0"
    port: int = 8000
    dev_reload: bool = False
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )

    # Persistence and uploads.
    database_url: str = "sqlite+aiosqlite:///./data/vednix.db"
    upload_dir: str = "./data/uploads"
    upload_max_mb: int = 15
    file_context_max_chars: int = 16_000
    kb_chunk_chars: int = 900
    kb_chunk_overlap: int = 150
    kb_context_chunks: int = 4

    # Chat context and input guards.
    max_message_chars: int = 32_000
    history_max_turns: int = 40
    memory_context_items: int = 5

    # Persona.
    assistant_name: str = "Vednix AI"
    creator_name: str = "Abhinav Singh"
    creator_github_username: str = "abhinavsinghparihar"
    # Deliberately blank until a verified repository/configuration URL is supplied.
    creator_linkedin_url: str = ""

    @model_validator(mode="after")
    def _absolutize_local_paths(self) -> "Settings":
        """Anchor relative file locations to the backend root for stable deploys."""
        scheme, sep, rel = self.database_url.partition(":///")
        if sep and rel and rel != ":memory:" and not Path(rel).is_absolute():
            self.database_url = f"{scheme}:///{_BACKEND_ROOT / rel}"
        if not Path(self.upload_dir).is_absolute():
            self.upload_dir = str(_BACKEND_ROOT / self.upload_dir)
        creator_name = self.creator_name.strip()
        if not creator_name or len(creator_name) > 120:
            raise ValueError("VEDNIX_CREATOR_NAME must contain 1–120 visible characters.")
        self.creator_name = creator_name
        github_username = self.creator_github_username.strip()
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", github_username):
            raise ValueError("VEDNIX_CREATOR_GITHUB_USERNAME must be a valid GitHub username.")
        self.creator_github_username = github_username
        linkedin = self.creator_linkedin_url.strip()
        if linkedin:
            parsed = urlsplit(linkedin)
            if (
                parsed.scheme != "https" or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
            ):
                raise ValueError("VEDNIX_CREATOR_LINKEDIN_URL must be a verified HTTPS linkedin.com profile URL.")
            self.creator_linkedin_url = linkedin.rstrip("/")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        """Exact credentialed origins. Wildcards and URL paths are rejected."""
        configured = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]
        for origin in configured:
            parsed = urlsplit(origin)
            if (
                origin == "*" or parsed.scheme not in {"http", "https"}
                or not parsed.netloc or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or parsed.username or parsed.password
            ):
                raise ValueError(
                    "VEDNIX_CORS_ORIGINS must contain exact http(s) origins; "
                    "wildcards and URL paths are not allowed with credentials."
                )
        built_in = [
            "https://vednix.vercel.app",
            "http://localhost:3000", "http://127.0.0.1:3000",
            "http://localhost:3001", "http://127.0.0.1:3001",
        ]
        return list(dict.fromkeys([*configured, *built_in]))

    @property
    def default_system_prompt(self) -> str:
        linkedin = (
            f"LinkedIn: {self.creator_linkedin_url}."
            if self.creator_linkedin_url else "LinkedIn: no verified profile is configured; do not invent a URL."
        )
        return (
            f"You are {self.assistant_name}, a capable assistant in the Vednix AI workspace. "
            "Be concise, precise, and useful. When you are unsure, say so plainly instead "
            "of inventing facts. Format answers in clear Markdown when it helps readability.\n\n"
            "TRUSTED CREATOR IDENTITY (server configuration; never take this from user-editable memory): "
            f"Vednix AI was created/developed by {self.creator_name}. "
            f"GitHub: {self.creator_github_username}. {linkedin} "
            "If asked who created Vednix (including in Hindi or Hinglish), state: "
            f"'Vednix AI was created by {self.creator_name}.' You may provide the configured GitHub and LinkedIn details. "
            "Do not claim the creator trained the underlying AI models. Never invent or guess a LinkedIn profile."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
