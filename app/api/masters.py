"""HTTP-роутер мастеров салона.

Создание мастера = создание User + Master в одной транзакции
(см. app/crud/master.py::create_master).

Права:
- владелец салона управляет всеми мастерами своего салона;
- сам мастер редактирует свой профиль (position, description),
  но не может менять salon_id и is_active;
- админ управляет любыми мастерами.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Path, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.crud.master import (
    add_service_to_master,
    create_master as create_master_crud,
    delete_master as delete_master_crud,
    get_master,
    get_master_with_services,
    get_masters,
    get_masters_by_salon,
    remove_service_from_master,
    update_master as update_master_crud,
)
from app.crud.salon import get_salon
from app.crud.service import get_service
from app.dependencies import (
    CurrentUser,
    DbSession,
    PaginationDep,
)
from app.models.enums import UserRole
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.schemas import (
    MasterCreate,
    MasterRead,
    MasterUpdate,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/masters", tags=["masters"])

MasterId = Annotated[
    int,
    Path(ge=1, description="Идентификатор мастера (положительное целое)"),
]
ServiceId = Annotated[
    int,
    Path(ge=1, description="Идентификатор услуги (положительное целое)"),
]


# ─────────── Хелперы ───────────

def _ensure_can_manage_salon(salon: Salon, user: User) -> None:
    """Пускает владельца салона или админа. Иначе 403."""
    if user.role == UserRole.ADMIN:
        return
    if salon.owner_id == user.id:
        return
    raise PermissionDeniedError(
        "Only salon owner or admin can manage masters of this salon"
    )


def _ensure_can_edit_master(
    master: Master,
    salon: Salon,
    user: User,
) -> None:
    """Пускает владельца салона, самого мастера или админа. Иначе 403."""
    if user.role == UserRole.ADMIN:
        return
    if salon.owner_id == user.id:
        return
    if master.user_id == user.id:
        return
    raise PermissionDeniedError(
        "Only salon owner, the master himself, or admin can edit this master"
    )


def _is_owner_or_admin(salon: Salon, user: User) -> bool:
    """True, если пользователь — владелец салона или админ."""
    return user.role == UserRole.ADMIN or salon.owner_id == user.id


async def _get_salon_or_404(db: AsyncSession, salon_id: int) -> Salon:
    """Достаёт салон или бросает 404."""
    salon = await get_salon(db, salon_id)
    if salon is None:
        raise NotFoundError.by_id("Salon", salon_id)
    return salon


async def _get_master_or_404(db: AsyncSession, master_id: int) -> Master:
    """Достаёт мастера или бросает 404."""
    master = await get_master(db, master_id)
    if master is None:
        raise NotFoundError.by_id("Master", master_id)
    return master


# ─────────── Публичные: список и один ───────────

@router.get(
    "",
    response_model=list[MasterRead],
    summary="Список мастеров (с фильтром по салону)",
)
async def list_masters(
    db: DbSession,
    pagination: PaginationDep,
    salon_id: Annotated[
        int | None,
        Query(ge=1, description="Фильтр: мастера конкретного салона"),
    ] = None,
) -> list[Master]:
    """Публичный список мастеров.

    Без `salon_id` — все мастера с пагинацией.
    С `salon_id` — мастера конкретного салона.
    """
    if salon_id is not None:
        masters = await get_masters_by_salon(
            db,
            salon_id=salon_id,
            skip=pagination.skip,
            limit=pagination.limit,
        )
    else:
        masters = await get_masters(
            db,
            skip=pagination.skip,
            limit=pagination.limit,
        )
    return list(masters)


@router.get(
    "/{master_id}",
    response_model=MasterRead,
    summary="Мастер по id",
)
async def get_master_by_id(
    master_id: MasterId,
    db: DbSession,
) -> Master:
    """Публичная информация о мастере."""
    return await _get_master_or_404(db, master_id)


# ─────────── Создание ───────────

@router.post(
    "",
    response_model=MasterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать мастера (владелец салона или админ)",
)
async def create_new_master(
    data: MasterCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Master:
    """Создаёт User + Master в одной транзакции.

    Email должен быть уникален — иначе 409.
    Права проверяются на салон (`data.salon_id`).
    """
    salon = await _get_salon_or_404(db, data.salon_id)
    _ensure_can_manage_salon(salon, current_user)

    try:
        master = await create_master_crud(db, data)
    except IntegrityError as exc:
        # Различаем по constraint name. str(exc.orig) у asyncpg
        # содержит имя нарушенного constraint'а (например,
        # "duplicate key value violates unique constraint \"ix_users_email\"").
        msg = str(exc.orig).lower()
        logger.warning(
            "Master create IntegrityError: %s (by user_id=%s)",
            exc.orig,
            current_user.id,
        )
        if "email" in msg:
            raise ConflictError(
                "User with this email already exists"
            ) from None
        if "phone" in msg:
            raise ConflictError(
                "User with this phone already exists"
            ) from None
        if "salon_id" in msg or "foreign key" in msg:
            raise ConflictError(
                "Salon does not exist (was it deleted?)"
            ) from None
        # Неизвестный constraint — не маскируем, пусть уйдёт как 500.
        raise

    logger.info(
        "Master created: id=%s user_id=%s salon_id=%s by user_id=%s",
        master.id,
        master.user_id,
        master.salon_id,
        current_user.id,
    )
    return master


# ─────────── Обновление ───────────

@router.patch(
    "/{master_id}",
    response_model=MasterRead,
    summary="Обновить мастера (владелец салона, сам мастер или админ)",
)
async def update_existing_master(
    master_id: MasterId,
    data: MasterUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> Master:
    """Обновляет профиль мастера.

    Доступно владельцу салона, самому мастеру или админу.

    Сам мастер может менять только `position` и `description`.
    Поля `salon_id` и `is_active` доступны только владельцу салона
    или админу — иначе мастер мог бы самовольно перевести себя
    в чужой салон или снять блокировку.
    """
    master = await _get_master_or_404(db, master_id)
    salon = await _get_salon_or_404(db, master.salon_id)
    _ensure_can_edit_master(master, salon, current_user)

    # Если это не owner/admin (значит, сам мастер) — запрещаем менять
    # привилегированные поля. Проверяем именно то, что клиент прислал
    # (model_fields_set), а не всё Optional-поле.
    if not _is_owner_or_admin(salon, current_user):
        forbidden_fields = {"salon_id", "is_active"} & data.model_fields_set
        if forbidden_fields:
            raise PermissionDeniedError(
                "Cannot change fields: "
                + ", ".join(sorted(forbidden_fields))
            )

    try:
        updated = await update_master_crud(db, master, data)
    except IntegrityError as exc:
        msg = str(exc.orig).lower()
        logger.warning(
            "Master update IntegrityError: %s (by user_id=%s)",
            exc.orig,
            current_user.id,
        )
        if "salon_id" in msg or "foreign key" in msg:
            raise ConflictError(
                "Salon does not exist (was it deleted?)"
            ) from None
        raise

    logger.info(
        "Master updated: id=%s by user_id=%s",
        master_id,
        current_user.id,
    )
    return updated


# ─────────── Удаление ───────────

@router.delete(
    "/{master_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить мастера (владелец салона или админ)",
)
async def delete_existing_master(
    master_id: MasterId,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Удаляет профиль мастера.

    Учётная запись User остаётся.

    Если на мастера ссылаются `appointments` без ON DELETE CASCADE,
    удаление отклоняется с 409 Conflict.
    """
    master = await _get_master_or_404(db, master_id)
    salon = await _get_salon_or_404(db, master.salon_id)
    _ensure_can_manage_salon(salon, current_user)

    try:
        await delete_master_crud(db, master)
    except IntegrityError as exc:
        logger.warning(
            "Master delete IntegrityError: %s (by user_id=%s)",
            exc.orig,
            current_user.id,
        )
        raise ConflictError(
            "Cannot delete master: it has related appointments"
        ) from None

    logger.info(
        "Master deleted: id=%s by user_id=%s",
        master_id,
        current_user.id,
    )


