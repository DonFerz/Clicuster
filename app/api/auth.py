"""HTTP-роутер аутентификации: регистрация, логин, refresh."""

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
)
async def register(database: DbSession, data: UserCreate) -> TokenPair:
    """Создаёт пользователя и сразу выдаёт пару токенов.

    Если email уже занят — 409 Conflict.
    """
    user = await register_user(database, data)
    return issue_tokens(user)


# ─────────── Логин ───────────
@router.post(
    "/login",
    response_model=TokenPair,
    summary="Логин по email и паролю",
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

    return issue_tokens(user)


__all__ = ["router"]
