"""Тесты записей (appointments).

ДОБАВЛЕНО 22.11.2026: модуль записей не существовал (файлы были пустыми),
поэтому это одновременно и тесты новой функциональности, и защита от
регрессий (двойная запись, права доступа, переходы статусов).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.tests.utils import (
    DEFAULT_PASSWORD,
    attach_service,
    create_appointment,
    create_master,
    create_salon,
    create_service,
    future_start,
    login,
    register,
    set_user_role,
)


async def _setup(client: AsyncClient):
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    service = await create_service(
        client, owner["headers"], salon["id"], duration_minutes=60
    )
    master = await create_master(client, owner["headers"], salon["id"])
    await attach_service(client, owner["headers"], master["id"], service["id"])
    return owner, salon, service, master


async def _master_headers(client: AsyncClient, master: dict) -> dict:
    response = await login(client, master["email"], DEFAULT_PASSWORD)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_client_creates_appointment(client: AsyncClient) -> None:
    _owner, _salon, service, master = await _setup(client)
    client_user = await register(client)
    start = future_start()

    appointment = await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=start,
        comment="  first visit  ",
    )

    assert appointment["status"] == "pending"
    assert appointment["client"]["id"] == client_user["user_id"]
    assert appointment["master"]["id"] == master["id"]
    assert appointment["service"]["id"] == service["id"]
    assert appointment["comment"] == "first visit"

    # end_time вычислен сервером: 60 минут
    start_dt = appointment["start_time"]
    end_dt = appointment["end_time"]
    assert start_dt.endswith("Z")
    assert end_dt > start_dt


async def test_client_cannot_pass_end_time(client: AsyncClient) -> None:
    _owner, _salon, service, master = await _setup(client)
    client_user = await register(client)
    start = future_start()

    response = await client.post(
        "/api/v1/appointments",
        headers=client_user["headers"],
        json={
            "master_id": master["id"],
            "service_id": service["id"],
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=12)).isoformat(),
        },
    )
    assert response.status_code == 422


async def test_naive_datetime_rejected(client: AsyncClient) -> None:
    _owner, _salon, service, master = await _setup(client)
    client_user = await register(client)

    response = await client.post(
        "/api/v1/appointments",
        headers=client_user["headers"],
        json={
            "master_id": master["id"],
            "service_id": service["id"],
            "start_time": "2030-01-01T12:00:00",
        },
    )
    assert response.status_code == 422


async def test_past_datetime_rejected(client: AsyncClient) -> None:
    _owner, _salon, service, master = await _setup(client)
    client_user = await register(client)
    past = future_start() - timedelta(days=3)

    response = await client.post(
        "/api/v1/appointments",
        headers=client_user["headers"],
        json={
            "master_id": master["id"],
            "service_id": service["id"],
            "start_time": past.isoformat(),
        },
    )
    assert response.status_code == 422


async def test_double_booking_conflict(client: AsyncClient) -> None:
    _owner, _salon, service, master = await _setup(client)
    first_client = await register(client)
    second_client = await register(client)
    start = future_start()

    await create_appointment(
        client,
        first_client["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=start,
    )

    response = await client.post(
        "/api/v1/appointments",
        headers=second_client["headers"],
        json={
            "master_id": master["id"],
            "service_id": service["id"],
            "start_time": (start + timedelta(minutes=30)).isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_adjacent_booking_allowed(client: AsyncClient) -> None:
    _owner, _salon, service, master = await _setup(client)
    first_client = await register(client)
    second_client = await register(client)
    start = future_start()

    await create_appointment(
        client,
        first_client["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=start,
    )
    second = await create_appointment(
        client,
        second_client["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=start + timedelta(minutes=60),
    )
    assert second["id"]


async def test_service_from_other_salon_rejected(client: AsyncClient) -> None:
    owner, _salon, _service, master = await _setup(client)
    other_salon = await create_salon(client, owner["headers"])
    foreign_service = await create_service(
        client, owner["headers"], other_salon["id"]
    )

    response = await client.post(
        "/api/v1/appointments",
        headers=owner["headers"],
        json={
            "master_id": master["id"],
            "service_id": foreign_service["id"],
            "start_time": future_start().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_master_must_provide_service(client: AsyncClient) -> None:
    owner, salon, _service, master = await _setup(client)
    unattached = await create_service(client, owner["headers"], salon["id"])

    response = await client.post(
        "/api/v1/appointments",
        headers=owner["headers"],
        json={
            "master_id": master["id"],
            "service_id": unattached["id"],
            "start_time": future_start().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_client_cannot_book_for_another_client(
    client: AsyncClient,
) -> None:
    _owner, _salon, service, master = await _setup(client)
    first = await register(client)
    second = await register(client)

    response = await client.post(
        "/api/v1/appointments",
        headers=first["headers"],
        json={
            "master_id": master["id"],
            "service_id": service["id"],
            "start_time": future_start().isoformat(),
            "client_id": second["user_id"],
        },
    )
    assert response.status_code == 403


async def test_owner_can_book_for_client(client: AsyncClient) -> None:
    owner, _salon, service, master = await _setup(client)
    target = await register(client)

    appointment = await create_appointment(
        client,
        owner["headers"],
        master_id=master["id"],
        service_id=service["id"],
        client_id=target["user_id"],
    )
    assert appointment["client"]["id"] == target["user_id"]


async def test_visibility_scopes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner, salon, service, master = await _setup(client)
    appointment_client = await register(client)
    stranger = await register(client)

    created = await create_appointment(
        client,
        appointment_client["headers"],
        master_id=master["id"],
        service_id=service["id"],
    )

    assert len(
        (await client.get(
            "/api/v1/appointments", headers=appointment_client["headers"]
        )).json()
    ) == 1

    assert (
        await client.get("/api/v1/appointments", headers=stranger["headers"])
    ).json() == []

    assert (
        await client.get(
            f"/api/v1/appointments/{created['id']}",
            headers=stranger["headers"],
        )
    ).status_code == 403

    master_headers = await _master_headers(client, master)
    assert len(
        (await client.get("/api/v1/appointments", headers=master_headers)).json()
    ) == 1

    assert len(
        (await client.get("/api/v1/appointments", headers=owner["headers"])).json()
    ) == 1

    admin = await register(client)
    await set_user_role(db_session, admin["user_id"], UserRole.ADMIN)
    assert len(
        (await client.get("/api/v1/appointments", headers=admin["headers"])).json()
    ) == 1


async def test_status_transitions(client: AsyncClient) -> None:
    owner, _salon, service, master = await _setup(client)
    client_user = await register(client)
    appointment = await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
    )
    url = f"/api/v1/appointments/{appointment['id']}"

    # клиент не может подтверждать
    forbidden = await client.patch(
        url, headers=client_user["headers"], json={"status": "confirmed"}
    )
    assert forbidden.status_code == 403

    confirmed = await client.patch(
        url, headers=owner["headers"], json={"status": "confirmed"}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    completed = await client.patch(
        url, headers=owner["headers"], json={"status": "completed"}
    )
    assert completed.status_code == 200

    # финальный статус нельзя изменить
    revert = await client.patch(
        url, headers=owner["headers"], json={"status": "pending"}
    )
    assert revert.status_code == 409


async def test_client_cancels_own_and_slot_frees_up(
    client: AsyncClient,
) -> None:
    _owner, _salon, service, master = await _setup(client)
    first = await register(client)
    second = await register(client)
    start = future_start()

    appointment = await create_appointment(
        client,
        first["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=start,
    )

    cancelled = await client.patch(
        f"/api/v1/appointments/{appointment['id']}",
        headers=first["headers"],
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # отменённая запись не блокирует слот (проверяется и в БД EXCLUDE-ом)
    rebooked = await create_appointment(
        client,
        second["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=start,
    )
    assert rebooked["status"] == "pending"


async def test_reschedule_and_conflict(client: AsyncClient) -> None:
    owner, _salon, service, master = await _setup(client)
    client_user = await register(client)

    first = await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=future_start(hour=10),
    )
    second = await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
        start_time=future_start(hour=14),
    )

    conflict = await client.patch(
        f"/api/v1/appointments/{second['id']}",
        headers=owner["headers"],
        json={"start_time": future_start(hour=10, minute=30).isoformat()},
    )
    assert conflict.status_code == 409

    moved = await client.patch(
        f"/api/v1/appointments/{second['id']}",
        headers=owner["headers"],
        json={"start_time": future_start(hour=16).isoformat()},
    )
    assert moved.status_code == 200
    moved_start = datetime.fromisoformat(
        moved.json()["start_time"].replace("Z", "+00:00")
    )
    assert moved_start == future_start(hour=16)
    assert first["id"] != second["id"]


async def test_delete_requires_owner(client: AsyncClient) -> None:
    owner, _salon, service, master = await _setup(client)
    client_user = await register(client)
    appointment = await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
    )
    url = f"/api/v1/appointments/{appointment['id']}"

    forbidden = await client.delete(url, headers=client_user["headers"])
    assert forbidden.status_code == 403

    allowed = await client.delete(url, headers=owner["headers"])
    assert allowed.status_code == 204

    assert (
        await client.get(url, headers=owner["headers"])
    ).status_code == 404


async def test_master_can_create_appointment_for_client(
    client: AsyncClient,
) -> None:
    _owner, _salon, service, master = await _setup(client)
    other_client = await register(client)
    master_headers = await _master_headers(client, master)

    response = await client.post(
        "/api/v1/appointments",
        headers=master_headers,
        json={
            "master_id": master["id"],
            "service_id": service["id"],
            "start_time": future_start().isoformat(),
            "client_id": other_client["user_id"],
        },
    )
    # Мастер — сотрудник салона, поэтому такой сценарий разрешён.
    assert response.status_code == 201
    assert response.json()["client"]["id"] == other_client["user_id"]
