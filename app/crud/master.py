from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.schemas.master import MasterCreate, MasterUpdate

# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • _get_master_with_user возвращает None вместо NoResultFound (→ 500),
#     если мастера удалили параллельно;
#   • в списках добавлены фильтры активности: публичный список больше не
#     показывает уволенных мастеров и мастеров закрытых салонов;
#   • добавлен lock_master() — блокировка строки мастера (SELECT ... FOR
#     UPDATE) для защиты от гонки при одновременной записи на одно время;
#   • добавлен count_masters.

async def _get_master_with_user(
    database: AsyncSession, master_id: int
) -> Master | None:
    """Внутренний хелпер: загружает мастера вместе с его учётной записью."""
    result = await database.execute(
        select(Master)
        .where(Master.id == master_id)
        .options(selectinload(Master.user))
    )
    return result.scalar_one_or_none()


async def create_master(database: AsyncSession, data: MasterCreate) -> Master:
    """
    Создание мастера вместе с учётной записью (User).
    Обе записи создаются в одной транзакции.
    """
    try:
        # 1. Создаём пользователя с ролью MASTER
        user = User(
            full_name=data.full_name,
            email=str(data.email).lower(),
            phone=data.phone,
            hashed_password=hash_password(data.password),
            role=UserRole.MASTER,
        )
        database.add(user)
        await database.flush()  # INSERT без commit — получаем user.id

        # 2. Создаём профиль мастера, привязанный к user.
        #    Передаём объект user, а не user.id — тогда master.user
        #    сразу в памяти, без дополнительного SELECT.
        master = Master(
            user=user,
            salon_id=data.salon_id,
            position=data.position,
            description=data.description,
        )
        database.add(master)
        await database.flush()  # получаем master.id до commit
        master_id = master.id
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    # master_id зафиксирован до commit — не зависим от expire_on_commit.
    created = await _get_master_with_user(database, master_id)
    if created is None:
        raise NotFoundError.by_id("Master", master_id)
    return created


async def get_master(database: AsyncSession, master_id: int) -> Master | None:
    """Поиск мастера по id. Учётная запись загружается сразу."""
    return await _get_master_with_user(database, master_id)


async def get_master_by_user_id(
    database: AsyncSession, user_id: int
) -> Master | None:
    """Поиск профиля мастера по id пользователя.

    ДОБАВЛЕНО 22.11.2026: нужно скриптам-сидам и будущему «мой профиль
    мастера» — раньше приходилось перебирать всех мастеров.
    """
    result = await database.execute(
        select(Master)
        .where(Master.user_id == user_id)
        .options(selectinload(Master.user))
    )
    return result.scalar_one_or_none()


async def lock_master(database: AsyncSession, master_id: int) -> Master | None:
    """Блокирует строку мастера до конца транзакции.

    ДОБАВЛЕНО: сериализует параллельные попытки записаться к одному мастеру.
    Без этого две одновременные заявки могли пройти проверку пересечения
    и обе сохраниться (double booking).
    """
    result = await database.execute(
        select(Master).where(Master.id == master_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def get_master_with_services(
    database: AsyncSession, master_id: int
) -> Master | None:
    """Поиск мастера по id с eager-загрузкой user и services.

    Используется для управления услугами мастера (attach/detach)
    и при бронировании (нужно проверить, что мастер оказывает услугу).
    """
    result = await database.execute(
        select(Master)
        .where(Master.id == master_id)
        .options(
            selectinload(Master.user),
            selectinload(Master.services),
        )
    )

    return result.scalar_one_or_none()


async def get_masters(
    database: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    *,
    is_active: bool | None = True,
    active_salon_only: bool = True,
) -> Sequence[Master]:
    """Список мастеров с пагинацией. Учётные записи загружаются сразу."""
    stmt = select(Master).options(selectinload(Master.user))
    if is_active is not None:
        stmt = stmt.where(Master.is_active.is_(is_active))
    if active_salon_only:
        stmt = stmt.join(Salon, Salon.id == Master.salon_id).where(
            Salon.is_active.is_(True)
        )
    result = await database.execute(
        stmt.order_by(Master.id).offset(skip).limit(limit)
    )

    return result.scalars().all()


async def get_masters_by_salon(
    database: AsyncSession,
    salon_id: int,
    skip: int = 0,
    limit: int = 20,
    *,
    is_active: bool | None = True,
) -> Sequence[Master]:
    """Список мастеров конкретного салона. Учётные записи загружаются сразу."""
    stmt = select(Master).where(Master.salon_id == salon_id)
    if is_active is not None:
        stmt = stmt.where(Master.is_active.is_(is_active))
    result = await database.execute(
        stmt.options(selectinload(Master.user))
        .order_by(Master.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


async def count_masters(
    database: AsyncSession,
    *,
    salon_id: int | None = None,
    is_active: bool | None = None,
) -> int:
    """Количество мастеров под фильтром (для пагинации)."""
    stmt = select(func.count()).select_from(Master)
    if salon_id is not None:
        stmt = stmt.where(Master.salon_id == salon_id)
    if is_active is not None:
        stmt = stmt.where(Master.is_active.is_(is_active))
    return int((await database.execute(stmt)).scalar_one())


async def update_master(
    database: AsyncSession,
    master: Master,
    data: MasterUpdate,
) -> Master:
    """Обновление переданных полей мастера."""
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(master, field, value)

    # Фиксируем id до commit — не зависим от expire_on_commit.
    master_id = master.id

    try:
        await database.commit()
    except Exception:
        await database.rollback()
        raise

    updated = await _get_master_with_user(database, master_id)
    if updated is None:
        raise NotFoundError.by_id("Master", master_id)
    return updated


async def delete_master(database: AsyncSession, master: Master) -> None:
    """Удаление мастера. Учётная запись (User) остаётся."""
    try:
        await database.delete(master)
        await database.commit()
    except Exception:
        await database.rollback()
        raise


async def add_service_to_master(
    database: AsyncSession,
    master: Master,
    service: Service,
) -> None:
    """Идемпотентно привязывает услугу к мастеру.

    Требует eager-загруженного `master.services`
    (см. `get_master_with_services`).
    """
    if service not in master.services:
        master.services.append(service)
        try:
            await database.commit()
        except Exception:
            await database.rollback()
            raise


async def remove_service_from_master(
    database: AsyncSession,
    master: Master,
    service: Service,
) -> None:
    """Идемпотентно убирает услугу у мастера.

    Требует eager-загруженного `master.services`
    (см. `get_master_with_services`).
    """
    if service in master.services:
        master.services.remove(service)
        try:
            await database.commit()
        except Exception:
            await database.rollback()
            raise
