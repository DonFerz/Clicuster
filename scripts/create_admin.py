"""Создание администратора (bootstrap).

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): в системе не было ни одного
способа создать пользователя с ролью ``admin`` — все регистрации через API
получают роль ``client``, а значит админские эндпоинты были недоступны
вообще никому.

Использование (из корня проекта, с активированным venv):

    python -m scripts.create_admin --email admin@example.com \
        --full-name "Иван Петров" --phone "+79990000000"

Если пароль не указан, будет сгенерирован и напечатан один раз.
Если пользователь с таким email уже есть — он будет повышен до админа
(и разблокирован), пароль не меняется.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from app.config import settings
from app.crud.user import (
    create_user,
    get_user_by_email,
    update_user_admin,
)
from app.database import async_session_maker, dispose_engine
from app.models.enums import UserRole
from app.schemas.user import UserAdminUpdate, UserCreate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Создать администратора Clicuster",
    )
    parser.add_argument("--email", required=True, help="Email администратора")
    parser.add_argument(
        "--full-name", default="Administrator", help="ФИО администратора"
    )
    parser.add_argument(
        "--phone", default="+70000000000", help="Телефон администратора"
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Пароль (если не указан — будет сгенерирован)",
    )
    return parser


async def _create_admin() -> int:
    args = _build_parser().parse_args()
    email = args.email.strip().lower()

    print(
        f"Подключение к БД: {settings.POSTGRES_HOST}:"
        f"{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

    async with async_session_maker() as db:
        existing = await get_user_by_email(db, email)
        if existing is not None:
            if existing.role == UserRole.ADMIN and existing.is_active:
                print(f"Пользователь {email} уже администратор.")
                return 0
            await update_user_admin(
                db,
                existing,
                UserAdminUpdate(role=UserRole.ADMIN, is_active=True),
            )
            print(f"Пользователь {email} повышен до администратора.")
            return 0

        password = args.password
        generated = False
        if not password:
            # Гарантируем букву и цифру: пароль должен пройти валидацию схемы.
            password = f"Aa1-{secrets.token_urlsafe(18)}"
            generated = True

        data = UserCreate(
            email=email,
            full_name=args.full_name,
            phone=args.phone,
            password=password,
        )

        try:
            user = await create_user(db, data, role=UserRole.ADMIN)
        except Exception as exc:  # noqa: BLE001
            print(f"Не удалось создать администратора: {exc}", file=sys.stderr)
            return 1

        print(f"Администратор создан: id={user.id}, email={user.email}")
        if generated:
            print(f"Пароль (сохраните, больше не показывается): {password}")
        return 0


async def main() -> int:
    try:
        return await _create_admin()
    finally:
        # Закрываем пул в том же event loop, где его использовали.
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
