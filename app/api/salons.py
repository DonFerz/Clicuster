"""HTTP-роутер салонов."""

import logging
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.crud.salon import (
    create_salon as create_salon_crud,
    delete_salon as delete_salon_crud,
    get_salon,
    get_salons,
    get_salons_by_owner,
    update_salon as update_salon_crud,
)
from app.dependencies import (
    CurrentUser,
    DbSession,
    PaginationDep,
)
from app.models.enums import UserRole
from app.models.salon import Salon
from app.models.user import User
from app.schemas import (
    SalonCreate,
    SalonRead,
    SalonUpdate,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/salons",
    tags=["salons"],
)

# Положительный int для path-параметров (отсекает 0 и отрицательные до CRUD).
SalonId = Annotated[
    int,
    Path(ge=1, description="Идентификатор салона (положительное целое)"),
]


# ─────────── Хелпер ───────────

def _ensure_can_edit(salon: Salon, user: User) -> None:
    """Пускает владельца салона или админа. Иначе 403."""
    if user.role == UserRole.ADMIN:
        return
    if salon.owner_id == user.id:
        return
    raise PermissionDeniedError(
        "Only salon owner or admin can modify this salon"
    )


# ─────────── Публичные: список и один ───────────

@router.get(
    "",
    response_model=list[SalonRead],
    summary="Список салонов",
)
async def list_salons(
    db: DbSession,
    pagination: PaginationDep,
) -> list[Salon]:
    """Публичный список салонов с пагинацией.

    Фильтрация по статусу (`is_active` / `is_approved` / ...) — забота
    `get_salons` в CRUD; роутер лишь прокидывает skip/limit.
    """
    salons = await get_salons(db, skip=pagination.skip, limit=pagination.limit)
    return list(salons)


@router.get(
    "/my",
    response_model=list[SalonRead],
    summary="Мои салоны (как владельца)",
)
async def list_my_salons(
    db: DbSession,
    current_user: CurrentUser,
    pagination: PaginationDep,
) -> list[Salon]:
    salons = await get_salons_by_owner(
        db,
        current_user.id,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return list(salons)


# ВАЖНО: все статические пути (/my, /featured, ...) должны быть
# объявлены ДО этого параметрического роута, иначе они будут
# матчиться как {salon_id} и падать с 422.
@router.get(
    "/{salon_id}",
    response_model=SalonRead,
    summary="Салон по id",
)
async def get_salon_by_id(
    salon_id: SalonId,
    db: DbSession,
) -> Salon:
    """Публичная информация о салоне."""
    salon = await get_salon(db, salon_id)
    if salon is None:
        raise NotFoundError.by_id("Salon", salon_id)
    return salon


# ─────────── Создание ───────────

@router.post(
    "",
    response_model=SalonRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать салон",
)
async def create_new_salon(
    data: SalonCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Salon:
    """Создаёт салон. Текущий пользователь становится его владельцем.

    Бизнес-ограничения (роль пользователя, лимит салонов на одного
    владельца) — забота CRUD-слоя/сервиса; роутер их не дублирует.
    """
    salon = await create_salon_crud(db, data, owner_id=current_user.id)
    logger.info(
        "Salon created: id=%s owner_id=%s by user_id=%s",
        salon.id,
        salon.owner_id,
        current_user.id,
    )
    return salon


# ─────────── Обновление ───────────

@router.patch(
    "/{salon_id}",
    response_model=SalonRead,
    summary="Обновить салон (владелец или админ)",
)
async def update_existing_salon(
    salon_id: SalonId,
    data: SalonUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> Salon:
    """Обновляет салон. Доступно владельцу или админу."""
    salon = await get_salon(db, salon_id)
    if salon is None:
        raise NotFoundError.by_id("Salon", salon_id)

    _ensure_can_edit(salon, current_user)

    updated = await update_salon_crud(db, salon, data)
    logger.info(
        "Salon updated: id=%s by user_id=%s",
        salon_id,
        current_user.id,
    )
    return updated


# ─────────── Удаление ───────────

@router.delete(
    "/{salon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить салон (владелец или админ)",
)
async def delete_existing_salon(
    salon_id: SalonId,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Удаляет салон вместе с его мастерами и услугами (cascade)."""
    salon = await get_salon(db, salon_id)
    if salon is None:
        raise NotFoundError.by_id("Salon", salon_id)

    _ensure_can_edit(salon, current_user)

    await delete_salon_crud(db, salon)
    logger.info(
        "Salon deleted: id=%s by user_id=%s",
        salon_id,
        current_user.id,
    )


__all__ = ["router"]
