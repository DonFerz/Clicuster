"""
Схемы для аутентификации: токены и их содержимое.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ─────────── Ответ клиенту: пара токенов ───────────
class TokenPair(BaseModel):
    """Пара access + refresh токенов.
    Возвращается клиенту при успешном логине/регистрации.
    Клиент использует access_token в заголовке Authorization,
    а refresh_token хранит для обновления access_token.
    """

    access_token: str = Field(..., description="JWT access-token")
    refresh_token: str = Field(..., description="JWT refresh-token")
    token_type: Literal["bearer"] = Field(default="bearer", description="Тип токена. Всегда 'bearer' (см. RFC 6750).")
    expires_in: int = Field(..., gt=0, description="Время жизни access-токена в секундах")


# ─────────── Содержимое JWT ───────────
class TokenPayload(BaseModel):
    """Payload, который мы кладём внутрь JWT
    Служит документацией: что именно кодируется/подписывается в токене
    Может использоваться для типизации при decode_token.
    """

    model_config = ConfigDict(extra="ignore")
    sub: str = Field(..., description="Subject — id пользователя (строкой)")
    exp: datetime = Field(..., description="Когда токен истекает (UTC)")
    iat: datetime = Field(..., description="Когда токен выдан (UTC)")
    nbf: datetime | None = Field(default=None, description="Not before — с какого момента токен валиден (UTC)")
    iss: str | None = Field(default=None, description="Issuer — кто выдал токен")
    aud: str | list[str] | None = Field(default=None, description="Audience — для кого токен")
    type: Literal["access", "refresh"] = Field(..., description="Тип токена (access или refresh)")


# ─────────── Тело запроса на refresh ───────────
class RefreshRequest(BaseModel):
    """Тело запроса POST /auth/refresh."""

    refresh_token: str = Field(..., min_length=1, max_length=4096, description="Refresh-токен")


# ─────────── Публичный API модуля ───────────
__all__ = ["RefreshRequest", "TokenPair", "TokenPayload"]
