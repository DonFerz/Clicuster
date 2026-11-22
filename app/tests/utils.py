"""Хелперы для тестов: регистрация, создание салонов/услуг/мастеров.

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): фабрики данных, чтобы тесты
не дублировали десятки строк подготовки.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.user import User

DEFAULT_PASSWORD = "StrongPass123"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"


def future_start(days: int = 1, hour: int = 12, minute: int = 0) -> datetime:
    """Ближайшая дата через N дней в указанное время UTC."""
    target = (datetime.now(timezone.utc) + timedelta(days=days)).date()
    return datetime.combine(
        target,
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=timezone.utc,
    )


async def register(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    full_name: str = "Test User",
    phone: str = "+79990000000",
) -> dict:
    """Регистрирует пользователя и возвращает токены, заголовки и профиль."""
    payload = {
        "full_name": full_name,
        "email": email or unique_email(),
        "phone": phone,
        "password": password,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    data["password"] = password
    data["payload"] = payload

    me = await client.get("/api/v1/users/me", headers=data["headers"])
    assert me.status_code == 200, me.text
    data["user"] = me.json()
    data["user_id"] = me.json()["id"]
    return data


async def create_salon(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {
        "name": f"Salon {uuid.uuid4().hex[:6]}",
        "address": "ул. Тестовая, 1",
        "phone": "+79990000001",
        "type": "barbershop",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/salons", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def create_service(
    client: AsyncClient, headers: dict, salon_id: int, **overrides
) -> dict:
    payload = {
        "name": f"Haircut {uuid.uuid4().hex[:4]}",
        "price": 150000,
        "duration_minutes": 60,
        "salon_id": salon_id,
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/services", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_master(
    client: AsyncClient, headers: dict, salon_id: int, **overrides
) -> dict:
    payload = {
        "full_name": "Master Test",
        "email": unique_email("master"),
        "phone": "+79990000002",
        "password": DEFAULT_PASSWORD,
        "salon_id": salon_id,
        "position": "master",
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/masters", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    data = response.json()
    data["password"] = payload["password"]
    data["email"] = payload["email"]
    return data


async def attach_service(
    client: AsyncClient, headers: dict, master_id: int, service_id: int
) -> None:
    response = await client.post(
        f"/api/v1/masters/{master_id}/services/{service_id}", headers=headers
    )
    assert response.status_code == 204, response.text


async def create_appointment(
    client: AsyncClient,
    headers: dict,
    *,
    master_id: int,
    service_id: int,
    start_time: datetime | None = None,
    **overrides,
) -> dict:
    payload = {
        "master_id": master_id,
        "service_id": service_id,
        "start_time": (start_time or future_start()).isoformat(),
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/appointments", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def set_user_role(
    db: AsyncSession, user_id: int, role: UserRole
) -> None:
    """Меняет роль пользователя напрямую в БД (bootstrap админа в тестах)."""
    await db.execute(update(User).where(User.id == user_id).values(role=role))
    await db.commit()


async def set_user_active(
    db: AsyncSession, user_id: int, is_active: bool
) -> None:
    await db.execute(
        update(User).where(User.id == user_id).values(is_active=is_active)
    )
    await db.commit()


async def login(
    client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD
):
    return await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )


async def login_headers(
    client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD
) -> dict:
    response = await login(client, email, password)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
