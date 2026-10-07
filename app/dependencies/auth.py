"""
Зависимости FastAPI для аутентификации и авторизации.

- oauth2_scheme           : читает Bearer-токен из заголовка Authorization.
- get_current_user        : достаёт User из токена.
- get_current_active_user : то же + проверяет is_active.
- CurrentUser             : алиас типа для роутеров.
- require_role(...)       : фабрика зависимостей для проверки ролей.
"""


from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.config import settings
from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
)
from app.core.security import decode_access_token
from app.crud.user import get_user
from app.dependencies.db import DbSession
from app.models.enums import UserRole
from app.models.user import User


__all__ = [
    "CurrentUser",
    "get_current_active_user",
    "get_current_user",
    "oauth2_scheme",
    "require_role",
]


# ─────────── Схема OAuth2 ───────────
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


# ─────────── Текущий пользователь ───────────
async def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if token is None:
        raise AuthenticationError("Missing authorization token")

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise AuthenticationError("Invalid or expired token") from None

    sub = payload.get("sub")
    if sub is None:
        raise AuthenticationError("Token payload is missing 'sub'")

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise AuthenticationError("Token 'sub' is not a valid user id")

    user = await get_user(db, user_id)
    if user is None:
        raise AuthenticationError("User from token not found")

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise AuthenticationError("User account is inactive")

    return current_user


# ─────────── Алиас для роутеров ───────────
CurrentUser = Annotated[User, Depends(get_current_active_user)]


# ─────────── Проверка ролей ───────────
def require_role(*allowed_roles: UserRole) -> Callable[..., Awaitable[User]]:
    if not allowed_roles:
        raise ValueError("At least one role must be specified")

    allowed_values = frozenset(r.value for r in allowed_roles)

    async def _role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        role = current_user.role
        role_value = role.value if isinstance(role, UserRole) else role
        if role_value not in allowed_values:
            raise PermissionDeniedError(
                f"Role '{role_value}' is not allowed here"
            )
        return current_user

    return _role_checker
