from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.mixins import TimestampMixin
from .base import Base
from .enums import UserRole
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .salon import Salon
    from .appointment import Appointment
    from .master import Master


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.CLIENT,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    salons: Mapped[list["Salon"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]
                         ] = relationship(back_populates="client")
    master_profile: Mapped["Master"] = relationship(
        back_populates="user", uselist=False)
