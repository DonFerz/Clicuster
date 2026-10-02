from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.appointment import Appointment
from app.models.master import Master
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate


# Цепочка eager-загрузки: у записи есть master (а у master — user),
# client и service. Все три нужны для AppointmentRead.
_APPOINTMENT_LOAD_OPTIONS = (
    selectinload(Appointment.master).selectinload(Master.user),
    selectinload(Appointment.client),
    selectinload(Appointment.service),
)


async def _get_appointment_full(
    database: AsyncSession, appointment_id: int
) -> Appointment:
    """Внутренний хелпер: загружает запись со всеми вложенными сущностями."""
    result = await database.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(*_APPOINTMENT_LOAD_OPTIONS)
    )
    return result.scalar_one()


async def create_appointment(
    database: AsyncSession,
    data: AppointmentCreate,
) -> Appointment:
    """Создание новой записи."""
    appointment = Appointment(
        client_id=data.client_id,
        master_id=data.master_id,
        service_id=data.service_id,
        start_time=data.start_time,
        end_time=data.end_time,
        comment=data.comment,
    )
    database.add(appointment)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return await _get_appointment_full(database, appointment.id)


async def get_appointment(
    database: AsyncSession,
    appointment_id: int,
) -> Appointment | None:
    """Поиск записи по id. Все вложенные сущности загружаются сразу."""
    result = await database.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(*_APPOINTMENT_LOAD_OPTIONS)
    )

    return result.scalar_one_or_none()


async def get_appointments(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Appointment]:
    """Список всех записей с пагинацией. Вложенные сущности загружаются сразу."""
    result = await database.execute(
        select(Appointment)
        .options(*_APPOINTMENT_LOAD_OPTIONS)
        .order_by(Appointment.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def get_appointments_by_client(
    database: AsyncSession,
    client_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Appointment]:
    """Записи конкретного клиента. Вложенные сущности загружаются сразу."""
    result = await database.execute(
        select(Appointment)
        .where(Appointment.client_id == client_id)
        .options(*_APPOINTMENT_LOAD_OPTIONS)
        .order_by(Appointment.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def get_appointments_by_master(
    database: AsyncSession,
    master_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Appointment]:
    """Записи конкретного мастера. Вложенные сущности загружаются сразу."""
    result = await database.execute(
        select(Appointment)
        .where(Appointment.master_id == master_id)
        .options(*_APPOINTMENT_LOAD_OPTIONS)
        .order_by(Appointment.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def update_appointment(
    database: AsyncSession,
    appointment: Appointment,
    data: AppointmentUpdate,
) -> Appointment:
    """Обновление переданных полей записи."""
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(appointment, field, value)

    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return await _get_appointment_full(database, appointment.id)


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
