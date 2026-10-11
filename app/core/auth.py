"""
Логика аутентификации: проверка пароля, регистрация, выдача токенов.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.crud.user import (
    create_user,
    get_user_by_email,
    set_user_password,
)
from app.models.user import User
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate, PasswordChange


# Фиктивный хеш, чтобы время ответа не зависело от существования email.
# Считается один раз при импорте модуля.
_DUMMY_HASH: str = hash_password("dummy-password-for-timing-protection")


async def authenticate_user(
    database: AsyncSession,
    email: str,
    password: str,
) -> User:
    """Проверяет email и пароль."""

    user = await get_user_by_email(database, email)

    if user is None:
        # Фиктивная проверка, чтобы время ответа не выдавало отсутствие email.
        verify_password(password, _DUMMY_HASH)
        raise AuthenticationError("Invalid email or password")

    if not verify_password(password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Invalid email or password")

    if needs_rehash(user.hashed_password):
        await set_user_password(database, user, hash_password(password))

    return user


async def register_user(database: AsyncSession, data: UserCreate) -> User:
    """Регистрирует нового пользователя."""

    existing_email = await get_user_by_email(database, data.email)
    if existing_email is not None:
        raise ConflictError("Email already registered")

    try:
        user = await create_user(database, data)
    except IntegrityError as exc:
        raise ConflictError("Email already registered") from exc

    return user


def issue_tokens(user: User) -> TokenPair:
    """Выдаёт пару access + refresh токенов для пользователя."""
    if not user.is_active:
        raise AuthenticationError("User is not active")

    token_data = {"sub": str(user.id)}

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def change_password(
    database: AsyncSession,
    user: User,
    data: PasswordChange,
) -> None:
    """Меняет пароль после проверки текущего."""

    if not verify_password(data.current_password, user.hashed_password):
        raise AuthenticationError("Invalid current password")

    await set_user_password(
        database,
        user,
        hash_password(data.new_password),
    )


__all__ = [
    "authenticate_user",
    "change_password",
    "issue_tokens",
    "register_user",
]
