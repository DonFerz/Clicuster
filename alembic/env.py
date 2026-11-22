import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# --- Приложение ---
from app.config import settings
from app.models import Base  # noqa: F401 — тянет все модели через app/models/__init__.py

# Объект конфигурации Alembic (читает alembic.ini)
config = context.config

# Настраивает логирование из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Подставляю URL из config.py в конфиг Alembic.
# Чтобы в alembic.ini НЕ нужно было хардкодить sqlalchemy.url.
#
# ИСПРАВЛЕНО 22.11.2026: configparser в alembic.ini использует %-подстановки,
# поэтому одиночный «%» в пароле/URL ломал alembic с InterpolationSyntaxError.
# Экранируем его удвоением.
config.set_main_option(
    "sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%")
)

# Метадата всех моделей — Alembic сравнивает её с реальной БД
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Офлайн-режим: генерирует SQL, не подключаясь к БД."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,             # отслеживать изменения типов колонок
        compare_server_default=True,   # отслеживать изменения server_default
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Синхронная обёртка — Alembic внутри работает синхронно."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Онлайн-режим: подключаемся к БД через asyncpg и запускаем миграции."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # для миграций пул не нужен
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
