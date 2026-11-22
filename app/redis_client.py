"""Подключение к Redis (кеш + очереди задач).

ИСПРАВЛЕНО 22.11.2026 (аудит/исправления):
  • КРИТИЧНО: использовалось несуществующее поле ``settings.redis_url``
    (правильное — ``REDIS_URL``). При включении Redis приложение падало с
    AttributeError;
  • подключение теперь ленивое и необязательное: если Redis выключен
    (REDIS_ENABLED=false) или недоступен, приложение продолжает работать,
    а в лог пишется предупреждение (раньше падал весь старт);
  • добавлены ping_redis() для health-check и защита от повторной
    инициализации.
"""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional["aioredis.Redis"] = None


async def init_redis() -> bool:
    """Инициализирует клиент Redis. Возвращает True, если он доступен."""
    global _client

    if not settings.REDIS_ENABLED:
        logger.info("Redis is disabled (REDIS_ENABLED=false)")
        return False

    if _client is not None:
        return True

    client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001 — приложение не должно падать
        logger.warning("Redis is unavailable, continuing without it: %s", exc)
        await client.aclose()
        return False

    _client = client
    logger.info("Redis connection established")
    return True


async def close_redis() -> None:
    """Закрытие клиента Redis. Вызывается на остановке приложения."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping_redis() -> bool:
    """Проверка доступности Redis (для /health/ready)."""
    if _client is None:
        return False
    try:
        await _client.ping()
        return True
    except Exception:  # noqa: BLE001
        return False


def get_redis_client() -> Optional["aioredis.Redis"]:
    """Возвращает активный клиент Redis или None."""
    return _client
