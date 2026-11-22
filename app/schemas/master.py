"""Схемы мастера.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • ``MasterCreate`` теперь наследует ``UserCreate`` — телефон, email и
    пароль валидируются теми же правилами, что при регистрации (раньше
    можно было создать мастера с телефоном из 5 пробелов и паролем «123»);
  • ``extra="forbid"`` на create/update;
  • ``salon_id`` не может быть <= 0;
  • описание обрезается по краям, пустое превращается в None.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MasterPosition
from app.schemas.user import UserCreate, UserPublic


class MasterBase(BaseModel):
    salon_id: int = Field(..., ge=1)
    position: MasterPosition = MasterPosition.MASTER
    description: Optional[str] = Field(default=None, max_length=500)


class MasterCreate(MasterBase, UserCreate):
    """Создание мастера = создание User + Master в одной транзакции."""

    model_config = ConfigDict(extra="forbid")


class MasterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salon_id: Optional[int] = Field(default=None, ge=1)
    position: Optional[MasterPosition] = None
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None

    @field_validator("description")
    @classmethod
    def _strip_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None


class MasterRead(MasterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    user: UserPublic


__all__ = ["MasterBase", "MasterCreate", "MasterRead", "MasterUpdate"]
