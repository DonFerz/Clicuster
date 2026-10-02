from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
# from app.core.security import hash_password


async def create_user(database: AsyncSession, data: UserCreate) -> User:
    """Создание нового пользователя. Пароль будет хэшироваться."""
    user = User(
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        hashed_password=data.password,  # TODO: заменить на hash_password(data.password)
    )
    database.add(user)
    await database.commit()
    await database.refresh(user)

    return user


async def get_user(database: AsyncSession, user_id: int) -> Optional[User]:
    """Поиск пользователя по id. Если пользователь не найден, возвращается None."""
    result = await database.execute(select(User).where(User.id == user_id))

    return result.scalar_one_or_none()


async def get_user_by_email(database: AsyncSession, email: str) -> Optional[User]:
    """Поиск пользователя по email. Если пользователь не найден, возвращается None."""
    result = await database.execute(select(User).where(User.email == email))

    return result.scalar_one_or_none()


async def get_users(database: AsyncSession, skip: int = 0, limit: int = 20) -> Sequence[User]:
    """Получение списка пользователей с пагинацией."""
    result = await database.execute(select(User).offset(skip).limit(limit))

    return result.scalars().all()


async def update_user(database: AsyncSession, user: User, data: UserUpdate) -> User:
    """Обновление переданных полей. Остальные поля остаются без изменений."""
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(user, field, value)
    await database.commit()
    await database.refresh(user)

    return user


async def delete_user(database: AsyncSession, user: User) -> None:
    """Удаление пользователя."""
    await database.delete(user)
    await database.commit()
