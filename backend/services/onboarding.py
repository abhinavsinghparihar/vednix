"""Onboarding / run-mode state — server-owned truth for the first-run wizard.

Three keys in app_settings:
  setup_complete : "1" once the user has passed the welcome flow
  mode           : free | cloud | demo | "" (chosen but not yet finished)
  demo_active    : "1" gates the chat pipeline with a friendly frame

Everything here is data, so it lives in the db (not env/config) and any
process restart resumes exactly where the user left the wizard.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from memory.models import AppSetting

VALID_MODES = {"free", "cloud", "demo"}


class OnboardingService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _get(self, key: str, default: str = "") -> str:
        async with self._sessions() as db:
            row = await db.get(AppSetting, key)
            return row.value if row else default

    async def _put(self, key: str, value: str) -> None:
        async with self._sessions() as db:
            row = await db.get(AppSetting, key)
            if row is None:
                db.add(AppSetting(key=key, value=value))
            else:
                row.value = value
            await db.commit()

    async def status(self) -> dict:
        return {
            "setup_complete": (await self._get("setup_complete")) == "1",
            "mode": (await self._get("mode")) or None,
            "demo_active": (await self._get("demo_active")) == "1",
        }

    async def is_demo_active(self) -> bool:
        return (await self._get("demo_active")) == "1"

    async def choose_mode(self, mode: str) -> dict:
        """Wizard step: user picked free / cloud / demo. Demo flips the chat
        gate on immediately; free/cloud flip it OFF (a returning AIS can
        always be re-gated by re-entering demo from Settings)."""
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
        await self._put("mode", mode)
        await self._put("demo_active", "1" if mode == "demo" else "0")
        if mode in ("free", "cloud"):
            # finishing the wizard path counts as setup; demo stays "open"
            await self._put("setup_complete", "1")
        return await self.status()

    async def complete(self) -> dict:
        await self._put("setup_complete", "1")
        return await self.status()

    async def reset_demo(self, active: bool) -> dict:
        await self._put("demo_active", "1" if active else "0")
        return await self.status()
