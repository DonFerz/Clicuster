from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.master import Master
from app.models.user import User
from app.schemas.master import MasterCreate, MasterUpdate


async def create_master(database: AsyncSession, data: MasterCreate) -> Master:
    """
    Создание мастера вместе с его учётной записью (User).
    Обе записи создаются в одной транзакции.
    """
    try:
        # 1. Создаём пользователя с ролью MASTER
        user = User(
            full_name=data.full_name,
            email=data.email,
            phone=data.phone,
            hashed_password=data.password,  # TODO: hash_password(data.password)
            role=UserRole.MASTER,
        )
        database.add(user)
        await database.flush()  # INSERT без commit — получаем user.id

        # 2. Создаём профиль мастера, привязанный к user
        master = Master(
            user_id=user.id,
            salon_id=data.salon_id,
            position=data.position,
            description=data.description,
        )
        database.add(master)
        await database.commit()
        await database.refresh(master)
    except Exception:
        await database.rollback()
        raise

    return master


async def get_master(database: AsyncSession, master_id: int) -> Master | None:
    """Поиск мастера по id. Если мастер не найден, возвращается None."""
    result = await database.execute(select(Master).where(Master.id == master_id))

    return result.scalar_one_or_none()


async def get_masters(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Master]:
    """Список мастеров с пагинацией."""
    result = await database.execute(
        select(Master).order_by(Master.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def get_masters_by_salon(
    database: AsyncSession,
    salon_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Master]:
    """Список мастеров конкретного салона."""
    result = await database.execute(
        select(Master)
        .where(Master.salon_id == salon_id)
        .order_by(Master.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def update_master(
    database: AsyncSession,
    master: Master,
    data: MasterUpdate,
) -> Master:
    """Обновление переданных полей мастера. Остальные поля остаются без изменений."""
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(master, field, value)

    try:
        await database.commit()
        await database.refresh(master)
    except Exception:
        await database.rollback()
        raise

    return master


async def delete_master(database: AsyncSession, master: Master) -> None:
    """Удаление мастера. Учётная запись (User) остаётся."""
    try:
        await database.delete(master)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
