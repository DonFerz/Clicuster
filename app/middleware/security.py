"""Middleware защитных HTTP-заголовков.

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): приложение не отдавало ни одного
security-заголовка — браузер мог встраивать API-ответы в iframe, угадывать
MIME-тип и кешировать ответы с токенами.

Что выставляется:
  * X-Content-Type-Options: nosniff — запрет MIME-sniffing;
  * X-Frame-Options: DENY — запрет встраивания в iframe;
  * Referrer-Policy: no-referrer — не отправлять URL во внешние ресурсы;
  * Permissions-Policy — отключение ненужных API браузера;
  * Cache-Control: no-store — для ответов аутентификации;
  * Strict-Transport-Security — только в prod (за HTTPS-прокси).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Добавляет стандартные защитные заголовки к каждому ответу."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)

        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )

        # Ответы с токенами не должны кешироваться ни браузером, ни прокси.
        if request.url.path.startswith(f"{settings.API_V1_PREFIX}/auth"):
            headers.setdefault("Cache-Control", "no-store")

        if settings.APP_ENV == "prod":
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response


__all__ = ["SecurityHeadersMiddleware"]
