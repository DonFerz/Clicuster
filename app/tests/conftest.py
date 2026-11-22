"""Фикстуры pytest: тестовая БД, HTTP-клиент, фабрики данных.

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): тестов не было вообще
(app/tests/test_api/test_auth.py был пустым файлом, conftest.py отсутствовал).

Как это работает:
  * тесты используют ОТДЕЛЬНУЮ базу (по умолчанию ``clicuster_test``), а не
    рабочую ``clicuster_db`` — данные разработчика не затрагиваются;
  * перед сессией схема public пересоздаётся и накатываются миграции Alembic
    (так проверяется и сама миграция, включая EXCLUDE-ограничение);
  * после каждого теста таблицы очищаются;
  * приложение подключается к БД через подмену зависимости get_db.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# ВАЖНО: переменные окружения выставляются ДО импорта app.config,
# иначе настройки прочитают .env с рабочей БД.
TEST_DB = os.environ.get("TEST_POSTGRES_DB", "clicuster_test")
os.environ["POSTGRES_DB"] = TEST_DB
os.environ["APP_ENV"] = "local"
os.environ["DEBUG"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"
# Независимый от .env ключ: тесты должны работать и без локального .env.
# BCRYPT_ROUNDS=4 — тесты не должны тратить минуты на bcrypt.
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"

from app.config import settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _psycopg2_connection():
    import psycopg2

    return psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname=TEST_DB,
    )


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """Пересоздаёт схему тестовой БД и накатывает миграции Alembic."""
    try:
        conn = _psycopg2_connection()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"PostgreSQL недоступен для тестов ({settings.POSTGRES_HOST}:"
            f"{settings.POSTGRES_PORT}/{TEST_DB}): {exc}"
        )

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE")
            cur.execute("CREATE SCHEMA public")
    finally:
        conn.close()

    env = os.environ.copy()
    env["POSTGRES_DB"] = TEST_DB
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Не удалось накатить миграции на тестовую БД:\n"
            f"{result.stdout}\n{result.stderr}"
        )


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Движок без пула: каждый тест получает чистые соединения.

    NullPool обязателен, потому что pytest-asyncio создаёт новый event loop
    на каждый тест, а пул «запоминает» соединения старого loop.
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Чистит таблицы после каждого теста (порядок не важен из-за CASCADE)."""
    yield
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE appointments, master_services, masters, services, "
                "salons, users RESTART IDENTITY CASCADE"
            )
        )


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP-клиент поверх ASGI-приложения с общей тестовой сессией БД."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
