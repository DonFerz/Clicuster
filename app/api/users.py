"""HTTP-роутер пользователей: профиль, смена пароля, админские операции."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.auth import change_password as change_password_logic
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.crud.user import (
    delete_user as delete_user_crud,
    get_user,
    get_users,
    update_user as update_user_crud,
)
from app.dependencies import (
    CurrentUser,
    DbSession,
    PaginationDep,
    require_role,
)
from app.dependencies.auth import get_current_active_user
from app.models.enums import UserRole
from app.models.user import User
from app.schemas import (
    PasswordChange,
    UserMe,
    UserPublic,
    UserUpdate,
)


router = APIRouter(prefix="/users", tags=["users"])


# ─────────── Свой профиль ───────────
@router.get(
    "/me",
    response_model=UserMe,
    summary="Профиль текущего пользователя",
)
async def get_me(current_user: CurrentUser) -> User:
    """Возвращает полный профиль текущего пользователя (с email и phone)."""
    return current_user


@router.patch(
    "/me",
    response_model=UserMe,
    summary="Обновление своего профиля",
)
async def update_me(
    data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> User:
    """Обновляет full_name, email, phone текущего пользователя.

    Схема UserUpdate запрещает лишние поля (extra="forbid"),
    поэтому попытка передать role, is_active и т. п. вернёт 422.
    CRUD-слой дополнительно ограничивает набор обновляемых полей
    через _UPDATABLE_USER_FIELDS — защита в глубину.
    """
    return await update_user_crud(db, current_user, data)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Смена пароля",
)
async def change_my_password(
    data: PasswordChange,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Меняет пароль после проверки текущего.

    Если `current_password` не совпадает — 401 (из `change_password_logic`).
    Если `new_password` совпадает с `current_password` — 422 (валидация схемы).
    """
    await change_password_logic(db, current_user, data)


# ─────────── Список (только админ) ───────────
@router.get(
    "",
    response_model=list[UserPublic],
    summary="Список пользователей (только админ)",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def list_users(
    db: DbSession,
    pagination: PaginationDep,
) -> list[User]:
    """Возвращает список пользователей с пагинацией.

    Публичные данные (без email/phone).
    """
    users = await get_users(db, skip=pagination.skip, limit=pagination.limit)
    return list(users)


# ─────────── Публичный профиль ───────────
@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Публичный профиль пользователя",
    dependencies=[Depends(get_current_active_user)],
)
async def get_user_public(user_id: int, db: DbSession) -> User:
    """Публичный профиль любого пользователя.

    Требует аутентификации (любой активный пользователь).
    Не содержит email и phone.
    """
    user = await get_user(db, user_id)
    if user is None:
        raise NotFoundError.by_id("User", user_id)
    return user


# ─────────── Удаление (только админ) ───────────
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление пользователя (только админ)",
)
async def delete_user_endpoint(
    user_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> None:
    """Удаляет пользователя.

    Нельзя удалить себя (защита от «остаться без админа»).
    """
    if user_id == admin.id:
        raise PermissionDeniedError("Cannot delete yourself")

    user = await get_user(db, user_id)
    if user is None:
        raise NotFoundError.by_id("User", user_id)

    await delete_user_crud(db, user)


__all__ = ["router"]
