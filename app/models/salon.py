from sqlalchemy import String, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.mixins import TimestampMixin
from .base import Base
from .enums import SalonType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .user import User
    from .master import Master
    from .service import Service


class Salon(Base, TimestampMixin):
    __tablename__ = "salons"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    type: Mapped[SalonType] = mapped_column(
        Enum(SalonType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="salons")
    masters: Mapped[list["Master"]] = relationship(
        back_populates="salon", cascade="all, delete-orphan")
    services: Mapped[list["Service"]] = relationship(
        back_populates="salon", cascade="all, delete-orphan")
