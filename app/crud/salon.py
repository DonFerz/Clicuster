from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.salon import Salon
from app.schemas.salon import SalonCreate, SalonUpdate


async def _get_salon_with_owner(
    database: AsyncSession, salon_id: int
) -> Salon:
    """Внутренний хелпер: загружает салон вместе с владельцем."""
    result = await database.execute(
        select(Salon)
        .where(Salon.id == salon_id)
        .options(selectinload(Salon.owner))
    )
    return result.scalar_one()


async def create_salon(database: AsyncSession, data: SalonCreate) -> Salon:
    """Создание нового салона. Возвращает салон с загруженным владельцем."""
    salon = Salon(
        name=data.name,
        address=data.address,
        phone=data.phone,
        type=data.type,
        owner_id=data.owner_id,
    )
    database.add(salon)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return await _get_salon_with_owner(database, salon.id)


async def get_salon(database: AsyncSession, salon_id: int) -> Salon | None:
    """Поиск салона по id. Владелец загружается сразу."""
    result = await database.execute(
        select(Salon)
        .where(Salon.id == salon_id)
        .options(selectinload(Salon.owner))
    )

    return result.scalar_one_or_none()


async def get_salons(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 10,
) -> Sequence[Salon]:
    """Список салонов с пагинацией. Владельцы загружаются сразу."""
    result = await database.execute(
        select(Salon)
        .options(selectinload(Salon.owner))
        .order_by(Salon.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def get_salons_by_owner(
    database: AsyncSession,
    owner_id: int,
    skip: int = 0,
    limit: int = 10,
) -> Sequence[Salon]:
    """Список салонов конкретного владельца. Владельцы загружаются сразу."""
    result = await database.execute(
        select(Salon)
        .where(Salon.owner_id == owner_id)
        .options(selectinload(Salon.owner))
        .order_by(Salon.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def update_salon(
    database: AsyncSession,
    salon: Salon,
    data: SalonUpdate,
) -> Salon:
    """Обновление переданных полей салона."""
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(salon, field, value)

    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return await _get_salon_with_owner(database, salon.id)


async def delete_salon(database: AsyncSession, salon: Salon) -> None:
    """Удаление салона."""
    try:
        await database.delete(salon)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
