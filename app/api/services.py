"""HTTP-роутер услуг салона.

Услуга принадлежит салону. Права на управление услугой
определяются правами на её салон (владелец или админ).
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
from app.crud.salon import get_salon
from app.crud.service import (
    create_service as create_service_crud,
    delete_service as delete_service_crud,
    get_service,
    get_services,
    get_services_by_salon,
    update_service as update_service_crud,
)
from app.dependencies import (
    CurrentUser,
    DbSession,
    PaginationDep,
)
from app.models.enums import UserRole
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.schemas import (
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])

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
        "Only salon owner or admin can manage services of this salon"
    )


async def _get_salon_or_404(db: AsyncSession, salon_id: int) -> Salon:
    """Достаёт салон или бросает 404."""
    salon = await get_salon(db, salon_id)
    if salon is None:
        raise NotFoundError.by_id("Salon", salon_id)
    return salon


async def _get_service_or_404(db: AsyncSession, service_id: int) -> Service:
    """Достаёт услугу или бросает 404."""
    service = await get_service(db, service_id)
    if service is None:
        raise NotFoundError.by_id("Service", service_id)
    return service


async def _get_service_with_permission_or_404(
    db: AsyncSession,
    service_id: int,
    user: User,
) -> Service:
    """Достаёт услугу, её салон и проверяет права пользователя.

    Единая точка для PATCH/DELETE: гарантирует, что права проверены
    именно на тот салон, которому услуга принадлежит сейчас.
    """
    service = await _get_service_or_404(db, service_id)
    salon = await _get_salon_or_404(db, service.salon_id)
    _ensure_can_manage_salon(salon, user)
    return service


# ─────────── Публичные: список и один ───────────

@router.get(
    "",
    response_model=list[ServiceRead],
    summary="Список услуг (с фильтром по салону)",
)
async def list_services(
    db: DbSession,
    pagination: PaginationDep,
    salon_id: Annotated[
        int | None,
        Query(ge=1, description="Фильтр: услуги конкретного салона"),
    ] = None,
) -> list[Service]:
    """Публичный список услуг.

    Без `salon_id` — все услуги с пагинацией.
    С `salon_id` — услуги конкретного салона.

    Если `salon_id` указывает на несуществующий салон, возвращается
    пустой список (а не 404) — это осознанное поведение публичного
    листинга.
    """
    if salon_id is not None:
        services = await get_services_by_salon(
            db,
            salon_id=salon_id,
            skip=pagination.skip,
            limit=pagination.limit,
        )
    else:
        services = await get_services(
            db,
            skip=pagination.skip,
            limit=pagination.limit,
        )
    return list(services)


@router.get(
    "/{service_id}",
    response_model=ServiceRead,
    summary="Услуга по id",
)
async def get_service_by_id(
    service_id: ServiceId,
    db: DbSession,
) -> Service:
    """Публичная информация об услуге."""
    return await _get_service_or_404(db, service_id)


# ─────────── Создание ───────────

@router.post(
    "",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать услугу (владелец салона или админ)",
)
async def create_new_service(
    data: ServiceCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Service:
    """Создаёт услугу в указанном салоне.

    Права проверяются на салон: создавать услуги может владелец
    салона (`data.salon_id`) или админ.
    """
    salon = await _get_salon_or_404(db, data.salon_id)
    _ensure_can_manage_salon(salon, current_user)

    service = await create_service_crud(db, data)
    logger.info(
        "Service created: id=%s salon_id=%s by user_id=%s",
        service.id,
        service.salon_id,
        current_user.id,
    )
    return service


# ─────────── Обновление ───────────

@router.patch(
    "/{service_id}",
    response_model=ServiceRead,
    summary="Обновить услугу (владелец салона или админ)",
)
async def update_existing_service(
    service_id: ServiceId,
    data: ServiceUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> Service:
    """Обновляет услугу.

    Права проверяются на салон, которому услуга принадлежит сейчас.
    `ServiceUpdate` не содержит `salon_id` — перенос услуги между
    салонами через этот эндпоинт невозможен. Если такая фича
    понадобится — отдельный эндпоинт с проверкой прав на оба салона
    (текущий и целевой).
    """
    service = await _get_service_with_permission_or_404(
        db, service_id, current_user,
    )

    updated = await update_service_crud(db, service, data)
    logger.info(
        "Service updated: id=%s by user_id=%s",
        service_id,
        current_user.id,
    )
    return updated


# ─────────── Удаление ───────────

@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить услугу (владелец салона или админ)",
)
async def delete_existing_service(
    service_id: ServiceId,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Удаляет услугу.

    Связанные записи `master_services` удалятся каскадно
    (ассоциативная таблица). Если на услугу ссылаются существующие
    `Appointment` без `ON DELETE`-правила, удаление отклоняется с 409.
    """
    service = await _get_service_with_permission_or_404(
        db, service_id, current_user,
    )

    try:
        await delete_service_crud(db, service)
    except IntegrityError:
        logger.warning(
            "Service delete conflict: id=%s by user_id=%s "
            "(related appointments exist)",
            service_id,
            current_user.id,
        )
        raise ConflictError(
            "Cannot delete service: it has related appointments"
        ) from None

    logger.info(
        "Service deleted: id=%s by user_id=%s",
        service_id,
        current_user.id,
    )


__all__ = ["router"]
