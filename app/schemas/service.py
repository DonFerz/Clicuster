"""Схемы услуги.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • КРИТИЧНО: ``ServiceRead``/``ServiceUpdate`` содержали поле ``is_active``,
    которого не было в ORM-модели ``Service`` — любой ответ со списком услуг
    падал с 500 (ResponseValidationError), а PATCH «is_active» молча
    игнорировался. Поле добавлено в модель и в миграцию, здесь оно
    документировано и валидируется.
  • ``extra="forbid"`` на create/update — защита от mass-assignment.
  • название обрезается по краям, длительность ограничена сутками.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_DURATION_MINUTES = 24 * 60


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    price: int = Field(..., ge=0, description="Цена в копейках/центах")
    duration_minutes: int = Field(..., gt=0, le=_MAX_DURATION_MINUTES)
    salon_id: int = Field(..., ge=1)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class ServiceCreate(ServiceBase):
    model_config = ConfigDict(extra="forbid")

    # ДОБАВЛЕНО: можно сразу создать услугу скрытой (например, архивной).
    is_active: bool = True


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    price: Optional[int] = Field(None, ge=0)
    duration_minutes: Optional[int] = Field(
        None, gt=0, le=_MAX_DURATION_MINUTES
    )
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class ServiceRead(ServiceBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = ["ServiceBase", "ServiceCreate", "ServiceRead", "ServiceUpdate"]
