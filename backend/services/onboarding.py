"""Server-owned first-run onboarding state."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from memory.models import AppSetting

VALID_MODES = {"cloud"}


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
        """Record the supported provider-backed workspace mode."""
        if mode not in VALID_MODES:
            raise ValueError("mode must be 'cloud'.")
        await self._put("mode", mode)
        await self._put("setup_complete", "1")
        return await self.status()

    async def complete(self) -> dict:
        await self._put("setup_complete", "1")
        return await self.status()
