from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.mixins import TimestampMixin

from .base import Base

if TYPE_CHECKING:
    from .appointment import Appointment
    from .master import Master
    from .salon import Salon


# ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
# ⚠ БЫЛО: у модели Service НЕ было колонки is_active, но она использовалась
#   в схемах ServiceRead/ServiceUpdate. Из-за этого ЛЮБОЙ ответ со списком
#   услуг падал с 500 (ResponseValidationError: missing is_active), а
#   PATCH {"is_active": false} молча ничего не сохранял.
# ✅ СТАЛО: колонка добавлена (boolean NOT NULL DEFAULT true) + миграция
#   2026_11_22_1200-9f1c2a7b4d10. Теперь услугу можно скрыть из публичного
#   прайса, не удаляя её и не ломая историю записей.
master_services = Table(
    "master_services",
    Base.metadata,
    Column("master_id", ForeignKey("masters.id"), primary_key=True),
    Column("service_id", ForeignKey("services.id"), primary_key=True),
)


class Service(Base, TimestampMixin):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    salon_id: Mapped[int] = mapped_column(
        ForeignKey("salons.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False)  # длительность в минутах
    # цена в копейках/центах (целое число)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    # ДОБАВЛЕНО: скрытие услуги без удаления (см. комментарий выше).
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False)

    # Связи
    salon: Mapped["Salon"] = relationship(back_populates="services")
    masters: Mapped[list["Master"]] = relationship(
        secondary="master_services",
        back_populates="services"
    )
    appointments: Mapped[list["Appointment"]
                         ] = relationship(back_populates="service")
