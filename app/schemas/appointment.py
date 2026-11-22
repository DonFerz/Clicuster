"""Схемы записи клиента (appointment).

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • УБРАН ``client_id`` из обязательных полей создания: раньше клиент мог
    создать запись от имени другого пользователя (mass-assignment).
    Теперь ``client_id`` опционален и принимается только от сотрудников
    салона (проверка в app/core/appointments.py).
  • ``end_time`` больше не принимается от клиента: он вычисляется на сервере
    из ``start_time`` + ``duration_minutes`` услуги. Раньше можно было
    записаться «на 10 минут», а занять «12 часов».
  • ``start_time`` — только timezone-aware (``AwareDatetime``). Наивное время
    раньше тихо сохранялось как локальное и ломало расписание.
  • Добавлен ``extra="forbid"`` и валидация ``end_time > start_time`` для
    ответа/обновления.
  • ``AppointmentRead`` отдаёт телефон клиента (``AppointmentClient``),
    потому что мастеру нужно позвонить; доступ к записи проверяется по ролям.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import RecordStatus
from app.schemas.master import MasterRead
from app.schemas.service import ServiceRead
from app.schemas.user import AppointmentClient


class AppointmentBase(BaseModel):
    """Общие поля записи (используется в ответах и документации)."""

    start_time: AwareDatetime
    end_time: AwareDatetime
    comment: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_time_order(self) -> "AppointmentBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        return self


class AppointmentCreate(BaseModel):
    """Создание записи.

    ``end_time`` вычисляется сервером: ``start_time + duration_minutes``.
    """

    model_config = ConfigDict(extra="forbid")

    master_id: int = Field(..., ge=1)
    service_id: int = Field(..., ge=1)
    start_time: AwareDatetime
    # Только для сотрудников: записать клиента «на себя».
    client_id: Optional[int] = Field(default=None, ge=1)
    comment: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _strip_comment(self) -> "AppointmentCreate":
        if self.comment is not None:
            self.comment = self.comment.strip() or None
        return self


class AppointmentUpdate(BaseModel):
    """Изменение записи: перенос, смена статуса, комментарий.

    ``master_id``/``service_id`` намеренно недоступны: смена услуги меняет
    длительность и цену, для этого нужен отдельный сценарий (см. roadmap).
    """

    model_config = ConfigDict(extra="forbid")

    start_time: Optional[AwareDatetime] = None
    status: Optional[RecordStatus] = None
    comment: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _strip_comment(self) -> "AppointmentUpdate":
        if self.comment is not None:
            self.comment = self.comment.strip() or None
        return self


class AppointmentRead(AppointmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RecordStatus
    created_at: datetime
    updated_at: datetime

    master: MasterRead
    client: AppointmentClient
    service: ServiceRead


__all__ = [
    "AppointmentBase",
    "AppointmentCreate",
    "AppointmentRead",
    "AppointmentUpdate",
]
