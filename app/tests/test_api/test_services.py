"""Тесты услуг.

ДОБАВЛЕНО 22.11.2026: раньше не было ни одного теста.
Здесь же — регрессия на главный найденный баг: отсутствие is_active
в модели Service (любой список услуг падал с 500).
"""

from __future__ import annotations

from httpx import AsyncClient

from app.tests.utils import (
    attach_service,
    create_appointment,
    create_master,
    create_salon,
    create_service,
    register,
)


async def test_list_services_works_and_has_is_active(
    client: AsyncClient,
) -> None:
    """Регрессия: ServiceRead требовал is_active, которого не было в модели."""
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    service = await create_service(client, owner["headers"], salon["id"])

    listing = await client.get(
        "/api/v1/services", params={"salon_id": salon["id"]}
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert len(body) == 1
    assert body[0]["id"] == service["id"]
    assert body[0]["is_active"] is True

    single = await client.get(f"/api/v1/services/{service['id']}")
    assert single.status_code == 200


async def test_stranger_cannot_create_service(client: AsyncClient) -> None:
    owner = await register(client)
    stranger = await register(client)
    salon = await create_salon(client, owner["headers"])

    response = await client.post(
        "/api/v1/services",
        headers=stranger["headers"],
        json={
            "name": "Hack",
            "price": 100,
            "duration_minutes": 30,
            "salon_id": salon["id"],
        },
    )
    assert response.status_code == 403


async def test_toggle_service_is_active(client: AsyncClient) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    service = await create_service(client, owner["headers"], salon["id"])

    patched = await client.patch(
        f"/api/v1/services/{service['id']}",
        headers=owner["headers"],
        json={"is_active": False, "price": 999},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False
    assert patched.json()["price"] == 999

    public = await client.get(
        "/api/v1/services", params={"salon_id": salon["id"]}
    )
    assert public.json() == []

    with_hidden = await client.get(
        "/api/v1/services",
        params={"salon_id": salon["id"], "include_inactive": "true"},
    )
    assert len(with_hidden.json()) == 1


async def test_service_validation(client: AsyncClient) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])

    negative = await client.post(
        "/api/v1/services",
        headers=owner["headers"],
        json={
            "name": "Bad",
            "price": -1,
            "duration_minutes": 30,
            "salon_id": salon["id"],
        },
    )
    assert negative.status_code == 422

    zero_duration = await client.post(
        "/api/v1/services",
        headers=owner["headers"],
        json={
            "name": "Bad",
            "price": 100,
            "duration_minutes": 0,
            "salon_id": salon["id"],
        },
    )
    assert zero_duration.status_code == 422

    extra = await client.post(
        "/api/v1/services",
        headers=owner["headers"],
        json={
            "name": "Bad",
            "price": 100,
            "duration_minutes": 30,
            "salon_id": salon["id"],
            "id": 123,
        },
    )
    assert extra.status_code == 422


async def test_delete_service_with_appointment_returns_409(
    client: AsyncClient,
) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    service = await create_service(client, owner["headers"], salon["id"])
    master = await create_master(client, owner["headers"], salon["id"])
    await attach_service(client, owner["headers"], master["id"], service["id"])

    client_user = await register(client)
    await create_appointment(
        client,
        client_user["headers"],
        master_id=master["id"],
        service_id=service["id"],
    )

    response = await client.delete(
        f"/api/v1/services/{service['id']}", headers=owner["headers"]
    )
    assert response.status_code == 409


async def test_delete_unused_service(client: AsyncClient) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])
    service = await create_service(client, owner["headers"], salon["id"])

    response = await client.delete(
        f"/api/v1/services/{service['id']}", headers=owner["headers"]
    )
    assert response.status_code == 204
    assert (
        await client.get(f"/api/v1/services/{service['id']}")
    ).status_code == 404
