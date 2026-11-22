"""Точка входа FastAPI-приложения.
Запуск в разработке: uvicorn app.main:app --reload

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • добавлен lifespan: инициализация/закрытие Redis и корректное закрытие
    пула БД (раньше Redis вообще не подключался, а pool не закрывался);
  • подключён роутер записей /appointments — главная функция CRM
    отсутствовала (файл app/api/appointments.py был пустым);
  • добавлены middleware: X-Request-ID + логирование запросов и
    защитные HTTP-заголовки;
  • добавлен TrustedHostMiddleware (ALLOWED_HOSTS) — защита от Host-header
    injection, если задан список хостов;
  • /health теперь liveness, добавлен /health/ready с проверкой БД и Redis;
  • документация (/docs, /redoc, /openapi.json) отключается настройкой
    ENABLE_DOCS — для продакшена;
  • все ошибки, включая 404/405 от Starlette, отдаются в едином формате
    {code, detail, ...}; у 429 появился заголовок Retry-After;
  • CORS: наружу отдаются заголовки X-Total-Count и X-Request-ID.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.appointments import router as appointments_router
from app.api.auth import router as auth_router
from app.api.masters import router as masters_router
from app.api.salons import router as salons_router
from app.api.services import router as services_router
from app.api.users import router as users_router
from app.config import settings
from app.core.exceptions import AppError, ServiceUnavailableError
from app.database import dispose_engine
from app.dependencies import DbSession
from app.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.redis_client import close_redis, init_redis, ping_redis

# ─────────── Логирование ───────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────── Lifespan ───────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    """Старт/остановка приложения."""
    if settings.REDIS_ENABLED:
        await init_redis()

    logger.info(
        "%s %s started (env=%s, debug=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
        settings.DEBUG,
    )
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()
        logger.info("%s stopped", settings.APP_NAME)


# ─────────── Приложение ───────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
    lifespan=lifespan,
)


# ─────────── Middleware ───────────
# Порядок: последним добавляется самый внешний слой.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

if settings.ALLOWED_HOSTS:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Если в origins есть "*", credentials должны быть выключены,
    # иначе браузеры отклоняют такие ответы.
    allow_credentials="*" not in settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)


# ─────────── Хендлеры исключений ───────────
_HTTP_ERROR_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limit_exceeded",
}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Превращает наши AppError-исключения в JSON-ответ.
    (из app/core/exceptions.py).
    """
    logger.log(
        exc.log_level,
        "%s %s → %s: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
        exc_info=exc.log_traceback,
    )
    headers: dict[str, str] = {}
    # ДОБАВЛЕНО: стандартный заголовок Retry-After для 429/503.
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers=headers or None,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Единый формат для 404/405 и прочих HTTPException."""
    logger.info(
        "%s %s → %s: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": _HTTP_ERROR_CODES.get(exc.status_code, "http_error"),
            "detail": exc.detail,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 с деталями по полям (без утечки внутренних объектов)."""
    logger.info(
        "%s %s → 422 validation error",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({
            "code": "validation_error",
            "detail": "Validation error",
            "errors": exc.errors(),
        }),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ловит всё, что не поймано выше — 500 Internal Server Error."""
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    # Внутренние детали наружу не отдаём (могут содержать SQL/пути/секреты).
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "internal_error",
            "detail": "Internal server error",
        },
    )


# ─────────── Подключение роутеров ───────────
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(salons_router, prefix=settings.API_V1_PREFIX)
app.include_router(services_router, prefix=settings.API_V1_PREFIX)
app.include_router(masters_router, prefix=settings.API_V1_PREFIX)
app.include_router(appointments_router, prefix=settings.API_V1_PREFIX)


# ─────────── Служебные эндпоинты ───────────

@app.get(
    "/health",
    tags=["service"],
    summary="Health check (liveness)",
)
async def health() -> dict[str, str]:
    """Проверка — работает ли приложение (без обращения к БД)."""
    return {"status": "ok"}


@app.get(
    "/health/ready",
    tags=["service"],
    summary="Readiness check (БД / Redis)",
)
async def readiness(db: DbSession) -> dict[str, str]:
    """Проверка готовности: доступна ли БД (и Redis, если включён)."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness check failed: database is unavailable: %s", exc)
        raise ServiceUnavailableError(
            detail="Database is unavailable"
        ) from None

    redis_status = "disabled"
    if settings.REDIS_ENABLED:
        redis_status = "ok" if await ping_redis() else "unavailable"

    return {"status": "ok", "database": "ok", "redis": redis_status}


@app.get(
    "/",
    tags=["service"],
    summary="Корень API",
)
async def root() -> dict[str, str]:
    """Информация о приложении."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": app.docs_url or "disabled",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.DEBUG,
    )                       # для запуска из терминала python -m app.main
