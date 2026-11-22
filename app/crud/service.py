from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate

# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • при создании сохраняется is_active (колонка добавлена в модель);
#   • в списках появился фильтр по активности: публичный прайс больше не
#     показывает скрытые/архивные услуги;
#   • update_service обновляет только поля схемы (is_active теперь реально
#     сохраняется, а не «прилипает» атрибутом в памяти);
#   • добавлен count_services.

async def create_service(database: AsyncSession, data: ServiceCreate) -> Service:
    """Создание новой услуги."""
    service = Service(
        name=data.name,
        description=data.description,
        price=data.price,
        duration_minutes=data.duration_minutes,
        salon_id=data.salon_id,
        is_active=data.is_active,
    )
    database.add(service)
    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    await database.refresh(service)
    return service


async def get_service(database: AsyncSession, service_id: int) -> Service | None:
    """Поиск услуги по id. Если услуга не найдена, возвращается None."""
    result = await database.execute(select(Service).where(Service.id == service_id))

    return result.scalar_one_or_none()


async def get_services(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    *,
    is_active: bool | None = True,
) -> Sequence[Service]:
    """Список услуг с пагинацией.

    is_active=True (по умолчанию) — только активные услуги.
    is_active=None — все (для владельца/админа).
    """
    stmt = select(Service)
    if is_active is not None:
        stmt = stmt.where(Service.is_active.is_(is_active))
    result = await database.execute(
        stmt.order_by(Service.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def get_services_by_salon(
    database: AsyncSession,
    salon_id: int,
    skip: int = 0,
    limit: int = 20,
    *,
    is_active: bool | None = True,
) -> Sequence[Service]:
    """Список услуг конкретного салона."""
    stmt = select(Service).where(Service.salon_id == salon_id)
    if is_active is not None:
        stmt = stmt.where(Service.is_active.is_(is_active))
    result = await database.execute(
        stmt.order_by(Service.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def count_services(
    database: AsyncSession,
    *,
    salon_id: int | None = None,
    is_active: bool | None = None,
) -> int:
    """Количество услуг под фильтром (для пагинации)."""
    stmt = select(func.count()).select_from(Service)
    if salon_id is not None:
        stmt = stmt.where(Service.salon_id == salon_id)
    if is_active is not None:
        stmt = stmt.where(Service.is_active.is_(is_active))
    return int((await database.execute(stmt)).scalar_one())


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

    await database.refresh(service)
    return service


async def delete_service(database: AsyncSession, service: Service) -> None:
    """Удаление услуги."""
    try:
        await database.delete(service)
        await database.commit()
    except Exception:
        await database.rollback()
        raise
