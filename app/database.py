from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • добавлена функция dispose_engine() — корректное закрытие пула при
#     остановке приложения (иначе остаются висящие соединения);
#   • get_db явно откатывает транзакцию при исключении и всегда закрывает
#     сессию (было и раньше, оставлено как защита в глубину: CRUD-слой
#     коммитит сам и тоже делает rollback при ошибке).

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Закрывает пул соединений (вызывается в lifespan приложения)."""
    await engine.dispose()
