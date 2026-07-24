"""
Async database engine/session factory.

Single-session SQLite in the original became per-op connections with no WAL.
Here: SQLAlchemy 2.0 async + WAL + foreign keys on; URL is settings-driven so
Postgres is a one-line change later (audit SC4).
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from memory.models import Base


def create_engine_and_session(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, pool_pre_ping=True, future=True)

    if database_url.startswith("sqlite"):
        # WAL + enforce FK constraints (audit SEC5 hardening)
        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def init_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
