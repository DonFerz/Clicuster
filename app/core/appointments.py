"""Бизнес-логика записей клиентов (appointments).

ФАЙЛ БЫЛ ПУСТЫМ. РЕАЛИЗОВАНО 22.11.2026 в рамках аудита:
  • создание записи с проверкой прав, доступности мастера/услуги/салона;
  • расчёт времени окончания на сервере (клиент не может его подделать);
  • защита от двойной записи: блокировка строки мастера (SELECT FOR UPDATE)
    + проверка пересечения интервалов + EXCLUDE-ограничение в PostgreSQL;
  • конечный автомат статусов (pending → confirmed → completed / cancelled);
  • разграничение прав: клиент видит/отменяет только свои записи, мастер —
    свои, владелец салона — все записи своего салона, админ — все;
  • единая проверка «свой/чужой» запись для чтения и изменения.

Раньше файлы app/core/appointments.py и app/api/appointments.py были пустыми,
то есть главная функция CRM (онлайн-запись) отсутствовала.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.crud.appointment import (
    count_appointments,
    create_appointment,
    delete_appointment,
    get_appointment,
    has_overlapping_appointment,
    list_appointments,
    update_appointment,
)
from app.crud.master import get_master_with_services, lock_master
from app.crud.salon import get_salon
from app.crud.service import get_service
from app.crud.user import get_user
from app.models.appointment import Appointment
from app.models.enums import RecordStatus, UserRole
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate
from app.utils.timezone import to_utc, utcnow

# ─────────── Статусы ───────────

# Разрешённые переходы. completed/cancelled — финальные.
_ALLOWED_TRANSITIONS: dict[RecordStatus, frozenset[RecordStatus]] = {
    RecordStatus.PENDING: frozenset(
        {RecordStatus.CONFIRMED, RecordStatus.CANCELLED, RecordStatus.COMPLETED}
    ),
    RecordStatus.CONFIRMED: frozenset(
        {RecordStatus.COMPLETED, RecordStatus.CANCELLED}
    ),
    RecordStatus.COMPLETED: frozenset(),
    RecordStatus.CANCELLED: frozenset(),
}

_BOOKED_MESSAGE = "Master is already booked for this time"


# ─────────── Права ───────────

def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def can_manage_salon(salon: Salon, user: User) -> bool:
    """Владелец салона или администратор."""
    return is_admin(user) or salon.owner_id == user.id


def is_master_of(master: Master, user: User) -> bool:
    return master.user_id == user.id


def is_salon_staff(master: Master, salon: Salon, user: User) -> bool:
    """Сотрудник салона: админ, владелец или сам мастер."""
    return is_admin(user) or can_manage_salon(salon, user) or is_master_of(
        master, user
    )


def ensure_can_access(appointment: Appointment, user: User) -> None:
    """Пускает клиента записи, её мастера, владельца салона и админа."""
    if is_admin(user):
        return
    if appointment.client_id == user.id:
        return
    master = appointment.master
    if master.user_id == user.id:
        return
    if master.salon.owner_id == user.id:
        return
    raise PermissionDeniedError("You have no access to this appointment")


def ensure_can_delete(appointment: Appointment, user: User) -> None:
    """Удалять записи (безвозвратно) может только владелец салона или админ."""
    if is_admin(user) or appointment.master.salon.owner_id == user.id:
        return
    raise PermissionDeniedError(
        "Only salon owner or admin can delete appointments"
    )


# ─────────── Проверки ───────────

async def _resolve_targets(
    database: AsyncSession,
    master_id: int,
    service_id: int,
) -> tuple[Master, Salon, Service]:
    """Достаёт мастера, салон и услугу и проверяет их согласованность."""
    master = await get_master_with_services(database, master_id)
    if master is None:
        raise NotFoundError.by_id("Master", master_id)

    salon = await get_salon(database, master.salon_id)
    if salon is None:
        raise NotFoundError.by_id("Salon", master.salon_id)

    service = await get_service(database, service_id)
    if service is None:
        raise NotFoundError.by_id("Service", service_id)

    if service.salon_id != master.salon_id:
        raise ValidationError(
            "Service belongs to another salon",
            fields={"service_id": "service is not provided in the master's salon"},
        )
    if not salon.is_active:
        raise ConflictError("Salon is not active")
    if not master.is_active:
        raise ConflictError("Master is not active")
    if not service.is_active:
        raise ConflictError("Service is not active")
    if all(s.id != service.id for s in master.services):
        raise ValidationError(
            "Master does not provide this service",
            fields={"service_id": "master is not linked to this service"},
        )

    return master, salon, service


def _validate_start_time(start_time) -> None:
    """Проверяет, что время записи в допустимом окне."""
    now = utcnow()
    earliest = now + timedelta(minutes=settings.BOOKING_MIN_LEAD_MINUTES)
    latest = now + timedelta(days=settings.BOOKING_HORIZON_DAYS)

    if start_time < earliest:
        raise ValidationError(
            "start_time must be in the future",
            fields={"start_time": "time has already passed"},
        )
    if start_time > latest:
        raise ValidationError(
            "start_time is too far in the future",
            fields={
                "start_time": f"booking horizon is {settings.BOOKING_HORIZON_DAYS} days"
            },
        )


def _validate_transition(
    current: RecordStatus,
    new: RecordStatus,
) -> None:
    if new == current:
        return
    if new not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ConflictError(
            f"Cannot change status from '{current.value}' to '{new.value}'"
        )


# ─────────── Создание ───────────

async def create_booking(
    database: AsyncSession,
    user: User,
    data: AppointmentCreate,
) -> Appointment:
    """Создаёт запись.

    Текущий пользователь по умолчанию становится клиентом. Сотрудник салона
    (владелец/мастер/админ) может указать ``client_id`` другого клиента.
    """
    master, salon, service = await _resolve_targets(
        database, data.master_id, data.service_id
    )

    client_id = data.client_id if data.client_id is not None else user.id
    if client_id != user.id:
        if not is_salon_staff(master, salon, user):
            raise PermissionDeniedError(
                "Only salon staff can create an appointment for another client"
            )
        client = await get_user(database, client_id)
        if client is None:
            raise NotFoundError.by_id("User", client_id)
        if not client.is_active:
            raise ConflictError("Client account is inactive")

    start_time = to_utc(data.start_time)
    _validate_start_time(start_time)
    end_time = start_time + timedelta(minutes=service.duration_minutes)

    # Блокируем мастера, чтобы параллельная заявка не прошла между
    # проверкой пересечения и INSERT.
    locked = await lock_master(database, master.id)
    if locked is None:
        raise NotFoundError.by_id("Master", master.id)
    if not locked.is_active:
        raise ConflictError("Master is not active")

    if await has_overlapping_appointment(
        database,
        master_id=master.id,
        start_time=start_time,
        end_time=end_time,
    ):
        raise ConflictError(_BOOKED_MESSAGE)

    try:
        return await create_appointment(
            database,
            client_id=client_id,
            master_id=master.id,
            service_id=service.id,
            start_time=start_time,
            end_time=end_time,
            comment=data.comment,
        )
    except IntegrityError:
        # Сработало EXCLUDE-ограничение в БД (гонка между процессами).
        raise ConflictError(_BOOKED_MESSAGE) from None


# ─────────── Изменение ───────────

async def update_booking(
    database: AsyncSession,
    user: User,
    appointment: Appointment,
    data: AppointmentUpdate,
) -> Appointment:
    """Перенос/смена статуса/комментарий с проверкой прав."""
    ensure_can_access(appointment, user)

    admin = is_admin(user)
    owner = appointment.master.salon.owner_id == user.id
    master_of = appointment.master.user_id == user.id
    client_of = appointment.client_id == user.id
    staff = admin or owner or master_of

    values: dict[str, Any] = {}
    now = utcnow()

    if data.status is not None:
        _validate_transition(appointment.status, data.status)
        if client_of and not staff:
            # Клиент может только отменить свою будущую запись.
            if data.status != RecordStatus.CANCELLED:
                raise PermissionDeniedError(
                    "Clients can only cancel appointments"
                )
            if appointment.start_time <= now:
                raise ValidationError(
                    "Cannot cancel an appointment that has already started"
                )
        values["status"] = data.status

    if data.start_time is not None:
        if appointment.status not in (
            RecordStatus.PENDING,
            RecordStatus.CONFIRMED,
        ):
            raise ConflictError(
                "Cannot reschedule a completed or cancelled appointment"
            )
        start_time = to_utc(data.start_time)
        _validate_start_time(start_time)
        end_time = start_time + timedelta(
            minutes=appointment.service.duration_minutes
        )

        locked = await lock_master(database, appointment.master_id)
        if locked is None:
            raise NotFoundError.by_id("Master", appointment.master_id)
        if not locked.is_active:
            raise ConflictError("Master is not active")

        if await has_overlapping_appointment(
            database,
            master_id=appointment.master_id,
            start_time=start_time,
            end_time=end_time,
            exclude_id=appointment.id,
        ):
            raise ConflictError(_BOOKED_MESSAGE)

        values["start_time"] = start_time
        values["end_time"] = end_time

    if "comment" in data.model_fields_set:
        values["comment"] = data.comment

    if not values:
        return appointment

    try:
        return await update_appointment(database, appointment, values)
    except IntegrityError:
        raise ConflictError(_BOOKED_MESSAGE) from None


# ─────────── Удаление ───────────

async def delete_booking(
    database: AsyncSession,
    user: User,
    appointment: Appointment,
) -> None:
    """Безвозвратное удаление записи (владелец салона или админ)."""
    ensure_can_delete(appointment, user)
    await delete_appointment(database, appointment)


# ─────────── Чтение ───────────

async def get_booking_or_404(
    database: AsyncSession,
    user: User,
    appointment_id: int,
) -> Appointment:
    """Достаёт запись и сразу проверяет, что пользователю можно её видеть."""
    appointment = await get_appointment(database, appointment_id)
    if appointment is None:
        raise NotFoundError.by_id("Appointment", appointment_id)
    ensure_can_access(appointment, user)
    return appointment


async def list_visible_appointments(
    database: AsyncSession,
    user: User,
    *,
    skip: int,
    limit: int,
    client_id: int | None = None,
    master_id: int | None = None,
    salon_id: int | None = None,
    status: RecordStatus | None = None,
    date_from=None,
    date_to=None,
) -> list[Appointment]:
    """Список записей, доступных пользователю (см. app.crud.appointment._apply_scope)."""
    appointments = await list_appointments(
        database,
        skip=skip,
        limit=limit,
        user_id=user.id,
        include_all=is_admin(user),
        client_id=client_id,
        master_id=master_id,
        salon_id=salon_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return list(appointments)


async def count_visible_appointments(
    database: AsyncSession,
    user: User,
    *,
    client_id: int | None = None,
    master_id: int | None = None,
    salon_id: int | None = None,
    status: RecordStatus | None = None,
    date_from=None,
    date_to=None,
) -> int:
    """Количество доступных пользователю записей (для пагинации)."""
    return await count_appointments(
        database,
        user_id=user.id,
        include_all=is_admin(user),
        client_id=client_id,
        master_id=master_id,
        salon_id=salon_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
