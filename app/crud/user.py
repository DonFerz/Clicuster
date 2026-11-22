from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserAdminUpdate, UserCreate, UserUpdate

# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • create_user принимает role — нужно для scripts/create_admin.py (раньше
#     администратора нельзя было создать вообще никак);
#   • get_user_by_email сравнивает email без учёта регистра (данные
#     нормализуются миграцией + схемами);
#   • добавлен update_user_admin — управление role/is_active только из
#     админского эндпоинта, отдельно от пользовательского update_user
#     (защита от mass-assignment);
#   • добавлен count_users.

_UPDATABLE_USER_FIELDS: frozenset[str] = frozenset(
    {"full_name", "email", "phone"}
)
# Админ дополнительно может менять роль и блокировку.
_UPDATABLE_ADMIN_FIELDS: frozenset[str] = _UPDATABLE_USER_FIELDS | {
    "role",
    "is_active",
}


async def create_user(
    database: AsyncSession,
    data: UserCreate,
    *,
    role: UserRole = UserRole.CLIENT,
) -> User:
    """Создание нового пользователя.

    role явно передаётся только доверенным кодом (CLI-скрипт создания
    администратора); из HTTP-запросов роль всегда CLIENT.
    """
    user = User(
        full_name=data.full_name,
        email=str(data.email).lower(),
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role=role,
    )
    database.add(user)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return user


async def get_user(database: AsyncSession, user_id: int) -> User | None:
    """Поиск пользователя по id. Если пользователь не найден, возвращается None."""
    result = await database.execute(select(User).where(User.id == user_id))

    return result.scalar_one_or_none()


async def get_user_by_email(database: AsyncSession, email: str) -> User | None:
    """Поиск пользователя по email без учёта регистра."""
    normalized = email.strip().lower()
    result = await database.execute(
        select(User).where(func.lower(User.email) == normalized)
    )

    return result.scalar_one_or_none()


async def get_users(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[User]:
    """Получение списка пользователей с пагинацией."""
    result = await database.execute(
        select(User).order_by(User.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def count_users(database: AsyncSession) -> int:
    """Всего пользователей (для пагинации)."""
    return int(
        (await database.execute(select(func.count()).select_from(User)))
        .scalar_one()
    )


async def count_active_admins(database: AsyncSession) -> int:
    """Количество активных администраторов.

    ДОБАВЛЕНО: защита от сценария «удалили/заблокировали последнего админа
    и потеряли доступ к управлению системой».
    """
    return int(
        (
            await database.execute(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                )
            )
        ).scalar_one()
    )


async def _apply_fields(
    database: AsyncSession,
    user: User,
    update_data: dict,
    allowed_fields: frozenset[str],
) -> User:
    """Общий помощник: применяет только разрешённые поля и коммитит."""
    for field, value in update_data.items():
        if field not in allowed_fields:
            continue
        if field == "email" and value is not None:
            value = str(value).lower()
        setattr(user, field, value)

    try:
        await database.commit()
        await database.refresh(user)
    except Exception:
        await database.rollback()
        raise

    return user


async def update_user(
    database: AsyncSession,
    user: User,
    data: UserUpdate,
) -> User:
    """Обновление переданных полей user. Роль/is_active менять нельзя."""
    return await _apply_fields(
        database, user, data.model_dump(exclude_unset=True),
        _UPDATABLE_USER_FIELDS,
    )


async def update_user_admin(
    database: AsyncSession,
    user: User,
    data: UserAdminUpdate,
) -> User:
    """Админское обновление: профиль + role + is_active."""
    return await _apply_fields(
        database, user, data.model_dump(exclude_unset=True),
        _UPDATABLE_ADMIN_FIELDS,
    )


async def set_user_password(
    database: AsyncSession,
    user: User,
    hashed_password: str,
) -> User:
    """Устанавливает новый хеш пароля. Используется для rehash и смены пароля."""
    user.hashed_password = hashed_password
    try:
        await database.commit()
        await database.refresh(user)
    except Exception:
        await database.rollback()
        raise

    return user


async def delete_user(database: AsyncSession, user: User) -> None:
    """Удаление пользователя."""
    try:
        await database.delete(user)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
