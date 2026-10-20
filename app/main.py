"""Точка входа FastAPI-приложения.
Запуск в разработке: uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.exceptions import AppError
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.salons import router as salons_router


# ─────────── Логирование ───────────
logger = logging.getLogger(__name__)


# ─────────── Приложение ───────────
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ─────────── CORS ───────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Если в origins есть "*", credentials должны быть выключены,
    # иначе браузеры отклоняют такие ответы.
    allow_credentials="*" not in settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────── Хендлеры исключений ───────────
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
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ловит всё, что не поймано выше — 500 Internal Server Error."""
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
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


@app.get(
    "/health",
    tags=["service"],
    summary="Health check",
)
async def health() -> dict[str, str]:
    """Проверка — работает ли приложение."""
    return {"status": "ok"}


@app.get(
    "/",
    tags=["service"],
    summary="Корень API",
)
async def root() -> dict[str, str]:
    """Информация о приложении."""
    return {
        "name": settings.APP_NAME,
        "docs": app.docs_url or "/docs",
        "version": getattr(settings, "VERSION", "0.1.0"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
