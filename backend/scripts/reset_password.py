#!/usr/bin/env python3
"""Local account recovery — run ON the machine hosting Vednix:

    cd backend
    python scripts/reset_password.py <username>

Sets a new password (typed interactively, hidden) and REVOKES every session
on the account — matching the product promise: whoever holds the machine owns
the recovery channel. A stand-in for email reset, which an offline-first app
cannot promise. Server can stay running; the change is effective immediately.
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow `python scripts/…`

from sqlalchemy import select, update  # noqa: E402

from config import get_settings  # noqa: E402
from core.tokens import hash_password  # noqa: E402
from memory.db import create_engine_and_session  # noqa: E402
from memory.models import AuthSession, User  # noqa: E402


async def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: python scripts/reset_password.py <username>")
        return 2
    username = sys.argv[1].strip().lower()

    pw1 = getpass.getpass("New password (min 8 chars): ")
    if len(pw1) < 8:
        print("Password must be at least 8 characters.")
        return 2
    if pw1 != getpass.getpass("Confirm new password: "):
        print("Passwords don't match.")
        return 2

    settings = get_settings()
    engine, session_factory = create_engine_and_session(settings.database_url)
    try:
        async with session_factory() as db:
            user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if user is None:
                print(f"No account named '{username}'.")
                return 1
            user.password_hash = hash_password(pw1)
            await db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
            await db.commit()
    finally:
        await engine.dispose()
    print(f"✓ Password reset for '{username}'. All sessions revoked — sign in fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
