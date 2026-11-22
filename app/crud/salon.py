from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.salon import Salon
from app.schemas.salon import SalonCreate, SalonUpdate

# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • _get_salon_with_owner больше не падает с NoResultFound (→ 500), если
#     салон удалили параллельно: возвращает None, вызывающий код бросает 404;
#   • в get_salons добавлен фильтр is_active — публичный список раньше отдавал
#     и закрытые салоны;
#   • count_salons — для заголовка X-Total-Count (удобно фронтенду).


async def _get_salon_with_owner(
    database: AsyncSession, salon_id: int
) -> Salon | None:
    """Внутренний хелпер: загружает салон вместе с владельцем."""
    result = await database.execute(
        select(Salon)
        .where(Salon.id == salon_id)
        .options(selectinload(Salon.owner))
    )
    return result.scalar_one_or_none()


async def create_salon(
    database: AsyncSession,
    data: SalonCreate,
    owner_id: int,
) -> Salon:
    """Создаёт салон от имени указанного владельца."""
    salon = Salon(
        name=data.name,
        address=data.address,
        phone=data.phone,
        type=data.type,
        owner_id=owner_id,
    )
    database.add(salon)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    created = await _get_salon_with_owner(database, salon.id)
    if created is None:  # салон успели удалить между commit и SELECT
        raise NotFoundError.by_id("Salon", salon.id)
    return created


async def get_salon(database: AsyncSession, salon_id: int) -> Salon | None:
    """Поиск салона по id. Владелец загружается сразу."""
    return await _get_salon_with_owner(database, salon_id)


async def get_salons(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    *,
    is_active: bool | None = None,
) -> Sequence[Salon]:
    """Список салонов с пагинацией. Владельцы загружаются сразу."""
    stmt = select(Salon).options(selectinload(Salon.owner))
    if is_active is not None:
        stmt = stmt.where(Salon.is_active.is_(is_active))
    result = await database.execute(
        stmt.order_by(Salon.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def get_salons_by_owner(
    database: AsyncSession,
    owner_id: int,
    skip: int = 0,
    limit: int = 10,
) -> Sequence[Salon]:
    result = await database.execute(
        select(Salon)
        .where(Salon.owner_id == owner_id)
        .options(selectinload(Salon.owner))
        .order_by(Salon.id)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def count_salons(
    database: AsyncSession,
    *,
    is_active: bool | None = None,
    owner_id: int | None = None,
) -> int:
    """Количество салонов под фильтром (для пагинации)."""
    stmt = select(func.count()).select_from(Salon)
    if is_active is not None:
        stmt = stmt.where(Salon.is_active.is_(is_active))
    if owner_id is not None:
        stmt = stmt.where(Salon.owner_id == owner_id)
    return int((await database.execute(stmt)).scalar_one())


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

    updated = await _get_salon_with_owner(database, salon.id)
    if updated is None:
        raise NotFoundError.by_id("Salon", salon.id)
    return updated


async def delete_salon(database: AsyncSession, salon: Salon) -> None:
    """Удаление салона."""
    try:
        await database.delete(salon)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
