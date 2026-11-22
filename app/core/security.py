"""Пароли и JWT.

ИСПРАВЛЕНО 22.11.2026 (аудит/исправления):
  • КРИТИЧНО: модуль импортировал ``passlib``, которого не было в
    requirements.txt, а закреплённый там ``bcrypt==5.0.0`` несовместим с
    passlib 1.7.4 (passlib читает удалённый ``bcrypt.__about__``). На чистой
    установке приложение вообще не запускалось, а на «старом» окружении
    ломалось на паролях длиннее 72 байт. Хеширование переписано на прямой
    вызов ``bcrypt`` — без passlib.
  • Сохранена 100% совместимость со старыми хешами passlib
    (``$bcrypt-sha256$v=2,...`` и ``$2b$...``) — существующие пользователи
    смогут войти без сброса пароля.
  • Пароль перед bcrypt прогоняется через HMAC-SHA256 с солью (как в
    passlib bcrypt_sha256 v=2), поэтому лимит bcrypt в 72 байта больше не
    обрезает длинные пароли.
  • Добавлена константа ``PASSWORD_MAX_LENGTH`` и безопасная обработка
    битых/чужих форматов хешей (возвращается False, а не 500).
  • JWT: без изменений по формату, но добавлена проверка, что
    ``SECRET_KEY`` достаточно длинный для HMAC (RFC 7518).
"""

from __future__ import annotations

import base64
import hmac
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Final, Literal

import bcrypt
from jose import JWTError, jwt

from app.config import settings

TokenType = Literal["access", "refresh"]

# Максимальная длина пароля, которую принимает API (в символах).
PASSWORD_MAX_LENGTH: Final[int] = 128
# ИЗМЕНЕНО 22.11.2026: стоимость bcrypt берётся из настроек (BCRYPT_ROUNDS),
# чтобы тесты могли использовать 4 раунда и работать быстро.

# Формат passlib bcrypt_sha256 v=2:
#   $bcrypt-sha256$v=2,t=2b,r=12$<salt22>$<checksum31>
_BCRYPT_SHA256_V2_RE: Final = re.compile(
    r"^\$bcrypt-sha256\$v=2,t=(?P<ident>2[abxy]),r=(?P<rounds>\d{1,2})"
    r"\$(?P<salt>[./A-Za-z0-9]{22})\$(?P<checksum>[./A-Za-z0-9]{31})$"
)
# Старый формат passlib bcrypt_sha256 v=1: $bcrypt-sha256$2b,12$<salt>$<checksum>
_BCRYPT_SHA256_V1_RE: Final = re.compile(
    r"^\$bcrypt-sha256\$(?P<ident>2[abxy]),(?P<rounds>\d{1,2})"
    r"\$(?P<salt>[./A-Za-z0-9]{22})\$(?P<checksum>[./A-Za-z0-9]{31})$"
)
# «Голый» bcrypt: $2b$12$<53 символа>
_RAW_BCRYPT_RE: Final = re.compile(r"^\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}$")


# ─────────── Startup checks ───────────
# Выполняются один раз при импорте модуля.

_ALLOWED_ALGORITHMS: frozenset[str] = frozenset({"HS256", "HS384", "HS512"})

if settings.ALGORITHM not in _ALLOWED_ALGORITHMS:
    # ИСПРАВЛЕНО: раньше список допускал RS*/ES*, но ключ всегда
    # симметричный — такие алгоритмы всё равно не смогли бы работать.
    raise RuntimeError(
        f"Unsupported JWT algorithm: {settings.ALGORITHM!r}. "
        f"Allowed: {sorted(_ALLOWED_ALGORITHMS)}"
    )

if len(settings.SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError(
        "SECRET_KEY must be at least 32 bytes for HMAC algorithms (RFC 7518)."
    )


# ─────────── Passwords ───────────

def _sha256_prehash(password: str, salt: str) -> bytes:
    """HMAC-SHA256(ключ=salt, пароль) → base64 (44 байта).

    Именно так passlib готовил вход для bcrypt в bcrypt_sha256 v=2.
    """
    digest = hmac.new(
        salt.encode("ascii"),
        password.encode("utf-8"),
        sha256,
    ).digest()
    return base64.b64encode(digest)


def _check_bcrypt(key: bytes, ident: str, rounds: int, salt: str, checksum: str) -> bool:
    """Сверяет bcrypt-хеш для уже подготовленного ключа."""
    full_hash = f"${ident}${rounds:02d}${salt}{checksum}".encode("ascii")
    try:
        return bcrypt.checkpw(key, full_hash)
    except (ValueError, TypeError):
        # Битый хеш/неподдерживаемая версия bcrypt — считаем пароль неверным.
        return False


def hash_password(password: str) -> str:
    """Превращает открытый пароль в bcrypt_sha256-хеш (формат passlib)."""
    if not password:
        raise ValueError("Password must not be empty")

    salt_full = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)  # b"$2b$12$<22>"
    parts = salt_full.decode("ascii").split("$")      # ['', '2b', '12', salt]
    ident, rounds_str, salt = parts[1], parts[2], parts[3]
    rounds = int(rounds_str)

    hashed = bcrypt.hashpw(_sha256_prehash(password, salt), salt_full)
    checksum = hashed.decode("ascii")[-31:]

    return f"$bcrypt-sha256$v=2,t={ident},r={rounds}${salt}${checksum}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет пароль против любого поддерживаемого формата хеша.

    Поддерживаются:
      * ``$bcrypt-sha256$v=2,...`` — новые хеши и старые хеши passlib;
      * ``$bcrypt-sha256$2b,12$...`` — очень старый passlib v=1;
      * ``$2b$...`` / ``$2a$...`` / ``$2y$...`` — «голый» bcrypt.

    Возвращает False для повреждённых/неизвестных хешей (никогда не 500).
    """
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False
    if not plain_password or not hashed_password:
        return False

    m = _BCRYPT_SHA256_V2_RE.match(hashed_password)
    if m:
        key = _sha256_prehash(plain_password, m.group("salt"))
        return _check_bcrypt(
            key,
            m.group("ident"),
            int(m.group("rounds")),
            m.group("salt"),
            m.group("checksum"),
        )

    m = _BCRYPT_SHA256_V1_RE.match(hashed_password)
    if m:
        # v=1: sha256 без HMAC — только для чтения старых хешей.
        key = base64.b64encode(sha256(plain_password.encode("utf-8")).digest())
        return _check_bcrypt(
            key,
            m.group("ident"),
            int(m.group("rounds")),
            m.group("salt"),
            m.group("checksum"),
        )

    if _RAW_BCRYPT_RE.match(hashed_password):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("ascii")
            )
        except (ValueError, TypeError):
            return False

    return False


def needs_rehash(hashed_password: str) -> bool:
    """True, если хеш устарел и его стоит пересчитать при следующем логине."""
    m = _BCRYPT_SHA256_V2_RE.match(hashed_password)
    if not m:
        return True
    return (
        m.group("ident") != "2b"
        or int(m.group("rounds")) < settings.BCRYPT_ROUNDS
    )


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
