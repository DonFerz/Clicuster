from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings


TokenType = Literal["access", "refresh"]

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)


# ─────────── Startup checks ───────────
# Выполняются один раз при импорте модуля.

_ALLOWED_ALGORITHMS: frozenset[str] = frozenset(
    {
        "HS256", "HS384", "HS512",
        "RS256", "RS384", "RS512",
        "ES256", "ES384", "ES512",
    }
)

if settings.ALGORITHM not in _ALLOWED_ALGORITHMS:
    raise RuntimeError(
        f"Unsupported JWT algorithm: {settings.ALGORITHM!r}. "
        f"Allowed: {sorted(_ALLOWED_ALGORITHMS)}"
    )

if settings.ALGORITHM.startswith("HS") and len(settings.SECRET_KEY.encode()) < 32:
    raise RuntimeError(
        "SECRET_KEY must be at least 32 bytes for HMAC algorithms (RFC 7518)."
    )


# ─────────── Passwords ───────────

def hash_password(password: str) -> str:
    """Превращает открытый пароль в bcrypt-хеш."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, соответствует ли открытый пароль хешу.

    Возвращает False, если хеш повреждён или имеет неизвестный формат.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """True, если хеш устарел и его стоит пересчитать при следующем логине."""
    try:
        return pwd_context.needs_update(hashed_password)
    except (ValueError, TypeError):
        return True


# ─────────── JWT ───────────

def _create_token(
    data: dict[str, Any],
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    to_encode: dict[str, Any] = {
        **data,
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": token_type,
    }

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Создаёт access-токен."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    return _create_token(data, "access", expires_delta)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Создаёт refresh-токен."""
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    return _create_token(data, "refresh", expires_delta)


def decode_token(
    token: str,
    expected_type: TokenType | None = None,
) -> dict[str, Any]:
    """Декодирует и валидирует JWT.

    Проверяет подпись, exp, iat, nbf, iss, aud.
    Если expected_type задан — проверяет claim "type".
    Бросает JWTError при любой проблеме.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        options={
            "require_exp": True,
            "require_iat": True,
            "require_nbf": True,
            "require_sub": True,
            "verify_aud": True,
            "verify_iss": True,
            "verify_signature": True,
        },
    )

    if expected_type is not None and payload.get("type") != expected_type:
        raise JWTError(
            f"Invalid token type: expected {expected_type!r}, "
            f"got {payload.get('type')!r}"
        )

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type="refresh")
