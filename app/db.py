"""SQLAlchemy 2.0 async engine + session factory.

One engine for the whole process. `DATABASE_URL` drives the dialect:

  * sqlite+aiosqlite:///path.sqlite3        — dev / single-user self-host
  * postgresql+asyncpg://USER:PASS@HOST/DB  — production (Neon, Supabase, RDS)

We deliberately keep this thin: callers obtain a session via
`async with session_scope() as session:` and own the transaction. Routes that
just need a session use the `get_session` FastAPI dependency.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

logger = logging.getLogger(__name__)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite refuses to open if the parent dir doesn't exist; create it."""
    if not url.startswith("sqlite"):
        return
    parsed = urlparse(url.replace("sqlite+aiosqlite", "sqlite", 1))
    # url like sqlite:///telemetry/heimdall.sqlite3  → path = /telemetry/...
    path = parsed.path.lstrip("/") if parsed.netloc == "" else parsed.path
    if path and path not in (":memory:",):
        Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_engine(settings: Settings) -> AsyncEngine:
    """Create the singleton engine. Idempotent — safe to call from lifespan."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine

    _ensure_sqlite_dir(settings.database_url)

    is_sqlite = settings.database_url.startswith("sqlite")
    # SQLite: small pool, NullPool semantics. Postgres: real pool with recycle
    # so long-lived workers don't hold dead Neon connections.
    engine_kwargs: dict = {"echo": False, "future": True}
    if not is_sqlite:
        engine_kwargs.update(
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    _engine = create_async_engine(settings.database_url, **engine_kwargs)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info(
        "db engine ready dialect=%s",
        _engine.dialect.name,
    )
    return _engine


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("DB not initialised — call init_engine() first.")
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session and commit/rollback automatically."""
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# FastAPI dependency form. Routes do:  session = Depends(get_session)
async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session
