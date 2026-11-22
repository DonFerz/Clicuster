"""Тесты салонов.

ДОБАВЛЕНО 22.11.2026: раньше не было ни одного теста.
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


async def test_create_salon_sets_owner(client: AsyncClient) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"], name="Barber House")

    assert salon["owner_id"] == owner["user_id"]
    assert salon["owner"]["id"] == owner["user_id"]
    assert salon["is_active"] is True

    fetched = await client.get(f"/api/v1/salons/{salon['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Barber House"


async def test_salon_requires_name(client: AsyncClient) -> None:
    owner = await register(client)
    response = await client.post(
        "/api/v1/salons",
        headers=owner["headers"],
        json={"name": "   ", "type": "barbershop"},
    )
    assert response.status_code == 422


async def test_salon_create_forbids_owner_id(client: AsyncClient) -> None:
    owner = await register(client)
    response = await client.post(
        "/api/v1/salons",
        headers=owner["headers"],
        json={
            "name": "Fake",
            "type": "barbershop",
            "owner_id": owner["user_id"],
        },
    )
    assert response.status_code == 422


async def test_public_list_hides_inactive_salons(client: AsyncClient) -> None:
    owner = await register(client)
    active = await create_salon(client, owner["headers"], name="Active Salon")
    hidden = await create_salon(client, owner["headers"], name="Hidden Salon")

    await client.patch(
        f"/api/v1/salons/{hidden['id']}",
        headers=owner["headers"],
        json={"is_active": False},
    )

    listing = await client.get("/api/v1/salons", params={"limit": 50})
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()]
    assert active["id"] in ids
    assert hidden["id"] not in ids
    assert int(listing.headers["X-Total-Count"]) == 1

    # владелец видит свой скрытый салон в /my
    my = await client.get("/api/v1/salons/my", headers=owner["headers"])
    assert hidden["id"] in [item["id"] for item in my.json()]


async def test_non_owner_cannot_update_or_delete(client: AsyncClient) -> None:
    owner = await register(client)
    stranger = await register(client)
    salon = await create_salon(client, owner["headers"])

    patch = await client.patch(
        f"/api/v1/salons/{salon['id']}",
        headers=stranger["headers"],
        json={"name": "Hijacked"},
    )
    assert patch.status_code == 403

    delete = await client.delete(
        f"/api/v1/salons/{salon['id']}", headers=stranger["headers"]
    )
    assert delete.status_code == 403


async def test_delete_salon_with_appointments_returns_409(
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
        f"/api/v1/salons/{salon['id']}", headers=owner["headers"]
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_delete_empty_salon(client: AsyncClient) -> None:
    owner = await register(client)
    salon = await create_salon(client, owner["headers"])

    response = await client.delete(
        f"/api/v1/salons/{salon['id']}", headers=owner["headers"]
    )
    assert response.status_code == 204

    got = await client.get(f"/api/v1/salons/{salon['id']}")
    assert got.status_code == 404
