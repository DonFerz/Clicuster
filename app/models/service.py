from sqlalchemy import String, ForeignKey, Integer, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.mixins import TimestampMixin
from .base import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .salon import Salon
    from .master import Master
    from .appointment import Appointment


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
        ForeignKey("salons.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False)  # длительность в минутах
    # цена в копейках/центах (целое число)
    price: Mapped[int] = mapped_column(Integer, nullable=False)

    # Связи
    salon: Mapped["Salon"] = relationship(back_populates="services")
    masters: Mapped[list["Master"]] = relationship(
        secondary="master_services",
        back_populates="services"
    )
    appointments: Mapped[list["Appointment"]
                         ] = relationship(back_populates="service")
