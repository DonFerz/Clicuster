"""Зависимость FastAPI для Redis.

ИСПРАВЛЕНО 22.11.2026 (аудит/исправления):
  • раньше зависимость ВСЕГДА бросала 503 («Redis is not configured yet»),
    даже если клиент был создан в app/redis_client.py;
  • теперь возвращает реальный клиент, а 503 отдаёт только если Redis
    действительно недоступен.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.core.exceptions import ServiceUnavailableError
from app.redis_client import get_redis_client

if TYPE_CHECKING:
    from redis.asyncio import Redis


async def get_redis() -> "Redis":
    """Отдаёт клиент Redis или 503, если Redis недоступен."""
    client = get_redis_client()
    if client is None:
        raise ServiceUnavailableError(detail="Redis is not configured yet")
    return client


RedisDep = Annotated["Redis", Depends(get_redis)]


__all__ = ["RedisDep", "get_redis"]
