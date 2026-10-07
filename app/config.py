from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──
    APP_NAME: str = "Clicuster"
    APP_ENV: Literal["local", "dev", "prod"] = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Security ──
    SECRET_KEY: str = ""
    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)

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
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = Field(default=6379, gt=0, le=65535)
    REDIS_DB: int = Field(default=0, ge=0)
    REDIS_PASSWORD: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ─────────── Validators ───────────
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if not isinstance(parsed, list):
                        raise ValueError("CORS_ORIGINS JSON must be a list")
                    return parsed
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "CORS_ORIGINS looks like JSON but is not valid JSON"
                    ) from exc
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

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
