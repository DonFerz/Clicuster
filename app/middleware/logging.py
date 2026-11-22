"""Middleware логирования запросов.

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): в проекте был пустой пакет
app/middleware, а логирование запросов упоминалось в structure.txt.
Теперь каждый запрос получает X-Request-ID (сквозная трассировка), а в лог
пишется метод, путь, статус и время обработки.

Важно: тело запроса и заголовок Authorization НЕ логируются — иначе в логи
попадут пароли и токены.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("clicuster.request")

# Разрешённые символы во входящем X-Request-ID (защита от инъекций в лог).
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _get_request_id(request: Request) -> str:
    incoming = request.headers.get("x-request-id")
    if incoming and _REQUEST_ID_RE.match(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Логирует каждый HTTP-запрос и проставляет X-Request-ID."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _get_request_id(request)
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_id=%s %s %s → unhandled error (%.1f ms)",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s %s %s → %s (%.1f ms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


__all__ = ["RequestLoggingMiddleware"]
