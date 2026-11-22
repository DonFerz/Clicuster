"""Тесты аутентификации.

ДОБАВЛЕНО 22.11.2026: файл был пустым.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import reset_rate_limiter
from app.tests.utils import (
    DEFAULT_PASSWORD,
    login,
    login_headers,
    register,
    set_user_active,
    unique_email,
)


async def test_register_returns_tokens_and_client_role(client: AsyncClient) -> None:
    data = await register(client)

    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["role"] == "client"
    assert data["user"]["email"] == data["payload"]["email"].lower()


async def test_register_duplicate_email_is_case_insensitive(
    client: AsyncClient,
) -> None:
    email = unique_email()
    await register(client, email=email)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Second",
            "email": email.upper(),
            "phone": "+79990000010",
            "password": DEFAULT_PASSWORD,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_register_weak_password_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Weak",
            "email": unique_email(),
            "phone": "+79990000011",
            "password": "12345678",
        },
    )
    assert response.status_code == 422


async def test_register_cannot_self_assign_role(client: AsyncClient) -> None:
    """Mass-assignment: role/is_active при регистрации запрещены схемой."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Hacker",
            "email": unique_email(),
            "phone": "+79990000012",
            "password": DEFAULT_PASSWORD,
            "role": "admin",
            "is_active": True,
        },
    )
    assert response.status_code == 422


async def test_login_ok_and_wrong_password(client: AsyncClient) -> None:
    data = await register(client)
    email = data["payload"]["email"]

    ok = await login(client, email)
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await login(client, email, "WrongPass999")
    assert bad.status_code == 401

    unknown = await login(client, unique_email(), DEFAULT_PASSWORD)
    assert unknown.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_refresh_token_flow(client: AsyncClient) -> None:
    data = await register(client)

    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    # access-токен нельзя использовать как refresh
    wrong_type = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": data["access_token"]},
    )
    assert wrong_type.status_code == 401

    garbage = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"}
    )
    assert garbage.status_code == 401


async def test_inactive_user_cannot_login(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    data = await register(client)
    await set_user_active(db_session, data["user_id"], False)

    response = await login(client, data["payload"]["email"])
    assert response.status_code == 401

    # и старый токен тоже перестаёт работать
    me = await client.get("/api/v1/users/me", headers=data["headers"])
    assert me.status_code == 401


async def test_change_password(client: AsyncClient) -> None:
    data = await register(client)
    headers = data["headers"]
    email = data["payload"]["email"]

    wrong = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "WrongPass123", "new_password": "NewPass1234"},
    )
    assert wrong.status_code == 401

    same = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={
            "current_password": DEFAULT_PASSWORD,
            "new_password": DEFAULT_PASSWORD,
        },
    )
    assert same.status_code == 422

    ok = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={
            "current_password": DEFAULT_PASSWORD,
            "new_password": "NewPass1234",
        },
    )
    assert ok.status_code == 204

    assert (await login(client, email, DEFAULT_PASSWORD)).status_code == 401
    assert (await login(client, email, "NewPass1234")).status_code == 200


async def test_login_rate_limit(client: AsyncClient) -> None:
    """Защита от подбора пароля (добавлена в рамках аудита)."""
    original = (
        settings.RATE_LIMIT_ENABLED,
        settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    settings.RATE_LIMIT_ENABLED = True
    settings.LOGIN_RATE_LIMIT_ATTEMPTS = 2
    settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60
    reset_rate_limiter()

    try:
        for _ in range(2):
            response = await login(client, unique_email("brute"), "WrongPass123")
            assert response.status_code == 401

        blocked = await login(client, unique_email("brute"), "WrongPass123")
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "rate_limit_exceeded"
        assert "Retry-After" in blocked.headers
    finally:
        (
            settings.RATE_LIMIT_ENABLED,
            settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        ) = original
        reset_rate_limiter()


async def test_password_hash_format_is_portable(client: AsyncClient) -> None:
    """Регрессия: пароли хешируются bcrypt_sha256 без passlib."""
    from app.core.security import hash_password, needs_rehash, verify_password

    stored = hash_password("StrongPass123")
    assert stored.startswith("$bcrypt-sha256$v=2,t=2b,r=")
    assert verify_password("StrongPass123", stored)
    assert not verify_password("other", stored)
    assert not needs_rehash(stored)
    assert not verify_password("x", "corrupted-hash")


@pytest.mark.parametrize("bad_token", ["", "abc", "a.b.c"])
async def test_me_rejects_bad_tokens(client: AsyncClient, bad_token: str) -> None:
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert response.status_code == 401


async def test_login_headers_helper(client: AsyncClient) -> None:
    data = await register(client)
    headers = await login_headers(client, data["payload"]["email"])
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
