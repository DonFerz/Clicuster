"""Простое ограничение частоты запросов (rate limiting).

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): раньше /auth/login можно было
перебирать пароли без ограничений — типичная уязвимость (brute force).

Реализация намеренно простая и без внешних зависимостей:
  * скользящее окно в памяти процесса (deque с монотонными метками времени);
  * ключ — IP клиента (или X-Forwarded-For, только если явно разрешено
    настройкой TRUST_PROXY_HEADERS, иначе клиент подделает заголовок);
  * ограничение действует в пределах одного процесса. Для нескольких
    воркеров/реплик нужен Redis-вариант (см. roadmap, REDIS_ENABLED).
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import Request

from app.config import settings
from app.core.exceptions import RateLimitError


class SlidingWindowRateLimiter:
    """Не более ``max_attempts`` событий за ``window_seconds`` для каждого ключа."""

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = float(window_seconds)
        self._events: dict[str, deque[float]] = {}

    def hit(self, key: str) -> int | None:
        """Регистрирует попытку.

        Возвращает None, если попытка разрешена, иначе — сколько секунд
        ждать до следующей.
        """
        now = time.monotonic()
        threshold = now - self.window_seconds

        events = self._events.setdefault(key, deque())
        while events and events[0] < threshold:
            events.popleft()

        if len(events) >= self.max_attempts:
            retry_after = int(events[0] + self.window_seconds - now) + 1
            return max(retry_after, 1)

        events.append(now)
        return None

    def reset(self, key: str | None = None) -> None:
        """Сбрасывает счётчики (для тестов и после успешного логина)."""
        if key is None:
            self._events.clear()
        else:
            self._events.pop(key, None)

    def cleanup(self) -> None:
        """Удаляет пустые/просроченные ключи, чтобы словарь не рос бесконечно."""
        threshold = time.monotonic() - self.window_seconds
        stale = [
            key
            for key, events in self._events.items()
            if not events or events[-1] < threshold
        ]
        for key in stale:
            self._events.pop(key, None)


_limiter: SlidingWindowRateLimiter | None = None


def get_limiter() -> SlidingWindowRateLimiter:
    """Ленивая инициализация лимитера из настроек."""
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowRateLimiter(
            max_attempts=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    return _limiter


def reset_rate_limiter() -> None:
    """Полный сброс (используется в тестах)."""
    get_limiter().reset()


def client_ip(request: Request) -> str:
    """IP клиента с учётом доверенного прокси."""
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Первый адрес в цепочке — исходный клиент.
            return forwarded.split(",")[0].strip() or "unknown"
    client = request.client
    return client.host if client and client.host else "unknown"


async def login_rate_limit(request: Request) -> None:
    """FastAPI-зависимость для /auth/login и /auth/register."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    limiter = get_limiter()
    limiter.cleanup()
    retry_after = limiter.hit(client_ip(request))
    if retry_after is not None:
        raise RateLimitError(retry_after=retry_after)


__all__ = [
    "SlidingWindowRateLimiter",
    "client_ip",
    "get_limiter",
    "login_rate_limit",
    "reset_rate_limiter",
]
