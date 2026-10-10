"""Зависимость FastAPI для Redis.

Сейчас — заглушка. Когда Redis будет подключён, заменить `if TYPE_CHECKING`
на реальный импорт `redis.asyncio.Redis`, а тело `get_redis` — на возврат
клиента из пула (см. app/redis_client.py).
"""

from typing import TYPE_CHECKING, Annotated
from fastapi import Depends
from app.core.exceptions import ServiceUnavailableError


if TYPE_CHECKING:
    from redis.asyncio import Redis


async def get_redis() -> "Redis":
    """Отдаёт клиент Redis. Пока Redis не подключён — 503."""
    raise ServiceUnavailableError(detail="Redis is not configured yet")


RedisDep = Annotated["Redis", Depends(get_redis)]


__all__ = ["RedisDep", "get_redis"]
