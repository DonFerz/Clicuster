"""Тесты мастеров.

ДОБАВЛЕНО 22.11.2026: раньше не было ни одного теста.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.tests.utils import (
    DEFAULT_PASSWORD,
    attach_service,
    create_appointment,
    create_master,
    create_salon,
    create_service,
    login,
    register,
)


async def _setup_salon_with_master(client: AsyncClient):
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    service = await create_service(client, owner["headers"], salon["id"])
    master = await create_master(client, owner["headers"], salon["id"])
    await attach_service(client, owner["headers"], master["id"], service["id"])
    return owner, salon, service, master


async def test_create_master_creates_master_user(client: AsyncClient) -> None:
    owner, salon, _service, master = await _setup_salon_with_master(client)

    assert master["salon_id"] == salon["id"]
    assert master["user"]["role"] == "master"

    # Мастер может войти под своим паролем
    response = await login(client, master["email"], DEFAULT_PASSWORD)
    assert response.status_code == 200

    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "master"


async def test_create_master_duplicate_email(client: AsyncClient) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    existing = await create_master(client, owner["headers"], salon["id"])

    # второй мастер с тем же email, что и у первого мастера
    response = await client.post(
        "/api/v1/masters",
        headers=owner["headers"],
        json={
            "full_name": "Duplicate",
            "email": existing["email"],
            "phone": "+79990000009",
            "password": DEFAULT_PASSWORD,
            "salon_id": salon["id"],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_stranger_cannot_create_master(client: AsyncClient) -> None:
    owner = await register(client)
    stranger = await register(client)
    salon = await create_salon(client, owner["headers"])

    response = await client.post(
        "/api/v1/masters",
        headers=stranger["headers"],
        json={
            "full_name": "Intruder",
            "email": "intruder@example.com",
            "phone": "+79990000008",
            "password": DEFAULT_PASSWORD,
            "salon_id": salon["id"],
        },
    )
    assert response.status_code == 403


async def test_attach_service_from_other_salon_forbidden(
    client: AsyncClient,
) -> None:
    owner, _salon, _service, master = await _setup_salon_with_master(client)
    other_salon = await create_salon(client, owner["headers"])
    foreign_service = await create_service(
        client, owner["headers"], other_salon["id"]
    )

    response = await client.post(
        f"/api/v1/masters/{master['id']}/services/{foreign_service['id']}",
        headers=owner["headers"],
    )
    assert response.status_code == 403


async def test_master_can_edit_own_profile_but_not_is_active(
    client: AsyncClient,
) -> None:
    _owner, _salon, _service, master = await _setup_salon_with_master(client)

    login_response = await login(client, master["email"], DEFAULT_PASSWORD)
    master_headers = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }

    ok = await client.patch(
        f"/api/v1/masters/{master['id']}",
        headers=master_headers,
        json={"description": "Топ-мастер"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["description"] == "Топ-мастер"

    forbidden = await client.patch(
        f"/api/v1/masters/{master['id']}",
        headers=master_headers,
        json={"is_active": False},
    )
    assert forbidden.status_code == 403


async def test_public_list_hides_inactive_masters(client: AsyncClient) -> None:
    owner, salon, _service, master = await _setup_salon_with_master(client)

    await client.patch(
        f"/api/v1/masters/{master['id']}",
        headers=owner["headers"],
        json={"is_active": False},
    )

    listing = await client.get(
        "/api/v1/masters", params={"salon_id": salon["id"]}
    )
    assert listing.status_code == 200
    assert listing.json() == []

    hidden = await client.get(
        "/api/v1/masters",
        params={"salon_id": salon["id"], "include_inactive": "true"},
    )
    assert len(hidden.json()) == 1


async def test_delete_master_with_appointments_returns_409(
    client: AsyncClient,
) -> None:
    owner, _salon, service, master = await _setup_salon_with_master(client)
    client_user = await register(client)
    await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
    )

    response = await client.delete(
        f"/api/v1/masters/{master['id']}", headers=owner["headers"]
    )
    assert response.status_code == 409


async def test_master_gets_404_for_unknown_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/masters/999999")
    assert response.status_code == 404
