"""HTTP-роутер аутентификации: регистрация, логин, refresh.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • на /auth/login и /auth/register добавлен rate limit (защита от подбора
    пароля и от массовой регистрации с одного IP);
  • refresh проверяет, что пользователь всё ещё активен, и что это именно
    refresh-токен (тип уже проверялся в decode_refresh_token);
  • в ответе /auth/login больше не «светится» разница между «нет такого
    email» и «неверный пароль» — это было и раньше, но теперь одинаково
    обрабатываются и заблокированные пользователи;
  • добавлен сброс счётчика rate limit только при явном решении
    (см. app/core/rate_limit.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError

from app.core.auth import (
    authenticate_user,
    issue_tokens,
    register_user,
)
from app.core.exceptions import AuthenticationError
from app.core.rate_limit import login_rate_limit
from app.core.security import decode_refresh_token
from app.crud.user import get_user
from app.dependencies import DbSession
from app.schemas import (
    RefreshRequest,
    TokenPair,
    UserCreate,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────── Регистрация ───────────
@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя",
    dependencies=[Depends(login_rate_limit)],
)
async def register(database: DbSession, data: UserCreate) -> TokenPair:
    """Создаёт пользователя и сразу выдаёт пару токенов.

    Новый пользователь всегда получает роль `client`.
    Если email уже занят — 409 Conflict.
    """
    user = await register_user(database, data)
    return issue_tokens(user)


# ─────────── Логин ───────────
@router.post(
    "/login",
    response_model=TokenPair,
    summary="Логин по email и паролю",
    dependencies=[Depends(login_rate_limit)],
)
async def login(
    database: DbSession,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPair:
    """Проверяет email + пароль, выдаёт пару токенов.

    Поле формы `username` содержит email.
    Все ошибки (неверный email, неверный пароль, is_active=False)
    возвращают одинаковое сообщение — защита от enumeration.
    """
    user = await authenticate_user(
        database,
        email=form_data.username,
        password=form_data.password,
    )
    return issue_tokens(user)


# ─────────── Обновление access-токена ───────────
@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Обновить access-токен по refresh-токену",
)
async def refresh(database: DbSession, data: RefreshRequest) -> TokenPair:
    """Принимает refresh-токен, возвращает новую пару.

    Проверяет подпись, срок годности, тип токена.
    Если refresh-токен невалиден — 401.
    """
    try:
        payload = decode_refresh_token(data.refresh_token)
    except JWTError:
        raise AuthenticationError("Invalid or expired refresh token") from None

    sub = payload.get("sub")
    if sub is None:
        raise AuthenticationError("Invalid refresh token payload")

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise AuthenticationError("Invalid refresh token payload") from None

    user = await get_user(database, user_id)
    if user is None:
        raise AuthenticationError("User from refresh token not found")

    # issue_tokens сам проверит is_active и вернёт 401 для заблокированных.
    return issue_tokens(user)


__all__ = ["router"]
