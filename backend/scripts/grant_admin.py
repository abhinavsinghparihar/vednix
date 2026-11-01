#!/usr/bin/env python3
"""Assign an existing account as owner, from the trusted server console only.

    cd backend
    python scripts/grant_admin.py <username>

No public endpoint, bootstrap password, or hardcoded admin identity exists.
Existing owners are preserved; public registration always creates members.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update  # noqa: E402
from config import get_settings  # noqa: E402
from memory.db import create_engine_and_session  # noqa: E402
from memory.models import AuthSession, User  # noqa: E402


async def grant_owner(sessions, username: str) -> bool:
    async with sessions() as db:
        user = (await db.execute(
            select(User).where(User.username == username.strip().lower())
        )).scalar_one_or_none()
        if user is None:
            raise LookupError("Account not found. Create the account first.")
        if user.role == "owner":
            return False
        user.role = "owner"
        # A privilege change requires fresh authentication on that account.
        await db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
        await db.commit()
        return True


async def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: python scripts/grant_admin.py <username>")
        return 2
    engine, sessions = create_engine_and_session(get_settings().database_url)
    try:
        try:
            changed = await grant_owner(sessions, sys.argv[1])
        except LookupError as exc:
            print(str(exc))
            return 1
        print("Administrator assigned. Sign in again." if changed else "Account is already an administrator; sessions unchanged.")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
