import asyncio

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.shared.infrastructure.settings import Settings, get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_bound_loop: asyncio.AbstractEventLoop | None = None


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def init_database(
    settings: Settings | None = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    global _engine, _session_factory, _bound_loop
    cfg = settings or get_settings()
    _engine = create_async_engine(cfg.database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    _bound_loop = _current_loop()
    return _engine, _session_factory


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    loop = _current_loop()
    if _session_factory is None or (loop is not None and loop is not _bound_loop):
        _, _session_factory = init_database()
    return _session_factory


def get_engine() -> AsyncEngine:
    global _engine
    loop = _current_loop()
    if _engine is None or (loop is not None and loop is not _bound_loop):
        _engine, _ = init_database()
    return _engine


async def close_database() -> None:
    global _engine, _session_factory, _bound_loop
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        _bound_loop = None
