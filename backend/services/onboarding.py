"""Onboarding / run-mode state — server-owned truth for the first-run wizard.

Two keys in app_settings:
  setup_complete : "1" once the user has passed the welcome flow
  mode           : free | cloud | "" (chosen but not yet finished)

Rule of the house: NO SIGNUP, NO ENTRY — there is no guest/demo mode. Every
choice completes first-run setup; the wizard is re-enterable anytime from
settings. Everything here is data, so it lives in the db (not env/config)
and any process restart resumes exactly where the user left the wizard.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from memory.models import AppSetting

VALID_MODES = {"free", "cloud"}


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
        }

    async def choose_mode(self, mode: str) -> dict:
        """Wizard step: user picked free (Vednix Engine on this machine) or
        cloud (bring-your-own API keys). Every choice completes first-run
        setup — re-entry is just visiting /onboarding again."""
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
        await self._put("mode", mode)
        await self._put("setup_complete", "1")
        return await self.status()

    async def complete(self) -> dict:
        await self._put("setup_complete", "1")
        return await self.status()
