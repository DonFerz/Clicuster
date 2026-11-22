"""HTTP-роутер записей клиентов (appointments).

ФАЙЛ БЫЛ ПУСТЫМ — роутер не был подключён к приложению, то есть главной
функции CRM (онлайн-запись) не существовало. РЕАЛИЗОВАНО 22.11.2026:

  POST   /appointments            — создать запись (клиент или сотрудник);
  GET    /appointments            — список доступных записей с фильтрами;
  GET    /appointments/{id}       — одна запись;
  PATCH  /appointments/{id}       — перенос/статус/комментарий;
  DELETE /appointments/{id}       — удаление (владелец салона или админ).

Права и бизнес-правила — в app/core/appointments.py.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from pydantic import AwareDatetime

from app.core.appointments import (
    count_visible_appointments,
    create_booking,
    delete_booking,
    get_booking_or_404,
    list_visible_appointments,
    update_booking,
)
from app.dependencies import (
    CurrentUser,
    DbSession,
    PaginationDep,
)
from app.models.appointment import Appointment
from app.models.enums import RecordStatus
from app.schemas import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

AppointmentId = Annotated[
    int,
    Path(ge=1, description="Идентификатор записи (положительное целое)"),
]


# ─────────── Создание ───────────

@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать запись",
)
async def create_new_appointment(
    data: AppointmentCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Appointment:
    """Записывает клиента к мастеру.

    * Время окончания считается на сервере по длительности услуги.
    * Нельзя записаться в прошлое (см. BOOKING_MIN_LEAD_MINUTES).
    * Двойная запись к одному мастеру невозможна — 409 Conflict.
    * `client_id` может передать только сотрудник салона; обычный клиент
      всегда записывается сам.
    """
    return await create_booking(db, current_user, data)


# ─────────── Список ───────────

@router.get(
    "",
    response_model=list[AppointmentRead],
    summary="Список записей (только доступные пользователю)",
)
async def list_appointments(
    db: DbSession,
    current_user: CurrentUser,
    pagination: PaginationDep,
    response: Response,
    client_id: Annotated[
        int | None, Query(ge=1, description="Фильтр по клиенту")
    ] = None,
    master_id: Annotated[
        int | None, Query(ge=1, description="Фильтр по мастеру")
    ] = None,
    salon_id: Annotated[
        int | None, Query(ge=1, description="Фильтр по салону")
    ] = None,
    status_filter: Annotated[
        RecordStatus | None,
        Query(alias="status", description="Фильтр по статусу записи"),
    ] = None,
    date_from: Annotated[
        AwareDatetime | None,
        Query(description="Начало периода (по start_time, включительно)"),
    ] = None,
    date_to: Annotated[
        AwareDatetime | None,
        Query(description="Конец периода (по start_time, включительно)"),
    ] = None,
) -> list[Appointment]:
    """Возвращает записи, которые пользователь вправе видеть.

    Клиент видит свои записи, мастер — записи к себе, владелец салона —
    все записи своих салонов, администратор — все записи.
    Фильтры не расширяют область видимости, а только сужают её.
    """
    appointments = await list_visible_appointments(
        db,
        current_user,
        skip=pagination.skip,
        limit=pagination.limit,
        client_id=client_id,
        master_id=master_id,
        salon_id=salon_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
    )
    response.headers["X-Total-Count"] = str(
        await count_visible_appointments(
            db,
            current_user,
            client_id=client_id,
            master_id=master_id,
            salon_id=salon_id,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
        )
    )
    return appointments


# ─────────── Одна запись ───────────

@router.get(
    "/{appointment_id}",
    response_model=AppointmentRead,
    summary="Запись по id",
)
async def get_appointment_by_id(
    appointment_id: AppointmentId,
    db: DbSession,
    current_user: CurrentUser,
) -> Appointment:
    """Доступна только участникам записи (клиент/мастер/владелец/админ)."""
    return await get_booking_or_404(db, current_user, appointment_id)


# ─────────── Изменение ───────────

@router.patch(
    "/{appointment_id}",
    response_model=AppointmentRead,
    summary="Перенести запись, сменить статус или комментарий",
)
async def update_existing_appointment(
    appointment_id: AppointmentId,
    data: AppointmentUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> Appointment:
    """Обновляет запись.

    * клиент может отменить свою будущую запись и оставить комментарий;
    * мастер может подтвердить/завершить/отменить запись к себе;
    * владелец салона и админ — любые допустимые переходы статусов.

    Недопустимый переход (например, completed → pending) — 409.
    """
    appointment = await get_booking_or_404(db, current_user, appointment_id)
    return await update_booking(db, current_user, appointment, data)


# ─────────── Удаление ───────────

@router.delete(
    "/{appointment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить запись (владелец салона или админ)",
)
async def delete_existing_appointment(
    appointment_id: AppointmentId,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Безвозвратно удаляет запись.

    Обычная отмена записи — это PATCH со статусом `cancelled`;
    DELETE оставлен для административных/ошибочных записей.
    """
    appointment = await get_booking_or_404(db, current_user, appointment_id)
    await delete_booking(db, current_user, appointment)


__all__ = ["router"]
