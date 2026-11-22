"""HTTP-роутер пользователей: профиль, смена пароля, админские операции.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • PATCH /users/me при попытке занять чужой email возвращал 500
    (IntegrityError) — теперь 409 Conflict;
  • добавлен PATCH /users/{user_id} (только админ): роль и блокировка.
    Раньше назначить администратора или заблокировать пользователя через
    API было невозможно;
  • DELETE /users/{user_id}: удаление пользователя со связанными данными
    (салоны/записи) раньше падало с 500 — теперь 409; нельзя удалить или
    разжаловать последнего активного администратора;
  • в списки добавлен заголовок X-Total-Count.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.exc import IntegrityError

from app.core.auth import change_password as change_password_logic
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.crud.user import (
    count_active_admins,
    count_users,
    get_user,
    get_users,
)
from app.crud.user import (
    delete_user as delete_user_crud,
)
from app.crud.user import (
    update_user as update_user_crud,
)
from app.crud.user import (
    update_user_admin as update_user_admin_crud,
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
    UserAdminUpdate,
    UserMe,
    UserPublic,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]

UserId = Annotated[
    int,
    Path(ge=1, description="Идентификатор пользователя (положительное целое)"),
]


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
    try:
        return await update_user_crud(db, current_user, data)
    except IntegrityError:
        # ДОБАВЛЕНО: уникальность email на уровне БД → 409, а не 500.
        raise ConflictError("Email already registered") from None


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
    response: Response,
) -> list[User]:
    """Возвращает список пользователей с пагинацией.

    Публичные данные (без email/phone).
    """
    users = await get_users(db, skip=pagination.skip, limit=pagination.limit)
    response.headers["X-Total-Count"] = str(await count_users(db))
    return list(users)


# ─────────── Публичный профиль ───────────
@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Публичный профиль пользователя",
    dependencies=[Depends(get_current_active_user)],
)
async def get_user_public(
    user_id: UserId,
    db: DbSession,
) -> User:
    """Публичный профиль любого пользователя.

    Требует аутентификации (любой активный пользователь).
    Не содержит email и phone.
    """
    user = await get_user(db, user_id)
    if user is None:
        raise NotFoundError.by_id("User", user_id)
    return user


# ─────────── Админское обновление ───────────
@router.patch(
    "/{user_id}",
    response_model=UserMe,
    summary="Обновить пользователя, роль или блокировку (только админ)",
)
async def update_user_by_admin(
    user_id: UserId,
    data: UserAdminUpdate,
    db: DbSession,
    admin: AdminUser,
) -> User:
    """Меняет профиль, роль и is_active.

    ДОБАВЛЕНО: единственный способ назначить администратора через API.
    Нельзя снять роль/заблокировать последнего активного админа.
    """
    user = await get_user(db, user_id)
    if user is None:
        raise NotFoundError.by_id("User", user_id)

    # ИСПРАВЛЕНО 22.11.2026: проверка «нельзя выключить себя» должна идти
    # ДО проверки последнего админа, иначе пользователь получал 409 вместо
    # понятного 403.
    if user_id == admin.id and data.is_active is False:
        raise PermissionDeniedError("Cannot deactivate yourself")

    demoting = (
        user.role == UserRole.ADMIN
        and (
            (data.role is not None and data.role != UserRole.ADMIN)
            or data.is_active is False
        )
    )
    if demoting and user.is_active:
        if await count_active_admins(db) <= 1:
            raise ConflictError("Cannot demote the last active administrator")

    try:
        return await update_user_admin_crud(db, user, data)
    except IntegrityError:
        raise ConflictError("Email already registered") from None


# ─────────── Удаление (только админ) ───────────
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление пользователя (только админ)",
)
async def delete_user_endpoint(
    user_id: UserId,
    db: DbSession,
    admin: AdminUser,
) -> None:
    """Удаляет пользователя.

    Нельзя удалить себя (защита от «остаться без админа») и последнего
    активного администратора.
    """
    if user_id == admin.id:
        raise PermissionDeniedError("Cannot delete yourself")

    user = await get_user(db, user_id)
    if user is None:
        raise NotFoundError.by_id("User", user_id)

    if user.role == UserRole.ADMIN and user.is_active:
        if await count_active_admins(db) <= 1:
            raise ConflictError("Cannot delete the last active administrator")

    try:
        await delete_user_crud(db, user)
    except IntegrityError:
        # Связанные салоны/записи не дают удалить пользователя.
        raise ConflictError(
            "Cannot delete user: related data exists "
            "(salons or appointments). Deactivate the user instead."
        ) from None


__all__ = ["router"]
