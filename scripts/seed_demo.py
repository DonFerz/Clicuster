"""Демо-данные для быстрого запуска (салон, услуги, мастер, клиент, запись).

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): README и structure.txt ссылались на
scripts/seed_db.py, но скрипта не было. Этот скрипт даёт «живые» данные,
чтобы сразу увидеть работу API/фронтенда.

Запуск (из корня проекта, после alembic upgrade head):

    python -m scripts.seed_demo

Скрипт идемпотентен: повторный запуск не создаёт дубликаты.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone

from app.core.appointments import create_booking
from app.crud.master import (
    add_service_to_master,
    create_master,
    get_master_by_user_id,
    get_master_with_services,
)
from app.crud.salon import create_salon, get_salons_by_owner
from app.crud.service import create_service
from app.crud.user import create_user, get_user_by_email
from app.database import async_session_maker, dispose_engine
from app.models.enums import MasterPosition, SalonType, UserRole
from app.schemas.appointment import AppointmentCreate
from app.schemas.master import MasterCreate
from app.schemas.salon import SalonCreate
from app.schemas.service import ServiceCreate
from app.schemas.user import UserCreate

ADMIN_EMAIL = "admin@example.com"
OWNER_EMAIL = "owner@example.com"
MASTER_EMAIL = "master@example.com"
CLIENT_EMAIL = "client@example.com"

DEMO_PASSWORD = "Demo12345"


async def _get_or_create_user(db, email: str, full_name: str, phone: str,
                              role: UserRole):
    user = await get_user_by_email(db, email)
    if user is not None:
        return user, False
    user = await create_user(
        db,
        UserCreate(
            email=email,
            full_name=full_name,
            phone=phone,
            password=DEMO_PASSWORD,
        ),
        role=role,
    )
    return user, True


async def _seed() -> int:
    async with async_session_maker() as db:
        admin, _ = await _get_or_create_user(
            db, ADMIN_EMAIL, "Demo Admin", "+70000000001", UserRole.ADMIN
        )
        owner, _ = await _get_or_create_user(
            db, OWNER_EMAIL, "Demo Owner", "+70000000002", UserRole.CLIENT
        )
        client, _ = await _get_or_create_user(
            db, CLIENT_EMAIL, "Demo Client", "+70000000003", UserRole.CLIENT
        )

        salons = await get_salons_by_owner(db, owner.id, limit=1)
        if salons:
            salon = salons[0]
            print(f"Салон уже существует: id={salon.id} «{salon.name}»")
        else:
            salon = await create_salon(
                db,
                SalonCreate(
                    name="Demo Barbershop",
                    address="ул. Примерная, 1",
                    phone="+70000000002",
                    type=SalonType.BARBERSHOP,
                ),
                owner_id=owner.id,
            )
            print(f"Салон создан: id={salon.id}")

        services = []
        for name, price, duration in (
            ("Мужская стрижка", 150000, 60),
            ("Борода", 80000, 30),
        ):
            service = await create_service(
                db,
                ServiceCreate(
                    name=name,
                    price=price,
                    duration_minutes=duration,
                    salon_id=salon.id,
                ),
            )
            services.append(service)
            print(f"Услуга: id={service.id} «{service.name}»")

        master_user = await get_user_by_email(db, MASTER_EMAIL)
        master = None
        if master_user is not None:
            # ДОБАВЛЕНО: явная функция поиска профиля по пользователю,
            # вместо перебора всех мастеров.
            master = await get_master_by_user_id(db, master_user.id)
        if master is None:
            master = await create_master(
                db,
                MasterCreate(
                    email=MASTER_EMAIL,
                    full_name="Demo Master",
                    phone="+70000000004",
                    password=DEMO_PASSWORD,
                    salon_id=salon.id,
                    position=MasterPosition.TOP_MASTER,
                    description="Демо-мастер",
                ),
            )
            print(f"Мастер создан: id={master.id}")

        master = await get_master_with_services(db, master.id)
        for service in services:
            await add_service_to_master(db, master, service)
        print("Услуги привязаны к мастеру")

        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        start_time = datetime.combine(
            tomorrow, time(hour=12, minute=0), tzinfo=timezone.utc
        )
        try:
            appointment = await create_booking(
                db,
                owner,
                AppointmentCreate(
                    master_id=master.id,
                    service_id=services[0].id,
                    client_id=client.id,
                    start_time=start_time,
                    comment="Демо-запись",
                ),
            )
            print(f"Запись создана: id={appointment.id} на {start_time}")
        except Exception as exc:  # noqa: BLE001 — сид не должен падать
            print(f"Запись не создана (возможно, слот занят): {exc}")

        print("\nДемо-учётные записи (пароль у всех: %s):" % DEMO_PASSWORD)
        print(f"  admin  : {ADMIN_EMAIL}")
        print(f"  owner  : {OWNER_EMAIL}")
        print(f"  master : {MASTER_EMAIL}")
        print(f"  client : {CLIENT_EMAIL}")
        print(f"\nid админа={admin.id}, владельца={owner.id}, "
              f"клиента={client.id}")
        return 0


async def main() -> int:
    try:
        return await _seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
