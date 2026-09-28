from sqlalchemy import String, ForeignKey, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.models.enums import RecordStatus
from app.models.mixins import TimestampMixin
from .base import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User
    from .master import Master
    from .service import Service


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False)
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, values_callable=lambda x: [e.value for e in x]),
        default=RecordStatus.PENDING,
        nullable=False,
    )
    comment: Mapped[str] = mapped_column(String(500), nullable=True)

    client: Mapped["User"] = relationship(back_populates="appointments")
    master: Mapped["Master"] = relationship(back_populates="appointments")
    service: Mapped["Service"] = relationship(back_populates="appointments")