# ─────────── Управление услугами мастера ───────────

@router.post(
    "/{master_id}/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Добавить услугу мастеру (владелец салона или админ)",
)
async def attach_service(
    master_id: MasterId,
    service_id: ServiceId,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Привязывает услугу к мастеру.

    Услуга должна принадлежать тому же салону, что и мастер.
    Идемпотентно: если услуга уже привязана — no-op.
    """
    master = await get_master_with_services(db, master_id)
    if master is None:
        raise NotFoundError.by_id("Master", master_id)

    service = await get_service(db, service_id)
    if service is None:
        raise NotFoundError.by_id("Service", service_id)

    if service.salon_id != master.salon_id:
        raise PermissionDeniedError(
            "Service belongs to a different salon"
        )

    salon = await _get_salon_or_404(db, master.salon_id)
    _ensure_can_manage_salon(salon, current_user)

    await add_service_to_master(db, master, service)
    logger.info(
        "Master service attached: master_id=%s service_id=%s by user_id=%s",
        master_id,
        service_id,
        current_user.id,
    )


@router.delete(
    "/{master_id}/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать услугу у мастера (владелец салона или админ)",
)
async def detach_service(
    master_id: MasterId,
    service_id: ServiceId,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Убирает привязку услуги к мастеру.

    Идемпотентно: если услуга не привязана — no-op.
    """
    master = await get_master_with_services(db, master_id)
    if master is None:
        raise NotFoundError.by_id("Master", master_id)

    service = await get_service(db, service_id)
    if service is None:
        raise NotFoundError.by_id("Service", service_id)

    salon = await _get_salon_or_404(db, master.salon_id)
    _ensure_can_manage_salon(salon, current_user)

    await remove_service_from_master(db, master, service)
    logger.info(
        "Master service detached: master_id=%s service_id=%s by user_id=%s",
        master_id,
        service_id,
        current_user.id,
    )


__all__ = ["router"]
