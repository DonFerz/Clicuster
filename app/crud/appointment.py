from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.appointment import Appointment
from app.models.enums import RecordStatus
from app.models.master import Master
from app.models.salon import Salon

# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • _get_appointment_full больше не падает с NoResultFound (→ 500), если
#     запись удалили параллельно — возвращает None;
#   • eager-загрузка дополнена салоном мастера: проверка прав
#     «владелец салона?» больше не делает лишний запрос в каждой строке
#     (и не падает с MissingGreenlet);
#   • добавлены list_appointments с фильтрами, has_overlapping_appointment
#     (проверка двойной записи) и count_appointments;
#   • create_appointment больше не принимает end_time от клиента — его
#     вычисляет бизнес-слой (app/core/appointments.py).

# Цепочка eager-загрузки: у записи есть master (а у master — user и salon),
# client и service. Всё это нужно для AppointmentRead и проверки прав.
_APPOINTMENT_LOAD_OPTIONS = (
    selectinload(Appointment.master).selectinload(Master.user),
    selectinload(Appointment.master).selectinload(Master.salon),
    selectinload(Appointment.client),
    selectinload(Appointment.service),
)


async def _get_appointment_full(
    database: AsyncSession, appointment_id: int
) -> Appointment | None:
    """Внутренний хелпер: загружает запись со всеми вложенными сущностями."""
    result = await database.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(*_APPOINTMENT_LOAD_OPTIONS)
    )
    return result.scalar_one_or_none()


async def create_appointment(
    database: AsyncSession,
    *,
    client_id: int,
    master_id: int,
    service_id: int,
    start_time: datetime,
    end_time: datetime,
    comment: str | None = None,
    status: RecordStatus = RecordStatus.PENDING,
) -> Appointment:
    """Создание новой записи.

    Вызывать только из app/core/appointments.py: там проверяются права,
    пересечения и удерживается блокировка мастера.
    """
    appointment = Appointment(
        client_id=client_id,
        master_id=master_id,
        service_id=service_id,
        start_time=start_time,
        end_time=end_time,
        status=status,
        comment=comment,
    )
    database.add(appointment)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    created = await _get_appointment_full(database, appointment.id)
    if created is None:
        raise NotFoundError.by_id("Appointment", appointment.id)
    return created


async def get_appointment(
    database: AsyncSession,
    appointment_id: int,
) -> Appointment | None:
    """Поиск записи по id. Все вложенные сущности загружаются сразу."""
    return await _get_appointment_full(database, appointment_id)


def _apply_scope(
    stmt,
    *,
    user_id: int | None,
    include_all: bool,
    salon_id: int | None,
    client_id: int | None,
    master_id: int | None,
    status: RecordStatus | None,
    date_from: datetime | None,
    date_to: datetime | None,
):
    """Общая часть фильтрации для list/count.

    include_all=False ограничивает выборку только «своими» записями:
    клиент — где он клиент, мастер — где он мастер, владелец — где он
    владелец салона. Условия объединяются через OR, поэтому один и тот же
    человек может быть и клиентом, и владельцем.
    """
    stmt = stmt.join(Master, Master.id == Appointment.master_id).join(
        Salon, Salon.id == Master.salon_id
    )

    if not include_all and user_id is not None:
        stmt = stmt.where(
            or_(
                Appointment.client_id == user_id,
                Master.user_id == user_id,
                Salon.owner_id == user_id,
            )
        )
    if salon_id is not None:
        stmt = stmt.where(Master.salon_id == salon_id)
    if client_id is not None:
        stmt = stmt.where(Appointment.client_id == client_id)
    if master_id is not None:
        stmt = stmt.where(Appointment.master_id == master_id)
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    if date_from is not None:
        stmt = stmt.where(Appointment.start_time >= date_from)
    if date_to is not None:
        stmt = stmt.where(Appointment.start_time <= date_to)
    return stmt


async def list_appointments(
    database: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 20,
    user_id: int | None = None,
    include_all: bool = False,
    client_id: int | None = None,
    master_id: int | None = None,
    salon_id: int | None = None,
    status: RecordStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Sequence[Appointment]:
    """Список записей под фильтром с пагинацией.

    date_from/date_to сравниваются с start_time (границы включительно).
    """
    stmt = _apply_scope(
        select(Appointment).options(*_APPOINTMENT_LOAD_OPTIONS),
        user_id=user_id,
        include_all=include_all,
        salon_id=salon_id,
        client_id=client_id,
        master_id=master_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )

    result = await database.execute(
        stmt.order_by(Appointment.start_time, Appointment.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def count_appointments(
    database: AsyncSession,
    *,
    user_id: int | None = None,
    include_all: bool = False,
    client_id: int | None = None,
    master_id: int | None = None,
    salon_id: int | None = None,
    status: RecordStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    """Количество записей под фильтром (для пагинации)."""
    stmt = _apply_scope(
        select(func.count()).select_from(Appointment),
        user_id=user_id,
        include_all=include_all,
        salon_id=salon_id,
        client_id=client_id,
        master_id=master_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return int((await database.execute(stmt)).scalar_one())


async def has_overlapping_appointment(
    database: AsyncSession,
    *,
    master_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_id: int | None = None,
) -> bool:
    """Есть ли у мастера активная запись, пересекающаяся с интервалом.

    ДОБАВЛЕНО: интервалы считаются полуоткрытыми [start, end) — запись
    «10:00-11:00» и «11:00-12:00» не конфликтуют. Отменённые записи
    не учитываются.
    """
    stmt = (
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.master_id == master_id,
            Appointment.status != RecordStatus.CANCELLED,
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(Appointment.id != exclude_id)
    return int((await database.execute(stmt)).scalar_one()) > 0


async def update_appointment(
    database: AsyncSession,
    appointment: Appointment,
    values: dict[str, Any],
) -> Appointment:
    """Применяет уже проверенные бизнес-слоем значения и коммитит."""
    for field, value in values.items():
        setattr(appointment, field, value)

    appointment_id = appointment.id

    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    updated = await _get_appointment_full(database, appointment_id)
    if updated is None:
        raise NotFoundError.by_id("Appointment", appointment_id)
    return updated


async def delete_appointment(
    database: AsyncSession,
    appointment: Appointment,
) -> None:
    """Удаление записи."""
    try:
        await database.delete(appointment)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
