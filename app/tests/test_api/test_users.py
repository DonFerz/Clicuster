"""Тесты пользователей и админских операций.

ДОБАВЛЕНО 22.11.2026: раньше не было ни одного теста.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.tests.utils import (
    attach_service,
    create_appointment,
    create_master,
    create_salon,
    create_service,
    register,
    set_user_role,
)


async def test_update_me_profile(client: AsyncClient) -> None:
    data = await register(client)

    response = await client.patch(
        "/api/v1/users/me",
        headers=data["headers"],
        json={"full_name": "  New Name  ", "phone": "+79991112233"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "New Name"
    assert body["phone"] == "+79991112233"


async def test_update_me_forbids_privileged_fields(client: AsyncClient) -> None:
    data = await register(client)

    response = await client.patch(
        "/api/v1/users/me",
        headers=data["headers"],
        json={"role": "admin"},
    )
    assert response.status_code == 422


async def test_update_me_duplicate_email_returns_409(
    client: AsyncClient,
) -> None:
    """Регрессия: раньше падало с 500 (IntegrityError)."""
    first = await register(client)
    second = await register(client)

    response = await client.patch(
        "/api/v1/users/me",
        headers=first["headers"],
        json={"email": second["payload"]["email"]},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_users_list_requires_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await register(client)

    forbidden = await client.get("/api/v1/users", headers=user["headers"])
    assert forbidden.status_code == 403

    await set_user_role(db_session, user["user_id"], UserRole.ADMIN)
    allowed = await client.get("/api/v1/users", headers=user["headers"])
    assert allowed.status_code == 200
    assert allowed.headers["X-Total-Count"] == "1"
    # Публичные данные без email/phone
    assert "email" not in allowed.json()[0]


async def test_admin_can_promote_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await register(client)
    await set_user_role(db_session, admin["user_id"], UserRole.ADMIN)

    target = await register(client)

    response = await client.patch(
        f"/api/v1/users/{target['user_id']}",
        headers=admin["headers"],
        json={"role": "admin"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"


async def test_cannot_demote_last_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await register(client)
    await set_user_role(db_session, admin["user_id"], UserRole.ADMIN)

    response = await client.patch(
        f"/api/v1/users/{admin['user_id']}",
        headers=admin["headers"],
        json={"role": "client"},
    )
    assert response.status_code == 409
    assert "last active administrator" in response.json()["detail"]


async def test_admin_cannot_deactivate_self(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await register(client)
    await set_user_role(db_session, admin["user_id"], UserRole.ADMIN)

    response = await client.patch(
        f"/api/v1/users/{admin['user_id']}",
        headers=admin["headers"],
        json={"is_active": False},
    )
    assert response.status_code == 403


async def test_admin_cannot_delete_self(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await register(client)
    await set_user_role(db_session, admin["user_id"], UserRole.ADMIN)

    response = await client.delete(
        f"/api/v1/users/{admin['user_id']}",
        headers=admin["headers"],
    )
    assert response.status_code == 403


async def test_delete_user_with_related_data_returns_409(
    client: AsyncClient, db_session: AsyncSession
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

    admin = await register(client)
    await set_user_role(db_session, admin["user_id"], UserRole.ADMIN)

    response = await client.delete(
        f"/api/v1/users/{client_user['user_id']}", headers=admin["headers"]
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_get_public_profile_hides_contacts(client: AsyncClient) -> None:
    viewer = await register(client)
    target = await register(client)

    response = await client.get(
        f"/api/v1/users/{target['user_id']}", headers=viewer["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert "email" not in body
    assert "phone" not in body


async def test_get_public_profile_404(client: AsyncClient) -> None:
    viewer = await register(client)
    response = await client.get("/api/v1/users/999999", headers=viewer["headers"])
    assert response.status_code == 404
