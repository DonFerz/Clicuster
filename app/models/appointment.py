from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import RecordStatus
from app.models.mixins import TimestampMixin

from .base import Base

if TYPE_CHECKING:
    from .master import Master
    from .service import Service
    from .user import User


class Appointment(Base, TimestampMixin):
    """Запись клиента к мастеру.

    ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
      • добавлен ``CheckConstraint`` ``end_time > start_time`` — раньше в БД
        можно было сохранить запись с окончанием раньше начала;
      • добавлены составные индексы ``(master_id, start_time)`` и
        ``(client_id, start_time)``: проверка пересечения интервалов и
        выборка «расписание на день» раньше шли full scan'ом;
      • на уровне PostgreSQL добавлено EXCLUDE-ограничение против
        двойной записи к одному мастеру (см. миграцию
        2026_11_22_1200-9f1c2a7b4d10) — приложение тоже проверяет
        пересечения, но БД гарантирует это при гонках;
      • внешние ключи намеренно без ON DELETE CASCADE: удаление клиента/
        мастера/услуги с историей записей должно возвращать 409, а не
        молча стирать историю.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_appointments_time_order"),
        Index("ix_appointments_master_start", "master_id", "start_time"),
        Index("ix_appointments_client_start", "client_id", "start_time"),
    )

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
