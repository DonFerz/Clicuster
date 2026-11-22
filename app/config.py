from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • добавлены настройки, которых не хватало для безопасной работы:
#       APP_VERSION, ENABLE_DOCS, ALLOWED_HOSTS, TRUST_PROXY_HEADERS,
#       RATE_LIMIT_*, LOGIN_RATE_LIMIT_*, BOOKING_* (лимиты записи), LOG_LEVEL;
#   • добавлен общий разбор списков из CSV/JSON (ALLOWED_HOSTS и CORS_ORIGINS
#     раньше обрабатывались по-разному);
#   • в проде запрещён DEBUG и пустые/короткие SECRET_KEY, проверка
#     CORS-источников ужесточена (HTTP допускается только для localhost);
#   • добавлена валидация REDIS_DB/POSTGRES_PORT и проверка согласованности
#     ACCESS/REFRESH-токенов;
#   • DATABASE_URL больше не собирается «руками» в alembic/env.py — здесь он
#     экранируется для configparser (см. alembic/env.py).
# ─────────────────────────────────────────────────────────────────────────────
import json
import logging
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──
    APP_NAME: str = "Clicuster"
    APP_VERSION: str = "0.1.0"
    APP_ENV: Literal["local", "dev", "prod"] = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # Документация (Swagger/ReDoc). В проде её обычно выключают.
    ENABLE_DOCS: bool = True

    # ── Security ──
    SECRET_KEY: str = ""
    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    # ДОБАВЛЕНО 22.11.2026: стоимость bcrypt вынесена в настройки. В тестах
    # ставится 4 — иначе прогон занимает минуты из-за хеширования паролей.
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # ── JWT issuer / audience ──
    JWT_ISSUER: str = "clicuster"
    JWT_AUDIENCE: str = "clicuster-api"

    # ── Database ──
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = Field(default=5432, gt=0, le=65535)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "clicuster_db"

    # Пул соединений SQLAlchemy.
    DB_POOL_SIZE: int = Field(default=5, gt=0)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    DB_POOL_TIMEOUT: int = Field(default=30, gt=0)
    DB_POOL_RECYCLE: int = Field(default=1800, gt=0)
    DB_POOL_PRE_PING: bool = True

    # ── Redis ──
    # ДОБАВЛЕНО: пока Redis в проекте не используется, поэтому по умолчанию
    # выключен — приложение не падает на старте, если Redis недоступен.
    REDIS_ENABLED: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = Field(default=6379, gt=0, le=65535)
    REDIS_DB: int = Field(default=0, ge=0)
    REDIS_PASSWORD: str = ""

    # ── HTTP / CORS ──
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    # ДОБАВЛЕНО: белый список Host-заголовков (защита от Host-header injection).
    # Пустой список = middleware TrustedHost отключён (удобно локально).
    ALLOWED_HOSTS: list[str] = []
    # ДОБАВЛЕНО: брать IP клиента из X-Forwarded-For можно только за доверенным
    # прокси, иначе клиент подделает IP и обойдёт rate limit.
    TRUST_PROXY_HEADERS: bool = False

    # ── Rate limiting (защита от подбора пароля) ──
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_ATTEMPTS: int = Field(default=10, gt=0)
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, gt=0)

    # ── Бронирование ──
    # Минимальный запас до начала записи (0 = можно «на сейчас»).
    BOOKING_MIN_LEAD_MINUTES: int = Field(default=0, ge=0)
    # Горизонт, на который вперёд можно записаться.
    BOOKING_HORIZON_DAYS: int = Field(default=90, gt=0, le=365)

    # ─────────── Validators ───────────
    @staticmethod
    def _parse_list(v: object, *, field_name: str) -> object:
        """Разбирает список из JSON-массива или строки через запятую."""
        if not isinstance(v, str):
            return v
        s = v.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{field_name} looks like JSON but is not valid JSON"
                ) from exc
            if not isinstance(parsed, list):
                raise ValueError(f"{field_name} JSON must be a list")
            return parsed
        return [item.strip() for item in s.split(",") if item.strip()]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        return cls._parse_list(v, field_name="CORS_ORIGINS")

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, v: object) -> object:
        return cls._parse_list(v, field_name="ALLOWED_HOSTS")

    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        level = v.upper().strip()
        if level not in _LOG_LEVELS:
            raise ValueError(
                f"LOG_LEVEL must be one of {sorted(_LOG_LEVELS)}"
            )
        return level

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        if not v:
            raise ValueError("SECRET_KEY is required (set it in .env)")
        if len(v.encode("utf-8")) < 32:
            raise ValueError("SECRET_KEY must be at least 32 bytes")
        return v

    @model_validator(mode="after")
    def _validate_env_specific(self) -> "Settings":
        # ДОБАВЛЕНО: refresh-токен должен жить дольше access-токена, иначе
        # клиент не сможет им пользоваться.
        if self.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 <= (
            self.ACCESS_TOKEN_EXPIRE_MINUTES
        ):
            raise ValueError(
                "REFRESH_TOKEN_EXPIRE_DAYS must be longer than "
                "ACCESS_TOKEN_EXPIRE_MINUTES"
            )

        if self.APP_ENV == "prod":
            if self.DEBUG:
                raise ValueError("DEBUG must be False in prod")

            if self.SECRET_KEY.startswith(("change-me", "dev", "test")):
                raise ValueError(
                    "SECRET_KEY looks like a placeholder for prod")

            if self.POSTGRES_PASSWORD == "postgres":
                raise ValueError("POSTGRES_PASSWORD must be changed for prod")

            max_per_worker = self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW
            if max_per_worker > 50:
                raise ValueError(
                    f"DB pool too large for prod: {max_per_worker} per worker. "
                    "Reduce DB_POOL_SIZE/DB_MAX_OVERFLOW "
                    "or raise Postgres max_connections."
                )

            # CORS в проде: только https, никаких '*'
            for origin in self.CORS_ORIGINS:
                if origin == "*":
                    raise ValueError(
                        "Wildcard CORS origin is not allowed in prod")
                if origin.startswith("http://") and not origin.startswith(
                    "http://localhost"
                ):
                    raise ValueError(f"Insecure CORS origin in prod: {origin}")
                if not origin.startswith(("http://", "https://")):
                    raise ValueError(f"Invalid CORS origin in prod: {origin}")

            # ДОБАВЛЕНО: в проде Swagger обычно не должен быть публичным.
            if self.ENABLE_DOCS:
                logging.getLogger(__name__).warning(
                    "ENABLE_DOCS=True in prod: /docs and /redoc are public"
                )

        return self

    # ─────────── Computed URLs ───────────
    def _build_db_url(self, driver: str) -> str:
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        return (
            f"postgresql+{driver}://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return self._build_db_url("asyncpg")

    @computed_field
    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self._build_db_url("psycopg2")

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        auth = (
            f":{quote(self.REDIS_PASSWORD, safe='')}@"
            if self.REDIS_PASSWORD
            else ""
        )
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
