from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate


async def create_service(database: AsyncSession, data: ServiceCreate) -> Service:
    """Создание новой услуги."""
    service = Service(
        name=data.name,
        description=data.description,
        price=data.price,
        duration_minutes=data.duration_minutes,
        salon_id=data.salon_id,
    )
    database.add(service)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return service


async def get_service(database: AsyncSession, service_id: int) -> Service | None:
    """Поиск услуги по id. Если услуга не найдена, возвращается None."""
    result = await database.execute(select(Service).where(Service.id == service_id))

    return result.scalar_one_or_none()


async def get_services(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Service]:
    """Список услуг с пагинацией."""
    result = await database.execute(
        select(Service).order_by(Service.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def get_services_by_salon(
    database: AsyncSession,
    salon_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Service]:
    """Список услуг конкретного салона."""
    result = await database.execute(
        select(Service)
        .where(Service.salon_id == salon_id)
        .order_by(Service.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def update_service(
    database: AsyncSession,
    service: Service,
    data: ServiceUpdate,
) -> Service:
    """Обновление переданных полей услуги. Остальные поля остаются без изменений."""
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(service, field, value)

    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    return service


async def delete_service(database: AsyncSession, service: Service) -> None:
    """Удаление услуги."""
    try:
        await database.delete(service)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
